# Agent 指标口径字典（Prompt 注入版）

> **用途**：注入 Analyst Agent 的 System Prompt，作为指标口径权威约束
> **来源**：与 `docs/metrics_dictionary.md` 同源，精简为 Prompt 格式
> **版本**：v1.0 | 2026-06-11

---

## 一、核心禁止用语与正确表述

| 禁止用语 | 正确表述 | 原因 |
|---------|---------|------|
| 留存率 | **短周期回访率** | 仅 9 天窗口，不等于长期留存 |
| 复购率 | **窗口内重复购买率** | 窗口外行为不可知 |
| 漏斗转化率 | **渗透率 / 行为覆盖率** | pv/fav/cart/buy 非严格线性漏斗 |
| 流失用户 | **低活跃未购买用户** | 9 天不足以判断流失 |
| 预期 LTV | **估算客单价（加⚠️注）** | 无价格字段，不可计算 LTV |

## 二、维度标注强制规则

- **行为维度购买率**：`buy_cnt/total_actions` ≈ 2.0%（每次提到必须标注"行为维度"）
- **用户维度购买率**：`is_buyer/total_users` ≈ 68.0%（每次提到必须标注"用户维度"）
- 两者完全不同，不可混用

## 三、关键指标速查表

### 3.1 流量与活跃

| 指标 | 数据来源 | 关键数值 | 约束 |
|------|---------|---------|------|
| DAU | `daily_behavior_summary.dau` | 周末较工作日+16% | 提及 DAU 必须同时给出购买率 |
| UV | 各聚合表 `uv` 字段 | 287,004（总用户） | 必须明确是全量UV还是特定行为UV |

### 3.2 行为路径与转化信号

| 指标 | 数据来源 | 关键数值 | 约束 |
|------|---------|---------|------|
| 加购渗透率 | `user_conversion_summary.cart_rate_pct` | 75.3% | 出现时必须对比收藏率39.8% |
| 收藏渗透率 | `user_conversion_summary.fav_rate_pct` | 39.8% | 不能解释为购买意向 |
| 购买用户占比 | `user_conversion_summary.buy_rate_pct` | 68.0% | 必须标注"用户维度" |
| 行为级购买占比 | `daily_behavior_summary.buy_rate_pct` | ~2.0% | 必须标注"行为维度" |
| 加购到购买转化信号 | 即席查询 `user_base_metrics` | — | ⚠️ 不能用 `buyer_cart_rate` 代替 |
| 加购未购用户数 | `cart_abandon_users` | 60,891 | 占加购用户28.3% |
| 路径购买信号率 | `path_conversion_signal.buy_signal_rate` | — | ⚠️ 不在 `funnel_path_detail` |
| 行为组合覆盖率 | `path_conversion_signal.user_pct` | — | 4种行为最多15种组合 |

### 3.3 短周期回访与重复购买

| 指标 | 数据来源 | 关键数值 | 约束 |
|------|---------|---------|------|
| 短周期回访率 | `cohort_retention_detail.retention_rate_pct` | D1: 78.8%, D7: 98.5% | ⚠️ D7 必须标注"周末周期效应" |
| 窗口内重复购买率 | 双口径（见下方） | — | ⚠️ 禁止表述为"复购率" |

**窗口内重复购买率双口径**：
- 口径①（推荐）：`user_segment_summary.repeat_buyer_rate_pct`（分母=购买用户）
- 口径②：`segment_summary` 中 `segment_name='window_repeat_buyer'` 的 `user_pct`（分母=全体用户）

### 3.4 Session 分析

| 指标 | 数据来源 | 关键数值 | 约束 |
|------|---------|---------|------|
| Session购买率 | `session_stats.buy_rate_pct` | ≤5行为: 7.5%, 6+行为: 13.0% | 标注"6行为临界点" |
| Session深度 | `session_stats.session_length_group` | 68% Session ≤5行为 | 标注30分钟切分规则 |

### 3.5 商品曝光效率

| 指标 | 数据来源 | 关键数值 | 约束 |
|------|---------|---------|------|
| 高曝光低转化商品 | `high_exposure_low_conversion_items` | 51.3万件 | ⚠️ Agent查询直接用表，不硬编码阈值 |
| 搜索直达商品 | `search_direct_items` | 11,781件 | buy_rate_pct为NULL(NOT >100%) |
| 商品曝光转化率 | `item_conversion.buy_rate_pct` | — | 搜索直达商品buy_rate=NULL |
| 商品效率汇总 | `product_efficiency_anomaly_summary` | 1行全局汇总 | helc_item_cnt, underexposed_gem_cnt |

### 3.6 用户分层

**三套分群来源（不可互代）**：

| 分群类型 | 表名 | 关键字段 |
|---------|------|---------|
| 规则分层（5层P0-P3+REF） | `segment_summary` | `segment_name`, `buyer_rate_pct`, `user_cnt` |
| KMeans聚类（5群C0-C4） | `user_cluster_summary` (parquet) | `cluster`, `buy_rate_pct` |
| 行为频次分层（6组） | `user_segment_summary` | `freq_group`, `buyer_rate_pct` |

**5层规则分层定义**：

| 层级 | 英文名 | 定义 | 优先级 |
|------|-------|------|--------|
| P0 | window_repeat_buyer | buy_cnt >= 2 | 最高 |
| P1 | cart_abandon_user | has_cart=1 AND is_buyer=0 (~60,891) | 高 |
| P2 | high_browse_weak_buy_signal | pv_cnt >= P75 AND is_buyer=0 | 中 |
| P3 | low_active_no_purchase | is_buyer=0（其余） | 低 |
| REF | single_purchase_user | is_buyer=1 AND buy_cnt=1 | 参照组 |

### 3.7 异动归因

| 异动 | 数据来源 | 关键数值 | 约束 |
|------|---------|---------|------|
| 周末DAU↑购买率↓ | `weekend_anomaly_summary` | DAU+16%, 购买率-10% | 归因"逛型流量增加" |
| 时段错配 | `hourly_behavior_summary` | 流量峰值21:00, 购买率峰值10:00(2.62%) | Push排期优化 |
| 商品效率异常 | `product_efficiency_anomaly_summary` | 51.3万HELC | 缺少曝光来源字段 |

## 四、重要表快速索引

| 表名 | 用途 | 来源SQL |
|------|------|---------|
| `user_base_metrics` | 所有用户行为基础聚合 | 00_init |
| `segment_summary` | 5层规则分层汇总 | 05_user_behavior_segmentation |
| `cart_abandon_users` | 加购未购用户画像(60,891人) | 05_cart_abandon_analysis |
| `cart_buyer_comparison` | 加购未购 vs 加购后购买对比 | 05_cart_abandon_analysis |
| `cart_abandon_summary` | 加购未购全局统计(1行) | 05_cart_abandon_analysis |
| `path_conversion_signal` | 行为组合购买信号率 | 02_behavior_path_signal |
| `path_sankey` | 行为时序邻接流向(Sankey) | 02_behavior_path_signal |
| `product_efficiency_anomaly_summary` | 商品效率全局汇总(1行) | 07_anomaly_attribution |
| `daily_behavior_summary` | 日度DAU/购买率趋势 | 03_behavior_analysis |
| `hourly_behavior_summary` | 小时购买效率分布 | 03_behavior_analysis |
| `user_conversion_summary` | 全局用户转化率汇总(1行) | 02_funnel_retention |
| `weekend_anomaly_summary` | 周末vs工作日异动对比 | 07_anomaly_attribution |
| `high_exposure_low_conversion_items` | 高曝光低转化商品 | 04_product_analysis |
| `search_direct_items` | 搜索直达商品(11,781件) | 04_product_analysis |

## 五、已知结论（增量分析基准，以下结论不要重复"发现"）

1. 加购渗透率75.3%远超收藏39.8%——用户路径非线性
2. Day1回访率78.8%，Day7回访率98.5%受周末周期效应影响
3. 51.3万件商品高曝光零购买信号（PV≥P75, buy=0）
4. C2购买率9.4%/人均PV 71；C0人均PV 198但购买率仅2.0%，类目广度43.6
5. C3(19%) 67.4%行为在周末；C4(12%)仅41.6%在周末
6. 周末DAU+16%但购买率低于工作日
7. Session>6行为后购买率13.0%（vs ≤5行为时7.5%）——6行为临界点
8. 购买率峰值10:00(2.62%)，流量峰值21:00——时序错位
9. 60,891用户加购未购，占加购用户28.3%
10. P0窗口内重复购买用户(P0层)购买率79.3%

## 六、Agent 查询速查规则

1. **Cluster数据不在DB中**：`user_cluster_result.parquet` 和 `user_cluster_summary.parquet` 是独立Parquet文件，必须用 `read_parquet('data/mart/...')` 查询
2. **路径购买信号率**：查 `path_conversion_signal`，不查 `funnel_path_detail`（后者无buy_signal_rate字段）
3. **搜索直达商品**：查 `search_direct_items` 表，不可用 `buy_rate_pct > 100` 过滤
4. **加购到购买转化信号**：即席查 `user_base_metrics`，不可用 `buyer_cart_rate` 代替
5. **高曝光低转化商品**：直接查 `high_exposure_low_conversion_items` 表，不硬编码阈值
6. **DuckDB INTERVAL语法**：用单引号 `INTERVAL '7' DAY`，不是 `INTERVAL 7 DAY`
7. **clean_data路径**：`read_parquet('data/clean_data.parquet')`
