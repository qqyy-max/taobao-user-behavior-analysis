-- ============================================================
-- 01_profiling.sql — 数据画像层
-- ============================================================
-- 职责：生成数据规模、用户/商品/类目基数、时间范围、
--       数值字段统计、行为分布统计
-- 输出表：profiling_summary（宽表，直接用于 README 展示和 Power BI 概览卡片）
-- 依赖：00_init.sql（提供 clean 视图）
-- ============================================================

-- ============================================================
-- 1. profiling_summary —— 数据画像汇总表
-- ============================================================
DROP TABLE IF EXISTS profiling_summary;
CREATE TABLE profiling_summary AS

-- 1.1 数据规模
SELECT 'total_rows'           AS metric, '总行数' AS metric_cn, COUNT(*)::VARCHAR       AS value FROM clean
UNION ALL
SELECT 'total_users',         '独立用户数',    COUNT(DISTINCT user_id)::VARCHAR         FROM clean
UNION ALL
SELECT 'total_items',         '独立商品数',    COUNT(DISTINCT item_id)::VARCHAR         FROM clean
UNION ALL
SELECT 'total_categories',    '独立类目数',    COUNT(DISTINCT category_id)::VARCHAR     FROM clean
UNION ALL
SELECT 'total_days',          '覆盖天数',      COUNT(DISTINCT dt)::VARCHAR             FROM clean
UNION ALL
SELECT 'date_range',          '日期范围',      MIN(dt)::VARCHAR || ' ~ ' || MAX(dt)::VARCHAR FROM clean

UNION ALL
-- 1.2 行为分布
SELECT 'pv_cnt',              '浏览(PV)行数',        SUM(CASE WHEN behavior_type='pv'   THEN 1 ELSE 0 END)::VARCHAR FROM clean
UNION ALL
SELECT 'fav_cnt',             '收藏(FAV)行数',       SUM(CASE WHEN behavior_type='fav'  THEN 1 ELSE 0 END)::VARCHAR FROM clean
UNION ALL
SELECT 'cart_cnt',            '加购(CART)行数',      SUM(CASE WHEN behavior_type='cart' THEN 1 ELSE 0 END)::VARCHAR FROM clean
UNION ALL
SELECT 'buy_cnt',             '购买(BUY)行数',       SUM(CASE WHEN behavior_type='buy'  THEN 1 ELSE 0 END)::VARCHAR FROM clean

UNION ALL
SELECT 'pv_pct',              '浏览占比(%)',         ROUND(100.0*SUM(CASE WHEN behavior_type='pv'   THEN 1 ELSE 0 END)/COUNT(*),2)::VARCHAR FROM clean
UNION ALL
SELECT 'fav_pct',             '收藏占比(%)',         ROUND(100.0*SUM(CASE WHEN behavior_type='fav'  THEN 1 ELSE 0 END)/COUNT(*),2)::VARCHAR FROM clean
UNION ALL
SELECT 'cart_pct',            '加购占比(%)',         ROUND(100.0*SUM(CASE WHEN behavior_type='cart' THEN 1 ELSE 0 END)/COUNT(*),2)::VARCHAR FROM clean
UNION ALL
SELECT 'buy_pct',             '购买占比(%)',         ROUND(100.0*SUM(CASE WHEN behavior_type='buy'  THEN 1 ELSE 0 END)/COUNT(*),2)::VARCHAR FROM clean

UNION ALL
-- 1.3 用户转化基数
SELECT 'pv_uv',               '浏览用户数(UV)',     COUNT(DISTINCT user_id)::VARCHAR FROM clean WHERE behavior_type='pv'
UNION ALL
SELECT 'fav_uv',              '收藏用户数(UV)',     COUNT(DISTINCT user_id)::VARCHAR FROM clean WHERE behavior_type='fav'
UNION ALL
SELECT 'cart_uv',             '加购用户数(UV)',     COUNT(DISTINCT user_id)::VARCHAR FROM clean WHERE behavior_type='cart'
UNION ALL
SELECT 'buy_uv',              '购买用户数(UV)',     COUNT(DISTINCT user_id)::VARCHAR FROM clean WHERE behavior_type='buy'

UNION ALL
-- 1.4 用户行为分位数 (基于每个用户总行为数)
SELECT 'user_actions_p10',    '用户行为数P10',      APPROX_QUANTILE(cnt, 0.10)::VARCHAR FROM (SELECT COUNT(*) AS cnt FROM clean GROUP BY user_id)
UNION ALL
SELECT 'user_actions_p25',    '用户行为数P25',      APPROX_QUANTILE(cnt, 0.25)::VARCHAR FROM (SELECT COUNT(*) AS cnt FROM clean GROUP BY user_id)
UNION ALL
SELECT 'user_actions_p50',    '用户行为数P50',      APPROX_QUANTILE(cnt, 0.50)::VARCHAR FROM (SELECT COUNT(*) AS cnt FROM clean GROUP BY user_id)
UNION ALL
SELECT 'user_actions_p75',    '用户行为数P75',      APPROX_QUANTILE(cnt, 0.75)::VARCHAR FROM (SELECT COUNT(*) AS cnt FROM clean GROUP BY user_id)
UNION ALL
SELECT 'user_actions_p90',    '用户行为数P90',      APPROX_QUANTILE(cnt, 0.90)::VARCHAR FROM (SELECT COUNT(*) AS cnt FROM clean GROUP BY user_id)
UNION ALL
SELECT 'user_actions_p95',    '用户行为数P95',      APPROX_QUANTILE(cnt, 0.95)::VARCHAR FROM (SELECT COUNT(*) AS cnt FROM clean GROUP BY user_id)
UNION ALL
SELECT 'user_actions_p99',    '用户行为数P99',      APPROX_QUANTILE(cnt, 0.99)::VARCHAR FROM (SELECT COUNT(*) AS cnt FROM clean GROUP BY user_id)

UNION ALL
-- 1.5 数值字段统计
SELECT 'user_id_min',         '用户ID最小值',      MIN(user_id)::VARCHAR    FROM clean
UNION ALL
SELECT 'user_id_max',         '用户ID最大值',      MAX(user_id)::VARCHAR    FROM clean
UNION ALL
SELECT 'item_id_min',         '商品ID最小值',      MIN(item_id)::VARCHAR    FROM clean
UNION ALL
SELECT 'item_id_max',         '商品ID最大值',      MAX(item_id)::VARCHAR    FROM clean
UNION ALL
SELECT 'category_id_min',     '类目ID最小值',      MIN(category_id)::VARCHAR FROM clean
UNION ALL
SELECT 'category_id_max',     '类目ID最大值',      MAX(category_id)::VARCHAR FROM clean
UNION ALL
SELECT 'ts_min',              '时间戳最小值',      MIN(ts)::VARCHAR         FROM clean
UNION ALL
SELECT 'ts_max',              '时间戳最大值',      MAX(ts)::VARCHAR         FROM clean;


-- ============================================================
-- 验证输出
-- ============================================================
SELECT '=== 01_profiling 执行完成 ===' AS status;
SELECT * FROM profiling_summary ORDER BY metric;
