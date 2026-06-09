# Power BI 数据字典（Data Dictionary）

> **项目**：淘宝用户行为分析与转化优化 · Power BI Dashboard
> **版本**：v3.0 | 2026-06-02
> **数据源**：`data/mart/*.parquet`（21 张聚合表）→ `exports/user_behavior_dashboard.xlsx`（19 Sheets）
>
> 本文档覆盖全部导出表，按业务模块分组编排，每字段包含：名称、含义、计算逻辑、业务解释、使用页面。

---

## 目录

### 维度表
1. [dim_date](#1-dim_date) — 日期维度
2. [dim_category](#2-dim_category) — 类目维度

### KPI 汇总表
3. [profiling_summary](#3-profiling_summary) — 数据画像 KPI
4. [user_conversion_summary](#4-user_conversion_summary) — 用户转化渗透率

### 漏斗与留存
5. [funnel_summary](#5-funnel_summary) — 行为转化漏斗（4 阶段）
6. [funnel_path_detail](#6-funnel_path_detail) — 多路径 Sankey 流向
7. [cohort_retention_detail](#7-cohort_retention_detail) — Cohort 留存明细
8. [cohort_retention_summary](#8-cohort_retention_summary) — 留存曲线汇总

### 用户行为
9. [daily_behavior_summary](#9-daily_behavior_summary) — DAU 日度行为趋势
10. [hourly_behavior_summary](#10-hourly_behavior_summary) — 24 小时行为分布
11. [weekday_behavior_summary](#11-weekday_behavior_summary) — 周末 vs 工作日对比
12. [session_stats](#12-session_stats) — Session 长度 × 购买率

### 商品与类目
13. [category_conversion](#13-category_conversion) — 类目转化分析
14. [item_conversion](#14-item_conversion) — 商品转化明细
15. [high_exposure_low_conversion_items](#15-high_exposure_low_conversion_items) — 高曝光低转化商品
16. [search_direct_items](#16-search_direct_items) — 搜索直达型商品
17. [search_direct_by_category](#17-search_direct_by_category) — 搜索直达商品按类目汇总

### 用户分群
18. [user_cluster_summary](#18-user_cluster_summary) — 用户聚类画像与策略
19. [user_cluster_result](#19-user_cluster_result) — 个体用户聚类标签
20. [user_segment_summary](#20-user_segment_summary) — 频次分群汇总
21. [cluster_temporal_profile](#21-cluster_temporal_profile) — 分群 × 时间偏好

---

## 1. dim_date

**粒度**：1 行 / 日期 — 共 9 行
**用途**：Power BI 全局日期筛选器、周末/工作日切换
**来源 SQL**：`07_export_mart.sql`
**Dashboard**：全局（所有页面共享）

| # | 字段名称 | 字段含义 | 计算逻辑 | 业务解释 | 使用页面 |
|---|----------|----------|----------|----------|----------|
| 1 | `dt` | 日期 | 数据窗口内的每一天 | 分析日期，范围 2017-11-25 ~ 2017-12-03（9 天） | 全局 |
| 2 | `year` | 年份 | `EXTRACT(YEAR FROM dt)` | 年份标识 | 全局 |
| 3 | `month` | 月份 | `EXTRACT(MONTH FROM dt)` | 月份标识 | 全局 |
| 4 | `day` | 日 | `EXTRACT(DAY FROM dt)` | 日标识 | 全局 |
| 5 | `weekday` | 星期几 | `DAYOFWEEK(dt)` — 0=周一 … 6=周日 | 用于判断工作日/周末 | 全局 |
| 6 | `is_weekend` | 是否周末 | `CASE WHEN weekday >= 5 THEN 1 ELSE 0` | **全局"工作日/周末"切换按钮的数据源。** 1=周末, 0=工作日 | 全局 |
| 7 | `month_label` | 月份标签 | 格式化字符串如 "2017-11" | 图表坐标轴标签 | 全局 |
| 8 | `week_start` | 所属周的周一日期 | `DATE_TRUNC('week', dt)` | 用于周度聚合分析 | 全局 |

### 业务要点

- 仅 9 天数据（2017-11-25 ~ 2017-12-03），周六~次周日，含 3 个周末日 + 6 个工作日
- **`is_weekend` 是整个 Dashboard 最有运营价值的全局交互**：周末 DAU+16% 但购买率-10%
- 在 Power BI 中设为日期表（Mark as Date Table），主键为 `dt`

---

## 2. dim_category

**粒度**：1 行 / 类目 — 共 8,787 行
**用途**：类目维度表，关联 `category_conversion` 和 `item_conversion`
**来源 SQL**：`07_export_mart.sql`（从 `category_conversion` 提取排名字段）
**Dashboard**：Page 4 Product Analysis

| # | 字段名称 | 字段含义 | 计算逻辑 | 业务解释 | 使用页面 |
|---|----------|----------|----------|----------|----------|
| 1 | `category_id` | 类目 ID | 脱敏整型 ID，范围 80 ~ 5,162,429 | 淘宝商品类目标识（脱敏），不可反解为真实类目名 | P4 |
| 2 | `exposure_rank` | 曝光排名 | `ROW_NUMBER() OVER (ORDER BY pv_cnt DESC)` | 1 = PV 最高的类目 | P4 |
| 3 | `conversion_rank` | 转化排名 | `ROW_NUMBER() OVER (ORDER BY buy_rate_pct DESC)` | 1 = 购买率最高的类目 | P4 |

### 业务要点

- 精简维度表，仅保留排名字段用于星型模型关联
- 类目的完整行为指标在 `category_conversion` 事实表中
- 主键：`category_id`

---

## 3. profiling_summary

**粒度**：1 行 / 指标 — 共 33 行
**用途**：KPI 卡片（总用户数、总商品数、整体转化率等）
**来源 SQL**：`01_profiling.sql`
**Dashboard**：Page 1 Executive Overview · Page 3 User Behavior · Page 4 Product Analysis
**Excel**：Sheet `profiling_summary`

| # | 字段名称 | 字段含义 | 计算逻辑 | 业务解释 | 使用页面 |
|---|----------|----------|----------|----------|----------|
| 1 | `metric` | 指标代码 | 英文字段名，如 `total_users`、`buy_pct` | 用于 Power BI DAX 中的 `CALCULATE(... FILTER(metric="..."))` | P1 P3 P4 |
| 2 | `metric_cn` | 指标中文名 | 如 "总用户数"、"整体行为购买率" | 图表标签 | P1 P3 P4 |
| 3 | `value` | 指标值 | 字符串类型（混合数值和百分比） | **注意：value 是 object/字符串类型，Power BI 中需用 `VALUE()` 转换为数值。** | P1 P3 P4 |

### 常用 metric 取值速查

| metric | metric_cn | 含义 |
|--------|-----------|------|
| `total_users` | 总用户数 | 28.7 万活跃用户 |
| `total_items` | 总商品数 | 258.5 万商品 |
| `total_categories` | 总类目数 | 8,788 |
| `buy_pct` | 行为购买率 | 2.01%（行为维度） |
| `user_buy_rate` | 用户购买率 | 67.97%（用户维度，至少购买过1次） |

### 业务要点

- 键值对结构，33 行覆盖所有 KPI 指标
- 在 Power BI 中建议创建度量值而非直接使用此表：
  ```
  Total Users = CALCULATE(VALUE(MAX(profiling_summary[value])), profiling_summary[metric]="total_users")
  ```

---

## 4. user_conversion_summary

**粒度**：1 行（全体用户汇总）
**用途**：用户维度的行为渗透率（PV/FAV/CART/BUY 各阶段覆盖了多少用户），以及购买用户 vs 全体用户的收藏/加购渗透率对比
**来源 SQL**：`02_funnel_retention.sql §4`
**Dashboard**：Page 1 Executive Overview · Page 2 Funnel & Retention
**Excel**：Sheet `user_conversion_summary`

| # | 字段名称 | 字段含义 | 计算逻辑 | 业务解释 | 使用页面 |
|---|----------|----------|----------|----------|----------|
| 1 | `total_users` | 总用户数 | `COUNT(DISTINCT user_id)` | 去重用户总数 | P1 |
| 2 | `pv_users` | 有浏览的用户数 | `COUNT(DISTINCT user_id WHERE has_pv=1)` | 产生过 PV 的用户数 | P2 |
| 3 | `fav_users` | 有收藏的用户数 | `COUNT(DISTINCT user_id WHERE has_fav=1)` | 产生过收藏的用户数 | P2 |
| 4 | `cart_users` | 有加购的用户数 | `COUNT(DISTINCT user_id WHERE has_cart=1)` | 产生过加购的用户数 | P2 |
| 5 | `buy_users` | 有购买的用户数 | `COUNT(DISTINCT user_id WHERE has_buy=1)` | 产生过购买的用户数 | P1 P2 |
| 6 | `fav_rate_pct` | 收藏渗透率 (%) | `fav_users / total_users × 100` | 全体用户中使用过收藏的比例 | P2 |
| 7 | `cart_rate_pct` | 加购渗透率 (%) | `cart_users / total_users × 100` | 全体用户中使用过加购的比例。**75% — 大部分用户会加购。** | P2 |
| 8 | `buy_rate_pct` | 购买率 (%) | `buy_users / total_users × 100` | **核心指标。** 67.97% — 约 2/3 用户至少购买过 1 次。 | P1 P2 |
| 9 | `buyer_fav_rate` | 购买用户的收藏率 (%) | 购买用户中有收藏的比例 | **41.4% — 与全体用户的 39.6% 接近。** 说明收藏不是购买的必要前置。 | P2 |
| 10 | `buyer_cart_rate` | 购买用户的加购率 (%) | 购买用户中有加购的比例 | **79.1% — 高于全体用户的 75.0%。** 加购才是购买的强前置信号。 | P2 |

### 业务要点

- **P2 图表 1b（FAV vs CART 渗透率对比）的核心数据源**：`fav_rate_pct` vs `cart_rate_pct` 和 `buyer_fav_rate` vs `buyer_cart_rate`
- 收藏渗透率（全体 39.6% vs 购买用户 41.4%）差距极小 → 收藏不是转化强信号
- 加购渗透率（全体 75.0% vs 购买用户 79.1%）差距更明显 → 加购是真正的购买前置

---

## 5. funnel_summary

**粒度**：1 行 / 行为阶段 — 共 4 行
**用途**：Power BI 漏斗图、KPI 卡片、阶段流失分析
**来源 SQL**：`02_funnel_retention.sql §1`
**Dashboard**：Page 1 Executive Overview · Page 2 Funnel & Retention
**Excel**：Sheet `funnel_summary`

| # | 字段名称 | 字段含义 | 计算逻辑 | 业务解释 | 使用页面 |
|---|----------|----------|----------|----------|----------|
| 1 | `stage` | 行为阶段代码 | 固定枚举：`pv` / `fav` / `cart` / `buy` | 转化链的 4 个关键节点 | P1 P2 |
| 2 | `stage_cn` | 行为阶段中文名 | 固定映射：浏览 / 收藏 / 加购 / 购买 | 图表标签 | P1 P2 |
| 3 | `uv` | 独立用户数 | `COUNT(DISTINCT user_id)` WHERE behavior_type = stage | 发生过该行为的去重用户数。**注意：漏斗各阶段非互斥，同一用户可出现在多个阶段。** | P1 P2 |
| 4 | `actions` | 行为记录数 | `COUNT(*)` WHERE behavior_type = stage | 该行为类型的总发生次数 | P1 |
| 5 | `conversion_rate_pct` | 渗透率 (%) | `uv / pv_uv × 100`，以 PV 的 UV 为基准 100% | **这不是严格漏斗的阶段转化率**，而是各行为 UV 相对 PV UV 的渗透率。 | P1 P2 |

### 补充：阶段间转化率（需 DAX 计算）

| 计算指标 | DAX 公式 | 含义 |
|----------|----------|------|
| PV → FAV 转化率 | `fav_uv / pv_uv` | 浏览用户中有多少产生了收藏 |
| FAV → CART 转化率 | `cart_uv / fav_uv` | 收藏用户中有多少产生了加购 |
| CART → BUY 转化率 | `buy_uv / cart_uv` | 加购用户中有多少完成了购买 |

---

## 6. funnel_path_detail

**粒度**：1 行 / 转化路径 — 共 6 行
**用途**：Sankey 多路径流向图（替换原单路径漏斗图），展示用户"跳过收藏直达加购"的反直觉行为
**来源 SQL**：`08_powerbi_supplement.sql §1`
**Dashboard**：Page 2 Funnel & Retention（图表 1 — Sankey 图）
**Excel**：Sheet `funnel_path_detail`

| # | 字段名称 | 字段含义 | 计算逻辑 | 业务解释 | 使用页面 |
|---|----------|----------|----------|----------|----------|
| 1 | `path_from` | 路径名称 | 如 "PV→FAV"、"PV→CART(skip FAV)"、"PV→BUY(direct)" | 可读的路径标签，用于 Sankey 图 Tooltip | P2 |
| 2 | `source` | 源阶段 | 行为阶段代码：PV / FAV / CART | Sankey 图的 Source 节点 | P2 |
| 3 | `target` | 目标阶段 | 行为阶段代码：FAV / CART / BUY | Sankey 图的 Target 节点 | P2 |
| 4 | `user_cnt` | 用户数 | 该路径的独立用户数 | **核心度量。** 加购用户远超收藏用户 → 用户跳过收藏直接加购 | P2 |

### 业务要点

- **Sankey 图核心发现**：`PV→CART(skip FAV)` 的用户数远超 `PV→FAV` → 收藏不是必要环节，加购才是
- 共 6 条路径：
  - `PV→FAV`：浏览后收藏（标准路径）
  - `PV→CART(skip FAV)`：跳过收藏直接加购 ⭐
  - `PV→BUY(direct)`：直接购买
  - `FAV→CART`：收藏后加购
  - `FAV→BUY`：收藏后购买
  - `CART→BUY`：加购后购买

---

## 7. cohort_retention_detail

**粒度**：1 行 / (Cohort 日期, 留存天数) — 共 44 行
**用途**：Power BI 留存热力图（Matrix Heatmap）
**来源 SQL**：`02_funnel_retention.sql §3`
**Dashboard**：Page 2 Funnel & Retention
**Excel**：Sheet `cohort_retention_detail`

| # | 字段名称 | 字段含义 | 计算逻辑 | 业务解释 | 使用页面 |
|---|----------|----------|----------|----------|----------|
| 1 | `cohort_date` | 队列日期 | `MIN(dt)` for each user — 用户首次活跃日期 | 每个 Cohort 的起点。同一 cohort_date 的用户在分析窗口内首次出现。 | P2 |
| 2 | `retention_day` | 留存天数 | `DATEDIFF('day', cohort_date, dt)` — 活跃日期距首日的天数 | Day 0 = 首日（存量），Day 1 = 次日。**范围 0~8（9 天窗口限制）。** | P2 |
| 3 | `retained_users` | 留存用户数 | `COUNT(DISTINCT user_id)` 在 retention_day 当天活跃 | 该 Cohort 在 retention_day 仍活跃的去重用户数 | P2 |
| 4 | `total_users` | Cohort 总用户数 | 该 cohort_date 的首日用户数 | 留存率的分母。同一 cohort_date 的所有行该值相同 | P2 |
| 5 | `retention_rate_pct` | 留存率 (%) | `retained_users / total_users × 100` | **核心留存指标。** 75% 表示该 Cohort 在该 Day 仍有 75% 的用户回访 | P2 |

### 业务要点

- **行 = cohort_date，列 = retention_day，值 = retention_rate_pct** → 热力图
- D0 始终为 100%（首日所有人都"在"）
- **实际共 44 行**（9 天窗口 × ~5 个 Cohort），非旧版文档中的 704 行（那是 82 天窗口的理论行数）
- 热力图的对角线衰减速度反映平台粘性
- 纵向比较（同一 retention_day 不同 cohort_date）可观察不同批次用户的质量差异

---

## 8. cohort_retention_summary

**粒度**：1 行 / 留存天数 — 共 9 行
**用途**：留存衰减曲线（折线图），展示所有 Cohort 的平均留存趋势
**来源 SQL**：`02_funnel_retention.sql §3`（AVG 聚合自 `cohort_retention_detail`）
**Dashboard**：Page 1 Executive Overview（图表 3）· Page 2 Funnel & Retention（图表 4）
**Excel**：Sheet `cohort_retention_summary`

| # | 字段名称 | 字段含义 | 计算逻辑 | 业务解释 | 使用页面 |
|---|----------|----------|----------|----------|----------|
| 1 | `retention_day` | 留存天数 | 0 ~ 8 | X 轴：距首日的天数 | P1 P2 |
| 2 | `total_retained_users` | 汇总留存用户数 | 所有 Cohort 在该 retention_day 的留存用户总和 | 用于计算加权平均留存率 | P1 P2 |
| 3 | `total_cohort_users` | 汇总 Cohort 总用户数 | 所有 Cohort 的总用户数之和 | 留存率的分母 | P1 P2 |
| 4 | `avg_retention_rate_pct` | 平均留存率 (%) | `total_retained_users / total_cohort_users × 100` | **Y 轴核心指标。** D1=78.8%, D7=98.5%（周末回峰）。 | P1 P2 |

### 业务要点

- D1 留存 ~78.8%（11/25 Cohort 的次日回访率）
- D7 跳至 98.5% 为周末周期效应（D7 恰好是周六，用户回访高峰）
- P1 图表 3 用折线图展示，标注 D1 和 D7 两个关键点
- 9 天窗口（D0~D8）限制长期留存观测

---

## 9. daily_behavior_summary

**粒度**：1 行 / 日期 — 共 9 行
**用途**：DAU 趋势图、购买率趋势、日度对比
**来源 SQL**：`03_behavior_analysis.sql §1`
**Dashboard**：Page 1 Executive Overview · Page 3 User Behavior
**Excel**：Sheet `daily_behavior_summary`

| # | 字段名称 | 字段含义 | 计算逻辑 | 业务解释 | 使用页面 |
|---|----------|----------|----------|----------|----------|
| 1 | `dt` | 日期 | `DATE(ts)` — 精确到天 | 分析日期，范围 2017-11-25 ~ 2017-12-03 | P1 P3 |
| 2 | `dau` | 日活跃用户数 | `COUNT(DISTINCT user_id)` per day | 当天至少产生 1 条行为记录的去重用户数。**核心流量指标。** | P1 P3 |
| 3 | `total_actions` | 总行为数 | `COUNT(*)` per day | 当天所有行为记录的总和（PV + FAV + CART + BUY） | P3 |
| 4 | `pv_cnt` | 浏览(PV)次数 | `SUM(CASE WHEN behavior_type='pv' THEN 1)` | 当天浏览行为次数 | P3 |
| 5 | `fav_cnt` | 收藏(FAV)次数 | `SUM(CASE WHEN behavior_type='fav' THEN 1)` | 当天收藏行为次数 | P3 |
| 6 | `cart_cnt` | 加购(CART)次数 | `SUM(CASE WHEN behavior_type='cart' THEN 1)` | 当天加购行为次数 | P3 |
| 7 | `buy_cnt` | 购买(BUY)次数 | `SUM(CASE WHEN behavior_type='buy' THEN 1)` | 当天购买行为次数。**GMV 代理指标。** | P1 P3 |
| 8 | `buy_rate_pct` | 购买率 (%) | `buy_cnt / total_actions × 100` | 当天所有行为中购买占比。**注意这是行为维度，非用户维度。** 约 2% 为正常水平。 | P1 P3 |
| 9 | `fav_rate_pct` | 收藏率 (%) | `fav_cnt / total_actions × 100` | 当天行为中收藏占比 | P3 |
| 10 | `cart_rate_pct` | 加购率 (%) | `cart_cnt / total_actions × 100` | 当天行为中加购占比 | P3 |
| 11 | `avg_actions_per_user` | 人均行为数 | `total_actions / dau` | 当天人均产生的行为次数。**反映用户参与深度。** 可与 DAU 结合判断"流量质量"。 | P3 |

### 业务要点

- **DAU 趋势**是平台健康度的核心时序指标，周末通常明显高于工作日
- **buy_rate_pct 趋势**更关键——DAU 涨但购买率跌，说明流量质量下降
- **avg_actions_per_user** 是衡量"用户粘性深度"的有效指标
- 共 9 行数据（9 天窗口），非旧版文档中的 82 行

---

## 10. hourly_behavior_summary

**粒度**：1 行 / 小时 — 共 24 行
**用途**：24 小时行为分布热力图、推送时段分析
**来源 SQL**：`03_behavior_analysis.sql §2`
**Dashboard**：Page 3 User Behavior
**Excel**：Sheet `hourly_behavior_summary`

| # | 字段名称 | 字段含义 | 计算逻辑 | 业务解释 | 使用页面 |
|---|----------|----------|----------|----------|----------|
| 1 | `hour` | 小时 (0-23) | `CAST(hour AS INTEGER)` — 取自 timestamp 的小时部分 | 0 = 凌晨 0:00-0:59，23 = 23:00-23:59 | P3 |
| 2 | `actions` | 总行为数 | `COUNT(*)` per hour | 该小时的所有行为记录数。**用于定位流量峰值。** | P3 |
| 3 | `pv_cnt` | 浏览次数 | `SUM(CASE WHEN behavior_type='pv' THEN 1)` | 该小时的 PV 量 | P3 |
| 4 | `fav_cnt` | 收藏次数 | `SUM(CASE WHEN behavior_type='fav' THEN 1)` | 该小时的收藏量 | P3 |
| 5 | `cart_cnt` | 加购次数 | `SUM(CASE WHEN behavior_type='cart' THEN 1)` | 该小时的加购量 | P3 |
| 6 | `buy_cnt` | 购买次数 | `SUM(CASE WHEN behavior_type='buy' THEN 1)` | 该小时的购买量 | P3 |
| 7 | `buy_rate_pct` | 购买率 (%) | `buy_cnt / actions × 100` | 该小时行为→购买的转化率。**用于发现"购买效率"最高的时段。** | P3 |
| 8 | `uv` | 独立用户数 | `COUNT(DISTINCT user_id)` per hour | 该小时活跃的去重用户数 | P3 |

### 业务要点

- 图表类型：堆叠柱状（PV/FAV/CART/BUY 分色） + 购买率折线（双轴）
- 典型模式：10-12 点、14-16 点、20-22 点为三个高峰
- **购买率峰值时段 ≠ 流量峰值时段**：10:00 购买率最高(2.62%)，21:00 流量最高但购买率仅 1.73%
- 推送排期建议：在购买率峰值前 30 分钟触达（如 9:30 而非 20:00）

---

## 11. weekday_behavior_summary

**粒度**：1 行 / 日期类型 — 共 2 行（工作日 × 1, 周末 × 1）
**用途**：周末 vs 工作日分组柱状图，揭示"流量潮汐"模式
**来源 SQL**：`03_behavior_analysis.sql §3`（按 `is_weekend` 聚合自 `daily_behavior_summary`）
**Dashboard**：Page 3 User Behavior（图表 3 — 分组柱状图）
**Excel**：Sheet `weekday_behavior_summary`

| # | 字段名称 | 字段含义 | 计算逻辑 | 业务解释 | 使用页面 |
|---|----------|----------|----------|----------|----------|
| 1 | `is_weekend` | 是否周末 | 0 = 工作日, 1 = 周末 | 分组标识 | P3 |
| 2 | `day_type` | 日期类型名称 | "工作日" / "周末" | 图表 X 轴标签 | P3 |
| 3 | `day_cnt` | 天数 | 工作日/周末的天数 | 工作日 6 天, 周末 3 天（9 天窗口） | P3 |
| 4 | `avg_dau` | 平均 DAU | `AVG(dau)` per day_type | **核心对比指标。** 周末 DAU 通常高于工作日。 | P3 |
| 5 | `avg_actions` | 平均日行为数 | `AVG(total_actions)` per day_type | 周末总行为量 vs 工作日 | P3 |
| 6 | `avg_buy` | 平均日购买数 | `AVG(buy_cnt)` per day_type | 购买行为的绝对量对比 | P3 |
| 7 | `avg_buy_rate_pct` | 平均购买率 (%) | `AVG(buy_rate_pct)` per day_type | **周末是否同比例提升？** 如果周末 DAU↑ 但购买率↓ → 流量质量下降 | P3 |
| 8 | `avg_cart_rate_pct` | 平均加购率 (%) | `AVG(cart_rate_pct)` per day_type | 加购率的工作日/周末差异 | P3 |

### 业务要点

- 仅 2 行数据，直接用于 Power BI 分组柱状图（Clustered Bar Chart）
- **核心发现**：周末 DAU +122% 但购买率 -10% — "逛"与"买"的时间错位
- 运营启示：周末适合做内容运营和发现推荐，工作日做促销转化

---

## 12. session_stats

**粒度**：1 行 / Session 长度分组 — 共 5 行
**用途**：Session 长度 × 购买率阶梯图，揭示"6 行为临界点"
**来源 SQL**：`03_behavior_analysis.sql §4`
**Dashboard**：Page 3 User Behavior（图表 4 — 阶梯折线图）
**Excel**：Sheet `session_stats`

| # | 字段名称 | 字段含义 | 计算逻辑 | 业务解释 | 使用页面 |
|---|----------|----------|----------|----------|----------|
| 1 | `session_length_group` | Session 分组 | "1次" / "2-5次" / "6-20次" / "21-50次" / "50+次" | X 轴标签 | P3 |
| 2 | `session_cnt` | Session 数量 | 该分组的 Session 总数 | 各分组的绝对 Session 量 | P3 |
| 3 | `session_pct` | Session 占比 (%) | `session_cnt / total_sessions × 100` | **68% Session ≤5 行为** — 大多数 Session 无效交互 | P3 |
| 4 | `buy_session_cnt` | 含购买的 Session 数 | 该分组中至少含 1 次购买的 Session 数 | 有效 Session 的绝对数量 | P3 |
| 5 | `buy_rate_pct` | Session 购买率 (%) | `buy_session_cnt / session_cnt × 100` | **Y 轴核心指标。** 6-20 组购买率翻倍（7.5%→13.0%）。 | P3 |
| 6 | `avg_actions` | Session 平均行为数 | 该分组 Session 的平均行为数 | 辅助参考 | P3 |
| 7 | `avg_duration_min` | Session 平均时长（分钟） | 该分组 Session 的平均时长 | 辅助参考 | P3 |

### 业务要点

- **"6 行为临界点"** 是核心发现：≥6 行为的 Session 购买率翻倍（从 7.5% → 13.0%）
- 运营策略：优化推荐位质量，帮助用户在前 5 个推荐位命中兴趣
- 图表类型：阶梯折线图（Step Line），6-20 组标红加粗突出

---

## 13. category_conversion

**粒度**：1 行 / 类目 — 共 8,787 行
**用途**：类目波士顿矩阵散点图、Top/Bottom 排行榜
**来源 SQL**：`04_product_analysis.sql §1`
**基础中间表**：`category_base_stats`（避免重扫 2,900 万行）
**Dashboard**：Page 4 Product Analysis
**Excel**：Sheet `category_conversion`

| # | 字段名称 | 字段含义 | 计算逻辑 | 业务解释 | 使用页面 |
|---|----------|----------|----------|----------|----------|
| 1 | `category_id` | 类目 ID | 脱敏整型 ID，范围 80 ~ 5,162,429 | 淘宝商品类目标识（脱敏） | P4 |
| 2 | `total_actions` | 总行为数 | `COUNT(*)` per category | 该类目下所有行为的总次数。**衡量类目热度。** | P4 |
| 3 | `pv_cnt` | 浏览次数 | `SUM(behavior_type='pv')` per category | 该类目的 PV 总量。**类目曝光量的代理指标。** | P4 |
| 4 | `fav_cnt` | 收藏次数 | `SUM(behavior_type='fav')` per category | 该类目的收藏总量 | P4 |
| 5 | `cart_cnt` | 加购次数 | `SUM(behavior_type='cart')` per category | 该类目的加购总量 | P4 |
| 6 | `buy_cnt` | 购买次数 | `SUM(behavior_type='buy')` per category | 该类目的购买总量。**类目 GMV 贡献的代理指标。** | P4 |
| 7 | `uv` | 独立用户数 | `COUNT(DISTINCT user_id)` per category | 接触过该类目的去重用户数 | P4 |
| 8 | `item_cnt` | 商品数 | `COUNT(DISTINCT item_id)` per category | 该类目下的去重商品数。**类目丰富度。** | P4 |
| 9 | `buy_uv` | 购买用户数 | `COUNT(DISTINCT user_id WHERE buy)` per category | 在该类目完成过购买的去重用户数 | P4 |
| 10 | `fav_rate_pct` | 收藏率 (%) | `fav_cnt / pv_cnt × 100` | 该类目浏览→收藏的转化效率。**行为维度。** | P4 |
| 11 | `cart_rate_pct` | 加购率 (%) | `cart_cnt / pv_cnt × 100` | 该类目浏览→加购的转化效率 | P4 |
| 12 | `buy_rate_pct` | 购买率 (%) | `buy_cnt / pv_cnt × 100` | 该类目浏览→购买的转化效率。**核心转化指标。** 注意：可能存在 >100% 的情况（搜索/推荐直达购买）。 | P4 |
| 13 | `user_buy_rate_pct` | 用户购买率 (%) | `buy_uv / uv × 100` | 该类目用户→购买用户的转化率。**用户维度，比行为维度的 buy_rate_pct 更精确。** | P4 |
| 14 | `exposure_rank` | 曝光排名 | `ROW_NUMBER() OVER (ORDER BY pv_cnt DESC)` | 1 = PV 最高的类目 | P4 |
| 15 | `conversion_rank` | 转化排名 | `ROW_NUMBER() OVER (ORDER BY buy_rate_pct DESC)` | 1 = 购买率最高的类目 | P4 |

### 业务要点

- **波士顿矩阵**：X 轴 = exposure_rank（逆序），Y 轴 = buy_rate_pct，气泡大小 = total_actions
  - 左上（低曝光高转化）→ **"宝藏类目"，增加推荐权重**
  - 右下（高曝光低转化）→ **"资源浪费"，降低推荐权重**
- **exposure_rank 与 conversion_rank 的差距**反映类目层级的资源错配程度
- `buy_rate_pct > 100%` 的类目：用户通过搜索/推荐直达购买，应优化搜索曝光

---

## 14. item_conversion

**粒度**：1 行 / 商品 — 共 2,584,912 行（**Excel 超限，仅 Parquet 直连 Power BI 或 `--all` 模式导出**）
**用途**：商品转化明细表、下钻分析
**来源 SQL**：`04_product_analysis.sql §2`
**Dashboard**：Page 4 Product Analysis（下钻明细）
**Excel**：仅 `--all` 模式导出（默认跳过）

| # | 字段名称 | 字段含义 | 计算逻辑 | 业务解释 | 使用页面 |
|---|----------|----------|----------|----------|----------|
| 1 | `item_id` | 商品 ID | 脱敏整型 ID，范围 1 ~ 5,163,068 | 商品唯一标识（脱敏） | P4 |
| 2 | `category_id` | 所属类目 ID | 商品→类目映射 | 关联 `category_conversion.category_id` | P4 |
| 3 | `total_actions` | 总行为数 | `COUNT(*)` per item | 该商品的行为总量 | P4 |
| 4 | `pv_cnt` | 浏览次数 | `SUM(behavior_type='pv')` per item | **商品的曝光量代理。** 用于定义"高曝光"阈值 (≥P75)。 | P4 |
| 5 | `fav_cnt` | 收藏次数 | `SUM(behavior_type='fav')` per item | 该商品被收藏次数 | P4 |
| 6 | `cart_cnt` | 加购次数 | `SUM(behavior_type='cart')` per item | 该商品被加购次数。**高意向信号。** | P4 |
| 7 | `buy_cnt` | 购买次数 | `SUM(behavior_type='buy')` per item | 该商品被购买次数 | P4 |
| 8 | `uv` | 独立用户数 | `COUNT(DISTINCT user_id)` per item | 接触过该商品的去重用户数 | P4 |
| 9 | `buy_uv` | 购买用户数 | `COUNT(DISTINCT user_id WHERE buy)` per item | 购买过该商品的去重用户数 | P4 |
| 10 | `fav_rate_pct` | 收藏率 (%) | `fav_cnt / pv_cnt × 100` | 浏览后收藏的比例 | P4 |
| 11 | `cart_rate_pct` | 加购率 (%) | `cart_cnt / pv_cnt × 100` | 浏览后加购的比例。**比 buy_rate 更灵敏的转化信号。** | P4 |
| 12 | `buy_rate_pct` | 购买率 (%) | `buy_cnt / pv_cnt × 100` | **核心转化指标。** 0% 意味着大量曝光零转化。 | P4 |
| 13 | `user_buy_rate_pct` | 用户购买率 (%) | `buy_uv / uv × 100` | 用户维度的转化率，消除单人多次购买的偏差 | P4 |
| 14 | `exposure_rank` | 曝光排名 | `ROW_NUMBER() OVER (ORDER BY pv_cnt DESC)` | 按 PV 降序排名。1 = 曝光最高的商品。 | P4 |
| 15 | `conversion_rank` | 转化排名 | `ROW_NUMBER() OVER (ORDER BY buy_rate_pct DESC)` | 按购买率降序排名。1 = 转化率最高的商品。 | P4 |

### 业务要点

- **此表 258 万行**，不适合导出 Excel（104 万行上限）。Power BI 直接导入 Parquet。
- 曝光排名 (exposure_rank) 与转化排名 (conversion_rank) 的差距是识别"问题商品"的核心逻辑
- `buy_rate_pct = 0` 且 `pv_cnt` 极高 → 严重问题商品，需排查详情页/价格/相关性
- `buy_cnt > 0 AND pv_cnt = 0` → 搜索直达型商品，见 `search_direct_items`

---

## 15. high_exposure_low_conversion_items

**粒度**：1 行 / 问题商品 — 共 512,540 行
**用途**：高曝光低转化商品明细表、曝光-转化排名差距直方图
**来源 SQL**：`04_product_analysis.sql §3`（从 `item_conversion` 筛选：pv_cnt ≥ P75 且 buy_rate_pct ≤ 中位数）
**Dashboard**：Page 4 Product Analysis（图表 3/4/5）
**Excel**：Sheet `high_exposure_low_conversion_it`（31 字符截断）

| # | 字段名称 | 字段含义 | 计算逻辑 | 业务解释 | 使用页面 |
|---|----------|----------|----------|----------|----------|
| 1 | `item_id` | 商品 ID | 脱敏整型 ID | 问题商品的唯一标识 | P4 |
| 2 | `category_id` | 所属类目 ID | 商品→类目映射 | 关联 `category_conversion` 获取类目转化信息 | P4 |
| 3 | `pv_cnt` | 浏览次数 | 该商品的 PV 量 | 衡量"高曝光"程度 | P4 |
| 4 | `fav_cnt` | 收藏次数 | 该商品的收藏量 | 中间行为信号 | P4 |
| 5 | `cart_cnt` | 加购次数 | 该商品的加购量 | 中间行为信号 | P4 |
| 6 | `buy_cnt` | 购买次数 | 该商品的购买量。**多数为 0。** | 转化结果 | P4 |
| 7 | `buy_rate_pct` | 购买率 (%) | `buy_cnt / pv_cnt × 100` | 核心问题指标。多数 ≤ 中位数。 | P4 |
| 8 | `cart_rate_pct` | 加购率 (%) | `cart_cnt / pv_cnt × 100` | 中间转化信号 | P4 |
| 9 | `exposure_rank` | 曝光排名 | 在全体商品中的 PV 排名 | 越小曝光越高 | P4 |
| 10 | `conversion_rank` | 转化排名 | 在全体商品中的购买率排名 | 越小转化越高 | P4 |
| 11 | `exposure_conversion_gap` | 曝光-转化差距 | `exposure_rank - conversion_rank` | **排名差距越大，商品越"名不副实"。** 正值 = 曝光排名好于转化排名（曝高转低）。 | P4 |

### 业务要点

- **筛选条件**：pv_cnt ≥ P75（高曝光）AND buy_rate_pct ≤ 中位数（低转化）
- **51.3 万件问题商品**消耗了大量推荐流量但几乎不贡献交易
- 在 Power BI 中建议：对 `exposure_conversion_gap > 500,000` 的商品做降权处理
- 表格条件格式：`buy_rate_pct = 0` → 深红背景；`cart_rate_pct = 0` → 橙色背景

---

## 16. search_direct_items

**粒度**：1 行 / 搜索直达商品 — 共 11,781 行
**用途**：识别"被购买但无浏览"的商品（搜索/推荐直达购买），定位被低估的高转化商品
**来源 SQL**：`08_powerbi_supplement.sql §2`（从 `item_conversion` 筛选 `buy_cnt > 0 AND pv_cnt = 0`）
**Dashboard**：Page 4 Product Analysis（图表 4 — 搜索直达型商品分布）
**Excel**：未导出到默认 Excel（可用 `--all` 或 Parquet 直连 Power BI）

| # | 字段名称 | 字段含义 | 计算逻辑 | 业务解释 | 使用页面 |
|---|----------|----------|----------|----------|----------|
| 1 | `item_id` | 商品 ID | 脱敏整型 ID | 搜索直达商品的唯一标识 | P4 |
| 2 | `category_id` | 所属类目 ID | 商品→类目映射 | 关联 `category_conversion` | P4 |
| 3 | `buy_cnt` | 购买次数 | 该商品被购买的次数 | 零曝光但已有购买 — **搜索/推荐直达信号** | P4 |
| 4 | `cart_cnt` | 加购次数 | 该商品被加购的次数 | 中间行为信号 | P4 |
| 5 | `buy_uv` | 购买用户数 | 购买过该商品的去重用户数 | 购买用户规模 | P4 |
| 6 | `exposure_rank` | 曝光排名 | 在全体商品中的 PV 排名 | 该商品的曝光排名（由于 pv_cnt=0，排名靠后） | P4 |
| 7 | `conversion_rank` | 转化排名 | 在全体商品中的购买率排名 | 无浏览但转化率高 — 排名可能有偏 | P4 |

### 业务要点

- **11,781 件商品**被购买但从未被"浏览"（pv_cnt = 0）
- 用户通过搜索/推荐直达购买 → **这些是"被低估的宝藏"**
- 应增加这些商品的搜索曝光和推荐权重
- 按类目汇总版见 `search_direct_by_category`

---

## 17. search_direct_by_category

**粒度**：1 行 / 类目 — 共 2,933 行
**用途**：搜索直达商品按类目汇总，识别搜索直达集中的类目
**来源 SQL**：`08_powerbi_supplement.sql §3`（从 `search_direct_items` 按 `category_id` 聚合）
**Dashboard**：Page 4 Product Analysis（图表 4 辅助分析）
**Excel**：Sheet `search_direct_by_category`

| # | 字段名称 | 字段含义 | 计算逻辑 | 业务解释 | 使用页面 |
|---|----------|----------|----------|----------|----------|
| 1 | `category_id` | 类目 ID | 脱敏整型 ID | 搜索直达商品所属类目 | P4 |
| 2 | `direct_item_cnt` | 搜索直达商品数 | 该类目下搜索直达商品的数量 | **核心指标。** 越大说明该类目"搜索直达"现象越普遍 | P4 |
| 3 | `total_buy_cnt` | 总购买次数 | 该类目搜索直达商品的总购买次数 | 搜索直达带来的 GMV 代理 | P4 |
| 4 | `total_buy_uv` | 总购买用户数 | 该类目搜索直达商品的总购买用户数 | 搜索直达覆盖的用户规模 | P4 |
| 5 | `avg_buy_per_item` | 件均购买次数 | `total_buy_cnt / direct_item_cnt` | 搜索直达商品的平均购买密度 | P4 |

### 业务要点

- 关联 `category_conversion` 可计算搜索直达占类目总购买的比例
- Top 5 类目（按 direct_item_cnt）是搜索直达优化的优先对象
- 2,933 个类目含有搜索直达商品（8,787 个总类目中约 33%）

---

## 18. user_cluster_summary

**粒度**：1 行 / 聚类 — 共 5 行
**用途**：用户分群概览、策略卡片、雷达图、价值矩阵
**来源**：`src/cluster_analysis.py` → 基于 `user_features` (35 维) + KMeans (K=5) 聚合
**Dashboard**：Page 1 Executive Overview · Page 5 User Segmentation
**Excel**：Sheet `user_cluster_summary`

### 18.1 标识与分群字段

| # | 字段名称 | 字段含义 | 计算逻辑 | 业务解释 | 使用页面 |
|---|----------|----------|----------|----------|----------|
| 1 | `cluster` | 聚类编号 (0-4) | KMeans 输出标签 | C0~C4，与 Python 聚类结果一一对应 | P1 P5 |
| 2 | `persona_name` | 用户画像名称 | 分析师根据聚类特征手工标注 | C0=探索型浏览用户, C1=高价值用户, C2=核心高价值用户, C3=高浏览低转化用户, C4=潜力转化用户 | P1 P5 |
| 3 | `icon` | 分群标签 | 分析师手工标注 | `[CORE]`=核心用户, `[POTENTIAL]`=潜力用户, `[EXPLORE]`=探索型, `[BROWSE]`=浏览型 | P5 |
| 4 | `priority` | 运营优先级 | 分析师根据购买率和规模综合评定 | P0-维护 > P1-转化 > P2-引导。**决定运营资源分配顺序。** | P5 |

### 18.2 规模与价值字段

| # | 字段名称 | 字段含义 | 计算逻辑 | 业务解释 | 使用页面 |
|---|----------|----------|----------|----------|----------|
| 5 | `user_cnt` | 用户数 | 聚类中的用户总数 | 该分群的绝对规模。C3 最大（84,175）、C1 最小（31,790） | P1 P5 |
| 6 | `user_pct` | 用户占比 (%) | `user_cnt / total_users × 100` | 5 个聚类占比之和 = 100% | P1 P5 |
| 7 | `buy_rate_pct` | 购买率 (%) | 该聚类中 `is_buyer=1` 的用户占比 | **核心价值指标。** C2=9.4% vs C3=0.8% — 差距 11.75 倍。 | P1 P5 |

### 18.3 行为特征字段

| # | 字段名称 | 字段含义 | 计算逻辑 | 业务解释 | 使用页面 |
|---|----------|----------|----------|----------|----------|
| 8 | `avg_pv` | 人均 PV | 该聚类用户 PV 的均值 | 反映浏览活跃度。C0=198（逛街型），C4=30（目标明确型） | P5 |
| 9 | `avg_active_days` | 人均活跃天数 | 该聚类用户 active_days 的均值 | 9 天窗口内的活跃天数。C0=8.4 天（几乎每天），C1=4.9 天 | P5 |
| 10 | `avg_lifecycle_days` | 人均生命周期（天） | 末次活跃 - 首次活跃 + 1 的均值 | 用户在平台上的总跨度天数 | P5 |
| 11 | `category_diversity` | 人均类目广度 | 该聚类用户浏览过的去重类目数均值 | **衡量兴趣广度。** C0=43.6（兴趣极广），C4=11.3（兴趣集中） | P5 |
| 12 | `cart_to_buy_rate` | 加购→购买率 (%) | 购买次数 / 加购次数 × 100 的聚类均值 | **>100% 表示用户多次购买同一商品（购买>加购），即复购信号。** C2=137.7% → 复购型用户。 | P5 |

### 18.4 时域特征字段

| # | 字段名称 | 字段含义 | 计算逻辑 | 业务解释 | 使用页面 |
|---|----------|----------|----------|----------|----------|
| 13 | `recent_7d_pct` | 近 7 日活跃占比 (%) | 最近 7 天中有活跃行为的天数占比的均值 | 衡量用户近期活跃度 | P5 |
| 14 | `weekly_volatility` | 行为稳定性 | 各周行为数的标准差 / 均值（变异系数） | **越低越稳定。** C1=0.001（行为极其规律），C3=0.838（行为波动大） | P5 |

### 18.5 运营策略字段

| # | 字段名称 | 字段含义 | 计算逻辑 | 业务解释 | 使用页面 |
|---|----------|----------|----------|----------|----------|
| 15 | `strategies` | 运营策略 | 分析师根据聚类画像手工制定 | 具体的运营动作组合 | P5 |
| 16 | `channel` | 触达渠道 | 分析师推荐 | Push + 短信 + 站内信等 | P5 |

### 各聚类速查

| Cluster | 画像名称 | 占比 | 购买率 | 人均 PV | 优先度 | 一句话策略 |
|---------|----------|------|--------|---------|--------|-----------|
| C0 | 探索型浏览用户 | 20.3% | 2.0% | 198 | P2-引导 | 品类发现推荐 + 首单激励 |
| C1 | 高价值用户 | 11.1% | 5.2% | 41 | P0-维护 | 会员升级 + VIP 活动 |
| C2 | 核心高价值用户 | 20.1% | 9.4% | 71 | P0-维护 | 会员权益升级 + 复购激励 |
| C3 | 高浏览低转化用户 | 29.3% | 0.8% | 89 | P1-转化 | 首单大额券 + 降价提醒 |
| C4 | 潜力转化用户 | 19.2% | 4.2% | 30 | P1-转化 | 加购未购限时折扣 + 品类优惠券 |

---

## 19. user_cluster_result

**粒度**：1 行 / 用户 — 共 287,004 行（**Excel 超限，仅 Parquet 直连 Power BI 或 `--all` 模式导出**）
**用途**：个体用户的聚类标签，下钻分析和交叉分析
**来源**：`src/cluster_analysis.py` — KMeans 预测结果
**Dashboard**：Page 5 User Segmentation（下钻分析）
**Excel**：仅 `--all` 模式导出（默认跳过）

| # | 字段名称 | 字段含义 | 计算逻辑 | 业务解释 | 使用页面 |
|---|----------|----------|----------|----------|----------|
| 1 | `user_id` | 用户 ID | 脱敏整型 ID | 用户唯一标识 | P5 |
| 2 | `cluster` | 聚类编号 (0-4) | KMeans 预测标签 | 与 `user_cluster_summary.cluster` 关联 | P5 |

### 业务要点

- **28.7 万行**，不适合导出 Excel。Power BI 直接导入 Parquet
- 主键：`user_id`
- 通过 `cluster` 字段与 `user_cluster_summary` 建立 1:N 关系
- 用于下钻：点击某个 Cluster → 展示该 Cluster 的用户明细

---

## 20. user_segment_summary

**粒度**：1 行 / 频次分组 — 共 6 行
**用途**：按行为频次分群的用户画像对比，用于 P5 交叉分析表
**来源 SQL**：`05_user_segmentation.sql`
**Dashboard**：Page 5 User Segmentation（图表 6 — 交叉表）
**Excel**：Sheet `user_segment_summary`

| # | 字段名称 | 字段含义 | 计算逻辑 | 业务解释 | 使用页面 |
|---|----------|----------|----------|----------|----------|
| 1 | `freq_group` | 频次分组 | "1-5" / "6-20" / "21-100" / "101-500" / "500+" | 按总行为数将用户分 5 组（共 6 行含"全体"汇总） | P5 |
| 2 | `user_cnt` | 用户数 | 该分组的用户数 | 各频次段的用户规模 | P5 |
| 3 | `user_pct` | 用户占比 (%) | `user_cnt / total_users × 100` | 用户分布 | P5 |
| 4 | `total_buy_cnt` | 总购买次数 | 该分组的购买行为总数 | 各频次段贡献的购买量 | P5 |
| 5 | `avg_buy_per_user` | 人均购买次数 | `total_buy_cnt / user_cnt` | 各频次段的购买密度 | P5 |
| 6 | `avg_actions_per_user` | 人均行为数 | 该分组的人均行为数 | 对应频次段的均值 | P5 |
| 7 | `avg_active_days` | 人均活跃天数 | 该分组的人均活跃天数 | 活跃天数随频次的变化 | P5 |
| 8 | `buyer_rate_pct` | 购买用户占比 (%) | 该分组中 `is_buyer=1` 的用户占比 | 各频次段的用户维度购买率 | P5 |
| 9 | `avg_buy_rate_pct` | 行为购买率 (%) | 该分组的行为→购买比例 | 行为维度购买率 | P5 |
| 10 | `avg_cart_rate_pct` | 加购率 (%) | 该分组的行为→加购比例 | 各频次段的加购活跃度 | P5 |
| 11 | `avg_fav_rate_pct` | 收藏率 (%) | 该分组的行为→收藏比例 | 各频次段的收藏活跃度 | P5 |
| 12 | `avg_lifecycle_days` | 人均生命周期（天） | 该分组的人均生命周期 | 高频率 = 长生命周期？ | P5 |
| 13 | `repeat_buyer_rate_pct` | 复购率 (%) | 多次购买的用户占比 | **衡量忠诚度。** 高频用户应有更高复购率。 | P5 |

### 业务要点

- 与 `user_cluster_summary` 交叉使用：行=Cluster, 列=freq_group, 值=user_cnt → 交叉表热力图
- 注意：如果包含"全体"汇总行，在 Power BI 中需过滤或单独处理

---

## 21. cluster_temporal_profile

**粒度**：1 行 / 聚类 — 共 5 行
**用途**：每个 Cluster 的时间偏好画像（周末/工作日、早/中/晚/夜），确定最佳触达时间
**来源 SQL**：`08_powerbi_supplement.sql §4`（从 `user_features` JOIN `user_cluster_result` 聚合）
**Dashboard**：Page 5 User Segmentation（图表 5 — 分群 × 周末/工作日行为占比）
**Excel**：Sheet `cluster_temporal_profile`

| # | 字段名称 | 字段含义 | 计算逻辑 | 业务解释 | 使用页面 |
|---|----------|----------|----------|----------|----------|
| 1 | `cluster` | 聚类编号 (0-4) | 与 `user_cluster_summary.cluster` 对应 | 关联 `user_cluster_summary` | P5 |
| 2 | `user_cnt` | 用户数 | 该聚类的用户数 | 验证数据完整性 | P5 |
| 3 | `avg_weekend_ratio_pct` | 周末行为占比 (%) | 该聚类用户在周末产生的行为占比的均值 | **C3=67.4%（周末战士），C4=41.6%（工作日买家）** | P5 |
| 4 | `avg_morning_ratio_pct` | 上午行为占比 (%) | 6:00-12:00 行为占比的均值 | 上午活跃偏好 | P5 |
| 5 | `avg_afternoon_ratio_pct` | 下午行为占比 (%) | 12:00-18:00 行为占比的均值 | 下午活跃偏好 | P5 |
| 6 | `avg_evening_ratio_pct` | 晚间行为占比 (%) | 18:00-24:00 行为占比的均值 | 晚间活跃偏好 | P5 |
| 7 | `avg_night_ratio_pct` | 深夜行为占比 (%) | 0:00-6:00 行为占比的均值 | 深夜活跃偏好 | P5 |
| 8 | `avg_hour_concentration` | 时段集中度 | 行为在 24 小时内的分布集中度（Gini 系数） | 越高说明行为越集中在少数时段 | P5 |
| 9 | `avg_buy_weekend_ratio_pct` | 购买行为周末占比 (%) | 该聚类用户的购买行为在周末的占比 | 购买行为的时间偏好 | P5 |

### 业务要点

- **P5 图表 5 的数据源**（替代原 Dashboard 设计中的 `user_features JOIN user_cluster_result`）
- 每个 Cluster 两根柱（工作日/周末），形成百分比堆叠柱状图
- **运营触达时间建议**：
  - C3（周末战士）：周六上午 10:00 触达
  - C4（工作日买家）：周三/四下午 14:00-16:00 触达
  - C0（探索型）：晚间 20:00 触达（晚间占比高）
- 关联 `user_cluster_summary` 的 `strategies` 和 `channel` 字段，制定"谁×何时×什么渠道×什么内容"的精准运营计划

---

## 附录 A：数据类型速查

| 表名 | 行数 | 列数 | 主键 | 关联表 | Excel 导出 |
|------|------|------|------|--------|-----------|
| `dim_date` | 9 | 8 | `dt` | `daily_behavior_summary`, `cohort_retention_detail` | ✓ |
| `dim_category` | 8,787 | 3 | `category_id` | `category_conversion`, `item_conversion`, `high_exposure_low_conversion_items`, `search_direct_items`, `search_direct_by_category` | ✓ |
| `profiling_summary` | 33 | 3 | `metric` | — | ✓ |
| `user_conversion_summary` | 1 | 10 | — | — | ✓ |
| `funnel_summary` | 4 | 5 | `stage` | — | ✓ |
| `funnel_path_detail` | 6 | 4 | `path_from` | — | ✓ |
| `cohort_retention_detail` | 44 | 5 | `(cohort_date, retention_day)` | `dim_date` | ✓ |
| `cohort_retention_summary` | 9 | 4 | `retention_day` | — | ✓ |
| `daily_behavior_summary` | 9 | 11 | `dt` | `dim_date` | ✓ |
| `hourly_behavior_summary` | 24 | 8 | `hour` | — | ✓ |
| `weekday_behavior_summary` | 2 | 8 | `is_weekend` | — | ✓ |
| `session_stats` | 5 | 7 | `session_length_group` | — | ✓ |
| `category_conversion` | 8,787 | 15 | `category_id` | `dim_category` | ✓ |
| `item_conversion` | 2,584,912 | 15 | `item_id` | `category_conversion` | 仅 --all |
| `high_exposure_low_conversion_items` | 512,540 | 11 | `item_id` | `category_conversion` | ✓ |
| `search_direct_items` | 11,781 | 7 | `item_id` | `category_conversion` | Parquet 直连 |
| `search_direct_by_category` | 2,933 | 5 | `category_id` | `dim_category` | ✓ |
| `user_cluster_summary` | 5 | 16 | `cluster` | `user_cluster_result`, `cluster_temporal_profile` | ✓ |
| `user_cluster_result` | 287,004 | 2 | `user_id` | `user_cluster_summary` | 仅 --all |
| `user_segment_summary` | 6 | 13 | `freq_group` | — | ✓ |
| `cluster_temporal_profile` | 5 | 9 | `cluster` | `user_cluster_summary` | ✓ |

---

## 附录 B：Power BI 星型模型关系

### 维度表 → 事实表

```
dim_date[dt] ──1:N── daily_behavior_summary[dt]
dim_date[dt] ──1:N── cohort_retention_detail[cohort_date]

dim_category[category_id] ──1:N── category_conversion[category_id]
dim_category[category_id] ──1:N── item_conversion[category_id]
dim_category[category_id] ──1:N── high_exposure_low_conversion_items[category_id]
dim_category[category_id] ──1:N── search_direct_items[category_id]
dim_category[category_id] ──1:N── search_direct_by_category[category_id]
```

### 用户分群内部关系

```
user_cluster_summary[cluster] ──1:N── user_cluster_result[cluster]
user_cluster_summary[cluster] ──1:N── cluster_temporal_profile[cluster]
```

### 事实表间关联（用于交叉分析）

```
item_conversion[category_id] ──N:1── category_conversion[category_id]
high_exposure_low_conversion_items[category_id] ──N:1── category_conversion[category_id]
search_direct_items[category_id] ──N:1── search_direct_by_category[category_id]
```

### 无需建立关系的独立表

以下表天然独立，直接用于各自页面的图表：

- **`profiling_summary`** — KPI 键值对，独立使用
- **`user_conversion_summary`** — 单行汇总，独立使用
- **`funnel_summary`** — 仅 4 行，独立使用
- **`funnel_path_detail`** — 仅 6 行，独立使用
- **`cohort_retention_summary`** — 仅 9 行，独立使用
- **`hourly_behavior_summary`** — 仅 24 行，独立使用
- **`weekday_behavior_summary`** — 仅 2 行，独立使用
- **`session_stats`** — 仅 5 行，独立使用
- **`user_segment_summary`** — 仅 6 行，独立使用

---

## 附录 C：已知数据注意事项

1. **funnel_summary.conversion_rate_pct** 不是阶段间转化率，而是各阶段 UV 相对 PV UV 的渗透率。阶段间转化率需 DAX 计算（`fav_uv/pv_uv` → `cart_uv/fav_uv` → `buy_uv/cart_uv`）。

2. **category_conversion.buy_rate_pct** 可能 >100%——商品/类目被搜索直达购买时，浏览数 < 购买数。属于正常数据，非异常。

3. **user_cluster_summary.cart_to_buy_rate** >100% 表示该群体存在复购行为（同一商品多次购买）。

4. **item_conversion 表 258 万行**，超出 Excel 104 万行上限，需 Power BI 直接导入 Parquet。`--all` 模式导出时会跳过（行数 > 1,000,000 安全线）。

5. **user_cluster_result 表 28.7 万行**，默认不导出 Excel。使用 `--all` 模式可导出（＜ 100 万安全线）。

6. **日期窗口**：数据窗口为 2017-11-25 ~ 2017-12-03，仅 9 天（周六~次周日），含 3 个周末日 + 6 个工作日。早期日期（2017-04-11 起）的数据已被过滤。

7. **中文编码**：Parquet 中文字段在 Windows 终端可能显示乱码，Power BI 导入后正常显示。Excel 导出后中文正常。

8. **profiling_summary.value** 是 object/字符串类型，Power BI 中需用 `VALUE()` DAX 函数转换后使用。

9. **Excel Sheet 名截断**：`high_exposure_low_conversion_items` 在 Excel 中名为 `high_exposure_low_conversion_it`（31 字符限制）。

10. **search_direct_items** 不在默认 Excel 导出中（补充表，来源于 `08_powerbi_supplement.sql`），在 Power BI 中通过 Parquet 直接导入。其按类目汇总版 `search_direct_by_category` 在默认导出中。

---

## 附录 D：与旧版数据字典的变更记录

| 变更项 | 旧版 (v2.0) | 新版 (v3.0) |
|--------|-------------|-------------|
| 覆盖表数 | 7 张 | **21 张**（全部导出表） |
| 行数来源 | 理论行数（82 天窗口） | **实际行数**（9 天窗口） |
| `cohort_retention_detail` 行数 | 704 | **44** |
| `daily_behavior_summary` 行数 | 82 | **9** |
| `category_conversion` 行数 | 8,788 | **8,787** |
| 新增表 | — | dim_date, dim_category, profiling_summary, user_conversion_summary, funnel_path_detail, cohort_retention_summary, weekday_behavior_summary, session_stats, high_exposure_low_conversion_items, search_direct_items, search_direct_by_category, user_cluster_result, user_segment_summary, cluster_temporal_profile |
| 星型模型关系 | 3 条 | **12 条**（含维度→事实 + 分群内部 + 事实表间关联） |
| 独立表清单 | 无 | **明确列出 9 张无需建立关系的表** |
| Excel 导出说明 | 无 | **详细标注每张表的导出状态** |
