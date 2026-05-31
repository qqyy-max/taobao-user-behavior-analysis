-- ============================================================
-- 00_init.sql — 共享基础层 (Shared Foundation Layer)
-- ============================================================
-- 职责：
--   1. 定义 clean 视图（一次性，所有后续 SQL 复用）
--   2. 创建 user_base_metrics 中间表（避免 02/05/06 重复聚合）
--   3. 创建 dim_date 日期维度（Power BI 星型模型）
-- 输出：
--   clean               — 清洗后全量数据视图
--   dim_date            — 日期维度表
--   user_base_metrics   — 用户基础指标宽表（被 02/05/06 复用）
-- 依赖：data/clean_data.parquet
-- ============================================================

-- ============================================================
-- 1. 共享数据源视图（全局唯一，不再在每个文件中重复定义）
-- ============================================================
CREATE OR REPLACE VIEW clean AS
SELECT * FROM read_parquet('data/clean_data.parquet');


-- ============================================================
-- 2. dim_date — 日期维度表 (Power BI Date Dimension)
-- ============================================================
DROP TABLE IF EXISTS dim_date;
CREATE TABLE dim_date AS
SELECT DISTINCT
    dt,
    CAST(strftime(dt, '%Y') AS INTEGER)                         AS year,
    CAST(strftime(dt, '%m') AS INTEGER)                         AS month,
    CAST(strftime(dt, '%d') AS INTEGER)                         AS day,
    CAST(strftime(dt, '%u') AS INTEGER)                         AS weekday,
    CASE CAST(strftime(dt, '%u') AS INTEGER)
        WHEN 6 THEN 1 WHEN 7 THEN 1 ELSE 0
    END                                                          AS is_weekend,
    strftime(dt, '%Y-%m')                                       AS month_label,
    -- 按周分组（用于周度趋势）
    DATE_TRUNC('week', dt)::DATE                                AS week_start
FROM clean
ORDER BY dt;


-- ============================================================
-- 3. user_base_metrics — 用户基础指标中间表
-- ============================================================
-- 说明：将 user_id 级别的行为聚合计算一次，供后续层直接引用。
--       02_funnel_retention 用其中的行为标记
--       05_user_analysis 用其中的基础指标计算画像
--       06_feature_mart 用其作为 base CTE 替代
DROP TABLE IF EXISTS user_base_metrics;
CREATE TABLE user_base_metrics AS
SELECT
    user_id,

    -- 行为计数
    COUNT(*)                                                     AS total_actions,
    SUM(CASE WHEN behavior_type = 'pv'   THEN 1 ELSE 0 END)     AS pv_cnt,
    SUM(CASE WHEN behavior_type = 'fav'  THEN 1 ELSE 0 END)     AS fav_cnt,
    SUM(CASE WHEN behavior_type = 'cart' THEN 1 ELSE 0 END)     AS cart_cnt,
    SUM(CASE WHEN behavior_type = 'buy'  THEN 1 ELSE 0 END)     AS buy_cnt,

    -- 活跃天数
    COUNT(DISTINCT dt)                                           AS active_days,
    COUNT(DISTINCT CASE WHEN behavior_type = 'buy'  THEN dt END) AS buy_days,
    COUNT(DISTINCT CASE WHEN behavior_type = 'cart' THEN dt END) AS cart_days,
    COUNT(DISTINCT CASE WHEN behavior_type = 'fav'  THEN dt END) AS fav_days,

    -- 时间窗口
    MIN(dt)                                                      AS first_active_date,
    MAX(dt)                                                      AS last_active_date,
    DATEDIFF('day', MIN(dt), MAX(dt)) + 1                       AS lifecycle_days,

    -- 关键标签
    CASE WHEN SUM(CASE WHEN behavior_type = 'buy'  THEN 1 ELSE 0 END) > 0 THEN 1 ELSE 0 END AS is_buyer,
    CASE WHEN SUM(CASE WHEN behavior_type = 'cart' THEN 1 ELSE 0 END) > 0 THEN 1 ELSE 0 END AS has_cart,
    CASE WHEN SUM(CASE WHEN behavior_type = 'fav'  THEN 1 ELSE 0 END) > 0 THEN 1 ELSE 0 END AS has_fav

FROM clean
GROUP BY user_id;


-- ============================================================
-- 4. category_base_stats — 类目基础统计中间表
-- ============================================================
DROP TABLE IF EXISTS category_base_stats;
CREATE TABLE category_base_stats AS
SELECT
    category_id,
    COUNT(*)                                                     AS total_actions,
    SUM(CASE WHEN behavior_type = 'pv'   THEN 1 ELSE 0 END)     AS pv_cnt,
    SUM(CASE WHEN behavior_type = 'fav'  THEN 1 ELSE 0 END)     AS fav_cnt,
    SUM(CASE WHEN behavior_type = 'cart' THEN 1 ELSE 0 END)     AS cart_cnt,
    SUM(CASE WHEN behavior_type = 'buy'  THEN 1 ELSE 0 END)     AS buy_cnt,
    COUNT(DISTINCT user_id)                                      AS uv,
    COUNT(DISTINCT item_id)                                      AS item_cnt,
    COUNT(DISTINCT CASE WHEN behavior_type = 'buy' THEN user_id END) AS buy_uv
FROM clean
GROUP BY category_id;


-- ============================================================
-- 验证
-- ============================================================
SELECT '=== 00_init 执行完成 ===' AS status;
SELECT 'dim_date'             AS tbl, COUNT(*) AS rows FROM dim_date
UNION ALL SELECT 'user_base_metrics', COUNT(*) FROM user_base_metrics
UNION ALL SELECT 'category_base_stats', COUNT(*) FROM category_base_stats;
