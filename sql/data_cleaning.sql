-- ============================================================
-- 淘宝用户行为数据清洗 (DuckDB SQL)
-- ============================================================

-- 1. 创建原始视图
CREATE OR REPLACE VIEW raw_data AS
SELECT
    column0 AS user_id,
    column1 AS item_id,
    column2 AS category_id,
    column3 AS behavior_type,
    column4 AS raw_timestamp
FROM read_csv_auto('data/user_data.csv', header=false, ignore_errors=true);


-- 2. 清洗：过滤异常数据 + 类型转换，写入清洗后表
DROP TABLE IF EXISTS clean_data;
CREATE TABLE clean_data AS
SELECT
    CAST(user_id    AS BIGINT)  AS user_id,
    CAST(item_id    AS BIGINT)  AS item_id,
    CAST(category_id AS BIGINT) AS category_id,
    behavior_type,
    to_timestamp(raw_timestamp) AS ts,
    CAST(raw_timestamp AS BIGINT) AS raw_ts
FROM raw_data
WHERE 1=1
    -- 去掉空值
    AND user_id       IS NOT NULL
    AND item_id       IS NOT NULL
    AND category_id   IS NOT NULL
    AND behavior_type IS NOT NULL
    AND raw_timestamp IS NOT NULL
    -- 仅保留四类合法行为
    AND behavior_type IN ('pv', 'fav', 'cart', 'buy')
    -- 去掉离谱时间戳（限制在 2017 年内）
    AND raw_timestamp BETWEEN 1483228800 AND 1514736000;


-- 3. 按日期维度添加派生字段，创建分析宽表
DROP TABLE IF EXISTS clean_data_enriched;
CREATE TABLE clean_data_enriched AS
SELECT
    *,
    CAST(strftime(ts, '%Y-%m-%d') AS DATE)  AS dt,
    strftime(ts, '%H')                       AS hour,
    strftime(ts, '%u')                       AS weekday,
    CASE strftime(ts, '%u')
        WHEN '6' THEN 1  WHEN '7' THEN 1
        ELSE 0
    END                                      AS is_weekend,
    strftime(ts, '%Y-%m')                    AS month
FROM clean_data;


-- 4. 去重：同一用户同一秒同一商品同一行为只保留一条
DELETE FROM clean_data_enriched
WHERE (user_id, item_id, behavior_type, raw_ts, dt) NOT IN (
    SELECT user_id, item_id, behavior_type, raw_ts, MIN(dt)
    FROM clean_data_enriched
    GROUP BY user_id, item_id, behavior_type, raw_ts
);


-- 5. 验证清洗结果
SELECT 'clean_data_enriched 行数' AS metric,
    COUNT(*) AS value
FROM clean_data_enriched
UNION ALL
SELECT
    '覆盖天数',
    COUNT(DISTINCT dt)
FROM clean_data_enriched
UNION ALL
SELECT
    '覆盖月份',
    COUNT(DISTINCT month)
FROM clean_data_enriched
UNION ALL
SELECT
    '行为分布(buy)',
    SUM(CASE WHEN behavior_type = 'buy' THEN 1 ELSE 0 END)
FROM clean_data_enriched
UNION ALL
SELECT
    '行为分布(cart)',
    SUM(CASE WHEN behavior_type = 'cart' THEN 1 ELSE 0 END)
FROM clean_data_enriched
UNION ALL
SELECT
    '行为分布(fav)',
    SUM(CASE WHEN behavior_type = 'fav' THEN 1 ELSE 0 END)
FROM clean_data_enriched
UNION ALL
SELECT
    '行为分布(pv)',
    SUM(CASE WHEN behavior_type = 'pv' THEN 1 ELSE 0 END)
FROM clean_data_enriched;


-- 6. 导出清洗后数据到 CSV（按日期排序）
COPY clean_data_enriched
TO 'data/clean_data.csv'
WITH (HEADER true, DELIMITER ',');


-- 7. （可选）导出为 Parquet，后续分析更快
COPY clean_data_enriched
TO 'data/clean_data.parquet'
WITH (FORMAT PARQUET, COMPRESSION ZSTD);
