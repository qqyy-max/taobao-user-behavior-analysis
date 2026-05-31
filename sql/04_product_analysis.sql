-- ============================================================
-- 04_product_analysis.sql — 商品 & 类目转化分析层
-- ============================================================
-- 职责：类目/商品维度的行为分布与转化率，
--       识别高曝光低转化商品
-- 输出表：
--   category_conversion               — Power BI 类目分析
--   item_conversion                   — 商品转化明细
--   high_exposure_low_conversion_items — 高曝光低转化商品清单
-- 依赖：00_init.sql（提供 clean 视图 + category_base_stats 中间表）
-- ============================================================


-- ============================================================
-- 1. category_conversion — 类目转化分析
--    ★ 使用 category_base_stats 中间表，补充计算转化率和排名
-- ============================================================
DROP TABLE IF EXISTS category_conversion;
CREATE TABLE category_conversion AS
SELECT
    category_id,
    total_actions,
    pv_cnt,
    fav_cnt,
    cart_cnt,
    buy_cnt,
    uv,
    item_cnt,
    buy_uv,
    ROUND(100.0 * fav_cnt  / NULLIF(pv_cnt, 0), 2)   AS fav_rate_pct,
    ROUND(100.0 * cart_cnt / NULLIF(pv_cnt, 0), 2)   AS cart_rate_pct,
    ROUND(100.0 * buy_cnt  / NULLIF(pv_cnt, 0), 2)   AS buy_rate_pct,
    ROUND(100.0 * buy_uv   / NULLIF(uv, 0), 2)       AS user_buy_rate_pct,
    ROW_NUMBER() OVER (ORDER BY pv_cnt DESC)          AS exposure_rank,
    ROW_NUMBER() OVER (ORDER BY
        ROUND(100.0 * buy_cnt / NULLIF(pv_cnt, 0), 2) DESC) AS conversion_rank
FROM category_base_stats
ORDER BY pv_cnt DESC;


-- ============================================================
-- 2. item_conversion — 商品转化分析
-- ============================================================
DROP TABLE IF EXISTS item_conversion;
CREATE TABLE item_conversion AS
WITH item_stats AS (
    SELECT
        item_id,
        category_id,
        COUNT(*)                                                     AS total_actions,
        SUM(CASE WHEN behavior_type = 'pv'   THEN 1 ELSE 0 END)     AS pv_cnt,
        SUM(CASE WHEN behavior_type = 'fav'  THEN 1 ELSE 0 END)     AS fav_cnt,
        SUM(CASE WHEN behavior_type = 'cart' THEN 1 ELSE 0 END)     AS cart_cnt,
        SUM(CASE WHEN behavior_type = 'buy'  THEN 1 ELSE 0 END)     AS buy_cnt,
        COUNT(DISTINCT user_id)                                      AS uv,
        COUNT(DISTINCT CASE WHEN behavior_type = 'buy' THEN user_id END) AS buy_uv
    FROM clean
    GROUP BY item_id, category_id
)
SELECT
    item_id,
    category_id,
    total_actions,
    pv_cnt,
    fav_cnt,
    cart_cnt,
    buy_cnt,
    uv,
    buy_uv,
    ROUND(100.0 * fav_cnt  / NULLIF(pv_cnt, 0), 2)   AS fav_rate_pct,
    ROUND(100.0 * cart_cnt / NULLIF(pv_cnt, 0), 2)   AS cart_rate_pct,
    ROUND(100.0 * buy_cnt  / NULLIF(pv_cnt, 0), 2)   AS buy_rate_pct,
    ROUND(100.0 * buy_uv   / NULLIF(uv, 0), 2)       AS user_buy_rate_pct,
    ROW_NUMBER() OVER (ORDER BY pv_cnt DESC)          AS exposure_rank,
    ROW_NUMBER() OVER (ORDER BY
        ROUND(100.0 * buy_cnt / NULLIF(pv_cnt, 0), 2) DESC) AS conversion_rank
FROM item_stats
ORDER BY pv_cnt DESC;


-- ============================================================
-- 3. high_exposure_low_conversion_items — 高曝光低转化商品
-- ============================================================
-- 定义：
--   高曝光 = PV >= 所有商品 PV 的 P75 分位
--   低转化 = buy_rate <= 所有商品 buy_rate 的中位数
DROP TABLE IF EXISTS high_exposure_low_conversion_items;
CREATE TABLE high_exposure_low_conversion_items AS
WITH thresholds AS (
    SELECT
        APPROX_QUANTILE(pv_cnt, 0.75)  AS pv_p75,
        MEDIAN(buy_rate_pct)           AS buy_rate_median
    FROM item_conversion
)
SELECT
    i.item_id,
    i.category_id,
    i.pv_cnt,
    i.fav_cnt,
    i.cart_cnt,
    i.buy_cnt,
    i.buy_rate_pct,
    i.cart_rate_pct,
    i.exposure_rank,
    i.conversion_rank,
    (i.exposure_rank - i.conversion_rank) AS exposure_conversion_gap
FROM item_conversion i, thresholds t
WHERE i.pv_cnt >= t.pv_p75
  AND i.buy_rate_pct <= t.buy_rate_median
ORDER BY i.pv_cnt DESC, i.buy_rate_pct ASC;


-- ============================================================
-- 验证输出
-- ============================================================
SELECT '=== 04_product_analysis 执行完成 ===' AS status;
SELECT 'category_conversion'               AS tbl, COUNT(*) AS rows FROM category_conversion
UNION ALL SELECT 'item_conversion',              COUNT(*) FROM item_conversion
UNION ALL SELECT 'high_exposure_low_conversion_items', COUNT(*) FROM high_exposure_low_conversion_items;
