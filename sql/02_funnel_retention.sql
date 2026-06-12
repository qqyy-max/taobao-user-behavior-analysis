-- ============================================================
-- 02_funnel_retention.sql — 行为渗透率 & 短周期回访层
-- ============================================================
-- 职责：行为覆盖率摘要、用户转化渗透率、Cohort 回访矩阵
-- 输出表：
--   funnel_summary            — 行为渗透率摘要（★ 非严格漏斗）
--   user_conversion_summary   — 用户行为渗透率一览
--   cohort_retention_detail   — 短周期回访明细热力图
--   cohort_retention_summary  — 回访汇总曲线
-- 依赖：00_init.sql（提供 clean 视图 + user_base_metrics 中间表）
--
-- ★ 重要说明：
--   1. pv/fav/cart/buy 不是严格线性漏斗。
--      funnel_summary 中的 conversion_rate_pct 实为各行为 UV 相对
--      PV UV 的渗透率，非阶段间转化率。
--      加购 UV (215,167) 远超收藏 UV (113,717) — 用户跳过收藏直接加购。
--      严禁将 conversion_rate_pct 解释为"漏斗转化率"。
--   2. cohort_retention_detail 仅 9 天窗口，D7 回访率 98.5% 为周末周期效应。
--      应表述为"短周期回访率"而非"留存率"。
-- ============================================================


-- ============================================================
-- 1. funnel_summary — 行为渗透率摘要
-- ============================================================
-- ★ 注意：此表为各行为类型的用户覆盖率，不是严格漏斗！
-- 以 PV 用户数为基准 100%，计算各阶段 UV 渗透率（Penetration Rate）
DROP TABLE IF EXISTS funnel_summary;
CREATE TABLE funnel_summary AS
WITH stage_uv AS (
    SELECT
        'pv'   AS stage, '浏览' AS stage_cn, COUNT(DISTINCT user_id) AS uv, COUNT(*) AS actions FROM clean WHERE behavior_type = 'pv'
    UNION ALL
    SELECT
        'fav',  '收藏', COUNT(DISTINCT user_id), COUNT(*) FROM clean WHERE behavior_type = 'fav'
    UNION ALL
    SELECT
        'cart', '加购', COUNT(DISTINCT user_id), COUNT(*) FROM clean WHERE behavior_type = 'cart'
    UNION ALL
    SELECT
        'buy',  '购买', COUNT(DISTINCT user_id), COUNT(*) FROM clean WHERE behavior_type = 'buy'
),
baseline AS (
    SELECT uv AS pv_uv FROM stage_uv WHERE stage = 'pv'
)
SELECT
    s.stage,
    s.stage_cn,
    s.uv,
    s.actions,
    ROUND(s.uv * 100.0 / b.pv_uv, 2) AS conversion_rate_pct
FROM stage_uv s, baseline b
ORDER BY CASE s.stage WHEN 'pv' THEN 1 WHEN 'fav' THEN 2 WHEN 'cart' THEN 3 WHEN 'buy' THEN 4 END;


-- ============================================================
-- 2. user_conversion_summary — 用户行为渗透率
--    ★ 使用 user_base_metrics 中间表，避免重新聚合 2800 万行
-- ============================================================
DROP TABLE IF EXISTS user_conversion_summary;
CREATE TABLE user_conversion_summary AS
SELECT
    COUNT(*)                                                      AS total_users,
    COUNT(*)                                                      AS pv_users,   -- 所有用户都有 PV
    SUM(has_fav)                                                  AS fav_users,
    SUM(has_cart)                                                 AS cart_users,
    SUM(is_buyer)                                                 AS buy_users,
    ROUND(100.0 * SUM(has_fav)  / NULLIF(COUNT(*), 0), 2)        AS fav_rate_pct,
    ROUND(100.0 * SUM(has_cart) / NULLIF(COUNT(*), 0), 2)        AS cart_rate_pct,
    ROUND(100.0 * SUM(is_buyer) / NULLIF(COUNT(*), 0), 2)        AS buy_rate_pct,
    -- 购买用户的兴趣行为渗透率
    ROUND(100.0 * SUM(CASE WHEN is_buyer=1 AND has_fav=1  THEN 1 ELSE 0 END)
                / NULLIF(SUM(is_buyer), 0), 2)                   AS buyer_fav_rate,
    ROUND(100.0 * SUM(CASE WHEN is_buyer=1 AND has_cart=1 THEN 1 ELSE 0 END)
                / NULLIF(SUM(is_buyer), 0), 2)                   AS buyer_cart_rate
FROM user_base_metrics;


-- ============================================================
-- 3. cohort_retention_detail — 短周期回访明细（热力图）
--    ★ 注意：仅 9 天窗口，D7 受周末周期效应影响
-- ============================================================
-- 以用户首次活跃日（cohort_date）为基准，追踪后续每天的回访情况
DROP TABLE IF EXISTS cohort_retention_detail;
CREATE TABLE cohort_retention_detail AS
WITH
user_cohort AS (
    SELECT
        user_id,
        MIN(dt) AS cohort_date
    FROM clean
    GROUP BY user_id
),
user_daily AS (
    SELECT DISTINCT
        user_id,
        dt
    FROM clean
),
cohort_daily AS (
    SELECT
        uc.cohort_date,
        uc.user_id,
        ud.dt,
        DATEDIFF('day', uc.cohort_date, ud.dt) AS retention_day
    FROM user_cohort uc
    JOIN user_daily ud ON uc.user_id = ud.user_id
    WHERE ud.dt >= uc.cohort_date
),
cohort_size AS (
    SELECT
        cohort_date,
        COUNT(DISTINCT user_id) AS total_users
    FROM user_cohort
    GROUP BY cohort_date
)
SELECT
    cd.cohort_date,
    cd.retention_day,
    COUNT(DISTINCT cd.user_id)          AS retained_users,
    cs.total_users,
    ROUND(100.0 * COUNT(DISTINCT cd.user_id) / cs.total_users, 2) AS retention_rate_pct
FROM cohort_daily cd
JOIN cohort_size cs ON cd.cohort_date = cs.cohort_date
GROUP BY cd.cohort_date, cd.retention_day, cs.total_users
ORDER BY cd.cohort_date, cd.retention_day;


-- ============================================================
-- 4. cohort_retention_summary — 回访汇总（回访曲线）
-- ============================================================
-- 所有 Cohort 按 retention_day 汇总的平均回访率
DROP TABLE IF EXISTS cohort_retention_summary;
CREATE TABLE cohort_retention_summary AS
SELECT
    retention_day,
    SUM(retained_users)                         AS total_retained_users,
    SUM(total_users)                            AS total_cohort_users,
    ROUND(100.0 * SUM(retained_users) / SUM(total_users), 2) AS avg_retention_rate_pct
FROM cohort_retention_detail
GROUP BY retention_day
ORDER BY retention_day;


-- ============================================================
-- 验证输出
-- ============================================================
SELECT '=== 02_funnel_retention 执行完成 ===' AS status;
SELECT 'funnel_summary'           AS tbl, COUNT(*) AS rows FROM funnel_summary
UNION ALL SELECT 'user_conversion_summary', COUNT(*) FROM user_conversion_summary
UNION ALL SELECT 'cohort_retention_detail', COUNT(*) FROM cohort_retention_detail
UNION ALL SELECT 'cohort_retention_summary', COUNT(*) FROM cohort_retention_summary;
