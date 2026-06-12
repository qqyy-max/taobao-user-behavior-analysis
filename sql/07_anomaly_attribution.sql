-- ============================================================
-- 07_anomaly_attribution.sql — 异动归因专题
-- ============================================================
-- 职责：针对 3 个已知异动现象，构建"现象→拆解维度→原因假设→
--       策略建议→验证方案"的分析数据表。
-- 输出表：
--   专题 1 周末流量高但购买信号弱：
--     weekend_anomaly_summary   — 周末 vs 工作日核心指标对比
--     weekend_behavior_mix       — 周末 vs 工作日行为类型结构拆解
--   专题 2 夜间流量高但上午购买信号更强：
--     hourly_anomaly_summary     — 各时段购买效率与流量对比
--     morning_evening_comparison — 上午(9-11) vs 晚间(20-22) 深度对比
--   专题 3 高曝光商品不转化：
--     high_exposure_low_conversion_category — 按类目的高曝光低转化商品分布
--     product_efficiency_anomaly_summary    — 商品效率异动汇总
--
-- 依赖：
--   03_behavior_analysis.sql (daily_behavior_summary,
--     hourly_behavior_summary, weekday_behavior_summary)
--   04_product_analysis.sql (item_conversion, category_conversion,
--     high_exposure_low_conversion_items)
--
-- ★ 核心前提：
--   异动归因 = 识别现象 → 维度拆解 → 原因假设 → 策略方向。
--   SQL 提供数据支撑，文档（docs/anomaly_attribution.md）负责解释。
--   9 天窗口限制：样本量有限（3 个周末日 vs 6 个工作日），
--   统计检验效力受限，结论应表述为"假设"和"方向"，非确定性归因。
-- ============================================================


-- ============================================================
-- Part 1: 周末流量高但购买信号弱
-- ============================================================
-- 现象：周末 DAU 高于工作日，但行为级购买占比低于工作日。
-- 拆解：人均行为数、行为类型结构（PV/FAV/CART/BUY占比）、
--       用户构成差异。

-- 1a. weekend_anomaly_summary — 周末 vs 工作日核心指标对比
DROP TABLE IF EXISTS weekend_anomaly_summary;
CREATE TABLE weekend_anomaly_summary AS
SELECT
    dw.is_weekend,
    CASE WHEN dw.is_weekend = 1 THEN '周末' ELSE '工作日' END AS day_type,
    COUNT(DISTINCT dw.dt)                                      AS day_cnt,
    -- 流量指标
    ROUND(AVG(dbs.dau), 0)                                     AS avg_dau,
    ROUND(AVG(dbs.total_actions), 0)                           AS avg_actions,
    ROUND(AVG(dbs.avg_actions_per_user), 1)                    AS avg_actions_per_user,
    -- 购买指标
    ROUND(AVG(dbs.buy_cnt), 0)                                 AS avg_buy_cnt,
    ROUND(AVG(dbs.buy_rate_pct), 2)                            AS avg_buy_rate_pct,
    -- 中间行为指标
    ROUND(AVG(dbs.cart_rate_pct), 2)                           AS avg_cart_rate_pct,
    ROUND(AVG(dbs.fav_rate_pct), 2)                            AS avg_fav_rate_pct,
    -- 加购到购买效率（行为维度）
    ROUND(AVG(1.0 * dbs.buy_cnt / NULLIF(dbs.total_actions, 0)) * 100, 2) AS avg_action_buy_rate
FROM dim_date dw
JOIN daily_behavior_summary dbs ON dw.dt = dbs.dt
GROUP BY dw.is_weekend
ORDER BY dw.is_weekend;

-- 1b. weekend_behavior_mix — 周末 vs 工作日行为结构拆解
DROP TABLE IF EXISTS weekend_behavior_mix;
CREATE TABLE weekend_behavior_mix AS
WITH mix_base AS (
    SELECT
        CASE WHEN dw.is_weekend = 1 THEN '周末' ELSE '工作日' END AS day_type,
        'PV'   AS behavior_type, ROUND(AVG(dbs.pv_cnt), 0)   AS avg_cnt, 1 AS sort_order FROM daily_behavior_summary dbs JOIN dim_date dw ON dbs.dt = dw.dt GROUP BY dw.is_weekend
        UNION ALL
    SELECT CASE WHEN dw.is_weekend = 1 THEN '周末' ELSE '工作日' END, 'FAV',  ROUND(AVG(dbs.fav_cnt), 0),  2 FROM daily_behavior_summary dbs JOIN dim_date dw ON dbs.dt = dw.dt GROUP BY dw.is_weekend
        UNION ALL
    SELECT CASE WHEN dw.is_weekend = 1 THEN '周末' ELSE '工作日' END, 'CART', ROUND(AVG(dbs.cart_cnt), 0), 3 FROM daily_behavior_summary dbs JOIN dim_date dw ON dbs.dt = dw.dt GROUP BY dw.is_weekend
        UNION ALL
    SELECT CASE WHEN dw.is_weekend = 1 THEN '周末' ELSE '工作日' END, 'BUY',  ROUND(AVG(dbs.buy_cnt), 0),  4 FROM daily_behavior_summary dbs JOIN dim_date dw ON dbs.dt = dw.dt GROUP BY dw.is_weekend
)
SELECT day_type, behavior_type, avg_cnt
FROM mix_base
ORDER BY day_type, sort_order;


-- ============================================================
-- Part 2: 夜间流量高但上午购买信号更强
-- ============================================================
-- 现象：21:00 流量峰值但购买率仅 1.73%，10:00 购买率峰值 2.62%。
-- 拆解：各时段 UV、行为数、购买率、加购率、人均行为数差异。
--      上午(9-11) vs 晚间(20-22) 深度对比。

-- 2a. hourly_anomaly_summary — 各时段购买效率与流量对比
DROP TABLE IF EXISTS hourly_anomaly_summary;
CREATE TABLE hourly_anomaly_summary AS
SELECT
    hour,
    actions,
    uv,
    buy_cnt,
    buy_rate_pct,
    -- 时段标签
    CASE
        WHEN hour BETWEEN 6 AND 11  THEN '上午(6-11)'
        WHEN hour BETWEEN 12 AND 17 THEN '下午(12-17)'
        WHEN hour BETWEEN 18 AND 21 THEN '晚间(18-21)'
        ELSE '深夜(22-5)'
    END AS time_slot,
    -- 人均行为数
    ROUND(1.0 * actions / NULLIF(uv, 0), 1)                       AS avg_actions_per_user,
    -- 各行为数量（行为结构拆解）
    pv_cnt,
    cart_cnt,
    fav_cnt,
    buy_cnt AS buy_cnt_detail,
    -- 加购率
    ROUND(100.0 * cart_cnt / NULLIF(pv_cnt, 0), 2)                AS cart_to_pv_rate
FROM hourly_behavior_summary
ORDER BY hour;

-- 2b. morning_evening_comparison — 上午 vs 晚间深度对比
DROP TABLE IF EXISTS morning_evening_comparison;
CREATE TABLE morning_evening_comparison AS
WITH morning AS (
    SELECT
        '上午(9-11)' AS period,
        SUM(actions)  AS total_actions,
        SUM(uv)       AS total_uv,
        SUM(buy_cnt)  AS total_buy,
        SUM(pv_cnt)   AS total_pv,
        SUM(cart_cnt) AS total_cart,
        SUM(fav_cnt)  AS total_fav
    FROM hourly_behavior_summary WHERE hour BETWEEN 9 AND 11
),
evening AS (
    SELECT
        '晚间(20-22)' AS period,
        SUM(actions)  AS total_actions,
        SUM(uv)       AS total_uv,
        SUM(buy_cnt)  AS total_buy,
        SUM(pv_cnt)   AS total_pv,
        SUM(cart_cnt) AS total_cart,
        SUM(fav_cnt)  AS total_fav
    FROM hourly_behavior_summary WHERE hour BETWEEN 20 AND 22
)
SELECT
    period,
    total_actions,
    total_uv,
    total_buy,
    total_pv,
    total_cart,
    total_fav,
    ROUND(100.0 * total_buy / NULLIF(total_actions, 0), 2)  AS buy_rate_pct,
    ROUND(100.0 * total_cart / NULLIF(total_pv, 0), 2)     AS cart_to_pv_rate,
    ROUND(1.0 * total_actions / NULLIF(total_uv, 0), 1)    AS avg_actions_per_user
FROM morning
UNION ALL
SELECT
    period,
    total_actions,
    total_uv,
    total_buy,
    total_pv,
    total_cart,
    total_fav,
    ROUND(100.0 * total_buy / NULLIF(total_actions, 0), 2),
    ROUND(100.0 * total_cart / NULLIF(total_pv, 0), 2),
    ROUND(1.0 * total_actions / NULLIF(total_uv, 0), 1)
FROM evening
ORDER BY period;


-- ============================================================
-- Part 3: 高曝光商品不转化
-- ============================================================
-- 现象：51.3 万件商品 PV ≥ P75 但购买率为 0%。
-- 拆解：按类目汇聚高曝光低转化商品分布，识别问题类目。
--       同时识别低曝光但高购买信号的商品（搜索直达型互补分析）。

-- 3a. high_exposure_low_conversion_category — 按类目分布
DROP TABLE IF EXISTS high_exposure_low_conversion_category;
CREATE TABLE high_exposure_low_conversion_category AS
SELECT
    helc.category_id,
    COUNT(*)                                              AS problem_item_cnt,
    ROUND(AVG(helc.pv_cnt), 1)                            AS avg_pv,
    ROUND(AVG(helc.cart_cnt), 1)                          AS avg_cart,
    ROUND(AVG(helc.cart_rate_pct), 2)                     AS avg_cart_rate_pct,
    -- 关联类目曝光排名
    MAX(cc.exposure_rank)                                 AS category_exposure_rank,
    MAX(cc.conversion_rank)                               AS category_conversion_rank,
    MAX(cc.buy_rate_pct)                                  AS category_buy_rate_pct
FROM high_exposure_low_conversion_items helc
LEFT JOIN category_conversion cc ON helc.category_id = cc.category_id
GROUP BY helc.category_id
ORDER BY problem_item_cnt DESC;

-- 3b. product_efficiency_anomaly_summary — 商品效率异动汇总
DROP TABLE IF EXISTS product_efficiency_anomaly_summary;
CREATE TABLE product_efficiency_anomaly_summary AS
WITH
-- 全量商品统计
total_stats AS (
    SELECT
        COUNT(*)                                          AS total_items,
        SUM(CASE WHEN buy_cnt = 0 THEN 1 ELSE 0 END)      AS zero_buy_items,
        SUM(CASE WHEN pv_cnt > 0 AND buy_cnt = 0 THEN 1 ELSE 0 END) AS exposed_zero_buy_items,
        SUM(CASE WHEN buy_cnt > 0 AND pv_cnt = 0 THEN 1 ELSE 0 END) AS search_direct_items
    FROM item_conversion
),
-- 高曝光低转化商品统计
helc_stats AS (
    SELECT
        COUNT(*)                                          AS helc_item_cnt,
        ROUND(AVG(pv_cnt), 1)                             AS avg_pv_helc,
        COUNT(DISTINCT category_id)                       AS helc_category_cnt
    FROM high_exposure_low_conversion_items
),
-- 低曝光高购买信号商品（PV 较低但有购买且购买率较高）
-- ★ 注意：数据显示所有有购买的商品 PV ≥ 5（P25 among items with buy>0）。
--    因此 "PV < P25 且有购买" 的条件在当前数据下返回 0——这是一个
--    有效的数据特征发现：购买行为在极低曝光商品中几乎不存在。
--    使用替代定义：PV < P50 且 buy_rate > P75 的商品。
low_exp_high_buy AS (
    SELECT
        COUNT(*)                                          AS underexposed_gem_cnt,
        ROUND(AVG(buy_cnt), 1)                            AS avg_buy_gems,
        ROUND(AVG(buy_rate_pct), 2)                       AS avg_buy_rate_gems
    FROM item_conversion
    WHERE pv_cnt > 0
      AND pv_cnt < (SELECT APPROX_QUANTILE(pv_cnt, 0.50) FROM item_conversion WHERE pv_cnt > 0)
      AND buy_cnt > 0
      AND buy_rate_pct > (SELECT APPROX_QUANTILE(buy_rate_pct, 0.75) FROM item_conversion WHERE pv_cnt > 0 AND buy_cnt > 0)
)
SELECT
    ts.total_items,
    ts.zero_buy_items,
    ROUND(100.0 * ts.zero_buy_items / NULLIF(ts.total_items, 0), 2)  AS zero_buy_pct,
    ts.exposed_zero_buy_items,
    ts.search_direct_items,
    hs.helc_item_cnt,
    hs.avg_pv_helc,
    hs.helc_category_cnt,
    ROUND(100.0 * hs.helc_category_cnt / 8787.0, 2)                  AS helc_category_pct,
    lh.underexposed_gem_cnt,
    lh.avg_buy_gems
FROM total_stats ts
CROSS JOIN helc_stats hs
CROSS JOIN low_exp_high_buy lh;


-- ============================================================
-- 验证输出
-- ============================================================
SELECT '=== 07_anomaly_attribution 执行完成 ===' AS status;

SELECT 'weekend_anomaly_summary'             AS tbl, COUNT(*) AS rows FROM weekend_anomaly_summary
UNION ALL SELECT 'weekend_behavior_mix',              COUNT(*) FROM weekend_behavior_mix
UNION ALL SELECT 'hourly_anomaly_summary',            COUNT(*) FROM hourly_anomaly_summary
UNION ALL SELECT 'morning_evening_comparison',        COUNT(*) FROM morning_evening_comparison
UNION ALL SELECT 'high_exposure_low_conversion_category', COUNT(*) FROM high_exposure_low_conversion_category
UNION ALL SELECT 'product_efficiency_anomaly_summary',   COUNT(*) FROM product_efficiency_anomaly_summary;

-- 周末 vs 工作日对比
SELECT '--- 周末 vs 工作日异常 ---' AS info;
SELECT * FROM weekend_anomaly_summary;

-- 上午 vs 晚间对比
SELECT '--- 上午(9-11) vs 晚间(20-22) ---' AS info;
SELECT * FROM morning_evening_comparison;

-- 商品效率异常汇总
SELECT '--- 商品效率异常汇总 ---' AS info;
SELECT * FROM product_efficiency_anomaly_summary;

-- 高曝光低转化商品 Top 5 类目
SELECT '--- 问题商品最多的 Top 5 类目 ---' AS info;
SELECT
    category_id,
    problem_item_cnt,
    avg_pv,
    avg_cart_rate_pct,
    category_exposure_rank,
    category_buy_rate_pct
FROM high_exposure_low_conversion_category
ORDER BY problem_item_cnt DESC
LIMIT 5;
