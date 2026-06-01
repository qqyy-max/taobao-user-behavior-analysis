-- ============================================================
-- 08_powerbi_supplement.sql — Power BI 增强补充表
-- ============================================================
-- 职责：为 insight audit 中新增/替换的图表提供数据支持
-- 输出：
--   funnel_path_detail           — Sankey 多路径漏斗（新增图表）
--   search_direct_items          — 搜索直达型商品分布（新增图表）
--   cluster_temporal_profile     — 分群×时间偏好（新增图表）
-- 依赖：00_init ~ 07_export_mart 全部执行完成
-- ============================================================

-- ============================================================
-- 1. funnel_path_detail — 多路径转化明细（Sankey 图）
-- ============================================================
-- 计算每对行为阶段之间的用户流向：
--   PV→FAV, PV→CART(跳过收藏), PV→BUY(直接购买)
--   FAV→CART, FAV→BUY, CART→BUY
DROP TABLE IF EXISTS funnel_path_detail;
CREATE TABLE funnel_path_detail AS
WITH user_behaviors AS (
    SELECT
        user_id,
        MAX(CASE WHEN behavior_type = 'pv'   THEN 1 ELSE 0 END) AS has_pv,
        MAX(CASE WHEN behavior_type = 'fav'  THEN 1 ELSE 0 END) AS has_fav,
        MAX(CASE WHEN behavior_type = 'cart' THEN 1 ELSE 0 END) AS has_cart,
        MAX(CASE WHEN behavior_type = 'buy'  THEN 1 ELSE 0 END) AS has_buy
    FROM clean
    GROUP BY user_id
)
SELECT 'PV→FAV' AS path_from, 'PV' AS source, 'FAV' AS target, COUNT(*) AS user_cnt FROM user_behaviors WHERE has_pv=1 AND has_fav=1
UNION ALL
SELECT 'PV→CART(skip FAV)', 'PV', 'CART', COUNT(*) FROM user_behaviors WHERE has_pv=1 AND has_cart=1 AND has_fav=0
UNION ALL
SELECT 'PV→BUY(direct)', 'PV', 'BUY', COUNT(*) FROM user_behaviors WHERE has_pv=1 AND has_buy=1 AND has_cart=0 AND has_fav=0
UNION ALL
SELECT 'FAV→CART', 'FAV', 'CART', COUNT(*) FROM user_behaviors WHERE has_fav=1 AND has_cart=1
UNION ALL
SELECT 'FAV→BUY', 'FAV', 'BUY', COUNT(*) FROM user_behaviors WHERE has_fav=1 AND has_buy=1
UNION ALL
SELECT 'CART→BUY', 'CART', 'BUY', COUNT(*) FROM user_behaviors WHERE has_cart=1 AND has_buy=1
ORDER BY user_cnt DESC;


-- ============================================================
-- 2. search_direct_items — 搜索直达型商品（buy>0 AND pv=0）
-- ============================================================
-- 这些商品被购买但从未被"浏览"——用户通过搜索/推荐直达购买
DROP TABLE IF EXISTS search_direct_items;
CREATE TABLE search_direct_items AS
SELECT
    i.item_id,
    i.category_id,
    i.buy_cnt,
    i.cart_cnt,
    i.buy_uv,
    i.exposure_rank,
    i.conversion_rank
FROM item_conversion i
WHERE i.buy_cnt > 0
  AND i.pv_cnt = 0
ORDER BY i.buy_cnt DESC;


-- ============================================================
-- 3. search_direct_by_category — 搜索直达商品按类目汇总
-- ============================================================
DROP TABLE IF EXISTS search_direct_by_category;
CREATE TABLE search_direct_by_category AS
SELECT
    sdi.category_id,
    COUNT(*)                         AS direct_item_cnt,
    SUM(sdi.buy_cnt)                 AS total_buy_cnt,
    SUM(sdi.buy_uv)                  AS total_buy_uv,
    ROUND(AVG(sdi.buy_cnt), 1)       AS avg_buy_per_item
FROM search_direct_items sdi
GROUP BY sdi.category_id
ORDER BY direct_item_cnt DESC;


-- ============================================================
-- 4. cluster_temporal_profile — 分群×时间偏好（P5 新增图表）
-- ============================================================
-- 从 user_features + user_cluster_result 聚合：
--   weekend_ratio, morning_ratio, afternoon_ratio,
--   evening_ratio, night_ratio, peak_hour
DROP TABLE IF EXISTS cluster_temporal_profile;
CREATE TABLE cluster_temporal_profile AS
WITH cluster_result AS (
    SELECT * FROM read_parquet('data/mart/user_cluster_result.parquet')
),
joined AS (
    SELECT
        cr.cluster,
        uf.weekend_ratio,
        uf.morning_ratio,
        uf.afternoon_ratio,
        uf.evening_ratio,
        uf.night_ratio,
        uf.hour_concentration,
        uf.buy_weekend_ratio
    FROM user_features uf
    JOIN cluster_result cr ON uf.user_id = cr.user_id
)
SELECT
    cluster,
    COUNT(*)                                   AS user_cnt,
    ROUND(AVG(weekend_ratio), 1)               AS avg_weekend_ratio_pct,
    ROUND(AVG(morning_ratio), 1)               AS avg_morning_ratio_pct,
    ROUND(AVG(afternoon_ratio), 1)             AS avg_afternoon_ratio_pct,
    ROUND(AVG(evening_ratio), 1)               AS avg_evening_ratio_pct,
    ROUND(AVG(night_ratio), 1)                 AS avg_night_ratio_pct,
    ROUND(AVG(hour_concentration), 3)          AS avg_hour_concentration,
    ROUND(AVG(buy_weekend_ratio), 1)           AS avg_buy_weekend_ratio_pct
FROM joined
GROUP BY cluster
ORDER BY cluster;


-- ============================================================
-- 5. 导出为 Parquet
-- ============================================================
COPY funnel_path_detail
TO 'data/mart/funnel_path_detail.parquet'
WITH (FORMAT PARQUET, COMPRESSION ZSTD);

COPY search_direct_items
TO 'data/mart/search_direct_items.parquet'
WITH (FORMAT PARQUET, COMPRESSION ZSTD);

COPY search_direct_by_category
TO 'data/mart/search_direct_by_category.parquet'
WITH (FORMAT PARQUET, COMPRESSION ZSTD);

COPY cluster_temporal_profile
TO 'data/mart/cluster_temporal_profile.parquet'
WITH (FORMAT PARQUET, COMPRESSION ZSTD);


-- ============================================================
-- 验证
-- ============================================================
SELECT '=== 08_powerbi_supplement 执行完成 ===' AS status;
SELECT 'funnel_path_detail'        AS tbl, COUNT(*) AS rows FROM funnel_path_detail
UNION ALL SELECT 'search_direct_items',      COUNT(*) FROM search_direct_items
UNION ALL SELECT 'search_direct_by_category',COUNT(*) FROM search_direct_by_category
UNION ALL SELECT 'cluster_temporal_profile', COUNT(*) FROM cluster_temporal_profile;
