-- ═══════════════════════════════════════════════════════════════
-- SQL Template: Anomaly Weekend — 周末流量异动归因
-- 用途：周末vs工作日DAU/购买率对比，归因分析
-- ═══════════════════════════════════════════════════════════════

-- 模板5-1: 周末 vs 工作日核心指标对比
SELECT * FROM weekend_anomaly_summary;

-- 模板5-2: 每日趋势（标注周末）
SELECT
    dbs.dt,
    dd.is_weekend,
    dbs.dau,
    dbs.total_actions,
    dbs.buy_rate_pct,
    dbs.avg_actions_per_user,
    ROUND(1.0 * dbs.cart_cnt / NULLIF(dbs.pv_cnt, 0) * 100, 2) AS cart_rate_pct
FROM daily_behavior_summary dbs
JOIN dim_date dd ON dbs.dt = dd.dt
ORDER BY dbs.dt;

-- 模板5-3: 周末 vs 工作日 — 用户行为类型占比
SELECT
    dd.is_weekend,
    CASE WHEN dd.is_weekend = 1 THEN '周末' ELSE '工作日' END AS day_type,
    SUM(dbs.pv_cnt) AS total_pv,
    SUM(dbs.fav_cnt) AS total_fav,
    SUM(dbs.cart_cnt) AS total_cart,
    SUM(dbs.buy_cnt) AS total_buy,
    ROUND(100.0 * SUM(dbs.pv_cnt) / SUM(dbs.total_actions), 1) AS pv_pct,
    ROUND(100.0 * SUM(dbs.fav_cnt) / SUM(dbs.total_actions), 1) AS fav_pct,
    ROUND(100.0 * SUM(dbs.cart_cnt) / SUM(dbs.total_actions), 1) AS cart_pct,
    ROUND(100.0 * SUM(dbs.buy_cnt) / SUM(dbs.total_actions), 1) AS buy_pct
FROM daily_behavior_summary dbs
JOIN dim_date dd ON dbs.dt = dd.dt
GROUP BY dd.is_weekend;

-- 模板5-4: 周末 vs 工作日 — 按小时的行为分布
SELECT
    dd.is_weekend,
    CASE WHEN dd.is_weekend = 1 THEN '周末' ELSE '工作日' END AS day_type,
    hbs.hour,
    AVG(hbs.actions) AS avg_actions,
    AVG(hbs.buy_rate_pct) AS avg_buy_rate_pct,
    AVG(hbs.cart_rate_pct) AS avg_cart_rate_pct
FROM hourly_behavior_summary hbs
CROSS JOIN (SELECT DISTINCT dt, is_weekend FROM dim_date) dd
GROUP BY dd.is_weekend, hbs.hour
ORDER BY dd.is_weekend, hbs.hour;

-- 模板5-5: 周末行为混合分析（新增表 weekend_behavior_mix）
SELECT * FROM weekend_behavior_mix;
