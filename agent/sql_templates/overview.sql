-- ═══════════════════════════════════════════════════════════════
-- SQL Template: Overview — 概览指标查询
-- 用途：全局KPI快速查询，Agent回答"当前经营数据"时使用
-- ═══════════════════════════════════════════════════════════════

-- 模板1-1: 全局核心KPI
SELECT
    (SELECT value FROM profiling_summary WHERE metric_cn = '总用户数') AS total_users,
    (SELECT value FROM profiling_summary WHERE metric_cn = '总行为数') AS total_actions;

-- 模板1-2: 用户转化汇总
SELECT
    total_users,
    pv_users,
    fav_users,
    cart_users,
    buy_users,
    fav_rate_pct,
    cart_rate_pct,
    buy_rate_pct
FROM user_conversion_summary;

-- 模板1-3: 加购未购用户全局统计
SELECT
    total_users,
    avg_cart_items,
    avg_cart_categories,
    avg_daily_pv,
    avg_active_days,
    recent_cart_1d,
    recent_cart_3d,
    ROUND(100.0 * total_users / (SELECT buy_users FROM user_conversion_summary), 1) AS abandon_vs_buyer_pct
FROM cart_abandon_summary;

-- 模板1-4: 商品效率全局汇总
SELECT
    helc_item_cnt,
    helc_item_pct,
    underexposed_gem_cnt,
    underexposed_gem_pct,
    avg_helc_pv,
    avg_gem_buy_cnt
FROM product_efficiency_anomaly_summary;

-- 模板1-5: 日度趋势概览（最近3天 + 整体均值）
SELECT
    dt,
    dau,
    total_actions,
    buy_cnt,
    buy_rate_pct,
    avg_actions_per_user
FROM daily_behavior_summary
ORDER BY dt;
