-- ═══════════════════════════════════════════════════════════════
-- SQL Template: Product Efficiency — 商品曝光效率
-- 用途：高曝光低转化商品规模、类目分布、搜索直达商品
-- ═══════════════════════════════════════════════════════════════

-- 模板4-1: 商品效率全局汇总
SELECT * FROM product_efficiency_anomaly_summary;

-- 模板4-2: 高曝光低转化商品 — Top 20（按PV降序）
SELECT
    item_id,
    category_id,
    pv_cnt,
    pv_uv,
    buy_cnt,
    buy_rate_pct,
    exposure_conversion_gap,
    repeat_view_rate
FROM high_exposure_low_conversion_items
ORDER BY pv_cnt DESC
LIMIT 20;

-- 模板4-3: 高曝光低转化商品 — 按类目汇总
SELECT
    h.category_id,
    COUNT(*) AS helc_item_cnt,
    ROUND(AVG(h.pv_cnt), 1) AS avg_pv,
    ROUND(AVG(h.exposure_conversion_gap), 1) AS avg_exposure_gap,
    COALESCE(c.buy_rate_pct, 0) AS category_overall_buy_rate_pct
FROM high_exposure_low_conversion_items h
LEFT JOIN category_conversion c ON h.category_id = c.category_id
GROUP BY h.category_id, c.buy_rate_pct
ORDER BY helc_item_cnt DESC
LIMIT 20;

-- 模板4-4: 搜索直达商品（被购买但无PV）
SELECT
    item_id,
    category_id,
    buy_cnt,
    buy_uv
FROM search_direct_items
ORDER BY buy_cnt DESC
LIMIT 20;

-- 模板4-5: 搜索直达商品按类目汇总
SELECT
    category_id,
    COUNT(*) AS direct_item_cnt,
    SUM(buy_cnt) AS total_buy_cnt
FROM search_direct_items
GROUP BY category_id
ORDER BY direct_item_cnt DESC;

-- 模板4-6: 商品转化率四象限（基于P50阈值动态计算）
WITH thresholds AS (
    SELECT
        APPROX_QUANTILE(pv_cnt, 0.50) AS pv_median,
        APPROX_QUANTILE(NULLIF(buy_rate_pct, 0), 0.50) AS buy_rate_median
    FROM item_conversion
    WHERE pv_cnt > 0
)
SELECT
    CASE
        WHEN ic.pv_cnt >= t.pv_median AND ic.buy_rate_pct > t.buy_rate_median THEN '高曝光高转化'
        WHEN ic.pv_cnt >= t.pv_median AND ic.buy_rate_pct <= t.buy_rate_median THEN '高曝光低转化'
        WHEN ic.pv_cnt < t.pv_median AND ic.buy_rate_pct > t.buy_rate_median THEN '低曝光高转化'
        ELSE '低曝光低转化'
    END AS quadrant,
    COUNT(*) AS item_cnt,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 1) AS item_pct,
    ROUND(AVG(ic.pv_cnt), 1) AS avg_pv,
    ROUND(AVG(ic.buy_rate_pct), 2) AS avg_buy_rate_pct
FROM item_conversion ic, thresholds t
WHERE ic.pv_cnt > 0
GROUP BY quadrant
ORDER BY item_cnt DESC;
