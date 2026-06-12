-- ═══════════════════════════════════════════════════════════════
-- 10_agent_metric_views.sql — Agent 专用指标视图
-- =============================================
-- 用途：为 Agent (LLM) 创建简化的预聚合视图，避免 Agent 写复杂的
--       read_parquet + 多表 JOIN 查询。
-- 运行：由 run_all.py 在最后一步执行
-- ═══════════════════════════════════════════════════════════════

-- .print [10_agent_metric_views] Creating Agent metric views...

-- ════════════════════════════════════════════════════════
-- View 1: agent_user_cluster — 用户+聚类标签合并视图
-- 将独立 Parquet 文件中的 cluster 标签与 DB 中 user_base_metrics
-- 合并，Agent 无需写 read_parquet + JOIN
-- ════════════════════════════════════════════════════════

DROP VIEW IF EXISTS agent_user_cluster;
CREATE VIEW agent_user_cluster AS
SELECT
    cr.user_id,
    cr.cluster,
    cs.persona_name   AS cluster_name,
    cs.buy_rate_pct   AS cluster_avg_buy_rate,
    cs.avg_pv         AS cluster_avg_pv,
    cs.user_cnt       AS cluster_user_cnt,
    cs.priority       AS cluster_priority
FROM read_parquet('data/mart/user_cluster_result.parquet') cr
LEFT JOIN read_parquet('data/mart/user_cluster_summary.parquet') cs
    ON cr.cluster = cs.cluster;


-- ════════════════════════════════════════════════════════
-- View 2: agent_user_full_profile — 用户完整画像（一键查）
-- 合并：user_base_metrics + cluster标签 + 规则分层
-- Agent 回答"某群体特征"时直接 SELECT * WHERE
-- ════════════════════════════════════════════════════════

DROP VIEW IF EXISTS agent_user_full_profile;
CREATE VIEW agent_user_full_profile AS
SELECT
    ubm.user_id,
    ubm.pv_cnt,
    ubm.fav_cnt,
    ubm.cart_cnt,
    ubm.buy_cnt,
    ubm.active_days,
    ubm.is_buyer,
    ubm.has_cart,
    ubm.has_fav,
    -- 行为维度购买率
    ROUND(100.0 * ubm.buy_cnt / NULLIF(ubm.total_actions, 0), 2) AS behavior_buy_rate_pct,
    -- 用户维度特征
    ubm.lifecycle_days      AS window_active_span,
    auc.cluster,
    auc.cluster_name,
    auc.cluster_priority,
    seg.segment_name,
    seg.segment_priority
FROM user_base_metrics ubm
LEFT JOIN agent_user_cluster auc ON ubm.user_id = auc.user_id
LEFT JOIN user_behavior_segment seg ON ubm.user_id = seg.user_id;


-- ════════════════════════════════════════════════════════
-- View 3: agent_daily_trend — 日度趋势（含周末标记）
-- Agent 回答"日度趋势"时直接 SELECT * ORDER BY dt
-- ════════════════════════════════════════════════════════

DROP VIEW IF EXISTS agent_daily_trend;
CREATE VIEW agent_daily_trend AS
SELECT
    dbs.dt,
    dd.is_weekend,
    CASE WHEN dd.is_weekend = 1 THEN '周末' ELSE '工作日' END AS day_type,
    dd.weekday,
    dbs.dau,
    dbs.total_actions,
    dbs.pv_cnt,
    dbs.fav_cnt,
    dbs.cart_cnt,
    dbs.buy_cnt,
    dbs.buy_rate_pct,
    dbs.cart_rate_pct,
    dbs.fav_rate_pct,
    dbs.avg_actions_per_user
FROM daily_behavior_summary dbs
JOIN dim_date dd ON dbs.dt = dd.dt
ORDER BY dbs.dt;


-- ════════════════════════════════════════════════════════
-- View 4: agent_hourly_efficiency — 24h购买效率（含时段标签）
-- Agent 回答"时段分析"时直接查询
-- ════════════════════════════════════════════════════════

DROP VIEW IF EXISTS agent_hourly_efficiency;
CREATE VIEW agent_hourly_efficiency AS
SELECT
    hour,
    actions,
    pv_cnt,
    fav_cnt,
    cart_cnt,
    buy_cnt,
    buy_rate_pct,
    uv,
    ROUND(1.0 * actions / NULLIF(uv, 0), 1) AS avg_actions_per_user,
    ROUND(1.0 * cart_cnt / NULLIF(pv_cnt, 0) * 100, 2) AS cart_rate_pct,
    CASE
        WHEN hour BETWEEN 6 AND 11 THEN '上午(6-11)'
        WHEN hour BETWEEN 12 AND 17 THEN '下午(12-17)'
        WHEN hour BETWEEN 18 AND 21 THEN '晚间(18-21)'
        ELSE '深夜(22-5)'
    END AS time_slot,
    RANK() OVER (ORDER BY actions DESC)      AS traffic_rank,
    RANK() OVER (ORDER BY buy_rate_pct DESC) AS conversion_rank
FROM hourly_behavior_summary
ORDER BY hour;


-- ════════════════════════════════════════════════════════
-- View 5: agent_segment_overview — 分层概览（含中文描述）
-- Agent 回答"分层规模"时直接查询
-- ════════════════════════════════════════════════════════

DROP VIEW IF EXISTS agent_segment_overview;
CREATE VIEW agent_segment_overview AS
SELECT
    segment_name,
    segment_priority,
    CASE segment_name
        WHEN 'window_repeat_buyer'         THEN 'P0-窗口内重复购买用户'
        WHEN 'cart_abandon_user'           THEN 'P1-加购未购买用户'
        WHEN 'high_browse_weak_buy_signal' THEN 'P2-高浏览弱购买信号用户'
        WHEN 'low_active_no_purchase'      THEN 'P3-低活跃未购买用户'
        WHEN 'single_purchase_user'        THEN 'REF-单次购买用户(参照组)'
    END AS segment_label,
    user_cnt,
    user_pct,
    buyer_rate_pct,
    avg_buy_cnt,
    avg_pv,
    avg_cart,
    avg_active_days,
    avg_category_diversity,
    cart_penetration_pct,
    fav_penetration_pct,
    avg_behavior_buy_rate
FROM segment_summary
ORDER BY
    CASE segment_priority
        WHEN 'P0'  THEN 1
        WHEN 'P1'  THEN 2
        WHEN 'P2'  THEN 3
        WHEN 'P3'  THEN 4
        WHEN 'REF' THEN 5
    END;


-- ════════════════════════════════════════════════════════
-- View 6: agent_cart_abandon_overview — 加购未购简化汇总
-- Agent 回答"加购未购"问题时一站式查询
-- ════════════════════════════════════════════════════════

DROP VIEW IF EXISTS agent_cart_abandon_overview;
CREATE VIEW agent_cart_abandon_overview AS
SELECT
    total_cart_abandon_users   AS abandon_user_cnt,
    avg_cart_items             AS avg_items_per_user,
    avg_cart_categories        AS avg_categories_per_user,
    avg_daily_pv,
    avg_active_days,
    last_cart_within_1d        AS recent_cart_1d,
    last_cart_within_3d        AS recent_cart_3d,
    pct_last_cart_1d,
    pct_last_cart_3d,
    avg_cart_to_pv_rate,
    -- 占加购用户比例
    ROUND(100.0 * total_cart_abandon_users / (
        SELECT COUNT(*) FROM user_base_metrics WHERE has_cart = 1
    ), 1)                   AS abandon_rate_pct,
    -- 占全量用户比例
    ROUND(100.0 * total_cart_abandon_users / (
        SELECT COUNT(*) FROM user_base_metrics
    ), 1)                   AS total_user_pct
FROM cart_abandon_summary;


-- ════════════════════════════════════════════════════════
-- View 7: agent_product_health — 商品健康度一览
-- 合并高曝光低转化 + 搜索直达 + 全局效率
-- ════════════════════════════════════════════════════════

DROP VIEW IF EXISTS agent_product_health;
CREATE VIEW agent_product_health AS
SELECT
    total_items,
    helc_item_cnt,
    helc_category_cnt,
    helc_category_pct,
    ROUND(100.0 * helc_item_cnt / NULLIF(total_items, 0), 2) AS helc_item_pct,
    exposed_zero_buy_items,
    ROUND(100.0 * exposed_zero_buy_items / NULLIF(total_items, 0), 2) AS exposed_zero_buy_pct,
    underexposed_gem_cnt,
    search_direct_items,
    avg_pv_helc,
    avg_buy_gems
FROM product_efficiency_anomaly_summary;


-- ════════════════════════════════════════════════════════
-- View 8: agent_weekend_workday_comparison — 周末vs工作日
-- 预聚合的周末/工作日对比（Agent 最常查询的对比之一）
-- ════════════════════════════════════════════════════════

DROP VIEW IF EXISTS agent_weekend_workday_comparison;
CREATE VIEW agent_weekend_workday_comparison AS
SELECT
    dd.is_weekend,
    CASE WHEN dd.is_weekend = 1 THEN '周末' ELSE '工作日' END AS day_type,
    ROUND(AVG(dbs.dau), 0)                     AS avg_dau,
    ROUND(AVG(dbs.buy_rate_pct), 2)            AS avg_buy_rate_pct,
    ROUND(AVG(dbs.cart_rate_pct), 2)           AS avg_cart_rate_pct,
    ROUND(AVG(dbs.fav_rate_pct), 2)            AS avg_fav_rate_pct,
    ROUND(AVG(dbs.avg_actions_per_user), 1)    AS avg_actions_per_user,
    ROUND(AVG(1.0 * dbs.cart_cnt / NULLIF(dbs.buy_cnt, 0)), 1) AS avg_cart_per_buy,
    SUM(dbs.total_actions)                     AS total_actions,
    SUM(dbs.buy_cnt)                           AS total_buy_cnt,
    COUNT(DISTINCT dbs.dt)                     AS day_cnt
FROM daily_behavior_summary dbs
JOIN dim_date dd ON dbs.dt = dd.dt
GROUP BY dd.is_weekend;


-- ════════════════════════════════════════════════════════
-- 输出视图清单
-- ════════════════════════════════════════════════════════

-- .print Agent metric views created:
-- .print   agent_user_cluster             — 用户+聚类标签(287,004行)
-- .print   agent_user_full_profile        — 用户完整画像(287,004行)
-- .print   agent_daily_trend              — 日度趋势(9行)
-- .print   agent_hourly_efficiency        — 24h购买效率(24行)
-- .print   agent_segment_overview         — 分层概览(5行)
-- .print   agent_cart_abandon_overview    — 加购未购概览(1行)
-- .print   agent_product_health           — 商品健康度(1行)
-- .print   agent_weekend_workday_comparison — 周末vs工作日(2行)
