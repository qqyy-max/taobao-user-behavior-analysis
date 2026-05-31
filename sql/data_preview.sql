-- ============================================================
-- 淘宝用户行为数据预览 (DuckDB SQL)
-- ============================================================

-- 1. 创建视图：从 CSV 直接读取（不加载到内存，DuckDB 自动列式优化）
CREATE OR REPLACE VIEW raw_data AS
SELECT
    column0 AS user_id,
    column1 AS item_id,
    column2 AS category_id,
    column3 AS behavior_type,
    column4 AS raw_timestamp
FROM read_csv_auto('data/user_data.csv', header=false, ignore_errors=true);


-- 2. 数据规模概览
SELECT
    '总行数' AS metric,
    COUNT(*) AS value
FROM raw_data
UNION ALL
SELECT
    '总用户数',
    COUNT(DISTINCT user_id)
FROM raw_data
UNION ALL
SELECT
    '总商品数',
    COUNT(DISTINCT item_id)
FROM raw_data
UNION ALL
SELECT
    '总类目数',
    COUNT(DISTINCT category_id)
FROM raw_data
UNION ALL
SELECT
    '时间范围',
    to_timestamp(MIN(raw_timestamp)) || ' ~ ' || to_timestamp(MAX(raw_timestamp))
FROM raw_data;


-- 3. 行为分布
SELECT
    behavior_type,
    CASE behavior_type
        WHEN 'pv'   THEN '浏览'
        WHEN 'fav'  THEN '收藏'
        WHEN 'cart' THEN '加购'
        WHEN 'buy'  THEN '购买'
        ELSE '未知'
    END AS behavior_name,
    COUNT(*) AS cnt,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) AS pct
FROM raw_data
GROUP BY behavior_type
ORDER BY cnt DESC;


-- 4. 抽样查看前 20 行（含可读时间）
SELECT
    user_id,
    item_id,
    category_id,
    behavior_type,
    raw_timestamp,
    to_timestamp(raw_timestamp) AS ts_readable
FROM raw_data
LIMIT 20;


-- 5. 检查各字段空值
SELECT
    'user_id'       AS col, SUM(CASE WHEN user_id       IS NULL THEN 1 ELSE 0 END) AS null_cnt,
    COUNT(*) AS total FROM raw_data
UNION ALL
SELECT
    'item_id',      SUM(CASE WHEN item_id      IS NULL THEN 1 ELSE 0 END),
    COUNT(*) FROM raw_data
UNION ALL
SELECT
    'category_id',  SUM(CASE WHEN category_id  IS NULL THEN 1 ELSE 0 END),
    COUNT(*) FROM raw_data
UNION ALL
SELECT
    'behavior_type',SUM(CASE WHEN behavior_type IS NULL THEN 1 ELSE 0 END),
    COUNT(*) FROM raw_data
UNION ALL
SELECT
    'raw_timestamp',SUM(CASE WHEN raw_timestamp IS NULL THEN 1 ELSE 0 END),
    COUNT(*) FROM raw_data;


-- 6. 检查异常 behavior_type
SELECT
    behavior_type,
    COUNT(*) AS cnt
FROM raw_data
WHERE behavior_type NOT IN ('pv', 'fav', 'cart', 'buy')
GROUP BY behavior_type;


-- 7. 检查时间戳异常（负数 / 远早于 2017 / 远晚于 2017）
SELECT
    '负数时间戳'     AS issue, COUNT(*) AS cnt FROM raw_data WHERE raw_timestamp < 0
UNION ALL
SELECT
    '早于2017-01-01' AS issue, COUNT(*) AS cnt FROM raw_data WHERE raw_timestamp > 0 AND raw_timestamp < 1483228800
UNION ALL
SELECT
    '晚于2018-01-01' AS issue, COUNT(*) AS cnt FROM raw_data WHERE raw_timestamp >= 1514736000;


-- 8. 用户行为频次分布（Top N 高频用户）
SELECT
    user_id,
    COUNT(*) AS total_actions,
    SUM(CASE WHEN behavior_type = 'buy'  THEN 1 ELSE 0 END) AS buy_cnt,
    SUM(CASE WHEN behavior_type = 'cart' THEN 1 ELSE 0 END) AS cart_cnt,
    SUM(CASE WHEN behavior_type = 'fav'  THEN 1 ELSE 0 END) AS fav_cnt,
    SUM(CASE WHEN behavior_type = 'pv'   THEN 1 ELSE 0 END) AS pv_cnt
FROM raw_data
GROUP BY user_id
ORDER BY total_actions DESC
LIMIT 20;


-- 9. DAU 趋势（按天聚合）
SELECT
    strftime(to_timestamp(raw_timestamp), '%Y-%m-%d') AS dt,
    COUNT(DISTINCT user_id) AS dau,
    COUNT(*) AS total_actions,
    SUM(CASE WHEN behavior_type = 'buy' THEN 1 ELSE 0 END) AS buy_actions
FROM raw_data
GROUP BY dt
ORDER BY dt;


-- 10. 数据完整性：检查同一 user+item 是否在 buy 之前有对应 pv
SELECT
    '有购买但无浏览记录的商品数' AS issue,
    COUNT(DISTINCT b.user_id || '_' || b.item_id) AS cnt
FROM (SELECT DISTINCT user_id, item_id FROM raw_data WHERE behavior_type = 'buy') b
LEFT JOIN (SELECT DISTINCT user_id, item_id FROM raw_data WHERE behavior_type = 'pv') p
    ON b.user_id = p.user_id AND b.item_id = p.item_id
WHERE p.user_id IS NULL;
