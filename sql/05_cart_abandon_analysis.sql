-- ============================================================
-- 05_cart_abandon_analysis.sql — 加购未购买用户专题
-- ============================================================
-- 职责：识别加购但 9 天窗口内未购买的用户，分析其行为特征、
--       加购商品分布，并与加购后购买用户做对比。
-- 输出表：
--   cart_abandon_users       — 加购未购买用户画像
--   cart_abandon_item_detail — 加购未购买用户的商品/类目明细
--   cart_buyer_comparison    — 加购未购 vs 加购后购买用户对比
--   cart_abandon_summary     — 专题汇总表
-- 依赖：00_init.sql（提供 user_base_metrics + clean 视图）
--
-- ★ 核心前提：
--   "加购未购买"定义为：在 9 天观察窗口内 has_cart=1 且 is_buyer=0。
--   这仅表示窗口内的状态，不代表用户永久不会购买：
--   ① 用户可能在窗口外延迟购买
--   ② 用户可能在其他平台/渠道完成了购买
--   ③ 用户加购可能是收藏替代行为（用加购代替心愿单）
--   不应将其表述为"购物车放弃率"或"流失用户"。
-- ============================================================


-- ============================================================
-- 1. cart_abandon_users — 加购未购买用户画像
-- ============================================================
-- 筛选条件：has_cart=1 AND is_buyer=0（9 天窗口内）
-- 包含字段：加购强度、浏览深度、活跃度、加购商品/类目数、时间特征
DROP TABLE IF EXISTS cart_abandon_users;
CREATE TABLE cart_abandon_users AS
WITH
-- 加购明细聚合
cart_detail AS (
    SELECT
        user_id,
        COUNT(*)                            AS cart_cnt,
        COUNT(DISTINCT item_id)             AS cart_item_cnt,
        COUNT(DISTINCT category_id)         AS cart_category_cnt,
        MAX(dt)                             AS last_cart_date
    FROM clean
    WHERE behavior_type = 'cart'
    GROUP BY user_id
),
-- 窗口最后一天（用于计算距最后加购天数）
window_end AS (
    SELECT MAX(dt) AS max_dt FROM clean
)
SELECT
    m.user_id,
    -- 从 user_base_metrics 获取核心行为指标
    m.pv_cnt,
    m.fav_cnt,
    m.cart_cnt,
    m.buy_cnt,
    m.total_actions,
    m.active_days,
    m.last_active_date,
    -- 加购商品/类目特征
    cd.cart_item_cnt,
    cd.cart_category_cnt,
    cd.last_cart_date,
    DATEDIFF('day', cd.last_cart_date, we.max_dt) AS days_since_last_cart,
    -- 派生行为特征
    ROUND(1.0 * m.cart_cnt / NULLIF(m.pv_cnt, 0) * 100, 2) AS cart_to_pv_rate,
    ROUND(1.0 * m.pv_cnt / NULLIF(m.active_days, 0), 1)   AS avg_daily_pv,
    ROUND(1.0 * m.fav_cnt / NULLIF(m.pv_cnt, 0) * 100, 2) AS fav_rate_pct
FROM user_base_metrics m
JOIN cart_detail cd ON m.user_id = cd.user_id
CROSS JOIN window_end we
WHERE m.has_cart = 1
  AND m.is_buyer = 0;


-- ============================================================
-- 2. cart_abandon_item_detail — 加购未购买用户的商品/类目明细
-- ============================================================
-- 粒度为 user_id × item_id，记录每个加购事件的商品、类目和时间
-- 用于：识别高意向品类的加购未购商品分布，支持精准商品推荐
DROP TABLE IF EXISTS cart_abandon_item_detail;
CREATE TABLE cart_abandon_item_detail AS
WITH
-- 加购未购用户的加购事件
cart_events AS (
    SELECT
        user_id,
        item_id,
        category_id,
        ts   AS cart_ts,
        dt   AS cart_date,
        hour AS cart_hour
    FROM clean
    WHERE behavior_type = 'cart'
      AND user_id IN (SELECT user_id FROM cart_abandon_users)
),
-- 标记加购前是否有浏览该商品
pv_before AS (
    SELECT
        c.user_id,
        c.item_id,
        CASE WHEN COUNT(p.ts) > 0 THEN 1 ELSE 0 END AS has_pv_before,
        CASE WHEN COUNT(f.ts) > 0 THEN 1 ELSE 0 END AS has_fav_before
    FROM cart_events c
    LEFT JOIN clean p
        ON c.user_id = p.user_id
       AND c.item_id = p.item_id
       AND p.behavior_type = 'pv'
       AND p.ts < c.cart_ts
    LEFT JOIN clean f
        ON c.user_id = f.user_id
       AND c.item_id = f.item_id
       AND f.behavior_type = 'fav'
       AND f.ts < c.cart_ts
    GROUP BY c.user_id, c.item_id
)
SELECT
    c.user_id,
    c.item_id,
    c.category_id,
    c.cart_ts,
    c.cart_date,
    c.cart_hour,
    COALESCE(pb.has_pv_before, 0)  AS has_pv_before,
    COALESCE(pb.has_fav_before, 0) AS has_fav_before
FROM cart_events c
LEFT JOIN pv_before pb
    ON c.user_id = pb.user_id
   AND c.item_id = pb.item_id
ORDER BY c.user_id, c.cart_ts;


-- ============================================================
-- 3. cart_buyer_comparison — 加购未购买 vs 加购后购买用户对比
-- ============================================================
-- 将加购用户分为两组，对比行为特征差异：
--   Group A: 加购未购买（cart_abandon_users）
--   Group B: 加购后购买（has_cart=1 AND is_buyer=1）
-- 用于：识别加购转化与未转化的关键行为差异
DROP TABLE IF EXISTS cart_buyer_comparison;
CREATE TABLE cart_buyer_comparison AS
WITH
comparison_base AS (
    SELECT
        m.user_id,
        CASE WHEN m.is_buyer = 0 THEN '加购未购买' ELSE '加购后购买' END AS user_group,
        m.pv_cnt,
        m.fav_cnt,
        m.cart_cnt,
        m.buy_cnt,
        m.total_actions,
        m.active_days,
        m.lifecycle_days,
        ROUND(1.0 * m.cart_cnt / NULLIF(m.pv_cnt, 0) * 100, 2) AS cart_to_pv_rate,
        ROUND(1.0 * m.pv_cnt / NULLIF(m.active_days, 0), 1)   AS avg_daily_pv
    FROM user_base_metrics m
    WHERE m.has_cart = 1
),
-- 加购类目数（从 clean 聚合）
cart_diversity AS (
    SELECT
        user_id,
        COUNT(DISTINCT item_id)     AS cart_item_cnt,
        COUNT(DISTINCT category_id) AS cart_category_cnt
    FROM clean
    WHERE behavior_type = 'cart'
    GROUP BY user_id
)
SELECT
    cb.user_group,
    COUNT(*)                                                AS user_cnt,
    ROUND(AVG(cb.pv_cnt), 1)                                AS avg_pv,
    ROUND(AVG(cb.fav_cnt), 1)                               AS avg_fav,
    ROUND(AVG(cb.cart_cnt), 1)                              AS avg_cart,
    ROUND(AVG(cb.buy_cnt), 1)                               AS avg_buy,
    ROUND(AVG(cb.total_actions), 1)                         AS avg_actions,
    ROUND(AVG(cb.active_days), 1)                           AS avg_active_days,
    ROUND(AVG(cb.lifecycle_days), 1)                        AS avg_lifecycle_days,
    ROUND(AVG(cb.cart_to_pv_rate), 2)                       AS avg_cart_to_pv_rate,
    ROUND(AVG(cb.avg_daily_pv), 1)                          AS avg_daily_pv,
    ROUND(AVG(cd.cart_item_cnt), 1)                         AS avg_cart_item_cnt,
    ROUND(AVG(cd.cart_category_cnt), 1)                     AS avg_cart_category_cnt
FROM comparison_base cb
JOIN cart_diversity cd ON cb.user_id = cd.user_id
GROUP BY cb.user_group
ORDER BY cb.user_group;


-- ============================================================
-- 4. cart_abandon_summary — 专题汇总表
-- ============================================================
-- 一行汇总：加购未购用户的全局统计
DROP TABLE IF EXISTS cart_abandon_summary;
CREATE TABLE cart_abandon_summary AS
SELECT
    COUNT(*)                                                            AS total_cart_abandon_users,
    ROUND(AVG(cart_cnt), 1)                                             AS avg_cart_cnt_per_user,
    ROUND(AVG(cart_item_cnt), 1)                                        AS avg_cart_items,
    ROUND(AVG(cart_category_cnt), 1)                                    AS avg_cart_categories,
    ROUND(AVG(pv_cnt), 1)                                               AS avg_pv,
    ROUND(AVG(active_days), 1)                                          AS avg_active_days,
    ROUND(AVG(cart_to_pv_rate), 2)                                      AS avg_cart_to_pv_rate,
    ROUND(AVG(avg_daily_pv), 1)                                         AS avg_daily_pv,
    ROUND(AVG(fav_rate_pct), 2)                                         AS avg_fav_rate_pct,
    -- 最近加购分布
    SUM(CASE WHEN days_since_last_cart = 0 THEN 1 ELSE 0 END)           AS last_cart_today,
    SUM(CASE WHEN days_since_last_cart <= 1 THEN 1 ELSE 0 END)          AS last_cart_within_1d,
    SUM(CASE WHEN days_since_last_cart <= 3 THEN 1 ELSE 0 END)          AS last_cart_within_3d,
    ROUND(100.0 * SUM(CASE WHEN days_since_last_cart <= 1 THEN 1 ELSE 0 END)
                / NULLIF(COUNT(*), 0), 2)                               AS pct_last_cart_1d,
    ROUND(100.0 * SUM(CASE WHEN days_since_last_cart <= 3 THEN 1 ELSE 0 END)
                / NULLIF(COUNT(*), 0), 2)                               AS pct_last_cart_3d
FROM cart_abandon_users;


-- ============================================================
-- 验证输出
-- ============================================================
SELECT '=== 05_cart_abandon_analysis 执行完成 ===' AS status;

SELECT 'cart_abandon_users'       AS tbl, COUNT(*) AS rows FROM cart_abandon_users
UNION ALL
SELECT 'cart_abandon_item_detail', COUNT(*) FROM cart_abandon_item_detail
UNION ALL
SELECT 'cart_buyer_comparison',    COUNT(*) FROM cart_buyer_comparison
UNION ALL
SELECT 'cart_abandon_summary',     COUNT(*) FROM cart_abandon_summary;

-- 显示加购未购用户汇总
SELECT '--- 加购未购买用户汇总 ---' AS info;
SELECT * FROM cart_abandon_summary;

-- 显示加购未购 vs 加购后购买用户对比
SELECT '--- 加购用户分组对比 ---' AS info;
SELECT * FROM cart_buyer_comparison;

-- 加购未购用户活跃天数分布
SELECT '--- 加购未购用户活跃天数分布 ---' AS info;
SELECT
    active_days,
    COUNT(*) AS user_cnt,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 1) AS pct
FROM cart_abandon_users
GROUP BY active_days
ORDER BY active_days;

-- 最近加购时间分布（距窗口结束天数）
SELECT '--- 距最后加购天数分布 ---' AS info;
SELECT
    days_since_last_cart,
    COUNT(*) AS user_cnt,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 1) AS pct
FROM cart_abandon_users
GROUP BY days_since_last_cart
ORDER BY days_since_last_cart;
