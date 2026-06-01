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
    -- 严格限制到官方数据集窗口：2017-11-25 ~ 2017-12-03（9 天）
    -- 边界经实证确认：min raw_ts of 2017-11-25 = 1511539200
    --                 max raw_ts of 2017-12-03 = 1512316799
    --                 min raw_ts of 2017-12-04 = 1512316805
    -- 左闭右开：>= 1511539200 且 < 1512316805，恰好 9 天
    AND raw_timestamp >= 1511539200
    AND raw_timestamp <  1512316805;


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


-- 6. ★ 数据质量守卫：验证时间窗口严格为 9 天 ★
--    若不满足（如早于 11-25 或晚于 12-03 的数据仍然存在），
--    后续阶段不应继续。
SELECT
    'DATA QUALITY GUARD' AS check_name,
    CASE
        WHEN MIN(dt) = '2017-11-25'
         AND MAX(dt) = '2017-12-03'
         AND COUNT(DISTINCT dt) = 9
        THEN 'PASS — 9-day window confirmed'
        ELSE 'FAIL — date range mismatch, STOP HERE'
    END AS result,
    MIN(dt) AS min_date,
    MAX(dt) AS max_date,
    COUNT(DISTINCT dt) AS distinct_days
FROM clean_data_enriched;

-- 若上面输出 FAIL，后续 SQL 不应继续执行。
-- 这里用 RAISE 方式确保 DuckDB 在检测到异常时抛出错误：
SELECT
    CASE
        WHEN (SELECT COUNT(DISTINCT dt) FROM clean_data_enriched) != 9
          OR (SELECT MIN(dt) FROM clean_data_enriched) != '2017-11-25'
          OR (SELECT MAX(dt) FROM clean_data_enriched) != '2017-12-03'
        THEN error('DATA QUALITY CHECK FAILED: expected 9 days (2017-11-25 ~ 2017-12-03), '
                    || 'got ' || (SELECT COUNT(DISTINCT dt)::VARCHAR FROM clean_data_enriched) || ' days '
                    || '(' || (SELECT MIN(dt)::VARCHAR FROM clean_data_enriched) || ' ~ '
                    || (SELECT MAX(dt)::VARCHAR FROM clean_data_enriched) || '). '
                    || 'Check raw_timestamp filter in data_cleaning.sql.')
        ELSE 'DATA QUALITY CHECK PASSED: 9-day window confirmed.'
    END AS guard_status;


-- 6. 导出清洗后数据到 CSV（按日期排序）
COPY clean_data_enriched
TO 'data/clean_data.csv'
WITH (HEADER true, DELIMITER ',');


-- 7. （可选）导出为 Parquet，后续分析更快
COPY clean_data_enriched
TO 'data/clean_data.parquet'
WITH (FORMAT PARQUET, COMPRESSION ZSTD);
