-- ═══════════════════════════════════════════════════════════════
-- SQL Template: Anomaly Hourly — 时段流量-转化错配
-- 用途：24小时流量vs购买率对比，Push排期优化
-- ═══════════════════════════════════════════════════════════════

-- 模板6-1: 24小时购买效率全景
SELECT
    hour,
    actions,
    buy_cnt,
    buy_rate_pct,
    uv,
    ROUND(1.0 * actions / NULLIF(uv, 0), 1) AS avg_actions_per_user,
    ROUND(1.0 * cart_cnt / NULLIF(pv_cnt, 0) * 100, 2) AS cart_rate_pct
FROM hourly_behavior_summary
ORDER BY hour;

-- 模板6-2: 时段分组对比（上午/下午/晚间/深夜）
SELECT
    CASE
        WHEN hour BETWEEN 6 AND 11 THEN '上午(6-11)'
        WHEN hour BETWEEN 12 AND 17 THEN '下午(12-17)'
        WHEN hour BETWEEN 18 AND 21 THEN '晚间(18-21)'
        ELSE '深夜(22-5)'
    END AS time_slot,
    SUM(actions) AS total_actions,
    SUM(buy_cnt) AS total_buy,
    ROUND(100.0 * SUM(buy_cnt) / NULLIF(SUM(actions), 0), 2) AS buy_rate_pct,
    ROUND(AVG(uv), 0) AS avg_uv,
    ROUND(AVG(1.0 * cart_cnt / NULLIF(pv_cnt, 0) * 100), 2) AS avg_cart_rate_pct
FROM hourly_behavior_summary
GROUP BY time_slot
ORDER BY
    CASE time_slot
        WHEN '上午(6-11)' THEN 1
        WHEN '下午(12-17)' THEN 2
        WHEN '晚间(18-21)' THEN 3
        ELSE 4
    END;

-- 模板6-3: 时段异动汇总（新增表）
SELECT * FROM hourly_anomaly_summary
ORDER BY hour;

-- 模板6-4: 流量峰值 vs 购买率峰值 时段排名
SELECT
    hour,
    actions,
    buy_rate_pct,
    RANK() OVER (ORDER BY actions DESC) AS traffic_rank,
    RANK() OVER (ORDER BY buy_rate_pct DESC) AS conversion_rank,
    RANK() OVER (ORDER BY actions DESC) - RANK() OVER (ORDER BY buy_rate_pct DESC) AS rank_gap
FROM hourly_behavior_summary
ORDER BY rank_gap DESC;

-- 模板6-5: 上午 vs 晚间对比（早间购买效率窗口）
SELECT
    '上午(6-11)' AS period,
    ROUND(AVG(buy_rate_pct), 2) AS avg_buy_rate_pct,
    ROUND(AVG(uv), 0) AS avg_uv,
    ROUND(AVG(1.0 * cart_cnt / NULLIF(pv_cnt, 0) * 100), 2) AS avg_cart_rate_pct
FROM hourly_behavior_summary
WHERE hour BETWEEN 6 AND 11
UNION ALL
SELECT
    '晚间(18-21)' AS period,
    ROUND(AVG(buy_rate_pct), 2) AS avg_buy_rate_pct,
    ROUND(AVG(uv), 0) AS avg_uv,
    ROUND(AVG(1.0 * cart_cnt / NULLIF(pv_cnt, 0) * 100), 2) AS avg_cart_rate_pct
FROM hourly_behavior_summary
WHERE hour BETWEEN 18 AND 21;
