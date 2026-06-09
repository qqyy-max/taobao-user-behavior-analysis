# Analysis Rules — 分析框架与 SOP

> **版本**：v1.0 | 2026-06-08
> **适用 Agent**：Analyst Agent（单 Agent 模式） / Analyst Agent（Multi-Agent 模式）
> **设计原则**：每个分析任务必须遵循标准化流程（SOP），确保输出一致性和可复现性。

---

## 目录

1. [分析总纲](#1-分析总纲)
2. [漏斗分析 SOP](#2-漏斗分析-sop)
3. [留存分析 SOP](#3-留存分析-sop)
4. [用户分层 SOP](#4-用户分层-sop)
5. [商品分析 SOP](#5-商品分析-sop)
6. [Session 分析 SOP](#6-session-分析-sop)
7. [时序分析 SOP](#7-时序分析-sop)
8. [交叉分析 SOP](#8-交叉分析-sop)
9. [分析输出规范](#9-分析输出规范)
10. [禁止行为](#10-禁止行为)

---

## 1. 分析总纲

### 1.1 每次分析任务的标准启动流程

```
Step 1: get_business_context()
   ↓  了解所有表的含义、已知核心结论、clean_data 字段
Step 2: 判断问题类型 → 匹配对应 SOP
   ↓  漏斗 / 留存 / 分群 / 商品 / Session / 时序 / 交叉
Step 3: get_table_schema(相关表名)
   ↓  确认字段名，不凭记忆猜字段
Step 4: 执行对应 SOP 的 SQL 查询步骤
   ↓  优先 query_duckdb（聚合表），需要原始数据时用 query_raw
Step 5: 输出按标准格式
   ↓  【数据摘要】→ 【增量洞察】→ 【数据局限】→ 【可执行建议】
```

### 1.2 数据源选择优先级

| 优先级 | 数据源 | 适用场景 |
|--------|--------|----------|
| **P0** | `query_duckdb` → analysis.db 聚合表 | 能用聚合表回答的问题（占总分析 80%） |
| **P1** | `query_duckdb` → `read_parquet('data/mart/*.parquet')` | Cluster 相关分析（user_cluster_summary / user_cluster_result） |
| **P2** | `query_raw` → clean_data.parquet | 需要原始行为序列、个体级数据、复杂跨表 JOIN |
| **P3** | `plot_bar` | 需要可视化时（不要滥用 —— 仅关键发现才画图） |

### 1.3 已知结论优先原则

以下结论已在 `get_business_context()` 中声明，**Agent 必须跳过这些分析，不要重复发现**：

1. PV→FAV 流失 60.2%，但加购 UV(215,167) 远超收藏 UV(113,717)——非线性漏斗
2. Day1 留存 78.8%（11/25 Cohort），Day7=98.5% 为周末周期效应
3. 51.3 万件高曝光低转化商品（PV≥P75，购买率=0%）
4. C2 购买率 9.4%/人均 PV 71；C0 人均 PV 198 但购买率仅 2.0%/类目广度 43.6
5. 周末 DAU +16% 但购买率低于工作日
6. Session >6 行为：购买率 13.0%（vs ≤5 行为 7.5%）
7. 购买率峰值 10:00（2.62%），流量峰值 21:00 — 时序错位
8. 20,089 用户加购未购；819 名超级用户购买率 81.8%

> **增量原则**：Agent 必须做**超出以上已知结论**的增量分析。如果分析结果完全在已知结论范围内 → 报告无增量发现 → 反思分析角度。

---

## 2. 漏斗分析 SOP

### 2.1 触发条件

用户问题包含："漏斗"、"转化率"、"流失"、"断裂"、"转化路径"、"CVR"、"PV→BUY"

### 2.2 标准分析步骤

```
Step A: 整体漏斗巡检
  表：funnel_summary
  SQL：SELECT * FROM funnel_summary
  输出：4 阶段 UV + 渗透率

Step B: 路径分析（Sankey 数据）
  表：funnel_path_detail
  SQL：SELECT * FROM funnel_path_detail
  目的：确认用户跳过收藏直接加购的规模

Step C: 用户维度渗透率
  表：user_conversion_summary
  SQL：SELECT * FROM user_conversion_summary
  重点关注：
    - fav_rate_pct (39.6%) vs cart_rate_pct (75.0%) 差距
    - buyer_fav_rate (41.4%) vs buyer_cart_rate (79.1%) 差距

Step D: Session 深度 × 漏斗关系（增量分析）
  表：session_stats
  SQL：SELECT * FROM session_stats ORDER BY session_length_group
  交叉：不同 Session 深度的用户到达漏斗各阶段的比例

Step E (增量): 分群漏斗对比
  表：user_cluster_summary + user_profile
  目的：各 Cluster 的漏斗渗透率差异 → 针对性运营
```

### 2.3 漏斗分析必须回答的问题

1. 各阶段流失率是多少？（引用具体 UV 和百分比）
2. 最大断裂点在哪里？（需标注流失最多的环节）
3. 这是线性漏斗吗？（必须提及加购 UV > 收藏 UV 的非线性特征）
4. 与已知结论的关系？（标注哪些是已知的，哪些是增量发现）

### 2.4 漏斗分析输出模板

```markdown
【数据摘要】
- 漏斗各阶段 UV：PV=X, FAV=X, CART=X, BUY=X
- 各阶段渗透率：X%, X%, X%
- 最大断裂点：XXX 阶段，流失 X%

【增量洞察】
- (如果与已知结论一致) 本次漏斗数据与已知结论一致，无增量发现
- (如果有新发现) 具体的新发现 + 数据支撑

【数据局限】
- 漏斗非互斥，用户可出现在多阶段
- 缺少转化时间窗口（无法区分"浏览后立即购买"vs"浏览后 3 天购买"）
```

---

## 3. 留存分析 SOP

### 3.1 触发条件

用户问题包含："留存"、"回访"、"粘性"、"流失周期"、"Day N"、"次日"

### 3.2 标准分析步骤

```
Step A: 留存曲线
  表：cohort_retention_summary
  SQL：SELECT * FROM cohort_retention_summary ORDER BY retention_day
  输出：D0→D8 留存曲线，标注 D1 和 D7

Step B: Cohort 热力图数据
  表：cohort_retention_detail
  SQL：SELECT * FROM cohort_retention_detail ORDER BY cohort_date, retention_day
  重点关注：
    - D1 留存最低的 Cohort（哪个 Cohort 首日后流失最多）
    - D7/D8 是否出现周末回峰（98% ✗ 真实留存）

Step C: Cohort 特征对比（增量分析）
  关联：cohort_retention_detail + daily_behavior_summary
  目的：分析首日活跃特征（DAU、购买率）与后续留存的关系

Step D (增量): 分群留存对比
  需要：query_raw 计算各 Cluster 的留存差异
```

### 3.3 留存分析必须标注的局限

1. **9 天窗口限制**：无法观测 D9+ 的真实留存衰减
2. **周末周期效应**：D7=98.5%（周六回峰），非真实留存
3. **单 Cohort 主导**：71% 用户首日在 11/25，数据偏差大

---

## 4. 用户分层 SOP

### 4.1 触发条件

用户问题包含："分群"、"聚类"、"Cluster"、"C0/C1/C2/C3/C4"、"用户画像"、"用户分层"、"RFM"、"高价值"

### 4.2 标准分析步骤

```
Step A: Cluster 画像总览
  表：read_parquet('data/mart/user_cluster_summary.parquet')
  SQL：SELECT * FROM read_parquet('data/mart/user_cluster_summary.parquet') ORDER BY cluster
  输出：5 个 Cluster 的规模、购买率、人均 PV、类目广度等

Step B: Cluster 时间偏好
  表：cluster_temporal_profile
  SQL：SELECT * FROM cluster_temporal_profile ORDER BY cluster
  重点关注：各 Cluster 的周末占比和时段分布

Step C: 频次分层交叉
  表：user_segment_summary
  SQL：SELECT * FROM user_segment_summary ORDER BY freq_group
  交叉：freq_group × cluster 的交叉分析

Step D (增量): Cluster 深度特征挖掘
  表：user_features + read_parquet('data/mart/user_cluster_result.parquet')
  目的：找出各 Cluster 的"特征签名"——哪些特征最能区分各群体

Step E (增量): 个体用户画像
  表：user_profile JOIN user_cluster_result
  目的：获取具体用户 ID 的画像（用于策略示例）
```

### 4.3 分群速查表（Agent 必须记忆）

| Cluster | 画像 | 占比 | 购买率 | 人均 PV | 核心特征 |
|---------|------|------|--------|---------|----------|
| C0 | 探索型浏览 | 20.3% | 2.0% | 198 | 类目广度 43.6，活跃 8.4 天 |
| C1 | 高价值用户 | 11.1% | 5.2% | 41 | 行为稳定（volatility=0.001） |
| C2 | 核心高价值 | 20.1% | 9.4% | 71 | cart_to_buy=137.7%（复购信号） |
| C3 | 高浏览低转化 | 29.3% | 0.8% | 89 | 67.4% 周末活跃 |
| C4 | 潜力转化 | 19.2% | 4.2% | 30 | 41.6% 周末 — "工作日买家" |

---

## 5. 商品分析 SOP

### 5.1 触发条件

用户问题包含："商品"、"类目"、"曝光"、"转化"、"推荐"、"搜索直达"、"无效曝光"

### 5.2 标准分析步骤

```
Step A: 类目波士顿矩阵数据
  表：category_conversion
  SQL：SELECT * FROM category_conversion ORDER BY pv_cnt DESC
  关注：exposure_rank 与 conversion_rank 差距大的类目

Step B: 问题商品清单
  表：high_exposure_low_conversion_items
  SQL：SELECT * FROM high_exposure_low_conversion_items ORDER BY exposure_conversion_gap DESC LIMIT 100
  规模：512,540 件

Step C: 搜索直达商品
  表：search_direct_by_category
  SQL：SELECT * FROM search_direct_by_category ORDER BY direct_item_cnt DESC
  规模：11,781 件商品，2,933 个类目

Step D (增量): 商品特征分析
  表：query_raw → clean_data.parquet
  目的：分析问题商品的 behavior 序列，找根因（如详情页缺失）
```

### 5.3 商品分析关键判断标准

| 场景 | 判断标准 | 行动建议 |
|------|----------|----------|
| 高曝光 + 高转化 | `exposure_rank < P25 AND conversion_rank < P25` | 保持推荐权重 |
| 高曝光 + 低转化 | `exposure_rank < P25 AND conversion_rank > P75` | 降权，排查根因 |
| 低曝光 + 高转化 | `exposure_rank > P75 AND conversion_rank < P25` | **增加曝光**（宝藏商品） |
| 低曝光 + 低转化 | `exposure_rank > P75 AND conversion_rank > P75` | 长尾 — 不需优先处理 |

---

## 6. Session 分析 SOP

### 6.1 触发条件

用户问题包含："Session"、"会话"、"行为深度"、"行为序列"、"停留时长"

### 6.2 标准分析步骤

```
Step A: Session 深度阶梯
  表：session_stats
  SQL：SELECT * FROM session_stats ORDER BY session_length_group
  关键发现：6 行为临界点（购买率 7.5% → 13.0%）

Step B: 个体会话明细（增量）
  表：session_summary
  SQL：SELECT * FROM session_summary WHERE has_buy = true LIMIT 100
  目的：分析含购买的 Session 的行为序列模式

Step C (增量): Session 时段分布
  表：query_raw → clean_data.parquet
  目的：分析不同时段 Session 深度差异 → 时段触达策略
```

---

## 7. 时序分析 SOP

### 7.1 触发条件

用户问题包含："时间"、"时段"、"小时"、"日期"、"趋势"、"周末"、"工作日"、"DAU"

### 7.2 标准分析步骤

```
Step A: DAU 日度趋势
  表：daily_behavior_summary
  SQL：SELECT * FROM daily_behavior_summary ORDER BY dt
  标注：周末日期、DAU 峰值、购买率峰值

Step B: 24 小时分布
  表：hourly_behavior_summary
  SQL：SELECT * FROM hourly_behavior_summary ORDER BY hour
  标注：购买率峰值 (10:00 2.62%)、流量峰值 (21:00)、时序错位

Step C: 周末 vs 工作日
  表：weekday_behavior_summary
  SQL：SELECT * FROM weekday_behavior_summary
  关键发现：周末 DAU +16% 但购买率 -10%
```

---

## 8. 交叉分析 SOP

### 8.1 标准交叉维度

| 交叉维度 | 数据源 | 典型问题 |
|----------|--------|----------|
| Cluster × 时段 | user_cluster_result + hourly_behavior | "C2 在什么时段最活跃？" |
| Cluster × 类目偏好 | user_cluster_result + category_conversion | "C0 浏览最多的类目是什么？" |
| Cluster × 留存 | user_cluster_result + cohort | "各分群的留存率差异？" |
| freq_group × Cluster | user_frequency_segment + user_cluster_result | "高频用户集中在哪些 Cluster？" |

### 8.2 交叉分析 SQL 模板

```sql
-- 模板：Cluster × 某个维度
SELECT
    cr.cluster,
    -- 聚合维度字段
    AVG(...) AS metric,
    COUNT(*) AS user_cnt
FROM read_parquet('data/mart/user_cluster_result.parquet') cr
JOIN {事实表} t ON cr.user_id = t.user_id
GROUP BY cr.cluster
ORDER BY cr.cluster
```

---

## 9. 分析输出规范

### 9.1 输出格式（Multi-Agent 模式）

Agent 必须按以下三段式输出：

```markdown
【数据摘要】
列出本次查询的关键数字（≥3 个具体数字）

【增量洞察】
超出已知结论的新发现，说明与已知结论的关系

【数据局限】
本次分析缺少什么，结论的适用范围
```

### 9.2 输出格式（单 Agent 模式）

```markdown
**核心数字**（≥3 个具体数字）
→ **增量洞察**（超出已知结论的新发现）
→ **可执行建议**（具体到触达渠道、时机、内容，可量化的 KPI）
```

### 9.3 数字密度要求

- 每段分析至少包含 **3 个**具体数字或百分比
- 禁止模糊表述：较高、明显、显著、一定程度、有所提升、比较低
- 必须用具体数字替代：如"购买率 9.4%"而非"购买率较高"

### 9.4 字数要求

- 最终分析结果 ≥ **150 字**
- 策略部分 ≥ **100 字**

---

## 10. 禁止行为

### 10.1 数据操作禁令

| # | 禁止行为 | 原因 |
|---|----------|------|
| 1 | 凭记忆猜字段名（不先 get_table_schema） | 字段名可能变化，导致 SQL 报错 |
| 2 | 对 cluster parquet 直接写表名查询 | 不在 analysis.db，必须用 `read_parquet` |
| 3 | 用 AVG 代替 COUNT(DISTINCT user_id) 计算 UV | UV 必须去重 |
| 4 | 混淆行为维度与用户维度的转化率 | 两个维度含义完全不同 |
| 5 | 忽略 9 天窗口限制 | 所有趋势判断必须标注此局限 |

### 10.2 分析陷阱

| # | 陷阱 | 正确做法 |
|---|------|----------|
| 1 | FAV→CART = 189% → "收藏到加购转化率很高" | ✗ 错误——这是伪指标，源群体 < 目标群体 |
| 2 | D7 留存 98.5% → "用户留存极高" | ✗ 错误——周末周期效应，非真实留存 |
| 3 | 人均 PV 198 (C0) → "C0 是高价值群体" | ✗ 错误——C0 购买率仅 2.0%，是高粘性低转化 |
| 4 | 周末 DAU 高 → "周末运营效果好" | ✗ 错误——周末购买率低于工作日，流量质量下降 |
| 5 | cart_to_buy_rate > 100% → "数据错误" | ✗ 错误——复购信号（同商品多次购买 > 一次加购） |
