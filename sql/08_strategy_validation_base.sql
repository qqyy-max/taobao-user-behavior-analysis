-- ============================================================
-- 08_strategy_validation_base.sql — 策略验证模拟基础表
-- ============================================================
-- 职责：为 S1/S2/S3 三条运营策略构建 A/B 实验的离线模拟分组基础表。
--       使用 hash(user_id) % N 模拟随机分组，标注"离线模拟"。
-- 输出：
--   v1_coupon_experiment_users       — V1 加购限时优惠三组实验用户
--   v2_welcome_coupon_users          — V2 高浏览首单券两组实验用户
--   v3_exposure_governance_users     — V3 曝光分层治理两组实验用户
--   v3_top1000_helc_items            — V3 标记的 Top 1000 高曝光零购买信号商品
-- 依赖：
--   00_init.sql（user_base_metrics）
--   04_product_analysis.sql（high_exposure_low_conversion_items）
--   05_cart_abandon_analysis.sql（cart_abandon_users）
--   05_user_behavior_segmentation.sql（user_behavior_segment）
-- ============================================================

-- ============================================================
-- 1. V1 模拟：加购未购用户限时优惠触达实验
-- ============================================================
-- 分组方式：hash(user_id) % 100
--   Group_A_Discount   : 0-32  (33%) — 48h 后发放 5% 限时折扣券 + Push 提醒
--   Group_B_Reminder   : 33-65 (33%) — 仅 Push 提醒，无折扣
--   Group_C_Control    : 66-99 (34%) — 不做任何干预
-- 人群：P1 cart_abandon_user（has_cart=1 AND is_buyer=0）
-- ============================================================

DROP TABLE IF EXISTS v1_coupon_experiment_users;
CREATE TABLE v1_coupon_experiment_users AS
WITH p1_users AS (
    SELECT
        m.user_id,
        m.pv_cnt,
        m.cart_cnt,
        m.fav_cnt,
        m.active_days,
        m.has_cart,
        m.is_buyer,
        m.first_active_date,
        m.last_active_date,
        ca.cart_item_cnt,
        ca.cart_category_cnt,
        ca.last_cart_date,
        ca.days_since_last_cart,
        ca.avg_daily_pv,
        ca.cart_to_pv_rate
    FROM user_base_metrics m
    JOIN cart_abandon_users ca ON m.user_id = ca.user_id
    WHERE m.has_cart = 1 AND m.is_buyer = 0
),
assigned AS (
    SELECT
        *,
        ABS(HASH(CAST(user_id AS VARCHAR))) % 100 AS hash_mod
    FROM p1_users
)
SELECT
    user_id,
    pv_cnt,
    cart_cnt,
    fav_cnt,
    active_days,
    has_cart,
    is_buyer,
    cart_item_cnt,
    cart_category_cnt,
    last_cart_date,
    days_since_last_cart,
    avg_daily_pv,
    cart_to_pv_rate,
    CASE
        WHEN hash_mod BETWEEN 0 AND 32  THEN 'Group_A_Discount'
        WHEN hash_mod BETWEEN 33 AND 65 THEN 'Group_B_Reminder'
        ELSE 'Group_C_Control'
    END AS experiment_group,
    CASE
        WHEN hash_mod BETWEEN 0 AND 32  THEN '折扣组：48h后发放5%限时折扣券+Push提醒'
        WHEN hash_mod BETWEEN 33 AND 65 THEN '仅提醒组：Push提醒，无折扣'
        ELSE '对照组：不做任何干预'
    END AS group_description,
    'v1_coupon_experiment' AS experiment_name,
    '离线模拟 — hash(user_id) % 100 随机分组' AS simulation_note
FROM assigned
ORDER BY user_id;


-- ============================================================
-- 2. V2 模拟：高浏览弱购买用户首单券实验
-- ============================================================
-- 分组方式：hash(user_id) % 2
--   Group_Exp_Coupon  : 0 (50%) — 首单无门槛10元券 + 品类收窄推荐（Top 5 类目）
--   Group_Ctrl_Normal : 1 (50%) — 正常推荐，无优惠
-- 人群：P2 high_browse_weak_buy_signal（pv_cnt >= P75 AND is_buyer=0）
-- ============================================================

DROP TABLE IF EXISTS v2_welcome_coupon_users;
CREATE TABLE v2_welcome_coupon_users AS
WITH p2_users AS (
    SELECT
        seg.user_id,
        seg.pv_cnt,
        seg.cart_cnt,
        seg.fav_cnt,
        seg.buy_cnt,
        seg.active_days,
        seg.is_buyer,
        seg.has_cart,
        seg.segment_name,
        seg.segment_priority,
        m.first_active_date,
        m.last_active_date,
        m.lifecycle_days
    FROM user_behavior_segment seg
    JOIN user_base_metrics m ON seg.user_id = m.user_id
    WHERE seg.segment_name = 'high_browse_weak_buy_signal'
),
assigned AS (
    SELECT
        *,
        ABS(HASH(CAST(user_id AS VARCHAR))) % 2 AS hash_mod
    FROM p2_users
)
SELECT
    user_id,
    pv_cnt,
    cart_cnt,
    fav_cnt,
    active_days,
    is_buyer,
    has_cart,
    lifecycle_days,
    first_active_date,
    last_active_date,
    CASE
        WHEN hash_mod = 0 THEN 'Group_Exp_Coupon'
        ELSE 'Group_Ctrl_Normal'
    END AS experiment_group,
    CASE
        WHEN hash_mod = 0 THEN '实验组：首单10元无门槛券+品类收窄推荐(Top5类目)'
        ELSE '对照组：正常推荐，无优惠'
    END AS group_description,
    'v2_welcome_coupon_experiment' AS experiment_name,
    '离线模拟 — hash(user_id) % 2 随机分组' AS simulation_note
FROM assigned
ORDER BY user_id;


-- ============================================================
-- 3. V3 模拟：高曝光低购买信号商品分层治理实验
-- ============================================================
-- 分组方式：hash(user_id) % 2
--   Group_Exp_Governance : 0 (50%) — 自然推荐中 Top 1000 高曝光零购买信号商品
--                                    权重降低50%（豁免商业化/活动/新品/品牌）
--   Group_Ctrl_Original  : 1 (50%) — 保持原始推荐算法
-- 人群：全量用户
-- [!!] 数据约束：无 exposure_source 字段，离线模拟中仅做用户分组和商品标记。
--              被降权商品标注为"假定已确认为自然推荐且匹配异常的商品"。
-- ============================================================

DROP TABLE IF EXISTS v3_exposure_governance_users;
CREATE TABLE v3_exposure_governance_users AS
WITH all_users AS (
    SELECT
        m.user_id,
        m.pv_cnt,
        m.cart_cnt,
        m.fav_cnt,
        m.buy_cnt,
        m.active_days,
        m.buy_days,
        m.cart_days,
        m.is_buyer,
        m.has_cart,
        m.has_fav,
        m.first_active_date,
        m.last_active_date,
        m.lifecycle_days
    FROM user_base_metrics m
),
assigned AS (
    SELECT
        *,
        ABS(HASH(CAST(user_id AS VARCHAR))) % 2 AS hash_mod
    FROM all_users
)
SELECT
    user_id,
    pv_cnt,
    cart_cnt,
    fav_cnt,
    buy_cnt,
    active_days,
    buy_days,
    cart_days,
    is_buyer,
    has_cart,
    has_fav,
    first_active_date,
    last_active_date,
    lifecycle_days,
    CASE
        WHEN hash_mod = 0 THEN 'Group_Exp_Governance'
        ELSE 'Group_Ctrl_Original'
    END AS experiment_group,
    CASE
        WHEN hash_mod = 0 THEN '实验组：自然推荐中Top1000高曝光零购买信号商品权重降低50%（豁免商业化/活动/新品/品牌）'
        ELSE '对照组：保持原始推荐算法'
    END AS group_description,
    'v3_exposure_governance_experiment' AS experiment_name,
    '离线模拟 — hash(user_id) % 2 随机分组。[!!] 无exposure_source字段，仅做分组+商品标记' AS simulation_note
FROM assigned
ORDER BY user_id;


-- ============================================================
-- 4. V3 标记商品：Top 1000 高曝光零购买信号商品
-- ============================================================
-- 从 high_exposure_low_conversion_items 中取 PV 最高的 1000 件商品，
-- 作为 V3 实验中"假定为自然推荐且匹配异常"的降权候选商品。
-- [!!] 标注：离线数据无法区分自然推荐 vs 商业化推广，此 Top 1000
--         在实际实验中需先接入 exposure_source 字段筛选确认。
-- ============================================================

DROP TABLE IF EXISTS v3_top1000_helc_items;
CREATE TABLE v3_top1000_helc_items AS
SELECT
    item_id,
    category_id,
    pv_cnt,
    fav_cnt,
    cart_cnt,
    buy_cnt,
    buy_rate_pct,
    cart_rate_pct,
    exposure_rank,
    conversion_rank,
    exposure_conversion_gap,
    ROW_NUMBER() OVER (ORDER BY pv_cnt DESC) AS pv_rank,
    '假定为自然推荐且匹配异常的高曝光零购买信号商品（待exposure_source字段确认）' AS governance_note
FROM high_exposure_low_conversion_items
ORDER BY pv_cnt DESC
LIMIT 1000;


-- ============================================================
-- 5. 效果追踪查询模板（离线模拟基线统计）
-- ============================================================

-- ── 5.1 V1 各组基线统计 ──────────────────────────────────────
-- 用途：验证分组随机性（各组在 cart_cnt、days_since_last_cart、
--       cart_item_cnt 等维度应无显著差异）
SELECT '=== V1 各组基线统计 ===' AS query_label;

SELECT
    experiment_group,
    COUNT(*)                                    AS user_cnt,
    ROUND(AVG(cart_cnt), 1)                    AS avg_cart_cnt,
    ROUND(AVG(cart_item_cnt), 1)               AS avg_cart_items,
    ROUND(AVG(cart_category_cnt), 1)           AS avg_cart_categories,
    ROUND(AVG(active_days), 1)                 AS avg_active_days,
    ROUND(AVG(days_since_last_cart), 1)        AS avg_days_since_cart,
    ROUND(AVG(avg_daily_pv), 1)                AS avg_daily_pv,
    ROUND(AVG(cart_to_pv_rate), 1)             AS avg_cart_to_pv_rate_pct
FROM v1_coupon_experiment_users
GROUP BY experiment_group
ORDER BY experiment_group;


-- ── 5.2 V1 转化率计算模板（真实实验时使用）───────────────────
-- [!!] 离线模拟中 V1 用户 is_buyer=0（定义约束），无法计算真实转化率。
--    以下为真实实验时的查询模板，仅展示 SQL 框架。
SELECT '=== V1 转化率计算模板（真实实验用，离线模拟中基线=0%） ===' AS query_label;

SELECT
    experiment_group,
    COUNT(*)                                    AS total_users,
    SUM(CASE WHEN is_buyer = 1 THEN 1 ELSE 0 END) AS converted_users,
    ROUND(100.0 * SUM(CASE WHEN is_buyer = 1 THEN 1 ELSE 0 END) / COUNT(*), 2) AS conversion_rate_pct,
    '[!!] 离线模拟中 converted_users=0（定义约束），真实实验中为非零值' AS note
FROM v1_coupon_experiment_users
GROUP BY experiment_group
ORDER BY experiment_group;


-- ── 5.3 V2 各组基线统计 ──────────────────────────────────────
-- 用途：验证分组随机性（各组在 pv_cnt、active_days、lifecycle_days
--       等维度应无显著差异）
SELECT '=== V2 各组基线统计 ===' AS query_label;

SELECT
    experiment_group,
    COUNT(*)                                    AS user_cnt,
    ROUND(AVG(pv_cnt), 1)                      AS avg_pv,
    ROUND(AVG(active_days), 1)                 AS avg_active_days,
    ROUND(AVG(lifecycle_days), 1)              AS avg_lifecycle_days,
    ROUND(AVG(fav_cnt), 1)                     AS avg_fav_cnt,
    SUM(CASE WHEN has_cart = 1 THEN 1 ELSE 0 END) AS cart_users,
    ROUND(100.0 * SUM(CASE WHEN has_cart = 1 THEN 1 ELSE 0 END) / COUNT(*), 2) AS cart_rate_pct
FROM v2_welcome_coupon_users
GROUP BY experiment_group
ORDER BY experiment_group;


-- ── 5.4 V2 首购率计算模板（真实实验时使用）───────────────────
-- [!!] 离线模拟中 V2 用户 is_buyer=0（定义约束），无法计算真实首购率。
--    以下为真实实验时的查询模板。
SELECT '=== V2 首购率计算模板（真实实验用，离线模拟中基线=0%） ===' AS query_label;

SELECT
    experiment_group,
    COUNT(*)                                    AS total_users,
    SUM(CASE WHEN is_buyer = 1 THEN 1 ELSE 0 END) AS first_purchase_users,
    ROUND(100.0 * SUM(CASE WHEN is_buyer = 1 THEN 1 ELSE 0 END) / COUNT(*), 2) AS first_purchase_rate_pct,
    '[!!] 离线模拟中 first_purchase_users=0（定义约束），真实实验中为非零值' AS note
FROM v2_welcome_coupon_users
GROUP BY experiment_group
ORDER BY experiment_group;


-- ── 5.5 V3 各组基线统计 ──────────────────────────────────────
-- 用途：验证分组随机性（全量用户在各指标维度应无显著差异）
SELECT '=== V3 各组基线统计 ===' AS query_label;

SELECT
    experiment_group,
    COUNT(*)                                    AS user_cnt,
    ROUND(AVG(pv_cnt), 1)                      AS avg_pv,
    ROUND(AVG(cart_cnt), 1)                    AS avg_cart,
    ROUND(AVG(buy_cnt), 1)                     AS avg_buy,
    ROUND(AVG(active_days), 1)                 AS avg_active_days,
    ROUND(100.0 * SUM(is_buyer) / COUNT(*), 2) AS buyer_rate_pct,
    ROUND(100.0 * SUM(has_cart) / COUNT(*), 2) AS cart_penetration_pct,
    ROUND(100.0 * SUM(has_fav) / COUNT(*), 2)  AS fav_penetration_pct
FROM v3_exposure_governance_users
GROUP BY experiment_group
ORDER BY experiment_group;


-- ── 5.6 V3 商品层面统计模板 ──────────────────────────────────
-- 用途：对比实验组 vs 对照组用户在高曝光零购买信号商品上的行为差异
-- [!!] 离线模拟中无法模拟推荐权重调整的实际效果，仅展示商品层面统计框架。
SELECT '=== V3 Top 1000 标记商品概览 ===' AS query_label;

SELECT
    COUNT(*)                                    AS marked_item_cnt,
    SUM(pv_cnt)                                 AS total_pv,
    ROUND(AVG(pv_cnt), 1)                      AS avg_pv,
    ROUND(AVG(buy_rate_pct), 2)                AS avg_buy_rate_pct,
    SUM(buy_cnt)                                AS total_buy_cnt
FROM v3_top1000_helc_items;


-- ── 5.7 V3 实验组 vs 对照组商品交互对比模板（真实实验用）─────
-- 用途：真实实验中，对比实验组和对照组用户在标记商品上的行为差异
SELECT '=== V3 实验组 vs 对照组商品交互对比模板（真实实验用） ===' AS query_label;

SELECT
    v3.experiment_group,
    COUNT(DISTINCT v3.user_id)                  AS user_cnt,
    '[!!] 真实实验中需 JOIN 推荐日志/曝光日志表获取商品级交互数据' AS note
FROM v3_exposure_governance_users v3
GROUP BY v3.experiment_group
ORDER BY v3.experiment_group;


-- ============================================================
-- 6. 导出为 Parquet
-- ============================================================

COPY v1_coupon_experiment_users
TO 'data/mart/v1_coupon_experiment_users.parquet'
WITH (FORMAT PARQUET, COMPRESSION ZSTD);

COPY v2_welcome_coupon_users
TO 'data/mart/v2_welcome_coupon_users.parquet'
WITH (FORMAT PARQUET, COMPRESSION ZSTD);

COPY v3_exposure_governance_users
TO 'data/mart/v3_exposure_governance_users.parquet'
WITH (FORMAT PARQUET, COMPRESSION ZSTD);

COPY v3_top1000_helc_items
TO 'data/mart/v3_top1000_helc_items.parquet'
WITH (FORMAT PARQUET, COMPRESSION ZSTD);


-- ============================================================
-- 7. 验证
-- ============================================================
SELECT '=== 08_strategy_validation_base 执行完成 ===' AS status;

SELECT 'v1_coupon_experiment_users'     AS tbl, COUNT(*) AS rows FROM v1_coupon_experiment_users
UNION ALL
SELECT 'v2_welcome_coupon_users',       COUNT(*) FROM v2_welcome_coupon_users
UNION ALL
SELECT 'v3_exposure_governance_users',  COUNT(*) FROM v3_exposure_governance_users
UNION ALL
SELECT 'v3_top1000_helc_items',         COUNT(*) FROM v3_top1000_helc_items;
