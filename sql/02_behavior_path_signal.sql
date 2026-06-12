-- ============================================================
-- 02_behavior_path_signal.sql — 非线性行为路径与转化信号
-- ============================================================
-- 职责：识别用户在 pv/fav/cart/buy 之间的实际行为组合，
--       量化哪些路径更接近购买（购买信号），构建 Sankey 流向数据。
-- 输出表：
--   user_behavior_path       — 用户维度行为组合表
--   path_conversion_signal   — 行为组合与购买信号强度
--   path_sankey              — 行为首次出现顺序的 Sankey 数据
-- 依赖：00_init.sql（提供 clean 视图 + user_base_metrics 中间表）
--
-- ★ 核心前提：
--   pv/fav/cart/buy 不是严格线性漏斗。
--   加购 UV (215,167) 远超收藏 UV (113,717) — 用户大量跳过收藏直接加购。
--   本模块聚焦"哪些行为组合更可能伴随购买"，而非"从 A 阶段转化到 B 阶段"。
--   所有"转化率"均应表述为"渗透率"、"覆盖率"或"关联信号"。
-- ============================================================


-- ============================================================
-- 1. user_behavior_path — 用户行为组合表
-- ============================================================
-- 为每个用户打标：产生过哪些行为类型（pv/fav/cart/buy）
-- behavior_combo 如 "pv+cart+buy"（跳过收藏）、"pv+fav+cart+buy"（完整路径）
DROP TABLE IF EXISTS user_behavior_path;
CREATE TABLE user_behavior_path AS
SELECT
    user_id,
    MAX(CASE WHEN behavior_type = 'pv'   THEN 1 ELSE 0 END) AS has_pv,
    MAX(CASE WHEN behavior_type = 'fav'  THEN 1 ELSE 0 END) AS has_fav,
    MAX(CASE WHEN behavior_type = 'cart' THEN 1 ELSE 0 END) AS has_cart,
    MAX(CASE WHEN behavior_type = 'buy'  THEN 1 ELSE 0 END) AS has_buy,
    -- 行为组合字符串（按 pv/fav/cart/buy 顺序）
    CONCAT_WS('+',
        CASE WHEN MAX(CASE WHEN behavior_type = 'pv'   THEN 1 ELSE 0 END) = 1 THEN 'pv'   END,
        CASE WHEN MAX(CASE WHEN behavior_type = 'fav'  THEN 1 ELSE 0 END) = 1 THEN 'fav'  END,
        CASE WHEN MAX(CASE WHEN behavior_type = 'cart' THEN 1 ELSE 0 END) = 1 THEN 'cart' END,
        CASE WHEN MAX(CASE WHEN behavior_type = 'buy'  THEN 1 ELSE 0 END) = 1 THEN 'buy'  END
    ) AS behavior_combo
FROM clean
GROUP BY user_id;


-- ============================================================
-- 2. path_conversion_signal — 行为组合与购买信号强度
-- ============================================================
-- 统计每种行为组合的用户数、购买用户数、购买信号率
-- ★ "buy_signal_rate" = 该组合中购买用户的占比
--   这是关联信号（association signal），不是因果转化率
DROP TABLE IF EXISTS path_conversion_signal;
CREATE TABLE path_conversion_signal AS
SELECT
    behavior_combo,
    COUNT(*)                                              AS user_cnt,
    SUM(has_buy)                                          AS buyer_cnt,
    ROUND(100.0 * SUM(has_buy) / NULLIF(COUNT(*), 0), 2) AS buy_signal_rate,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 2)     AS user_pct,
    -- 辅助特征：该组合用户的人均行为统计
    ROUND(AVG(has_pv), 2)   AS pv_penetration,
    ROUND(AVG(has_fav), 2)  AS fav_penetration,
    ROUND(AVG(has_cart), 2) AS cart_penetration
FROM user_behavior_path
GROUP BY behavior_combo
ORDER BY buy_signal_rate DESC;


-- ============================================================
-- 3. path_sankey — 行为首次出现顺序的 Sankey 数据
-- ============================================================
-- 基于每个用户各行为类型的首次出现时间，构建行为之间的流向。
-- 例如：用户先 pv(10:00) → 然后 cart(10:05) → 然后 buy(10:10)
--       会产生两条流向：pv→cart, cart→buy
-- ★ 这不是路径转化，而是行为出现的时序邻接关系
DROP TABLE IF EXISTS path_sankey;
CREATE TABLE path_sankey AS
WITH
-- 每个用户每种行为类型的首次出现时间
user_first_behavior AS (
    SELECT
        user_id,
        behavior_type,
        MIN(ts) AS first_ts,
        ROW_NUMBER() OVER (
            PARTITION BY user_id
            ORDER BY MIN(ts)
        ) AS seq
    FROM clean
    GROUP BY user_id, behavior_type
),
-- 按时间顺序构建邻接对
transitions AS (
    SELECT
        a.user_id,
        a.behavior_type AS source,
        b.behavior_type AS target
    FROM user_first_behavior a
    JOIN user_first_behavior b
        ON a.user_id = b.user_id
       AND a.seq + 1 = b.seq  -- a 的下一时序行为是 b
)
SELECT
    source,
    target,
    COUNT(DISTINCT user_id) AS user_cnt
FROM transitions
GROUP BY source, target
ORDER BY user_cnt DESC;


-- ============================================================
-- 验证输出
-- ============================================================
SELECT '=== 02_behavior_path_signal 执行完成 ===' AS status;

SELECT 'user_behavior_path'        AS tbl, COUNT(*) AS rows FROM user_behavior_path
UNION ALL
SELECT 'path_conversion_signal',   COUNT(*) FROM path_conversion_signal
UNION ALL
SELECT 'path_sankey',              COUNT(*) FROM path_sankey;

-- 显示行为组合概览（Top 10 按用户数）
SELECT '--- 行为组合 Top 10（按用户数）---' AS info;
SELECT
    behavior_combo,
    user_cnt,
    buyer_cnt,
    buy_signal_rate,
    user_pct
FROM path_conversion_signal
ORDER BY user_cnt DESC
LIMIT 10;

-- 显示 Sankey 流向概览
SELECT '--- Sankey 流向 ---' AS info;
SELECT source, target, user_cnt FROM path_sankey;
