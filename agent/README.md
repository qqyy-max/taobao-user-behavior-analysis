# Agent 本地 AI 数据分析助手

> **定位**：基于 LLM Tool Use / Multi-Agent 架构的本地 analysis 工作流提效工具
> **版本**：v2.1 | 2026-06-11

---

## 定位声明

**本地 AI 数据分析助手与运营分析工作流提效工具**

基于 LLM Tool Use / Agent 模式，将日常数据分析中的重复性工作（指标口径查询、SQL 模板调用、DuckDB 本地查询、分析结果解释、异动归因初稿、运营策略初稿）自动化，提升分析效率。

**定位为本地分析工具**，不是后端系统、企业级平台或自动决策系统。

---

## 智能分流与弹性协作流

```
                     业务问题输入
                         │
                         ▼
             【LLM 语义分类分流路由器】
             (classify_query_by_llm)
                         │
        ┌────────────────┼────────────────┐
        ▼                ▼                ▼
   METRIC_QUERY    DEEP_ANALYSIS   STRATEGY_DESIGN
  (指标提取模式)    (深度分析模式)   (策略设计模式)
        │                │                │
    轻量校验         完整校验         完整校验
        │                │                │
        └────────┬───────┘                │
                 ▼                        ▼
           【Analyst】               【Analyst】
         数据查询与归因            数据查询与归因
                 │                        │
                 ▼                        ▼
           【Reviewer】              【Reviewer】
          弹性规则校验拦截          弹性规则校验拦截
                 │                        │
                 ├─不通过 (重试最多2次)    ├─不通过 (重试最多2次)
                 │                        │
                 ▼ (通过)                 ▼ (通过)
             输出报告                 【Strategist】
                                   根据数据生成运营策略
                                          │
                                          ▼
                                      输出完整报告
```

### 1. 意图分流与条件激活机制

系统在 [multi_agent.py](file:///e:/taobao_user_shopping_behavior_dataset/src/multi_agent.py) 中通过 `classify_query_by_llm` 对用户输入的提问进行自动语义分流，实现资源的按需调度与快速响应：

*   **METRIC_QUERY (指标提取模式)**：当提问仅涉及简单指标或数据提取时触发。Analyst 启用轻量级校验（跳过高阶数据局限和模糊词检查），直接返回，**不激活** Strategist，确保极速响应。
*   **DEEP_ANALYSIS (深度分析模式)**：当提问涉及归因、特征或关联分析时触发。Analyst 启用完整审查校验，**不激活** Strategist。
*   **STRATEGY_DESIGN (策略设计模式)**：当提问涉及策略、方案或 A/B 实验设计时触发。Analyst 启用完整审查校验，并**自动激活** Strategist 生成可落地的四要素运营策略。
*   *注：若大模型网络请求失败，系统将自动降级使用正则匹配分类，保证系统鲁棒性。*

### 2. 角色职责

| 角色 | 职责 | 实现方式 | 是否 LLM |
|------|------|---------|---------|
| **Analyst** | 查数据、输出结构化分析结论 | LLM + DuckDB Tool Use | ✅ LLM |
| **Reviewer** | 校验口径、时间窗口、模糊词、过度推断 | **Python 规则引擎**（非 LLM） | ❌ 规则 |
| **Strategist** | 基于分析结论生成运营策略 | LLM（不查数据，仅推理） | ✅ LLM |

### 3. Reviewer 弹性校验体系

为解决硬编码匹配缺乏弹性的问题，系统对 [reviewer.py](file:///e:/taobao_user_shopping_behavior_dataset/agent/reviewer.py) 的规则判定进行了弹性分级重构：

*   **阻断级 (Blocker) — 必须修复并重试**：
    *   `B-001`：数字/百分比支撑不足（数量 < 3 个）。
    *   `B-003`：分析结论篇幅严重过短（字数 < 150 字）。
    *   `B-004`：缺失核心结构段落（如【数据摘要】）。
    *   `S-001`：策略类输出缺失核心四要素。
*   **警告级 (Warning) — 警示提示，通过校验不重试**：
    *   `B-002`：存在口语化模糊表述（如“较高”、“明显”、“偏低”）。
    *   `D-001`：包含禁止用语（如“留存率”应表述为“短周期回访率”；“复购率”应表述为“窗口内重复购买率”等）。
    *   `D-002`/`D-003`/`D-005`：未标注周末效应、维度口径或窗口限制等。
    *   *效果*：当只触发警告级规则时，Reviewer 将判定通过，并在 UI/控制台中输出警告日志，**不再触发 Analyst 的 Retry 重试死循环**，极大地节省了 Token 消耗和等待延迟。

### 4. 工具异常自愈能力

为防止 Analyst 在猜测表名或 SQL 语法出现偏差时发生崩溃，[tools.py](file:///e:/taobao_user_shopping_behavior_dataset/src/tools.py) 的核心数据查询工具（`get_table_schema` / `plot_bar` / `query_duckdb` / `query_raw`）全面包裹了 `try-except` 异常捕获机制，将执行层错误转换为 JSON 错误反馈返回给 LLM（如 `"error": "Table cart_not_buy_users does not exist. Did you mean 'cart_abandon_users'?"`），**从而引导 Analyst 自动进行 SQL/表名自愈修正**。

---

## 目录结构

```
agent/
├── README.md                    # 本文件 — Agent 项目说明、定位、工作流
├── app.py                       # 支持 Web/终端 双模运行的入口文件
├── metrics_dictionary.md        # Agent 专用指标口径字典（Prompt 格式适配）
├── reviewer.py                  # 弹性规则校验引擎
├── evaluation_cases.md          # 8 个测试用例场景及通过准则
├── run_tests.py                 # 自动化测试回归脚本
├── sql_templates/               # SQL 模板库
│   ├── overview.sql             # 概览指标查询模板
│   ├── cart_abandon.sql         # 加购未购分析模板
│   ├── user_segment.sql         # 用户分层查询模板
│   ├── product_efficiency.sql   # 商品曝光效率查询模板
│   ├── anomaly_weekend.sql      # 周末异动归因模板
│   └── anomaly_hourly.sql       # 时段异动归因模板
└── prompts/                     # Agent System Prompt 模版
    ├── analyst.md               # Analyst 增强版 Prompt
    └── strategist.md            # Strategist 策略提示词
```

---

## 使用方法

### 1. Streamlit 可视化 Web 看板（网页端提问）

系统提供了可视化的交互网页，支持配置模型供应商、输入业务问答及实时展现回归测试通过率：

```bash
streamlit run agent/app.py
```

### 2. 命令行终端交互（命令行提问）

[app.py](file:///e:/taobao_user_shopping_behavior_dataset/agent/app.py) 现已兼容 CLI 提问模式。可以通过指定 `-q` 与可选的 `--provider` 在控制台中直接输出结果，并自动记录 interactions 备份与 insights 记忆：

```bash
python agent/app.py -q "分析加购未购用户的特征，并给出运营策略" --provider anthropic
```

### 3. 运行回归测试
```bash
python agent/run_tests.py
```

---

## 测试问题集 (T1-T8)

详见 `agent/evaluation_cases.md`，覆盖以下 8 个典型业务场景的质量审核：

| # | 场景 | 问题类型 | 核心指标与校验标准 |
|---|------|---------|-------------------|
| T1 | 指标口径查询 | 购买率双维度区分 | 行为维度 (~2.0%) 与用户维度 (~68.0%) 严格标注且给出公式 |
| T2 | 专题分析查询 | 加购未购用户特征 | 锁定 60,891 人与 28.3% 占比，进行加购周期分布下钻 |
| T3 | 用户分层查询 | 5层规则分层规模/购买率 | 比较规则分层规模差异，限定在 segment_summary 范围 |
| T4 | 异动归因 | 周末购买率下降 | 归因“逛型流量增加”，周末 DAU +16% 与购买率下降对比 |
| T5 | 时段分析 | 夜间vs上午购买效率 | 流量峰值（21:00）与购买率峰值（10:00，2.62%）错配分析 |
| T6 | 商品效率 | 高曝光低转化商品 | 锁定 51.3 万 HELC 商品，声明缺少曝光来源数据限制 |
| T7 | 策略生成 | 加购未购运营策略 | 激活 Strategist 生成满足群体、时机、动作、KPI 的四要素策略 |
| T8 | 实验设计 | A/B实验方案 | 实验分组（A/B/C）、显著性检验（卡方检验）、7天观察期与离线声明 |

---

## 输出质量评估标准

| 维度 | 合格标准 | 权重 |
|------|---------|------|
| SQL 正确性 | 查询无语法错误、返回预期结果（工具层集成自愈） | 20% |
| 指标口径一致性 | 与 metrics_dictionary.md 定义一致 | 20% |
| 9 天窗口约束 | 不使用"长期留存/复购/生命周期/流失"（警告级） | 15% |
| 非线性路径约束 | 不使用"漏斗转化率"（警告级） | 10% |
| 数字支撑 | 每个结论至少引用 1 个具体数字，全文 ≥ 3 个（阻断级） | 15% |
| 策略可执行性 | 包含目标群体、触达时机、具体动作、KPI（阻断级） | 10% |
| 离线声明 | 策略验证类问题明确说明"设计方案，非实际结果"（警告级） | 10% |
