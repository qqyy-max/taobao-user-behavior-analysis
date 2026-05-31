-- ============================================================
-- 07_export_mart.sql — 统一导出层 (Unified Export Mart)
-- ============================================================
-- 职责：将分析结果表统一导出为 Parquet，供 Power BI / Python 消费。
--       Parquet 格式比 DuckDB 表更便携，Power BI 可直接导入。
--
-- 输出目录: data/mart/          (Power BI / 分析报告)
--          data/features/       (Python ML)
--
-- 依赖：00_init ~ 06_feature_mart 全部执行完成
-- ============================================================

-- ============================================================
-- A. Power BI Dashboard 核心表
-- ============================================================

-- A1. 数据画像 — 概览卡片
COPY (SELECT * FROM profiling_summary ORDER BY metric)
TO 'data/mart/profiling_summary.parquet'
WITH (FORMAT PARQUET, COMPRESSION ZSTD);

-- A2. 转化漏斗 — 漏斗图
COPY (SELECT * FROM funnel_summary ORDER BY stage)
TO 'data/mart/funnel_summary.parquet'
WITH (FORMAT PARQUET, COMPRESSION ZSTD);

-- A3. 用户转化率 — KPI 指标
COPY (SELECT * FROM user_conversion_summary)
TO 'data/mart/user_conversion_summary.parquet'
WITH (FORMAT PARQUET, COMPRESSION ZSTD);

-- A4. 留存明细 — 热力图
COPY (SELECT * FROM cohort_retention_detail ORDER BY cohort_date, retention_day)
TO 'data/mart/cohort_retention_detail.parquet'
WITH (FORMAT PARQUET, COMPRESSION ZSTD);

-- A5. 留存曲线 — 折线图
COPY (SELECT * FROM cohort_retention_summary ORDER BY retention_day)
TO 'data/mart/cohort_retention_summary.parquet'
WITH (FORMAT PARQUET, COMPRESSION ZSTD);

-- A6. 日度行为趋势 — DAU 趋势图
COPY (SELECT * FROM daily_behavior_summary ORDER BY dt)
TO 'data/mart/daily_behavior_summary.parquet'
WITH (FORMAT PARQUET, COMPRESSION ZSTD);

-- A7. 小时行为分布 — 时段热力图
COPY (SELECT * FROM hourly_behavior_summary ORDER BY hour)
TO 'data/mart/hourly_behavior_summary.parquet'
WITH (FORMAT PARQUET, COMPRESSION ZSTD);

-- A8. 周末 vs 工作日 — 对比柱状图
COPY (SELECT * FROM weekday_behavior_summary ORDER BY is_weekend)
TO 'data/mart/weekday_behavior_summary.parquet'
WITH (FORMAT PARQUET, COMPRESSION ZSTD);

-- A9. 类目转化 — 排行榜 & 散点图
COPY (SELECT * FROM category_conversion ORDER BY exposure_rank)
TO 'data/mart/category_conversion.parquet'
WITH (FORMAT PARQUET, COMPRESSION ZSTD);

-- A10. 商品转化 — 明细表
COPY (SELECT * FROM item_conversion ORDER BY exposure_rank)
TO 'data/mart/item_conversion.parquet'
WITH (FORMAT PARQUET, COMPRESSION ZSTD);

-- A11. 高曝光低转化商品 — 问题清单
COPY (SELECT * FROM high_exposure_low_conversion_items ORDER BY pv_cnt DESC, buy_rate_pct ASC)
TO 'data/mart/high_exposure_low_conversion_items.parquet'
WITH (FORMAT PARQUET, COMPRESSION ZSTD);

-- A12. 用户分群汇总 — 柱状图 & 表格
COPY (SELECT * FROM user_segment_summary ORDER BY user_cnt DESC)
TO 'data/mart/user_segment_summary.parquet'
WITH (FORMAT PARQUET, COMPRESSION ZSTD);

-- A13. Session 统计 — 会话转化分析
COPY (SELECT * FROM session_stats ORDER BY session_cnt DESC)
TO 'data/mart/session_stats.parquet'
WITH (FORMAT PARQUET, COMPRESSION ZSTD);


-- ============================================================
-- B. 维度表 (Power BI 星型模型)
-- ============================================================

-- B1. 日期维度
COPY (SELECT * FROM dim_date ORDER BY dt)
TO 'data/mart/dim_date.parquet'
WITH (FORMAT PARQUET, COMPRESSION ZSTD);

-- B2. 类目维度（从 category_conversion 提取）
COPY (
    SELECT DISTINCT
        category_id,
        exposure_rank,
        conversion_rank
    FROM category_conversion
    ORDER BY category_id
)
TO 'data/mart/dim_category.parquet'
WITH (FORMAT PARQUET, COMPRESSION ZSTD);


-- ============================================================
-- C. Python ML 特征表
-- ============================================================
-- (已在 06_feature_mart.sql 中导出到 data/features/user_features.parquet)
-- 此处仅做验证
SELECT
    'data/features/user_features.parquet' AS exported_file,
    COUNT(*) AS rows
FROM user_features;


-- ============================================================
-- D. 可选导出：用户画像明细（大表，按需启用）
-- ============================================================
-- COPY (SELECT * FROM user_profile)
-- TO 'data/mart/user_profile.parquet'
-- WITH (FORMAT PARQUET, COMPRESSION ZSTD);


-- ============================================================
-- 验证摘要
-- ============================================================
SELECT '=== 07_export_mart 执行完成 ===' AS status;
SELECT 'Exported to data/mart/' AS target, COUNT(*) AS files
FROM (
    SELECT 'profiling_summary' AS t UNION ALL
    SELECT 'funnel_summary' UNION ALL
    SELECT 'user_conversion_summary' UNION ALL
    SELECT 'cohort_retention_detail' UNION ALL
    SELECT 'cohort_retention_summary' UNION ALL
    SELECT 'daily_behavior_summary' UNION ALL
    SELECT 'hourly_behavior_summary' UNION ALL
    SELECT 'weekday_behavior_summary' UNION ALL
    SELECT 'category_conversion' UNION ALL
    SELECT 'item_conversion' UNION ALL
    SELECT 'high_exposure_low_conversion_items' UNION ALL
    SELECT 'user_segment_summary' UNION ALL
    SELECT 'session_stats' UNION ALL
    SELECT 'dim_date' UNION ALL
    SELECT 'dim_category'
);
