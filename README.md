# 淘宝用户行为分析：短周期转化机会识别 & AI 分析助手

[![Python](https://img.shields.io/badge/Python-3.11-blue)](https://www.python.org/)
[![DuckDB](https://img.shields.io/badge/DuckDB-1.0-yellow)](https://duckdb.org/)
[![Scikit--learn](https://img.shields.io/badge/Scikit--learn-1.5-orange)](https://scikit-learn.org/)
[![Power BI](https://img.shields.io/badge/Power%20BI-Dashboard-gold)](https://powerbi.microsoft.com/)
[![LLM](https://img.shields.io/badge/LLM-Tool%20Use-green)]()

> **2,911 万行 × 9 天 × 28.7 万用户 — 从数据清洗到运营策略的完整分析链路，配合本地 AI Agent 实现分析工作流提效。**

---

## 项目总览（30 秒速览）

```
┌──────────────────────────────────────────────────────────────────┐
│                        A 线 · 业务分析主线                         │
│  ETL → 指标体系 → 8层SQL模块 → 用户分层/聚类 → 异动归因           │
│  → Power BI 3页看板 → 运营策略 S1-S3 + A/B 验证方案               │
│                                                                  │
│  核心成果: 60,891 加购未购用户 · 51.3万 曝光异常商品                │
│           11,781 搜索直达商品 · 周末流量陷阱 · 6行为临界点          │
├──────────────────────────────────────────────────────────────────┤
│                        B 线 · AI 提效辅助                         │
│  LLM Tool Use 编排 · 8个 DuckDB 查询工具 · 规则校验引擎            │
│  Analyst → Reviewer → Strategist 三 Agent 流水线                  │
│                                                                  │
│  提效成果: 指标查询/分析/策略生成半自动化 · 8/8 测试用例通过         │
└──────────────────────────────────────────────────────────────────┘
```

---

## 目录

- [A 线 · 业务分析](#a-线--业务分析主线)
  - [1. 数据概览与分析边界](#1-数据概览与分析边界)
  - [2. 架构设计](#2-架构设计)
  - [3. 核心商业洞察](#3-核心商业洞察)
  - [4. 用户分层体系](#4-用户分层体系)
  - [5. 商品曝光效率分析](#5-商品曝光效率分析)
  - [6. 运营策略与 A/B 验证](#6-运营策略与-ab-验证)
  - [7. Power BI 决策看板](#7-power-bi-决策看板)
- [B 线 · AI 数据分析助手](#b-线--ai-数据分析助手)
  - [8. Agent 架构设计](#8-agent-架构设计)
  - [9. 工具层与规则校验引擎](#9-工具层与规则校验引擎)
  - [10. 三 Agent 协作流水线](#10-三-agent-协作流水线)
- [11. 技术栈与项目结构](#11-技术栈与项目结构)
- [12. 快速开始](#12-快速开始)
- [13. 演进路线图](#13-演进路线图)

---

# A 线 · 业务分析主线

## 1. 数据概览与分析边界

### 1.1 数据来源

| 属性 | 值 |
|------|-----|
| 来源 | 阿里天池 — User Behavior from Taobao |
| 时间范围 | 2017-11-25 ~ 2017-12-03（9 天，3 周末日 + 6 工作日） |
| 规模 | **2,911 万** 行为记录 · **28.7 万** 用户 · **258 万** 商品 · **8,787** 类目 |
| 字段 | `user_id`, `item_id`, `category_id`, `behavior_type` (pv/fav/cart/buy), `timestamp` |

### 1.2 关键边界（面试必读）

| 边界 | 约束 |
|------|------|
| 9 天窗口 | 不推断长期趋势、月度季节性、用户生命周期 |
| pv/fav/cart/buy 非线性 | 不使用"漏斗转化率"，使用"渗透率"或"行为覆盖率" |
| 短周期回访 ≠ 留存 | Day 7 回访率 98.5% 是 ⚠️ **周末周期效应**（周六→周六），非真实长期留存 |
| 窗口内重复购买 ≠ 复购 | 9 天内多次购买 ≠ 长期复购行为 |
| 无价格/画像/曝光来源字段 | GMV 以购买次数代理，商品效率分析仅作行为异常识别 |

### 1.3 维度差异标注（高频易错点）

| 概念 | 数值 | 口径 | 来源 |
|------|------|------|------|
| **行为维度**购买率 | ~2.0% | buy_cnt / total_actions | `daily_behavior_summary.buy_rate_pct` |
| **用户维度**购买率 | 68.0% | is_buyer=1 用户 / 全部用户 | `user_conversion_summary.buy_rate_pct` |
| **窗口内**重复购买率 | 79.3%（口径①） | 购买≥2次用户 / 购买用户 | `user_segment_summary.repeat_buyer_rate_pct` |

> ⚠️ 行为维度 2.0% ≠ 用户维度 68.0% —— 分母不同，结论不同，每次给出购买率必须标注维度。

---

## 2. 架构设计

### 2.1 数据流

```
Raw CSV (1.0 GB)                                               Power BI
    │                                                             ▲
    ▼ data_cleaning.py                                            │
Clean Parquet (337 MB, ZSTD)                                      │
    │                                                             │
    ▼ 00_init.sql (共享基础层: user_base_metrics + dim_date)       │
    │                                                             │
    ├─ 01_profiling.sql ─── 数据质量画像                           │
    ├─ 02_funnel_retention.sql ─── 行为渗透率 & 短周期回访          │
    ├─ 02_behavior_path_signal.sql ─── 非线性路径 & Sankey 数据     │
    ├─ 03_behavior_analysis.sql ─── 日/时/Session 行为分析         │
    ├─ 04_product_analysis.sql ─── 商品 & 类目效率                 │
    ├─ 05_user_analysis.sql ─── 用户画像 & 频次分层                 │
    ├─ 05_cart_abandon_analysis.sql ─── 加购未购专题               │
    ├─ 05_user_behavior_segmentation.sql ─── 5 层规则分层          │
    ├─ 06_feature_mart.sql ─── 35 维特征宽表 (→ sklearn)          │
    ├─ 07_anomaly_attribution.sql ─── 周末/时段/商品异动归因       │
    ├─ 07_export_mart.sql ─── 15 张 Parquet ──────────────────────►│
    ├─ 08_strategy_validation_base.sql ─── A/B 实验分组模拟        │
    ├─ 08_powerbi_supplement.sql ─── Sankey/搜索直达/分群时间偏好   │
    └─ 10_agent_metric_views.sql ─── Agent 专用指标视图            │
```

### 2.2 数据仓库分层

| 层 | 产出 | 消费者 |
|----|------|--------|
| **Raw** | 原始 CSV | ETL |
| **Clean** | `clean_data.parquet` | SQL 全层 |
| **DWD** | `user_base_metrics`, `category_base_stats`（中间表） | 02/05/06 |
| **DWS** | 28 张聚合分析表 | DuckDB 查询 |
| **ADS** | 15 张 Parquet 宽表 | Power BI |
| **Feature** | 35 维特征 Parquet | Python ML |

### 2.3 关键中间表（避免重复扫描）

| 中间表 | 粒度 | 被引用 | 节省扫描 |
|--------|------|--------|----------|
| `user_base_metrics` | user_id | 02/05/06 | ~5,800 万行 |
| `category_base_stats` | category_id | 04 | ~2,900 万行 |

---

## 3. 核心商业洞察

### 🔴 洞察 1：周末流量陷阱 — DAU +16%，购买率 -10%

周末用户以"逛"为主（浏览深度 +16%，加购率基本持平），工作日用户目的明确（买了就走）。**周末应做内容运营（直播/短视频），工作日做促销投入。**

> 来源：`weekend_behavior_summary` — 周末 avg_dau 243,844 vs 工作日 209,593

### 🔴 洞察 2：时序错位 — 21:00 流量峰值 vs 10:00 购买率峰值

| 时段 | 行为量 | 行为维度购买率 | 用户行为特征 |
|------|--------|---------------|-------------|
| **10:00** | ~401 万 | **2.62%** 🔺 | 目的明确，"买了就走" |
| **21:00** | ~697 万 | **1.73%** 🔻 | 睡前浏览，"逛而不买" |

> **运营启示**：促销 Push 安排在 **9:30**（购买率窗口前），限时秒杀安排在 **10:00-11:00** 和 **14:00-15:00**。

> 来源：`hourly_behavior_summary`, `morning_evening_comparison`

### 🔴 洞察 3：Session 6 行为临界点 — 购买率从 7.5% 翻倍至 13.0%

68% 的 Session ≤5 个行为，但超过 6 个行为后购买率翻倍。**前 5 个推荐位必须命中用户兴趣** — 这是产品优化的关键阈值。

> 来源：`session_summary`, `session_stats`

### 🔴 洞察 4：加购未购是真机会，收藏是伪问题

用户行为路径：浏览 → 加购 → 购买，收藏环节被大量跳过（加购渗透率 75.3% vs 收藏渗透率 39.8%）。

| 群体 | 人数 | 关键发现 |
|------|------|---------|
| **加购未购用户** | **60,891 人**（占加购用户 28.3%） | 已表达购买意向，窗口内未完成购买 |
| 加购后购买用户 | ~154,276 人 | 加购到购买是该平台主流转化路径 |

> **不应强行提升收藏率**。真正该优化的是加购未购转化：在加购后 24-48h 内触达，预期转化 10-15%。

> 来源：`cart_abandon_summary`, `cart_buyer_comparison`

### 🔴 洞察 5：0.29% 超级用户驱动 79.3% 窗口内重复购买

| 分群 | 人数 | 占比 | 人均行为 | 窗口内重复购买率 |
|------|------|------|---------|-----------------|
| **超级用户** | 819 | 0.29% | 564 次 | 79.3% |
| 高频用户（预备队） | 107,000 | 37.3% | 101-500 次 | — |

> 来源：`user_frequency_segment`, `user_segment_summary`

---

## 4. 用户分层体系

项目构建了三套互补的用户分群，交叉验证：

### 4.1 规则分层（5 层，优先级逐降）

| 层级 | 名称 | 定义 | 用户数 | 运营优先级 |
|------|------|------|--------|-----------|
| **P0** | 窗口内重复购买用户 | buy_cnt ≥ 2 | ~155K | 最高 — 常购清单、会员权益 |
| **P1** | 加购未购用户 | has_cart=1, is_buyer=0 | **60,891** | 高 — 限时折扣、降价提醒 |
| **P2** | 高浏览弱购买信号 | pv ≥ P75, is_buyer=0 | ~71K | 中 — 首单券、品类收窄 |
| **P3** | 低活跃未购买 | 其余 is_buyer=0 | ~14K | 低 — 轻触达 Push |
| **REF** | 单次购买用户 | buy_cnt=1 | — | 参照组，不主动运营 |

> 来源：`segment_summary`（`05_user_behavior_segmentation.sql`）

### 4.2 KMeans 聚类（5 群，32 维特征）

| Cluster | 占比 | 购买率 | 人均PV | 活跃天 | 用户画像 | 时间偏好 |
|---------|------|--------|--------|--------|----------|----------|
| **C2** | 20.0% | **9.4%** | 71 | 7.6 | 核心高价值 | 均衡（49.5%周末） |
| **C4** | 11.5% | **5.1%** | 41 | 4.9 | 高价值 | 工作日买家（41.6%周末） |
| **C3** | 19.1% | 4.1% | 29 | 5.3 | 潜力转化 | **周末战士（67.4%周末）** |
| **C0** | 20.2% | 2.0% | **198** | 8.4 | 探索型浏览 | 43.6 类目广度 |
| **C1** | 29.2% | 0.8% | 90 | 7.8 | 高浏览低转化 | 待触达 |

> 来源：`user_cluster_summary`, `cluster_temporal_profile`

---

## 5. 商品曝光效率分析

### 5.1 四象限框架

基于 PV 和购买率构建商品四象限：

| 象限 | 定义 | 数量 | 策略 |
|------|------|------|------|
| **高曝光低购买信号** 🔴 | PV ≥ P75, buy_rate ≤ MEDIAN | **51.3 万** 件 | 拆解流量来源，区分自然推荐 vs 付费推广 |
| **高曝光高购买信号** 🟢 | PV ≥ P75, buy_rate > MEDIAN | 少量 | 加大曝光，标杆商品 |
| **低曝光高购买信号** 🟡 | PV < P75, buy_rate > MEDIAN | 1.6 万 件 | "待挖掘宝石"，增加自然推荐曝光 |
| **搜索直达** 🔵 | pv=0, buy>0 | **11,781** 件 | 搜索端增加曝光，可能为复购心智商品 |

### 5.2 关键数字

| 指标 | 数值 | 说明 |
|------|------|------|
| 全量商品 | 2,584,912 件 | — |
| 窗口内零购买商品 | 2,303,732 件（89.1%） | 仅 9 天，含长尾 |
| 高曝光低购买信号商品 | 512,540 件 | PV ≥ P75 但 buy_rate ≤ MEDIAN |
| 搜索直达商品 | 11,781 件 | 无 PV 记录但有购买 |
| 待挖掘宝石商品 | 16,395 件 | 低曝光但高购买率 |

> ⚠️ 无曝光来源/价格/利润字段 — 不直接等同于推荐降权，需先判断曝光来源（自然推荐 vs 付费推广 vs 活动资源位）。

> 来源：`product_efficiency_anomaly_summary`, `high_exposure_low_conversion_items`, `search_direct_items`

---

## 6. 运营策略与 A/B 验证

### 6.1 三策略矩阵（S1-S3）

| 策略 | 目标群体 | 触发条件 | 动作 | 渠道 | 监控指标 |
|------|---------|---------|------|------|---------|
| **S1** 加购召回 | P1 加购未购 ~6.1万人 | 加购后 48h 未购 | 5% 限时折扣券（24h有效）+ Push 提醒 | Push + 站内信 | 加购到购买转化信号率 |
| **S2** 首单激活 | P2 高浏览弱购买信号 | Session ≥ 6 次行为 | 首单 10 元券 + Top 5 品类收窄推荐 | Push + 站内推荐 | 首购率 |
| **S3** 商品治理 | 象限 B 高曝光零购买商品 51.3万件 | 确认为自然推荐且匹配异常 | 降权 50%（仅自然推荐），释放流量给 1.2 万搜索直达商品 | 推荐算法排序层 | 自然推荐位购买率 |

> **S3 核心原则**：不直接降权，先区分曝光来源。商业化推广 / 活动资源位 / 品牌曝光 / 新品冷启动商品豁免降权。

### 6.2 A/B 实验方案（离线设计）

| 实验 | 分组 | 样本量 | 主指标 | 检验方法 |
|------|------|--------|--------|----------|
| **V1** 加购召回 | A(5%折扣) / B(无折扣Push) / C(对照) | 每组 ~20,000 | 加购到购买转化信号率 | χ², α=0.05, power≥0.8 |
| **V2** 首单激活 | 实验（首单券+收窄推荐）/ 对照（正常推荐） | 每组 ~1,660 | 首购率 | χ² |
| **V3** 商品治理 | 实验（治理后推荐）/ 对照（原推荐） | 每组 ~143,500 | 自然推荐位购买率 + 人均PV | t-test |

> ⚠️ 所有 A/B 方案为离线设计，基于历史数据模拟分组，非真实业务实验结果。`converted_users=0`（模拟限制）。

> 来源：`08_strategy_validation_base.sql`, `docs/operation_strategy.md`, `docs/strategy_validation_plan.md`

---

## 7. Power BI 决策看板

基于 Excel 13 张数据表，构建 **3 页精简决策型看板**（每页回答 1 个核心运营问题）：

| 页面 | 核心 KPI | 关键图表 |
|------|----------|----------|
| **Page 1 — 经营概览与转化健康度** | 总用户 28.7万、用户购买率 68.0%、行为购买率 2.0% | DAU 趋势与购买率双轴、行为类型占比、4 阶段行为渗透率条形图 |
| **Page 2 — 时段与行为模式分析** | 21:00 流量峰值 vs 10:00 购买率峰值、Session 6 行为临界点 | 24h 流量×购买率双轴、周末 vs 工作日对比、Session 深度购买率阶梯、类目转化 TOP 50 |
| **Page 3 — 用户分层与运营策略** | 规则分层与 KMeans 聚类 | 用户分层气泡图（X:avg_pv, Y:buyer_rate, Size:user_cnt）、KMeans 5聚类对比、策略卡片组 |

> 详细设计见 `docs/powerbi_dashboard_design.md`

---

# B 线 · AI 数据分析助手

## 8. Agent 架构设计

### 8.1 整体架构

```
用户输入 (CLI)
    │
    ▼
┌──────────────────────────────────────────┐
│           Orchestrator                    │
│  加载 Memory Context → 注入 System Prompt  │
│  → 路由: Single-Agent / Multi-Agent       │
└──────────────┬───────────────────────────┘
               │
    ┌──────────┼──────────┐
    ▼          ▼          ▼
┌────────┐ ┌────────┐ ┌──────────┐
│Analyst │→│Reviewer│→│Strategist│  ← Multi-Agent 流水线
│ (查数据)│ │(规则校验)│ │ (出策略)  │
└───┬────┘ └───┬────┘ └────┬─────┘
    │          │           │
    └──────────┼───────────┘
               ▼
┌──────────────────────────────────────────┐
│         DuckDB Tool Layer (8 工具)         │
│  list_tables · get_table_schema ·          │
│  query_duckdb · query_raw ·                │
│  get_business_context · plot_bar          │
└──────────────┬───────────────────────────┘
               ▼
┌──────────────────────────────────────────┐
│           Data Layer                       │
│  analysis.db (28 聚合表) + 15 Parquet 宽表  │
└──────────────────────────────────────────┘
```

### 8.2 三种运行模式

| 模式 | 命令 | Agent 链路 | 适用场景 |
|------|------|-----------|----------|
| **Single-Agent** | `python src/core_agent.py -q "..."` | 单 LLM 查数据 → 输出结论 | 快速问答、指标查询 |
| **Multi-Agent** | `python src/multi_agent.py -q "..."` | Analyst → Reviewer → Strategist | 深度分析、策略生成 |
| **测试** | `python agent/run_tests.py --offline` | 预置样本 → Reviewer 校验 | CI/回归测试 |

---

## 9. 工具层与规则校验引擎

### 9.1 DuckDB 工具层（8 个 Tool）

| 工具 | 功能 | 类型 |
|------|------|------|
| `list_tables` | 列出所有分析表 | 元数据 |
| `get_table_schema` | 获取表结构和行数 | 元数据 |
| `query_duckdb` | 查询聚合表（analysis.db） | 只读查询 |
| `query_raw` | 查询原始数据（Parquet 直读） | 只读查询 |
| `get_business_context` | 获取指标口径字典 & 数据限制 | 知识检索 |
| `plot_bar` | 生成柱状图（matplotlib） | 可视化 |

### 9.2 非 LLM 规则校验引擎（Reviewer）

Reviewer 使用 **纯 Python 正则规则**（非 LLM），对 Analyst 输出进行三道关卡校验：

| 关卡 | 规则 | 严重级别 |
|------|------|---------|
| **B 级（基础）** | 数字密度 ≥ 3 · 无模糊词 · 内容 ≥ 150 字 | **BLOCKER** |
| **D 级（领域）** | 禁止用语检测（留存率/复购率/流失） · 维度标注检查 · 窗口限制标注 | **BLOCKER** |
| **S 级（策略）** | 策略四要素齐全 · KPI 可量化 · 禁出策略检测 | **BLOCKER** |

> **设计理念**：规则明确的校验用正则（低成本、可解释），语义复杂的问题留给 LLM Reviewer（未来演进）。

### 9.3 Agent 专用知识注入

| 注入源 | 内容 | 注入时机 |
|--------|------|---------|
| `docs/metrics_dictionary.md` | 30+ 指标口径、数据来源、口径风险 | System Prompt |
| `CLAUDE.md` | 表汇总、禁止用语、分层规则 | System Prompt |
| Memory System | 跨 Session 洞察提取（JSON） | 每次对话注入 Top-5 |

---

## 10. 三 Agent 协作流水线

### 10.1 职责分工

| Agent | 实现方式 | 职责 |
|-------|---------|------|
| **Analyst** | LLM + DuckDB Tool Use | 接收分析问题 → 规划工具调用 → 查询数据 → 输出分析结论 |
| **Reviewer** | Python 正则规则引擎（非 LLM） | 校验数字密度、禁止用语、维度标注、策略要素 → FAIL 则触发重试 |
| **Strategist** | LLM（不查数据，仅推理） | 基于 Analyst 结论生成运营策略 → 输出四要素策略卡片 |

### 10.2 Multi-Agent 执行流程

```
Question
  │
  ▼
Analyst (LLM + Tool Use)
  │ → 调用 query_duckdb / get_business_context
  │ → 输出分析结论
  ▼
Reviewer (Python 规则引擎)
  │ → 检查 B/D/S 三级规则
  │ → PASS? ──Yes──→ Strategist
  │ → FAIL? ──→ 返回 feedback → Analyst 重试 (max_retry=2)
  ▼
Strategist (LLM, 仅推理)
  │ → 基于分析结论生成策略
  │ → 输出 [P0] [P1] 策略卡片
  ▼
Final Output (Markdown)
```

### 10.3 测试结果

| 指标 | 数值 |
|------|------|
| 测试用例 | **8/8 全部通过** (T1-T8) |
| Reviewer 评级 | **优秀** |
| 测试模式 | 离线（预置样本 + 规则校验） |
| 覆盖场景 | 指标查询 · 加购分析 · 分群查询 · 异动归因 · 时段分析 · 商品效率 · 策略生成 · A/B 设计 |

---

## 11. 技术栈与项目结构

### 11.1 技术栈

| 层 | 技术 | 用途 |
|----|------|------|
| **ETL** | Python + DuckDB | 数据清洗、类型转换、去重、日期派生 |
| **分析** | DuckDB SQL（15 个文件、14 层顺序执行） | 行为路径、短周期回访、行为分析、商品效率、用户分层 |
| **特征工程** | DuckDB SQL | 35 维用户特征宽表（零空值，可直接建模） |
| **聚类** | Python (sklearn) | KMeans (K=5), Elbow + Silhouette 选 K |
| **可视化** | Python (matplotlib) + Power BI | 6 张分析图表 + 3 页精简决策型看板 |
| **Agent** | Python + LLM API (DeepSeek/Anthropic) | Tool Use 编排、规则校验、策略生成 |

### 11.2 项目结构

```
taobao-user-behavior-analysis/
├── README.md                              # 项目主文档（本文件）
├── CLAUDE.md                              # Claude Code 上下文配置
├── implementation_plan.md                 # 项目执行计划
│
├── sql/                                   # ★ SQL 分析层（15 个文件）
│   ├── run_all.py                         # 全流程编排器（断点续跑、表验证、日志）
│   ├── 00_init.sql                        # 共享基础层
│   ├── 01_profiling.sql                   # 数据画像
│   ├── 02_funnel_retention.sql            # 行为渗透率 & 短周期回访
│   ├── 02_behavior_path_signal.sql        # 非线性路径 & Sankey
│   ├── 03_behavior_analysis.sql           # 日/时/Session 分析
│   ├── 04_product_analysis.sql            # 商品 & 类目分析
│   ├── 05_user_analysis.sql               # 用户画像 & 频次分层
│   ├── 05_cart_abandon_analysis.sql       # 加购未购专题
│   ├── 05_user_behavior_segmentation.sql  # 5 层规则分层
│   ├── 06_feature_mart.sql                # 35 维特征宽表
│   ├── 07_anomaly_attribution.sql         # 异动归因
│   ├── 07_export_mart.sql                 # 统一导出 Parquet
│   ├── 08_strategy_validation_base.sql    # A/B 实验分组模拟
│   ├── 08_powerbi_supplement.sql          # Power BI 补充表
│   └── 10_agent_metric_views.sql          # Agent 专用视图
│
├── src/                                   # Python 模块
│   ├── core_agent.py                      # Single-Agent + LLM 抽象层
│   ├── multi_agent.py                     # Multi-Agent 流水线
│   ├── tools.py                           # DuckDB 工具层（8 个 Tool）
│   ├── user_clustering.py                 # KMeans 聚类
│   ├── cluster_analysis.py                # 聚类分析 & 画像
│   ├── cluster_labels_cn.py               # 中文聚类标签
│   ├── visualization.py                   # 可视化（6 张图表）
│   └── export_for_powerbi.py              # Power BI 工作簿导出
│
├── agent/                                 # Agent 测试 & Reviewer
│   ├── run_tests.py                       # 自动化测试脚本（T1-T8）
│   ├── reviewer.py                        # 规则校验引擎
│   └── test_results.json                  # 测试结果
│
├── docs/                                  # 文档体系
│   ├── metrics_dictionary.md              # ★ 指标口径字典（30+ 指标）
│   ├── data_limitations.md                # 数据限制与分析边界
│   ├── user_segmentation_rules.md         # 用户分层规则
│   ├── operation_strategy.md              # 运营策略设计（S1-S3）
│   ├── strategy_validation_plan.md        # A/B 验证方案
│   ├── anomaly_attribution.md             # 异动归因分析
│   ├── business_narrative.md              # 业务主线定义
│   ├── powerbi_dashboard_design.md        # Power BI 看板设计
│   ├── data_dictionary.md                 # 数据字典
│   └── resume_description.md              # 简历描述（4 版本）
│
├── data/
│   ├── analysis.db                        # DuckDB 分析库
│   ├── clean_data.parquet                 # Clean Layer（337 MB）
│   ├── mart/                              # Power BI 数据源（15 Parquet）
│   └── features/                          # ML 特征表
│
├── outputs/figures/                       # 分析图表（6 张 PNG）
└── experiment_log.md                      # 执行日志（自动生成）
```

---

## 12. 快速开始

```bash
# 1. 安装依赖
pip install duckdb pandas pyarrow scikit-learn matplotlib

# 2. ETL（首次运行）
python sql/data_cleaning.py all

# 3. 全量 SQL 分析 + 自动导出 Parquet
python sql/run_all.py                    # 全部执行
python sql/run_all.py --show-tables      # 查看所有表
python sql/run_all.py --from 05          # 断点续跑

# 4. 用户聚类
python src/user_clustering.py

# 5. 聚类分析 & 可视化
python src/cluster_analysis.py
python src/visualization.py

# 6. Agent 测试
python agent/run_tests.py --offline      # Reviewer 校验测试

# 7. Agent 交互（需 LLM API Key）
python src/core_agent.py -q "加购未购用户有多少？"
python src/multi_agent.py -q "分析周末购买率下降原因"

# 8. Power BI → 导入 data/mart/*.parquet
```

---

## 13. 演进路线图

```
V1 (Current)         V2 (Design)          V3 (Vision)          V4-V5 (Vision)
Static Dataset  →  Incremental Pipeline  →  MCP Tool Layer  →  RAG + Real-time
```

| 能力维度 | V1 当前 | V2 设计 | V3 愿景 |
|----------|:---:|:---:|:---:|
| **数据更新** | 静态快照 | 日度增量 | 日度增量 |
| **Agent 规划** | Prompt 嵌入 | Prompt 嵌入 | 独立 Planner Agent |
| **Agent 校验** | Python 正则 | Python 正则 | LLM Reviewer |
| **工具协议** | Python dispatch | Python dispatch | MCP Server |
| **Memory 检索** | Top-5 最近 | Top-5 最近 | 向量语义相似度 |
| **规则执行** | Markdown 文档 | YAML 可执行引擎 | 热加载 + 自演进 |
| **部署方式** | CLI | CLI + 调度器 | MCP + 调度器 |

> 详细设计见 `implementation_plan.md` 第十五章。

---

## 项目亮点总结

| # | 亮点 | 体现能力 |
|---|------|---------|
| 1 | **SQL-First 架构**：核心分析在 SQL 中完成，Python 仅做 ML，Power BI 仅做可视化 | 数据工程、架构设计 |
| 2 | **完整口径体系**：30+ 指标有明确定义、计算口径、数据来源、口径风险 | 数据质量意识 |
| 3 | **三套分层交叉验证**：规则分层(5层) + KMeans聚类(5群) + 频次分层(6组) | 用户分析深度 |
| 4 | **时序差异化运营**：结合周末效应、小时级周期、Session 临界点 | 业务洞察力 |
| 5 | **四象限商品效率框架**：曝光 × 购买率矩阵，区分 51.3万/1.2万/1.6万 三类问题商品 | 商品分析能力 |
| 6 | **策略+验证闭环**：S1-S3 运营策略 → V1-V3 A/B 实验方案（离线设计） | 策略思维 |
| 7 | **AI 提效落地**：LLM Tool Use + 非 LLM 规则校验引擎 + 8/8 测试通过 | AI 工程能力 |
| 8 | **工程化编排**：`run_all.py` 断点续跑、表验证、日志、自动导出 | 工程素养 |
| 9 | **数据质量审计**：发现并修复清洗窗口过宽（82天→9天），全链路重跑验证 | 数据严谨性 |

---

> 📌 **面试提示**：先讲 A 线业务分析（5 分钟），再用 B 线展示 AI 提效能力（2 分钟）。不让 Agent 抢走业务分析主线。
