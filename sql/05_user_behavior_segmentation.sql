-- ============================================================
-- 05_user_behavior_segmentation.sql — 窗口内用户行为规则分层
-- ============================================================
-- 职责：基于 9 天窗口内行为特征，用可解释的业务规则将用户分为
--       5 个群组。分层命名与数据的实际购买率严格一致。
-- 输出表：
--   user_behavior_segment   — 用户维度分层结果（每用户一个主分层）
--   segment_summary         — 分层汇总（规模、购买信号、活跃特征）
--   segment_action_matrix   — 分层对应运营动作与注意事项
-- 依赖：
--   00_init.sql（user_base_metrics）
--   05_user_analysis.sql（user_profile — 提供 category_diversity）
--
-- ★ 核心前提：
--   1. 仅 9 天观察窗口。不使用"生命周期""流失用户""忠诚用户""LTV"等表述。
--   2. KMeans 为探索性验证（src/user_clustering.py），本规则分层为主分层。
--   3. 每用户归入唯一主分层，按优先级从高到低 CASE 匹配。
--   4. P75 分位数阈值在 SQL 中动态计算（APPROX_QUANTILE），不硬编码。
--   5. 分层名称必须与 segment_summary 中的 buyer_rate 一致：
--      购买率=0 的层不命名为包含购买含义的名称，
--      购买率=100% 的层不命名为"潜力"或"可能"。
-- ============================================================


-- ============================================================
-- 0. 动态阈值
-- ============================================================
DROP TABLE IF EXISTS _seg_thresholds;
CREATE TABLE _seg_thresholds AS
SELECT
    APPROX_QUANTILE(pv_cnt, 0.75) AS pv_p75
FROM user_base_metrics;


-- ============================================================
-- 1. user_behavior_segment — 用户维度分层结果
-- ============================================================
-- 优先级规则（高→低，首次匹配即归入）：
--   1. buy_cnt >= 2                                  → window_repeat_buyer
--   2. has_cart=1 AND is_buyer=0                     → cart_abandon_user
--   3. pv_cnt >= P75 AND is_buyer=0                  → high_browse_weak_buy_signal
--      ★ 严格限制 is_buyer=0——本层仅含未购买用户。
--   4. is_buyer=0                                    → low_active_no_purchase
--   5. 其余（buy_cnt=1 的购买用户）                    → single_purchase_user
--
-- ★ single_purchase_user 仅作为参照组（REF），不作为重点运营对象。
--   运营重心在 P1（cart_abandon_user）和 P2（high_browse_weak_buy_signal）。
DROP TABLE IF EXISTS user_behavior_segment;
CREATE TABLE user_behavior_segment AS
WITH thresholds AS (
    SELECT pv_p75 FROM _seg_thresholds
),
user_ext AS (
    SELECT
        m.*,
        ROUND(100.0 * m.buy_cnt / NULLIF(m.total_actions, 0), 2) AS buy_rate_pct,
        ROUND(1.0 * m.pv_cnt / NULLIF(m.active_days, 0), 1)      AS avg_daily_pv
    FROM user_base_metrics m
)
SELECT
    e.user_id,
    e.pv_cnt,
    e.cart_cnt,
    e.buy_cnt,
    e.fav_cnt,
    e.total_actions,
    e.active_days,
    e.lifecycle_days,
    e.is_buyer,
    e.has_cart,
    e.has_fav,
    e.buy_rate_pct,
    e.avg_daily_pv,
    -- 分层判定（5 类，每用户唯一归属）
    CASE
        WHEN e.buy_cnt >= 2
            THEN 'window_repeat_buyer'
        WHEN e.has_cart = 1 AND e.is_buyer = 0
            THEN 'cart_abandon_user'
        WHEN e.pv_cnt >= (SELECT pv_p75 FROM thresholds)
         AND e.is_buyer = 0
            THEN 'high_browse_weak_buy_signal'
        WHEN e.is_buyer = 0
            THEN 'low_active_no_purchase'
        ELSE 'single_purchase_user'
    END AS segment_name,
    -- 运营优先级
    CASE
        WHEN e.buy_cnt >= 2 THEN 'P0'
        WHEN e.has_cart = 1 AND e.is_buyer = 0 THEN 'P1'
        WHEN e.pv_cnt >= (SELECT pv_p75 FROM thresholds)
         AND e.is_buyer = 0 THEN 'P2'
        WHEN e.is_buyer = 0 THEN 'P3'
        ELSE 'REF'
    END AS segment_priority,
    -- 分层理由
    CASE
        WHEN e.buy_cnt >= 2
            THEN '9 天窗口内购买 ≥2 次，仅表示窗口内重复购买行为，不推断长期忠诚'
        WHEN e.has_cart = 1 AND e.is_buyer = 0
            THEN '有加购但窗口内无购买。可能延迟购买/跨平台购买/加购作为收藏替代，不推断"放弃"'
        WHEN e.pv_cnt >= (SELECT pv_p75 FROM thresholds)
         AND e.is_buyer = 0
            THEN '浏览深度高（PV≥P75）但窗口内无购买，购买信号弱'
        WHEN e.is_buyer = 0
            THEN '窗口内无购买行为，且不满足以上任一规则。可能是后期新用户或自然流量'
        ELSE '窗口内购买 1 次。作为单次购买参照组，不作为重点运营对象'
    END AS segment_reason
FROM user_ext e;


-- ============================================================
-- 2. segment_summary — 分层汇总
-- ============================================================
DROP TABLE IF EXISTS segment_summary;
CREATE TABLE segment_summary AS
WITH user_diversity AS (
    SELECT user_id, category_diversity FROM user_profile
)
SELECT
    s.segment_name,
    s.segment_priority,
    COUNT(*)                                                       AS user_cnt,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 2)              AS user_pct,
    -- 购买指标（用于验证分层命名是否与数据一致）
    ROUND(100.0 * AVG(s.is_buyer), 1)                              AS buyer_rate_pct,
    ROUND(AVG(s.buy_cnt), 2)                                       AS avg_buy_cnt,
    SUM(s.buy_cnt)                                                 AS total_buy_cnt,
    -- 行为活跃度
    ROUND(AVG(s.pv_cnt), 1)                                        AS avg_pv,
    ROUND(AVG(s.cart_cnt), 1)                                      AS avg_cart,
    ROUND(AVG(s.fav_cnt), 1)                                       AS avg_fav,
    ROUND(AVG(s.total_actions), 1)                                 AS avg_actions,
    ROUND(AVG(s.active_days), 1)                                   AS avg_active_days,
    ROUND(AVG(s.buy_rate_pct), 2)                                  AS avg_behavior_buy_rate,
    ROUND(AVG(s.avg_daily_pv), 1)                                  AS avg_daily_pv,
    -- 类目广度
    ROUND(AVG(COALESCE(d.category_diversity, 0)), 1)               AS avg_category_diversity,
    -- 行为覆盖率
    ROUND(100.0 * AVG(s.has_cart), 1)                              AS cart_penetration_pct,
    ROUND(100.0 * AVG(s.has_fav), 1)                               AS fav_penetration_pct
FROM user_behavior_segment s
LEFT JOIN user_diversity d ON s.user_id = d.user_id
GROUP BY s.segment_name, s.segment_priority
ORDER BY
    CASE s.segment_priority
        WHEN 'P0' THEN 1 WHEN 'P1' THEN 2 WHEN 'P2' THEN 3
        WHEN 'P3' THEN 4 WHEN 'REF' THEN 5
    END;


-- ============================================================
-- 3. segment_action_matrix — 分层运营动作与注意事项
-- ============================================================
DROP TABLE IF EXISTS segment_action_matrix;
CREATE TABLE segment_action_matrix AS
SELECT
    segment_name,
    segment_priority,
    CASE segment_name
        WHEN 'window_repeat_buyer'
            THEN '维护：常购清单、关联品类推荐、会员权益标记。购买后 24h 推送关联商品。'
                 || '★ 9 天窗口内重复购买 ≠ 长期忠诚。过度推送可能引起反感。'
        WHEN 'cart_abandon_user'
            THEN '转化：加购后 24-48h 推送限时折扣/降价提醒。优先触达最近加购用户。'
                 || '★ 用户可能已在其他平台购买或延迟购买。不表述为"购物车放弃"。'
        WHEN 'high_browse_weak_buy_signal'
            THEN '引导：首单无门槛券、品类收窄推荐（聚焦 Top 5 类目）。浏览峰值时段触达。'
                 || '★ 本层用户 is_buyer=0，严格无购买。可能是跨平台比价或纯浏览用户。不表述为"流失风险"。'
        WHEN 'low_active_no_purchase'
            THEN '轻触达：站内消息/Push 引导回访。注册后 24h 首次触达。'
                 || '★ 窗口后期新用户可能仅出现 1-2 天，不表述为"沉默"。'
        WHEN 'single_purchase_user'
            THEN '参照组，不作为重点运营对象。可用于与 cart_abandon_user 做对比分析。'
                 || '★ 1 次购买可能是偶发行为，不推断"可培养的忠诚用户"。'
    END AS recommended_action,
    CASE segment_name
        WHEN 'window_repeat_buyer'            THEN '购买后 24h'
        WHEN 'cart_abandon_user'              THEN '加购后 24-48h'
        WHEN 'high_browse_weak_buy_signal'    THEN '浏览峰值时段'
        WHEN 'low_active_no_purchase'         THEN '首日活跃后 24h'
        WHEN 'single_purchase_user'           THEN '—（参照组，不主动运营）'
    END AS recommended_timing,
    CASE segment_name
        WHEN 'window_repeat_buyer'            THEN '窗口内人均购买次数'
        WHEN 'cart_abandon_user'              THEN '加购到购买转化信号率'
        WHEN 'high_browse_weak_buy_signal'    THEN '首购率'
        WHEN 'low_active_no_purchase'         THEN '回访率'
        WHEN 'single_purchase_user'           THEN '窗口内第二次购买率（参照）'
    END AS monitor_kpi,
    CASE segment_name
        WHEN 'window_repeat_buyer'
            THEN '① 不推断长期忠诚 ② "窗口内重复购买"≠ 长期复购 ③ 9 天窗口限制'
        WHEN 'cart_abandon_user'
            THEN '① 不用"购物车放弃率"② 不用"流失"③ 标注窗口限制④ 可能延迟/跨平台购买'
        WHEN 'high_browse_weak_buy_signal'
            THEN '① 不推断"流失风险"② 弱购买信号 ≠ 无购买意愿③ 可能为比价用户'
        WHEN 'low_active_no_purchase'
            THEN '① 不推断"沉默"或"流失"② 窗口后期新用户在此层③ 9 天行为不完整'
        WHEN 'single_purchase_user'
            THEN '① 参照组，非运营重点② 偶发购买 ≠ 长期价值③ 不推断可培养的忠诚用户'
    END AS terminology_guardrail
FROM segment_summary
ORDER BY
    CASE segment_priority
        WHEN 'P0' THEN 1 WHEN 'P1' THEN 2 WHEN 'P2' THEN 3
        WHEN 'P3' THEN 4 WHEN 'REF' THEN 5
    END;


-- ============================================================
-- 清理
-- ============================================================
DROP TABLE IF EXISTS _seg_thresholds;


-- ============================================================
-- 验证输出
-- ============================================================
SELECT '=== 05_user_behavior_segmentation 执行完成 ===' AS status;

SELECT 'user_behavior_segment' AS tbl, COUNT(*) AS rows FROM user_behavior_segment
UNION ALL SELECT 'segment_summary', COUNT(*) FROM segment_summary
UNION ALL SELECT 'segment_action_matrix', COUNT(*) FROM segment_action_matrix;

-- 分层概览（含 buyer_rate —— 用于验证命名与数据一致性）
SELECT '--- 分层概览（验证 buyer_rate 与 segment_name 一致性）---' AS info;
SELECT
    segment_name,
    segment_priority,
    user_cnt,
    user_pct,
    buyer_rate_pct,
    avg_buy_cnt,
    avg_pv,
    avg_active_days,
    avg_category_diversity,
    cart_penetration_pct,
    fav_penetration_pct
FROM segment_summary
ORDER BY
    CASE segment_priority
        WHEN 'P0' THEN 1 WHEN 'P1' THEN 2 WHEN 'P2' THEN 3
        WHEN 'P3' THEN 4 WHEN 'REF' THEN 5
    END;

-- 命名一致性检查
SELECT '--- 命名一致性检查 ---' AS info;
SELECT
    segment_name,
    buyer_rate_pct,
    CASE
        WHEN segment_name LIKE '%nonbuyer%' AND buyer_rate_pct > 0
            THEN '⚠️ 命名含 nonbuyer 但购买率 > 0'
        WHEN segment_name LIKE '%no_purchase%' AND buyer_rate_pct > 0
            THEN '⚠️ 命名含 no_purchase 但购买率 > 0'
        WHEN segment_name LIKE '%repeat_buyer%' AND buyer_rate_pct < 100
            THEN '⚠️ 命名含 buyer 但购买率 < 100%'
        WHEN segment_name LIKE '%weak_buy%' AND buyer_rate_pct > 50
            THEN '⚠️ 命名含 weak 但购买率 > 50%'
        ELSE '[OK] 命名与数据一致'
    END AS naming_audit
FROM segment_summary;

-- 分段覆盖验证
SELECT '--- 分段覆盖验证（应 = 287,004）---' AS info;
SELECT SUM(user_cnt) AS total_segmented_users FROM segment_summary;
