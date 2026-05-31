-- ============================================================
-- 06_feature_mart.sql — 特征宽表层 (Feature Mart for ML)
-- ============================================================
-- 职责：为 Python sklearn 聚类建模准备可直接使用的特征宽表。
--       所有字段数值化、无空值、可直接进入 StandardScaler。
-- 输出：
--   user_features           — DuckDB 表
--   data/features/user_features.parquet — 持久化文件
-- 依赖：00_init.sql（提供 clean 视图 + user_base_metrics 中间表）
-- ============================================================


-- ============================================================
-- user_features — 用户特征宽表
-- ============================================================
DROP TABLE IF EXISTS user_features;
CREATE TABLE user_features AS
WITH
-- 1. 时域特征
user_hour_agg AS (
    SELECT user_id, CAST(hour AS INTEGER) AS hour_val, is_weekend, COUNT(*) AS cnt
    FROM clean GROUP BY user_id, hour, is_weekend
),
user_total AS (
    SELECT user_id, SUM(cnt) AS total_cnt FROM user_hour_agg GROUP BY user_id
),
time_features AS (
    SELECT
        h.user_id,
        ROUND(100.0 * SUM(CASE WHEN h.hour_val >= 22 OR h.hour_val < 6 THEN h.cnt ELSE 0 END)
                    / NULLIF(t.total_cnt, 0), 2)                         AS night_ratio,
        ROUND(100.0 * SUM(CASE WHEN h.hour_val >= 6 AND h.hour_val < 12 THEN h.cnt ELSE 0 END)
                    / NULLIF(t.total_cnt, 0), 2)                         AS morning_ratio,
        ROUND(100.0 * SUM(CASE WHEN h.hour_val >= 12 AND h.hour_val < 18 THEN h.cnt ELSE 0 END)
                    / NULLIF(t.total_cnt, 0), 2)                         AS afternoon_ratio,
        ROUND(100.0 * SUM(CASE WHEN h.hour_val >= 18 AND h.hour_val < 22 THEN h.cnt ELSE 0 END)
                    / NULLIF(t.total_cnt, 0), 2)                         AS evening_ratio,
        ROUND(100.0 * SUM(CASE WHEN h.is_weekend = 1 THEN h.cnt ELSE 0 END)
                    / NULLIF(t.total_cnt, 0), 2)                         AS weekend_ratio,
        ROUND(SUM(pow(1.0 * h.cnt / t.total_cnt, 2)), 4)                AS hour_concentration
    FROM user_hour_agg h JOIN user_total t ON h.user_id = t.user_id
    GROUP BY h.user_id, t.total_cnt
),

-- 2. 最活跃时段
peak_hour_feature AS (
    SELECT DISTINCT user_id,
        FIRST_VALUE(CAST(hour AS INTEGER)) OVER (PARTITION BY user_id ORDER BY cnt DESC) AS peak_hour
    FROM (SELECT user_id, hour, COUNT(*) AS cnt FROM clean GROUP BY user_id, hour)
),

-- 3. 最常交互类目
favorite_category_feature AS (
    SELECT DISTINCT user_id,
        FIRST_VALUE(category_id) OVER (PARTITION BY user_id ORDER BY cnt DESC) AS favorite_category
    FROM (SELECT user_id, category_id, COUNT(*) AS cnt FROM clean GROUP BY user_id, category_id)
),

-- 4. 类目 & 商品广度
diversity_features AS (
    SELECT user_id,
        COUNT(DISTINCT category_id) AS category_diversity,
        COUNT(DISTINCT item_id)     AS item_diversity
    FROM clean GROUP BY user_id
),

-- 4b. 类目集中度
category_concentration_feature AS (
    SELECT user_id,
        ROUND(1.0 * MAX(cnt) / SUM(cnt), 4) AS category_concentration
    FROM (SELECT user_id, category_id, COUNT(*) AS cnt FROM clean GROUP BY user_id, category_id)
    GROUP BY user_id
),

-- 5. 行为深度特征（从 clean 直接算比率）
depth_features AS (
    SELECT user_id,
        ROUND(100.0 * SUM(CASE WHEN behavior_type='cart' THEN 1 ELSE 0 END)
              / NULLIF(SUM(CASE WHEN behavior_type='pv' THEN 1 ELSE 0 END), 0), 2) AS cart_to_pv_ratio,
        ROUND(100.0 * SUM(CASE WHEN behavior_type='fav' THEN 1 ELSE 0 END)
              / NULLIF(SUM(CASE WHEN behavior_type='pv' THEN 1 ELSE 0 END), 0), 2) AS fav_to_pv_ratio,
        ROUND(100.0 * SUM(CASE WHEN behavior_type='buy' THEN 1 ELSE 0 END)
              / NULLIF(SUM(CASE WHEN behavior_type='pv' THEN 1 ELSE 0 END), 0), 2) AS buy_to_pv_ratio,
        ROUND(100.0 * SUM(CASE WHEN behavior_type='buy' THEN 1 ELSE 0 END)
              / NULLIF(SUM(CASE WHEN behavior_type='cart' THEN 1 ELSE 0 END), 0), 2) AS buy_to_cart_ratio
    FROM clean GROUP BY user_id
),

-- 6. 近期活跃衰减
recency_features AS (
    SELECT user_id,
        ROUND(100.0 * SUM(CASE WHEN dt >= (SELECT MAX(dt) FROM clean) - INTERVAL 7 DAY THEN 1 ELSE 0 END)
              / NULLIF(COUNT(*), 0), 2)                         AS recent_7d_actions_pct,
        ROUND(100.0 * SUM(CASE WHEN dt >= (SELECT MAX(dt) FROM clean) - INTERVAL 30 DAY THEN 1 ELSE 0 END)
              / NULLIF(COUNT(*), 0), 2)                         AS recent_30d_actions_pct,
        DATEDIFF('day', MAX(dt), (SELECT MAX(dt) FROM clean))   AS days_since_last_active
    FROM clean GROUP BY user_id
),

-- 7. 周度行为稳定性
weekly_behavior AS (
    SELECT user_id,
        ROUND(STDDEV_SAMP(weekly_cnt) / NULLIF(AVG(weekly_cnt), 0), 4) AS weekly_volatility,
        COUNT(*)                                                       AS active_weeks
    FROM (SELECT user_id, DATE_TRUNC('week', dt) AS week, COUNT(*) AS weekly_cnt
          FROM clean GROUP BY user_id, DATE_TRUNC('week', dt))
    GROUP BY user_id
),

-- ★ 8. 新增：活跃小时数 + 活跃星期数
active_diversity AS (
    SELECT user_id,
        COUNT(DISTINCT CAST(hour AS INTEGER)) AS active_hours,
        COUNT(DISTINCT weekday)               AS active_weekdays
    FROM clean GROUP BY user_id
),

-- ★ 9. 新增：周末购买占比
buy_weekend_feature AS (
    SELECT user_id,
        ROUND(100.0 * SUM(CASE WHEN is_weekend=1 THEN 1 ELSE 0 END)
              / NULLIF(COUNT(*), 0), 2) AS buy_weekend_ratio
    FROM clean WHERE behavior_type='buy'
    GROUP BY user_id
)

SELECT
    m.user_id,

    -- === 行为计数（4 特征）===
    m.pv_cnt,
    COALESCE(m.fav_cnt, 0)              AS fav_cnt,
    COALESCE(m.cart_cnt, 0)             AS cart_cnt,
    COALESCE(m.buy_cnt, 0)              AS buy_cnt,

    -- === 转化率特征（4 特征）===
    COALESCE(df.fav_to_pv_ratio, 0)     AS fav_rate,
    COALESCE(df.cart_to_pv_ratio, 0)    AS cart_rate,
    COALESCE(df.buy_to_pv_ratio, 0)     AS buy_rate,
    COALESCE(df.buy_to_cart_ratio, 0)   AS cart_to_buy_rate,

    -- === 活跃度特征（5 特征）===
    m.active_days,
    COALESCE(m.buy_days, 0)             AS buy_days,
    ROUND(1.0 * COALESCE(m.buy_days,0) / NULLIF(m.active_days, 0), 3) AS buy_days_ratio,
    COALESCE(ad.active_hours, 0)        AS active_hours,
    COALESCE(ad.active_weekdays, 0)     AS active_weekdays,

    -- === 行为强度特征（3 特征）===
    ROUND(1.0 * m.pv_cnt / NULLIF(m.active_days, 0), 1)     AS avg_daily_actions,
    ROUND(1.0 * COALESCE(m.buy_cnt,0) / NULLIF(m.active_days,0), 3) AS avg_daily_buy,
    ROUND(1.0 * COALESCE(m.cart_cnt,0) / NULLIF(m.active_days,0), 2) AS avg_daily_cart,

    -- === 兴趣广度（2 特征）===
    COALESCE(dv.category_diversity, 0)  AS category_diversity,
    COALESCE(dv.item_diversity, 0)      AS item_diversity,

    -- === 时间偏好（6 特征）===
    COALESCE(tf.weekend_ratio, 0)       AS weekend_ratio,
    COALESCE(tf.night_ratio, 0)         AS night_ratio,
    COALESCE(tf.morning_ratio, 0)       AS morning_ratio,
    COALESCE(tf.afternoon_ratio, 0)     AS afternoon_ratio,
    COALESCE(tf.evening_ratio, 0)       AS evening_ratio,
    COALESCE(tf.hour_concentration, 0)  AS hour_concentration,
    COALESCE(bw.buy_weekend_ratio, 0)   AS buy_weekend_ratio,

    -- === 兴趣偏好（4 特征）===
    COALESCE(fc.favorite_category, 0)   AS favorite_category,
    COALESCE(cc.category_concentration, 0) AS category_concentration,

    -- === 活跃稳定性（5 特征）===
    m.lifecycle_days,
    COALESCE(wb.active_weeks, 0)        AS active_weeks,
    COALESCE(wb.weekly_volatility, 0)   AS weekly_volatility,
    COALESCE(rf.recent_7d_actions_pct, 0)  AS recent_7d_actions_pct,
    COALESCE(rf.recent_30d_actions_pct, 0) AS recent_30d_actions_pct,
    COALESCE(rf.days_since_last_active, 999) AS days_since_last_active,

    -- === 标签（聚类时排除）===
    m.is_buyer

FROM user_base_metrics m
LEFT JOIN depth_features                  df ON m.user_id = df.user_id
LEFT JOIN time_features                   tf ON m.user_id = tf.user_id
LEFT JOIN active_diversity                ad ON m.user_id = ad.user_id
LEFT JOIN buy_weekend_feature             bw ON m.user_id = bw.user_id
LEFT JOIN favorite_category_feature       fc ON m.user_id = fc.user_id
LEFT JOIN diversity_features              dv ON m.user_id = dv.user_id
LEFT JOIN category_concentration_feature  cc ON m.user_id = cc.user_id
LEFT JOIN weekly_behavior                 wb ON m.user_id = wb.user_id
LEFT JOIN recency_features                rf ON m.user_id = rf.user_id
LEFT JOIN peak_hour_feature               ph ON m.user_id = ph.user_id;


-- ============================================================
-- 导出为 Parquet（Python sklearn 直接读取）
-- ============================================================
COPY user_features
TO 'data/features/user_features.parquet'
WITH (FORMAT PARQUET, COMPRESSION ZSTD);


-- ============================================================
-- 验证
-- ============================================================
SELECT '=== 06_feature_mart 执行完成 ===' AS status;
SELECT 'user_features' AS tbl, COUNT(*) AS rows, COUNT(DISTINCT user_id) AS unique_users
FROM user_features;

-- 空值检查
SELECT
    SUM(CASE WHEN pv_cnt IS NULL THEN 1 ELSE 0 END) AS null_pv,
    SUM(CASE WHEN buy_rate IS NULL THEN 1 ELSE 0 END) AS null_buy_rate,
    SUM(CASE WHEN active_hours IS NULL THEN 1 ELSE 0 END) AS null_active_hours,
    SUM(CASE WHEN buy_weekend_ratio IS NULL THEN 1 ELSE 0 END) AS null_buy_weekend
FROM user_features;
