# list_tables

> 时间: 2026-06-08 16:23:20
> Provider: anthropic
> Source: agent

---

以下是 analysis.db 中所有可用的分析结果表：

| # | 表名 | 业务含义 |
|---|------|----------|
| 1 | `category_base_stats` | 类目基础统计 |
| 2 | `category_conversion` | 类目转化分析（曝光量 / 购买率 / 排名） |
| 3 | `cluster_temporal_profile` | 各 Cluster 时段偏好画像 |
| 4 | `cohort_retention_detail` | 逐 Cohort × 逐天留存明细 |
| 5 | `cohort_retention_summary` | 所有 Cohort 平均留存汇总 |
| 6 | `daily_behavior_summary` | 日度行为汇总（DAU / PV / 购买率） |
| 7 | `dim_date` | 日期维度表（年月日 / 星期 / 是否周末） |
| 8 | `funnel_path_detail` | 用户实际行为路径（Sankey 数据） |
| 9 | `funnel_summary` | 漏斗各阶段 UV 和转化率 |
| 10 | `high_exposure_low_conversion_items` | 51.3 万件高曝光低转化商品 |
| 11 | `hourly_behavior_summary` | 小时级行为与购买率 |
| 12 | `item_conversion` | 商品级转化 |
| 13 | `profiling_summary` | 全局基准指标 |
| 14 | `search_direct_by_category` | 按类目汇总搜索直达商品数 |
| 15 | `search_direct_items` | 搜索直达商品（有购买无 PV） |
| 16 | `session_stats` | Session 行为深度与转化关系 |
| 17 | `session_summary` | 每个 Session 的明细行为 |
| 18 | `user_base_metrics` | 用户基础指标 |
| 19 | `user_conversion_summary` | 全量用户转化基准 |
| 20 | `user_features` | 35 维聚类特征宽表 |
| 21 | `user_frequency_segment` | 每用户频率分组明细 |
| 22 | `user_profile` | 每用户行为画像 |
| 23 | `user_segment_summary` | 频率分层整体统计 |
| 24 | `weekday_behavior_summary` | 工作日 vs 周末对比 |

共 **24 张表**。其中 `category_base_stats` 和 `user_base_metrics` 是新增的（原文档中未列出）。需要查看哪张表的结构或开始什么分析？
