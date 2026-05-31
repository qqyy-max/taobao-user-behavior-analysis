-- ============================================================
-- 05_user_analysis.sql — 用户分析层
-- ============================================================
-- 职责：用户画像、行为频次分层、分群汇总
-- 输出表：
--   user_profile            — 用户行为画像（事实表）
--   user_frequency_segment  — 用户频次分群
--   user_segment_summary    — Power BI 分群汇总
-- 依赖：00_init.sql（提供 clean 视图 + user_base_metrics 中间表）
-- ============================================================


-- ============================================================
-- 1. user_profile — 用户行为画像
--    ★ 基于 user_base_metrics 中间表，补充人均指标和时域特征
-- ============================================================
DROP TABLE IF EXISTS user_profile;
CREATE TABLE user_profile AS
WITH
-- 用户最常交互的类目
user_fav_category AS (
    SELECT DISTINCT
        user_id,
        FIRST_VALUE(category_id) OVER (
            PARTITION BY user_id ORDER BY cnt DESC
        ) AS favorite_category
    FROM (
        SELECT user_id, category_id, COUNT(*) AS cnt
        FROM clean
        GROUP BY user_id, category_id
    )
),
-- 用户类目和商品多样性
user_diversity AS (
    SELECT
        user_id,
        COUNT(DISTINCT category_id) AS category_diversity,
        COUNT(DISTINCT item_id)     AS item_diversity
    FROM clean
    GROUP BY user_id
)
SELECT
    m.user_id,
    m.total_actions,
    m.pv_cnt,
    m.fav_cnt,
    m.cart_cnt,
    m.buy_cnt,
    m.active_days,
    m.buy_days,
    m.cart_days,
    m.fav_days,
    m.first_active_date,
    m.last_active_date,
    m.lifecycle_days,
    m.is_buyer,

    -- 人均指标
    ROUND(1.0 * m.total_actions / NULLIF(m.active_days, 0), 1)  AS avg_actions_per_day,
    ROUND(1.0 * m.buy_cnt       / NULLIF(m.active_days, 0), 3)  AS avg_buy_per_day,

    -- 行为转化率（用户粒度）
    ROUND(100.0 * m.buy_cnt  / NULLIF(m.total_actions, 0), 2)   AS buy_rate_pct,
    ROUND(100.0 * m.cart_cnt / NULLIF(m.total_actions, 0), 2)   AS cart_rate_pct,
    ROUND(100.0 * m.fav_cnt  / NULLIF(m.total_actions, 0), 2)   AS fav_rate_pct,

    -- 类目 & 多样性
    COALESCE(f.favorite_category, 0)   AS favorite_category,
    COALESCE(d.category_diversity, 0)  AS category_diversity,
    COALESCE(d.item_diversity, 0)      AS item_diversity,

    -- 复购标记
    CASE WHEN m.buy_cnt > 1 THEN 1 ELSE 0 END                   AS is_repeat_buyer

FROM user_base_metrics m
LEFT JOIN user_fav_category f ON m.user_id = f.user_id
LEFT JOIN user_diversity d ON m.user_id = d.user_id;


-- ============================================================
-- 2. user_frequency_segment — 用户行为频次分层
--    ★ 直接从 user_profile 读取，不重复聚合
-- ============================================================
DROP TABLE IF EXISTS user_frequency_segment;
CREATE TABLE user_frequency_segment AS
SELECT
    user_id,
    total_actions,
    buy_cnt,
    active_days,
    CASE
        WHEN total_actions = 1                    THEN '1次'
        WHEN total_actions BETWEEN   2 AND   5    THEN '2-5次'
        WHEN total_actions BETWEEN   6 AND  20    THEN '6-20次'
        WHEN total_actions BETWEEN  21 AND 100    THEN '21-100次'
        WHEN total_actions BETWEEN 101 AND 500    THEN '101-500次'
        WHEN total_actions > 500                  THEN '500+次'
    END AS freq_group,
    CASE
        WHEN is_buyer = 1 THEN '购买用户'
        ELSE '非购买用户'
    END AS buyer_group
FROM user_profile;


-- ============================================================
-- 3. user_segment_summary — 分群汇总（Power BI 用）
-- ============================================================
DROP TABLE IF EXISTS user_segment_summary;
CREATE TABLE user_segment_summary AS
SELECT
    ufs.freq_group,
    COUNT(*)                                                      AS user_cnt,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 2)             AS user_pct,
    SUM(up.buy_cnt)                                               AS total_buy_cnt,
    ROUND(AVG(up.buy_cnt), 2)                                    AS avg_buy_per_user,
    ROUND(AVG(up.total_actions), 1)                              AS avg_actions_per_user,
    ROUND(AVG(up.active_days), 1)                                AS avg_active_days,
    ROUND(100.0 * SUM(CASE WHEN up.is_buyer=1 THEN 1 ELSE 0 END)
                / NULLIF(COUNT(*), 0), 2)                        AS buyer_rate_pct,
    ROUND(AVG(up.buy_rate_pct), 2)                               AS avg_buy_rate_pct,
    ROUND(AVG(up.cart_rate_pct), 2)                              AS avg_cart_rate_pct,
    ROUND(AVG(up.fav_rate_pct), 2)                               AS avg_fav_rate_pct,
    ROUND(AVG(up.lifecycle_days), 1)                             AS avg_lifecycle_days,
    ROUND(100.0 * SUM(CASE WHEN up.is_repeat_buyer=1 THEN 1 ELSE 0 END)
                / NULLIF(SUM(up.is_buyer), 0), 2)               AS repeat_buyer_rate_pct
FROM user_profile up
JOIN user_frequency_segment ufs ON up.user_id = ufs.user_id
GROUP BY ufs.freq_group
ORDER BY MIN(ufs.total_actions);


-- ============================================================
-- 验证输出
-- ============================================================
SELECT '=== 05_user_analysis 执行完成 ===' AS status;
SELECT 'user_profile'            AS tbl, COUNT(*) AS rows FROM user_profile
UNION ALL SELECT 'user_frequency_segment', COUNT(*) FROM user_frequency_segment
UNION ALL SELECT 'user_segment_summary',   COUNT(*) FROM user_segment_summary;
