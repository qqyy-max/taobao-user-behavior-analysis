-- ═══════════════════════════════════════════════════════════════
-- SQL Template: User Segment — 用户分层查询
-- 用途：规则分层规模、购买率对比、交叉分析
-- ═══════════════════════════════════════════════════════════════

-- 模板3-1: 5层规则分层汇总
SELECT
    segment_name,
    segment_priority,
    user_cnt,
    user_pct,
    buyer_rate_pct,
    avg_buy_cnt,
    avg_pv,
    avg_cart,
    avg_active_days,
    avg_category_diversity,
    cart_penetration_pct,
    fav_penetration_pct
FROM segment_summary
ORDER BY
    CASE segment_priority
        WHEN 'P0' THEN 1
        WHEN 'P1' THEN 2
        WHEN 'P2' THEN 3
        WHEN 'P3' THEN 4
        WHEN 'REF' THEN 5
    END;

-- 模板3-2: KMeans 聚类汇总（需 read_parquet）
SELECT
    cluster,
    persona_name,
    user_cnt,
    user_pct,
    buy_rate_pct,
    avg_pv,
    avg_active_days,
    category_diversity,
    cart_to_buy_rate
FROM read_parquet('data/mart/user_cluster_summary.parquet')
ORDER BY cluster;

-- 模板3-3: 行为频次分层（user_segment_summary）
SELECT
    freq_group,
    user_cnt,
    user_pct,
    avg_buy_per_user,
    buyer_rate_pct
FROM user_segment_summary
ORDER BY
    CASE freq_group
        WHEN '高频(≥1000)' THEN 1
        WHEN '中高频(500-999)' THEN 2
        WHEN '中频(100-499)' THEN 3
        WHEN '低频(50-99)' THEN 4
        WHEN '微频(10-49)' THEN 5
        WHEN '极低频(1-9)' THEN 6
    END;

-- 模板3-4: 规则分层 × KMeans 聚类交叉表
SELECT
    s.segment_name,
    s.segment_priority,
    cr.cluster,
    COUNT(*) AS user_cnt,
    ROUND(AVG(ubm.buy_cnt), 2) AS avg_buy_cnt,
    ROUND(AVG(ubm.pv_cnt), 1) AS avg_pv,
    ROUND(AVG(ubm.active_days), 1) AS avg_active_days
FROM read_parquet('data/mart/user_cluster_result.parquet') cr
JOIN user_base_metrics ubm ON cr.user_id = ubm.user_id
JOIN user_behavior_segment s ON cr.user_id = s.user_id
GROUP BY s.segment_name, s.segment_priority, cr.cluster
ORDER BY s.segment_priority, cr.cluster;

-- 模板3-5: P1(加购未购)用户按活跃天数分组
SELECT
    CASE
        WHEN active_days >= 7 THEN '高活跃(7-9天)'
        WHEN active_days >= 4 THEN '中活跃(4-6天)'
        ELSE '低活跃(1-3天)'
    END AS activity_level,
    COUNT(*) AS user_cnt,
    ROUND(AVG(pv_cnt), 1) AS avg_pv,
    ROUND(AVG(cart_cnt), 1) AS avg_cart
FROM user_behavior_segment
WHERE segment_name = 'cart_abandon_user'
GROUP BY activity_level
ORDER BY user_cnt DESC;
