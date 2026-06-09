# 数据库表结构速查

## analysis.db 实际存在的表（已验证）

| 表名 | 粒度 | 核心字段 | 业务含义 |
|------|------|----------|----------|
| `funnel_summary` | 行为阶段 | stage/stage_cn/uv/actions/conversion_rate_pct | PV→FAV→CART→BUY 各阶段 UV 和转化率 |
| `funnel_path_detail` | 路径 | path_from/source/target/user_cnt | 用户实际行为路径 Sankey 数据 |
| `user_conversion_summary` | 全局（单行） | total_users/pv_users/fav_users/cart_users/buy_users/fav_rate_pct/cart_rate_pct/buy_rate_pct/buyer_fav_rate/buyer_cart_rate | 全量用户转化基准（**注意：不是 user_cluster_summary**） |
| `cohort_retention_detail` | cohort_date × retention_day | retained_users/total_users/retention_rate_pct | 逐 Cohort 逐天留存 |
| `cohort_retention_summary` | retention_day | avg_retention_rate_pct | 所有 Cohort 平均留存汇总 |
| `daily_behavior_summary` | dt | dau/pv_cnt/fav_cnt/cart_cnt/buy_cnt/buy_rate_pct | 日度行为汇总 |
| `hourly_behavior_summary` | hour | actions/buy_cnt/buy_rate_pct/uv | 小时级行为和购买率 |
| `weekday_behavior_summary` | is_weekend | avg_dau/avg_buy_rate_pct | 工作日 vs 周末对比 |
| `session_stats` | session_length_group | session_cnt/buy_rate_pct/avg_duration_min | Session 行为深度与转化关系 |
| `session_summary` | session_id | user_id/action_cnt/buy_cnt/cart_cnt/fav_cnt/pv_cnt/has_buy/session_duration_min/session_date | 每个 Session 的明细行为 |
| `category_conversion` | category_id | pv_cnt/buy_cnt/buy_rate_pct/exposure_rank/conversion_rank | 类目转化分析 |
| `item_conversion` | item_id | pv_cnt/buy_cnt/buy_rate_pct/exposure_rank | 商品级转化 |
| `high_exposure_low_conversion_items` | item_id | pv_cnt/buy_rate_pct/exposure_conversion_gap | 51.3 万件高曝光低转化商品 |
| `search_direct_items` | item_id | — | 搜索直达商品（有购买无 PV） |
| `search_direct_by_category` | category_id | — | 按类目汇总搜索直达商品数 |
| `user_segment_summary` | freq_group | user_cnt/user_pct/avg_buy_per_user/buyer_rate_pct | 频率分层整体统计 |
| `user_frequency_segment` | user_id | total_actions/buy_cnt/active_days/freq_group/buyer_group | 每用户的频率分组明细 |
| `user_profile` | user_id | pv_cnt/buy_cnt/active_days/buy_rate_pct/category_diversity/lifecycle_days/is_buyer | 每用户行为画像 |
| `user_features` | user_id | 35维特征：buy_rate/cart_to_buy_rate/weekend_ratio/night_ratio/morning_ratio/category_diversity/hour_concentration等 | 聚类特征宽表 |
| `cluster_temporal_profile` | cluster | avg_weekend_ratio_pct/avg_morning_ratio_pct/avg_evening_ratio_pct/avg_night_ratio_pct/avg_buy_weekend_ratio_pct | 各 Cluster 时段偏好画像 |
| `profiling_summary` | metric | value | 全局基准指标 |
| `dim_date` | dt | year/month/day/weekday/is_weekend | 日期维度 |

> [!IMPORTANT]
> **没有 `user_cluster_summary` 表！** 对应的表是：
> - Cluster 画像 → 需要 JOIN `user_features`（含 cluster 字段）和 `cluster_temporal_profile`
> - 用户转化汇总 → `user_conversion_summary`
> - 频率分层 → `user_segment_summary` + `user_frequency_segment`

## clean_data.parquet 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `user_id` | int | 用户 ID（脱敏） |
| `item_id` | int | 商品 ID（脱敏） |
| `category_id` | int | 类目 ID（脱敏） |
| `behavior_type` | str | pv/fav/cart/buy |
| `ts` | int | Unix 时间戳（秒） |
| `dt` | str | 日期 YYYY-MM-DD |
| `hour` | int | 小时 0-23 |
| `weekday` | int | 0=周一 … 6=周日 |
| `is_weekend` | bool | 是否周末 |

## 核心指标定义

- **转化率**：用 UV（去重用户数）计算，非行为次数
- **留存率**：基于 cohort_date（首次活跃日），同一用户在 retention_day 天后仍活跃的比例
- **Cluster 编号**：C0~C4 无顺序含义，不代表价值高低；cluster 字段存在于 `user_features` 表
- **Session**：连续行为间隔 ≤30 分钟算同一 Session（来自 session_stats/session_summary 表）
- **DuckDB INTERVAL 语法**：用单引号 `INTERVAL '7' DAY`，不是 `INTERVAL 7 DAY`

## 已知核心结论（不要重复发现）

1. PV→FAV 流失 60.2%，但加购 UV(215,167) 远超收藏 UV(113,717)——是非线性漏斗
2. Day1 留存 78.8%（最大 Cohort 11/25 的 204,904 人）；Day7 留存 98.5% 是**周末周期效应**非真实留存
3. 51.3 万件商品：PV≥P75(≥6次) 且购买率=0%
4. C0：人均 PV 198，购买率 2.0%，类目广度 43.6；C2：购买率 9.4%，人均 PV 71
5. C3（19%）67.4% 行为在周末；C4（12%）仅 41.6% 在周末
6. 周末 DAU +16%，购买率低于工作日
7. Session >6 个行为：购买率 13.0%（vs ≤5 行为时 7.5%）
8. 购买率峰值 10:00（2.62%），流量峰值 21:00
9. 20,089 用户加购未购；819 名超级用户购买率 81.8%

## 查 C0 行为模式的正确 SQL 路径

> [!CAUTION]
> `user_cluster_summary` 和 `user_cluster_result` **不在 analysis.db** 里，是独立 parquet 文件，必须用 `read_parquet` 路径查询！

```sql
-- 第1步：直接查 Cluster 汇总画像
SELECT cluster, persona_name, user_cnt, buy_rate_pct, avg_pv, category_diversity
FROM read_parquet('data/mart/user_cluster_summary.parquet')
ORDER BY cluster;

-- 第2步：获取 C0 用户 ID（cluster=0）并 JOIN user_profile 获取详细特征
SELECT cr.cluster,
       AVG(up.pv_cnt)             AS avg_pv,
       AVG(up.buy_rate_pct)       AS avg_buy_rate,
       AVG(up.category_diversity) AS avg_cat_diversity,
       AVG(up.cart_rate_pct)      AS avg_cart_rate,
       COUNT(*)                   AS user_cnt
FROM read_parquet('data/mart/user_cluster_result.parquet') cr
JOIN user_profile up ON cr.user_id = up.user_id
WHERE cr.cluster = 0
GROUP BY cr.cluster;

-- 第3步（如需原始行为序列）：用 query_raw 查 clean_data.parquet
-- 先从 user_cluster_result 拿到 C0 的 user_id 样本，再查原始行为
```

