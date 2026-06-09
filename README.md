# 淘宝用户行为分析与转化优化 — 端到端数据项目

[![Python](https://img.shields.io/badge/Python-3.11-blue)](https://www.python.org/)
[![DuckDB](https://img.shields.io/badge/DuckDB-1.0-yellow)](https://duckdb.org/)
[![Scikit-learn](https://img.shields.io/badge/Scikit--learn-1.5-orange)](https://scikit-learn.org/)
[![Power BI](https://img.shields.io/badge/Power%20BI-Dashboard-gold)](https://powerbi.microsoft.com/)

> **从 2,911 万行用户行为日志 → 5 类用户画像 → 差异化运营策略**
>
> 一个面向数据分析岗位招聘的完整商业分析项目，展示从数据清洗到业务建议的全流程能力。

---

## 1. 项目背景

淘宝平台面临一个核心增长矛盾：

> **浏览行为占比 89.5%，但购买仅占 2.0%。近 30% 的用户属于"高浏览低转化"群体，购买率不足 1%。**

这意味着大量流量未能有效变现。本项目的目标是：

- 定位用户在转化链路的哪个环节流失最严重
- 识别高曝光低转化的商品和用户群体
- 通过无监督学习对用户分群，设计差异化运营策略
- 将分析结果落地为 Power BI 仪表盘，支持运营团队日常决策

---

## 2. 数据集

| 属性 | 值 |
|------|-----|
| **来源** | 阿里天池 — User Behavior from Taobao |
| **时间范围** | 2017-11-25 ~ 2017-12-03（9 天，经数据质量审计确认） |
| **规模** | 2,911 万 行为记录 |
| **用户数** | 28.7 万（去重） |
| **商品数** | 258 万 |
| **类目数** | 8,787 |

| 字段 | 说明 |
|------|------|
| `user_id` | 用户 ID（脱敏） |
| `item_id` | 商品 ID（脱敏） |
| `category_id` | 类目 ID（脱敏） |
| `behavior_type` | pv（浏览）/ fav（收藏）/ cart（加购）/ buy（购买） |
| `timestamp` | Unix 时间戳 |

---

## 3. 技术栈

| 层 | 技术 | 用途 |
|----|------|------|
| **ETL** | Python + DuckDB SQL | 数据清洗、类型转换、去重、日期派生 |
| **分析** | DuckDB SQL（8 层分层架构） | 漏斗、留存、行为、商品、用户画像 |
| **特征工程** | DuckDB SQL | 35 维用户特征宽表（零空值，可直接建模） |
| **聚类** | Python (sklearn) | KMeans 用户分群，Elbow + Silhouette 选 K |
| **可视化** | Python (matplotlib) + Power BI | 6 张分析图表 + 5 页交互式仪表盘 |

---

## 4. 项目架构

```
                       ┌──────────────────────┐
                       │   Raw Data (CSV)      │
                       │   1.0 GB, 2,911 万行   │
                       └──────────┬───────────┘
                                  │ data_cleaning.py
                                  ▼
                       ┌──────────────────────┐
                       │  Clean Layer          │
                       │  clean_data.parquet   │
                       │  337 MB, ZSTD 压缩    │
                       └──────────┬───────────┘
                                  │ 00_init.sql (共享基础层)
                                  ▼
        ┌─────────────────────────┼─────────────────────────┐
        │                         │                         │
        ▼                         ▼                         ▼
┌───────────────┐       ┌───────────────┐       ┌───────────────┐
│  01 Profiling │       │ 02 Funnel &   │       │ 03 Behavior   │
│  (数据画像)    │       │    Retention  │       │   (行为分析)   │
└───────┬───────┘       └───────┬───────┘       └───────┬───────┘
        │                       │                       │
        ▼                       ▼                       ▼
┌───────────────┐       ┌───────────────┐       ┌───────────────┐
│04 Product     │       │ 05 User       │       │06 Feature Mart│
│   (商品分析)   │       │   (用户画像)   │       │  (特征宽表)    │
└───────┬───────┘       └───────┬───────┘       └───────┬───────┘
        │                       │                       │
        └───────────────────────┼───────────────────────┘
                                │
                    ┌───────────┴───────────┐
                    │                       │
                    ▼                       ▼
          ┌───────────────┐       ┌───────────────┐
          │ 07 Export Mart│       │ src/clustering │
          │  (→ Power BI) │       │  (→ Python ML) │
          └───────┬───────┘       └───────┬───────┘
                  │                       │
                  ▼                       ▼
          ┌───────────────┐       ┌───────────────┐
          │ 15 Parquet    │       │ 5 User Clusters│
          │ data/mart/    │       │ + Personas     │
          └───────┬───────┘       └───────┬───────┘
                  │                       │
                  └───────────┬───────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │   Power BI        │
                    │   5-Page Dashboard │
                    │   + 6 Fig PNGs    │
                    └──────────────────┘
```

### 分层设计（数据仓库方法论）

| 层 | 位置 | 内容 | 消费者 |
|----|------|------|--------|
| **Raw** | `data/raw/` | 原始 CSV | ETL |
| **Clean** | `data/clean_data.parquet` | 清洗+日期派生 | SQL |
| **DWD** | `00_init.sql` | `user_base_metrics` 中间表 | 02/05/06 |
| **DWS** | `01-05_*.sql` | 聚合分析表 | DuckDB |
| **ADS** | `07_export_mart.sql` | 15 张 Parquet 宽表 | Power BI |
| **Feature** | `06_feature_mart.sql` | 35 维特征 Parquet | Python ML |

### 中间表设计（避免重复计算）

| 中间表 | 粒度 | 被引用 | 避免扫描量 |
|--------|------|--------|-----------|
| `user_base_metrics` | user_id | 02/05/06 | ~5,800 万行 |
| `category_base_stats` | category_id | 04 | ~2,900 万行 |

---

## 5. 核心分析成果

### 5.1 转化漏斗：用户跳过收藏，直接加购

| 阶段 | 用户数 | 渗透率 (vs PV) | 关键发现 |
|------|--------|---------------|----------|
| 浏览 (PV) | 285,815 | 100% | 基准 |
| 收藏 (FAV) | 113,717 | 39.8% | 仅 40% 用户使用过收藏 |
| 加购 (CART) | 215,167 | **75.3%** | 远超收藏 — 用户更倾向直接加购 |
| 购买 (BUY) | 195,078 | 68.3% | 68% 用户在 9 天内至少购买 1 次 |

> **洞察**：这不是线性漏斗。加购 UV (215,167) 远超收藏 UV (113,717)——用户行为模式是"浏览→加购→购买"，收藏环节被大量跳过。不应强行提升收藏率，而应关注"加购未购"的 2 万用户——他们是最接近转化的群体。购买用户的收藏渗透率仅 41.4%，加购渗透率则达 79.1%。

### 5.2 用户留存：9 天窗口限制 + 周末周期效应

**Cohort 结构**：71% 的用户首日出现在 11/25（周六），导致留存曲线被单 Cohort 主导。

以最大的 11/25 Cohort (204,904 人) 为例：

| 留存天数 | 对应日期 | 留存率 | 说明 |
|----------|----------|--------|------|
| Day 0 | 11/25 (Sat) | 100.0% | 基准 |
| Day 1 | 11/26 (Sun) | 78.8% | 真实次日留存 |
| Day 3 | 11/28 (Tue) | 76.0% | 工作日留存 |
| Day 6 | 12/01 (Fri) | 77.3% | 工作日稳定 |
| Day 7 | 12/02 (Sat) | 98.5% | ⚠️ 周六回峰，非真实留存 |

> **洞察**：Day 7 留存率跳到 98.5% 是**周末周期效应**——周六用户在一周后的周六自然回访，不能解读为"高留存"。9 天窗口内可观测到的真实留存衰减很小（Day 1→Day 6 仅从 78.8%→77.3%，几乎持平），说明窗口内用户整体活跃。要评估真实长期留存需 ≥30 天窗口排除周期效应。

### 5.3 商品分析：51.3 万件高曝光低转化商品

- 定义：PV ≥ P75（≥6 次浏览）**且** 购买转化率 ≤ 中位数（0%）
- 全量 258 万商品中 89.1% 零购买，但 51.3 万件有 ≥6 次 PV 仍零转化——占用了推荐位但不产生交易
- 另有 11,781 件商品被直接购买（无 PV）——搜索直达型，应增加搜索曝光
- 需在下一次推荐排序中对零购买高 PV 商品降权

### 5.4 用户聚类：5 类用户画像

使用 **KMeans (K=5)** 对 287,004 名用户基于 32 维行为特征进行聚类：

| Cluster | 占比 | 购买率 | 人均PV | 活跃天 | 用户画像 |
|---------|------|--------|--------|--------|----------|
| **C2** | 20.0% | **9.4%** | 71 | 7.6 | 核心高价值用户 |
| **C4** | 11.5% | **5.1%** | 41 | 4.9 | 高价值用户 |
| **C3** | 19.1% | 4.1% | 29 | 5.3 | 潜力转化用户 |
| **C0** | 20.2% | 2.0% | **198** | 8.4 | 探索型浏览用户 |
| **C1** | 29.2% | **0.8%** | 90 | 7.8 | 高浏览低转化用户 |

> **关键洞察**：Cluster 0 人均 PV 高达 198，类目广度 43.6（远超其他群体），但购买率仅 2.0% — 他们是"逛"的用户，而非"买"的用户。
>
> **时间偏好差异**：C3（潜力转化）67.4% 行为集中在周末——"周末战士"，周六上午触达最佳；C4（高价值用户）仅 41.6% 在周末——"工作日买家"，周三/周四触达；C2（核心）分布最均衡（49.5% 周末）。

---

## 6. 关键商业洞察

### 6.1 周末流量陷阱

> **周末 DAU +16%，但购买率 -10%**。周末用户以"逛"为主（打发时间），工作日用户目的明确（买了就走）。周末应做内容运营而非促销投入。

### 6.2 时间错位：上午买、晚上逛

> 购买率峰值在 **10:00 (2.62%)**，流量峰值在 **21:00 (243 万行为)**。促销 Push 应安排在 9:30 而非 20:00。限时秒杀最佳时段：10:00-11:00 或 14:00-15:00。

### 6.3 6 行为临界点

> **68% 的 Session ≤5 个行为**，但超过 6 个行为后购买率从 7.5% **翻倍**至 13.0%。前 5 个推荐位必须命中用户兴趣——这是产品优化的关键阈值。

### 6.4 819 个超级用户

> 仅 **0.29% 用户（819 人）** 人均 564 次行为，购买率 81.8%，复购率 79.3%。他们是平台核心资产，值得 1v1 维护。另有 10.7 万高频用户（101-500 次）是"超级用户预备队"。

### 6.5 收藏是伪问题，加购未购是真机会

> 用户跳过收藏直接加购——不应强行提升收藏率。真正该优化的是"加购未购"：**20,089 个用户加购过但从未购买**，他们对商品有兴趣但缺最后推力。

---

## 7. 运营策略建议

### 7.1 按用户分群 × 时序差异化运营

| 用户分群 | 优先级 | 最佳触达时间 | 核心策略 | 触达渠道 | 目标KPI |
|----------|--------|------------|----------|----------|---------|
| 核心高价值 C2 (20%) | P0 | 随时 | 会员权益升级、复购提醒、常购清单 | Push+短信+站内信 | 复购率+10% |
| 高价值用户 C4 (12%) | P0 | 周三/四下午 | 会员升级、关联品类推荐、VIP活动 | Push+站内信 | ARPU+15% |
| 潜力转化 C3 (19%) | P1 | **周六 10:00** | 加购未购限时折扣（67%行为在周末） | Push+站内信 | 购买转化+25% |
| 探索型浏览 C0 (20%) | P2 | 周末晚间 | 品类收窄推荐（从 43 类→5-10 类） | 站内推荐+Push | 首购率+15% |
| 高浏览低转化 C1 (29%) | P1 | 工作日 9:30 | 首单大额券、降价提醒、社交推荐 | Push+站内弹窗 | 首购转化+30% |

### 7.2 产品与算法优化

1. **加购未购转化**：对 2 万加购未购用户推送限时折扣（比收藏优化 ROI 更高）
2. **Session 前 5 行为优化**：68% Session ≤5 行为，前 5 个推荐位命中率决定整体转化
3. **减少无效曝光**：对 51.3 万件高曝光零购买商品降权，释放流量给 1.2 万件"搜索直达型"商品
4. **时序差异化**：周末推内容（直播/短视频），工作日推促销；Push 选 9:30 而非 20:00

---

## 8. Power BI Dashboard

基于 15 张 Parquet 宽表构建 5 页交互式仪表盘：

| 页面 | 核心 KPI | 关键图表 |
|------|----------|----------|
| **Executive Overview** | 总用户、购买率、漏斗渗透率 | KPI 卡片、漏斗概览、DAU 双轴、留存曲线 |
| **Funnel & Retention** | 阶段渗透率、加购未购数 | **Sankey 多路径图**、留存热力图、留存曲线 |
| **User Behavior** | DAU、峰值时段、周末溢价 | 日度趋势、**24h 购买vs流量双轴**、**Session 阶梯图** |
| **Product Analysis** | 类目排行、问题商品数 | 波士顿矩阵、排行榜、**搜索直达商品分布** |
| **User Segmentation** | 分群人数、分群购买率 | 价值矩阵、策略卡片、**分群×周末占比图** |

> 详细设计方案见 `docs/powerbi_dashboard_design.md`（已更新，含 4 个新增图表 + 2 个替换图表）

---

## 9. 数据质量审计

本项目经过完整的数据质量审计：

- **根因定位**：`data_cleaning.sql` 过滤条件过宽（保留全年 → 82 天），修正为严格 9 天窗口
- **全链路修复**：清洗 → 基础层 → 聚合层 → 特征层 → 聚类 → BI 导出，全部重跑
- **聚类验证**：修复前后聚类中心几乎一致（差异 <0.1pp），确认修复正确
- **留存修正**：移除被 82 天窗口污染的虚假留存数据（D1=53%→78.8%，去除 D7=5~8% 的错误结论）
- 详见 `docs/audit_report.md`、`docs/fix_summary.md`、`docs/validation_report.md`

---

## 10. 项目亮点

1. **SQL-First 架构**：核心分析在 SQL 中完成，Python 仅做 ML，Power BI 仅做可视化 — 层次分明，可维护性强
2. **数据质量审计**：发现并修复了清洗过滤条件过宽（82 天→9 天），全链路验证通过，体现数据工程严谨性
3. **数据仓库分层**：Raw → Clean → DWD → DWS → ADS → Feature，各层独立，可回溯
4. **时序差异化策略**：结合周末效应、小时级周期、Session 临界点，输出含具体触达时间的运营方案
5. **完整特征工程**：35 维用户特征覆盖 7 大行为维度，零空值，直接支持 sklearn 建模
6. **业务驱动聚类**：不是跑模型就结束，每个 Cluster 都有画像、时间偏好、触达时间和运营策略
7. **工程化编排**：`run_all.py` 支持断点续跑、表验证、日志记录、自动导出 Parquet

---

## 11. 项目结构

```
taobao-user-behavior-analysis/
│
├── README.md                         # 项目文档（本文档）
├── docs/
│   ├── analysis_report.md            # 正式分析报告（修订版）
│   ├── powerbi_dashboard_design.md   # Power BI Dashboard 设计方案
│   ├── data_dictionary.md            # 数据字典（74 字段）
│   ├── insight_audit.md              # 分析洞察审计报告
│   ├── audit_report.md               # 数据质量审计报告
│   ├── fix_summary.md                # 修复总结
│   └── validation_report.md          # 验证报告
│
├── sql/                              # SQL 分析层
│   ├── 00_init.sql                   # 共享基础层（中间表 + 维度表）
│   ├── 01_profiling.sql              # 数据画像
│   ├── 02_funnel_retention.sql       # 漏斗 & 留存
│   ├── 03_behavior_analysis.sql      # 日度/小时/Session 分析
│   ├── 04_product_analysis.sql       # 商品 & 类目分析
│   ├── 05_user_analysis.sql          # 用户画像 & 分群
│   ├── 06_feature_mart.sql           # 特征宽表（35 维 → sklearn）
│   ├── 07_export_mart.sql            # 统一导出 Parquet
│   ├── 08_powerbi_supplement.sql     # Power BI 补充表（Sankey/搜索直达/分群时间偏好）
│   ├── data_cleaning.py              # ETL 入口
│   ├── data_cleaning.sql             # ETL SQL（已修复时间窗口）
│   ├── data_preview.sql              # 数据预览
│   └── run_all.py                    # ★ 全流程编排器
│
├── src/                              # Python 分析模块
│   ├── user_clustering.py            # 用户聚类（KMeans）
│   ├── cluster_analysis.py           # 聚类分析 & 用户画像
│   ├── visualization.py              # 可视化（6 张图表）
│   └── export_for_powerbi.py         # Power BI 工作簿导出
│
├── notebooks/                        # Jupyter Notebook
│   └── 01_cluster_report.ipynb       # 聚类分析报告
│
├── data/
│   ├── raw/                          # 原始数据
│   ├── clean_data.parquet            # Clean Layer（337 MB）
│   ├── analysis.db                   # DuckDB 分析库
│   ├── mart/                         # ★ Power BI 数据源（15 Parquet）
│   └── features/                     # ML 特征表
│
├── outputs/
│   └── figures/                      # 分析图表（6 张 PNG）
│
└── experiment_log.md                 # 执行日志（自动生成）
```

---

## 12. 快速开始

```bash
# 1. 安装依赖
pip install duckdb pandas pyarrow scikit-learn matplotlib

# 2. ETL（首次运行）
python sql/data_cleaning.py all

# 3. 全量 SQL 分析 + 自动导出 Parquet
python sql/run_all.py

# 4. 用户聚类
python src/user_clustering.py

# 5. 聚类分析 & 画像
python src/cluster_analysis.py

# 6. 可视化
python src/visualization.py

# 7. Power BI → 导入 data/mart/*.parquet
```

---

## 13. 局限性与下一步

| 局限 | 改进方向 |
|------|----------|
| 仅 9 天数据，无法分析月度/季节性趋势 | 接入更长时间窗口的数据 |
| 缺少用户人口统计学特征 | 补充年龄、性别、地域等画像字段 |
| 缺少商品属性（价格、品牌、评分） | 接入商品信息表做联合分析 |
| 无实时行为流数据 | 对接 Flink/Kafka 做实时特征和推荐 |
| 策略建议未经 A/B 实验验证 | 设计实验框架，量化策略效果 |

---

## 14. AI Data Analysis Agent（当前实现）

### 14.1 Agent 架构

```
┌─────────────────────────────────────────────────────────────┐
│                      用户输入 (CLI)                          │
│           python src/agent.py -q "分析漏斗转化"               │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    Agent Orchestrator                        │
│                     (agent.py main)                          │
│                                                             │
│  加载 Memory Context → 注入 System Prompt → 调用 LLM         │
└──────────────────────────┬──────────────────────────────────┘
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ Single-Agent │  │ Multi-Agent  │  │  Report Gen  │
│   Mode       │  │    Mode      │  │    Mode      │
│ (agent.py)   │  │(multi_agent) │  │  (--report)  │
└──────┬───────┘  └──────┬───────┘  └──────┬───────┘
       │                 │                  │
       │    ┌────────────┼────────────┐      │
       │    ▼            ▼            ▼      │
       │  Analyst    Reviewer    Strategist  │
       │  (查数据)   (规则校验)   (出策略)    │
       │    │            │            │      │
       │    └────────────┼────────────┘      │
       │                 ▼                   │
       │         _save_interaction()         │
       │       (md 保存 + Memory 提取)        │
       │                                     │
       ▼                                     ▼
┌─────────────────────────────────────────────────────────────┐
│                    DuckDB Tool Layer                         │
│                                                             │
│  list_tables │ get_table_schema │ query_duckdb │ query_raw  │
│  plot_bar │ get_business_context                             │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                     Data Layer                               │
│     analysis.db (24 聚合表) + clean_data.parquet (2900 万行)  │
│     data/mart/*.parquet (15 张 BI 宽表)                       │
└─────────────────────────────────────────────────────────────┘
```

### 14.2 Agent 模式对比

| 模式 | 入口 | Agent 链路 | 适用场景 |
|------|------|-----------|----------|
| **Single-Agent** | `agent.py -q "..."` | 单 LLM 查数据 + 输出结论 | 快速问答、简单分析 |
| **Multi-Agent** | `multi_agent.py -q "..."` | Analyst → Reviewer(规则校验+重试) → Strategist | 深度分析、需要策略输出 |
| **Report Gen** | `agent.py --report` | 多问题串行 → 聚合为报告 | 定期报告生成 |

### 14.3 各 Agent 职责

| Agent | 文件 | 职责 | 当前实现方式 |
|-------|------|------|-------------|
| **Planner** | (隐式, 在 System Prompt 中) | 决定分析路径、工具调用顺序 | System Prompt 指令 |
| **Analyst** | `agent.py:run_agent()` / `multi_agent.py:ANALYST_PROMPT` | 查数据、输出分析结论 | LLM + DuckDB Tool Use |
| **Reviewer** | `tools.py:rule_based_review()` | 校验数字密度、模糊词、内容长度 | Python 正则规则（非 LLM） |
| **Strategist** | `multi_agent.py:STRATEGIST_PROMPT` | 基于分析结论制定运营策略 | LLM（不查数据，仅推理） |

> **当前阶段说明**：Agent 系统基于 LLM Tool Use 模式运行。Planner 能力内嵌在 System Prompt 指令中，Reviewer 使用规则引擎（正则匹配）而非独立 LLM Agent。Memory 系统使用 JSON 文件持久化，Rule 系统以 Markdown 文档形式定义（供 Agent prompt 引用），尚未实现可执行 Rule Engine。

### 14.4 关键模块

| 模块 | 文件 | 功能 | 成熟度 |
|------|------|------|--------|
| **LLM 抽象层** | `agent.py:LLMClient` | 统一 DeepSeek/Anthropic API 差异 | ✅ 可用 |
| **Tool Layer** | `tools.py` | 6 个 DuckDB 查询工具 + 业务上下文 | ✅ 可用 |
| **Memory 系统** | `memory.py` | 跨 Session 洞察提取、JSON 存储、去重注入 | ✅ 可用 |
| **Rule 文档** | `rules/*.md` (5 文件) | 指标定义、分析 SOP、Review 清单、策略映射、Memory 规范 | 📋 文档 |
| **交互保存** | `agent.py:_save_interaction()` | 每次 Q&A 自动保存 md + 提取 Memory | ✅ 可用 |
| **报告生成** | `agent.py:generate_report()` | 多问题串行 → 聚合 Markdown 报告 | ✅ 可用 |

### 14.5 Agent 启动流程

```
1. format_memory_context(max_items=5)  →  注入历史洞察到 System Prompt
2. load_system_prompt()                →  加载 system.md + metrics.md
3. LLMClient(provider)                 →  初始化 API 客户端
4. run_agent(question, memory_ctx)     →  执行 Tool Use 循环
5. _save_interaction(q, result, llm)   →  保存 md + 提取 Memory
```

---

## 15. Production Readiness & Incremental Architecture（演进设计）

> **标注规范**：
> - ✅ **Current** — 当前已实现
> - 🔧 **Planned** — 有明确设计，待实现
> - 📐 **Design** — 架构设计阶段
> - 🔮 **Vision** — 远期愿景

---

### 15.1 Incremental Data Pipeline

从静态 9 天快照迁移到每日增量场景的管道设计。

#### 15.1.1 管道总览

```
                                    ┌─────────────────┐
                                    │  Source System   │
                                    │  (淘宝行为日志)   │
                                    └────────┬────────┘
                                             │ daily batch / CDC
                                             ▼
          ┌──────────────────────────────────────────────────────┐
          │                  Ingestion Layer                      │
          │                                                      │
          │  ingestion_date  = DATE('today')                     │
          │  batch_id         = UUID7 (time-ordered)              │
          │  file format      = Parquet (ZSTD, compression=3)    │
          │  partition        = dt={YYYY-MM-DD}                  │
          └──────────────────────────┬───────────────────────────┘
                                     │
                                     ▼
┌────────────────────────────────────────────────────────────────┐
│                        Processing Layers                        │
│                                                                │
│  Raw ────► Clean ────► DWD ────► DWS ────► ADS ────► Agent    │
│  (CSV)     (Parquet)  (中间表)  (聚合表)  (BI宽表)  (Tool Use) │
│                                                                │
│  Partition: dt=*      dt=*      dt=*     dt=*      full        │
│  Strategy:  append    overwrite overwrite overwrite overwrite   │
└────────────────────────────────────────────────────────────────┘
```

#### 15.1.2 分层策略

| 层 | 存储 | 分区键 | 更新策略 | 保留策略 | 状态 |
|----|------|--------|----------|----------|------|
| **Raw** | `data/raw/dt={date}/` | `dt` | append (幂等: `batch_id` 去重) | 90 天 → 冷归档 | 📐 |
| **Clean** | `data/clean/dt={date}/` | `dt` | overwrite (当日全量重算) | 90 天 | 📐 |
| **DWD** | `analysis.db` (DuckDB) | — | incremental upsert (MERGE) | 永久 (聚合层) | 📐 |
| **DWS** | `analysis.db` (DuckDB) | — | full refresh (依赖 DWD 增量) | 永久 | 📐 |
| **ADS** | `data/mart/*.parquet` | — | full refresh (每次 DWS 完成后) | 永久 | 📐 |
| **Agent** | — | — | 读取 ADS + Clean, 不写回 | — | ✅ |

#### 15.1.3 增量加载流程

```
┌──────────────────────────────────────────────────────────────┐
│                  Incremental Load (每日执行)                   │
│                                                              │
│  Step 1: 检查分区                                             │
│    IF partition_exists(dt='2026-06-08') → SKIP (幂等)         │
│                                                              │
│  Step 2: 加载新分区                                           │
│    COPY raw_events FROM 's3://bucket/dt=2026-06-08/*.csv'     │
│    SET ingestion_date = '2026-06-08'                         │
│    SET batch_id = uuid7()                                    │
│                                                              │
│  Step 3: Clean (当日清洗)                                     │
│    → 类型转换、去重、日期派生、is_weekend 标记                  │
│    → WRITE data/clean/dt=2026-06-08/ (overwrite)             │
│                                                              │
│  Step 4: DWD 增量更新                                         │
│    → user_base_metrics: INSERT OR REPLACE (当日用户)           │
│    → category_base_stats: INSERT OR REPLACE (当日类目)         │
│                                                              │
│  Step 5: DWS 全量刷新                                         │
│    → funnel_summary, cohort_retention, daily_behavior...      │
│    → 依赖 DWD 全量 (累积历史) 重算                             │
│                                                              │
│  Step 6: ADS 导出                                             │
│    → 重写 data/mart/*.parquet (Power BI 数据源)               │
│                                                              │
│  Step 7: 质量检查                                             │
│    → 行数校验: |today_rows - 7d_avg| < 3σ                     │
│    → 去重校验: COUNT(*) = COUNT(DISTINCT user_id, ts)         │
│    → 指标校验: buy_uv ≤ pv_uv, 转化率 ∈ [0,100]              │
│    → 通过 → 标记 partition 为 valid                           │
│    → 失败 → alert, 回滚 partition                             │
└──────────────────────────────────────────────────────────────┘
```

#### 15.1.4 历史回填策略

```sql
-- 回填模式: 从最早日期到最晚日期逐日执行增量流程
-- 每天一个 batch_id, 顺序执行, 确保 DWD 累积正确

-- 伪代码:
FOR dt IN (SELECT DISTINCT dt FROM raw_events ORDER BY dt):
    load_partition(dt)
    clean_partition(dt)
    upsert_dwd(dt)
    IF dt == LAST_DAY:
        full_refresh_dws()
        export_ads()
```

---

### 15.2 Memory Architecture

#### 15.2.1 当前实现 vs 目标架构

```
当前 (V1):                          目标 (V3):
┌──────────────────┐               ┌──────────────────────────┐
│  insights.json   │               │     Memory Service        │
│  (单文件, ~30条)  │               │                          │
│                  │               │  ┌────────────────────┐  │
│  load_memory()   │               │  │ Short-Term Memory   │  │
│  save_memory()   │               │  │ (Session 内上下文)   │  │
│  extract()       │               │  │ - 当前对话历史       │  │
│  format()        │               │  │ - 工具调用结果       │  │
│                  │               │  │ - 中间分析结果       │  │
│  评分: 无         │               │  │ TTL: 1 session      │  │
│  去重: 无         │               │  └─────────┬──────────┘  │
│  检索: 最近5条     │               │            │             │
│                  │               │  ┌─────────▼──────────┐  │
│                  │               │  │ Long-Term Memory    │  │
│                  │               │  │ (跨 Session 知识库)  │  │
│                  │               │  │ - 洞察库 (scored)   │  │
│                  │               │  │ - 策略效果库         │  │
│                  │               │  │ - 分析模板库         │  │
│                  │               │  │ TTL: 永久 (衰减)    │  │
│                  │               │  └────────────────────┘  │
│                  │               │                          │
│                  │               │  Scoring • Dedup         │
│                  │               │  Retrieval • Decay       │
└──────────────────┘               └──────────────────────────┘
```

#### 15.2.2 Memory 分层详解

| 维度 | Short-Term Memory | Long-Term Memory |
|------|-------------------|------------------|
| **范围** | 当前 Session | 所有历史 Session |
| **内容** | 对话历史、SQL 查询、中间结果 | 洞察结论、数字事实、策略效果 |
| **生命周期** | Session 结束即清除 | 永久保留（带衰减） |
| **存储** | LLM Context Window | `insights.json` + 未来: 向量数据库 |
| **检索方式** | 全量在上下文中 | Top-K 按 score 排序 → 注入 prompt |
| **当前状态** | ✅ LLM 原生支持 | ✅ `format_memory_context(max_items=5)` |
| **目标状态** | ✅ 已实现 | 🔧 增加 Scoring/Dedup/Retrieval |

#### 15.2.3 Memory 处理流水线

```
Analysis Result (Analyst 输出)
    │
    ▼
extract_insights()          ← LLM 提取 3-5 条数字结论
    │
    ▼
Scoring (重要性评分)          ← 🔧 待实现: 数据密度/增量性/可复用性/行动价值
    │
    ▼
Deduplication (去重)         ← 🔧 待实现: 语义相似度 > 0.7 → 合并
    │
    ▼
Storage                     ← ✅ insights.json (当前) / 🔮 向量数据库 (未来)
    │
    ▼
Retrieval (检索)             ← ✅ Top-5 by recency (当前) / 🔧 Top-K by score (未来)
    │
    ▼
Injection (注入)             ← ✅ format_memory_context() → System Prompt 前缀
```

#### 15.2.4 Memory 评分规则（设计）

| 维度 | 权重 | 评分逻辑 |
|------|------|----------|
| 数据密度 | 30% | key_findings 中具体数字的数量 (3=0.5, 5=1.0) |
| 增量程度 | 25% | 与已知核心结论的语义重叠度 (重叠越低分数越高) |
| 可复用性 | 20% | 结论是否能直接用于未来分析 (通用性强=高分) |
| 行动价值 | 15% | 是否能直接推导运营策略 |
| 规模影响 | 10% | 涉及的群体规模 (大群体=高分) |

> 详细去重规则、衰退策略、质量审计见 `rules/memory_rules.md`

---

### 15.3 Rule Engine

#### 15.3.1 当前实现 vs 目标架构

| 层级 | 当前 (V1) | 目标 (V3) |
|------|-----------|-----------|
| **规则定义** | Markdown 文档 (`rules/*.md`) | 可执行规则文件 (`rules/*.yaml` 或 `.py`) |
| **规则执行** | `rule_based_review()` — 仅 3 条正则 | 完整 Rule Engine — 阻断/警告/信息 三级 |
| **校验时机** | Analyst 输出后 (Multi-Agent 模式) | 全链路: 数据→分析→策略 三阶段 |
| **规则管理** | 手动维护 .md | 规则版本化 + 热加载 |

#### 15.3.2 三级规则体系

```
┌─────────────────────────────────────────────────────────────┐
│                     Rule Engine Pipeline                     │
│                                                             │
│  Input → [Metric Validation] → [Insight Validation] →       │
│          [Strategy Validation] → Output                     │
│                                                             │
│  Level 1: BLOCKER  → 阻断输出, 要求 Analyst 重做             │
│  Level 2: WARNING  → 标注警告, 输出但标记                    │
│  Level 3: INFO     → 建议优化, 不阻断                        │
└─────────────────────────────────────────────────────────────┘
```

#### 15.3.3 示例规则

**Metric Validation (当前部分实现 ✅ → 完整规则 📐)**

```yaml
# rules/metric_validation.yaml (设计)
rules:
  - id: MV-001
    name: "buy_uv 不超 pv_uv"
    severity: BLOCKER
    check: "$.data.buy_uv <= $.data.pv_uv"
    message: "购买用户数 ({buy_uv}) > 浏览用户数 ({pv_uv})"
    
  - id: MV-002
    name: "用户维度转化率 ≤ 100%"
    severity: BLOCKER
    check: "$.metrics.user_buy_rate_pct <= 100"
    message: "用户维度转化率 {rate}% 超过 100%"

  - id: MV-003
    name: "Day7 留存标注周期效应"
    severity: WARNING
    check: |
      IF $.metrics.d7_retention > 90:
        REQUIRES "周末周期效应" IN $.text.annotations
    message: "Day7 留存 {rate}% 需标注周末周期效应"

  - id: MV-004
    name: "行为购买率正常范围"
    severity: INFO
    check: "1.5 <= $.metrics.action_buy_rate_pct <= 3.0"
    message: "行为维度购买率 {rate}% 偏离正常范围 (1.5-3.0%)"
```

**Insight Validation (当前限制: 仅长度检查 ✅ → 完整规则 📐)**

```yaml
# rules/insight_validation.yaml (设计)
rules:
  - id: IV-001
    name: "数字密度 ≥ 3"
    severity: BLOCKER
    check: "count(re.findall(r'\d+\.?\d*%?', text)) >= 3"
    message: "数字支撑不足（仅 {count} 个，要求 ≥3）"
    # ✅ 当前已在 rule_based_review() 中实现

  - id: IV-002
    name: "禁止模糊词"
    severity: BLOCKER
    check: "no_match(text, ['较高','明显','显著','一定程度','有所'])"
    # ✅ 当前已在 rule_based_review() 中实现

  - id: IV-003
    name: "增量检查 — 不重复已知结论"
    severity: WARNING
    check: |
      known = ["PV→FAV 流失 60.2%", "Day1 留存 78.8%", ...]
      overlap = sum(1 for k in known if k in text)
      ASSERT overlap <= 2
    message: "{overlap}/8 条与已知结论完全重复"

  - id: IV-004
    name: "反直觉结论自洽"
    severity: WARNING
    check: |
      IF "FAV→CART" in text AND "189%" in text:
        REQUIRES "源群体小于目标群体" IN text
    message: "FAV→CART>100% 需说明非线性特征"
```

**Strategy Validation (当前: 人工审查 → 目标: 自动化 📐)**

```yaml
# rules/strategy_validation.yaml (设计)
rules:
  - id: SV-001
    name: "策略包含四要素"
    severity: BLOCKER
    check: |
      FOR each strategy:
        REQUIRES all(["目标群体", "触达时机", "具体动作", "KPI"]) IN strategy
    message: "策略缺少必要元素: {missing}"

  - id: SV-002
    name: "KPI 可量化"
    severity: BLOCKER
    check: |
      FOR each KPI:
        REQUIRES re.search(r'\d+\.?\d*%?', kpi_text)
    message: "KPI 缺少具体数字: {kpi_text}"

  - id: SV-003
    name: "群体引用具体"
    severity: WARNING
    check: |
      FOR each strategy:
        REQUIRES any(["C0","C1","C2","C3","C4",
                       "高频","中频","低频","沉默",
                       "加购未购","已购","复购"]) IN strategy
    message: "策略未指定具体用户群体"

  - id: SV-004
    name: "禁出策略检测"
    severity: BLOCKER
    banned: ["提升用户体验", "优化推荐算法", "加大营销投入",
             "加强用户教育", "提高商品质量", "增加用户粘性"]
    check: "no_match(strategy, banned)"
    message: "策略包含禁出表述: {matched}"
```

---

### 15.4 Production Deployment Roadmap

```
┌──────────────────────────────────────────────────────────────────┐
│                     EVOLUTION ROADMAP                             │
│                                                                  │
│  V1              V2                V3             V4         V5  │
│  Static ──────► Incremental ────► MCP Tool ────► RAG ────► Real- │
│  Dataset        Pipeline          Layer          KB       time   │
│                                                                  │
│  ✅ Current     📐 Design         🔮 Vision      🔮       🔮     │
└──────────────────────────────────────────────────────────────────┘
```

#### V1 — Static Dataset Analysis ✅ Current

```
技术栈: Python + DuckDB + sklearn + Power BI
数据:    单次加载 9 天静态 CSV
Agent:   LLM Tool Use (6 DuckDB 工具)
Memory:  JSON 文件 (格式化为 prompt 前缀)
Rule:    Markdown 文档 + 简单正则校验
```

**已实现功能：**

| 能力 | 实现 |
|------|------|
| 数据管道 | ✅ ETL → Clean → DWD → DWS → ADS (sql/run_all.py) |
| 用户分群 | ✅ KMeans K=5 + 35 维特征 + 画像生成 |
| Agent 系统 | ✅ Single-Agent + Multi-Agent (Analyst/Reviewer/Strategist) |
| Tool Use | ✅ 6 个 DuckDB 查询工具 (聚合表 + 原始数据) |
| Memory | ✅ 跨 Session 洞察存储 (JSON) + prompt 注入 |
| Rule 文档 | ✅ 5 份 Markdown 规则文件 (metrics/analysis/review/strategy/memory) |
| BI 看板 | ✅ Power BI 5 页交互仪表盘 (15 张 Parquet) |
| 报告生成 | ✅ Markdown 报告 (agent.py --report) |
| 交互保存 | ✅ 每次 Q&A 自动保存 md + 提取 Memory |

#### V2 — Incremental Pipeline 📐 Design

```
新增:
  ├── 每日增量加载 (ingestion_date + batch_id + dt 分区)
  ├── DWD 增量 upsert (MERGE 新用户/新行为)
  ├── DWS 全量刷新 (累积历史重算)
  ├── 数据质量监控 (行数校验 / 去重校验 / 指标校验)
  ├── 历史回填脚本 (逐日顺序执行)
  └── 失败告警 + 分区回滚

技术栈新增: Apache Airflow / Prefect (调度), S3/MinIO (存储)
```

**新增文件（规划）：**
```
sql/
├── incremental_load.py       # 增量加载入口
├── quality_checks.py         # 数据质量监控
├── backfill.py               # 历史回填脚本
└── alerts.yaml               # 告警规则配置
```

#### V3 — MCP Tool Layer & Advanced Memory 🔮 Vision

```
Agent 层升级:
  ├── MCP Server: DuckDB Tools 包装为 MCP Tools
  │     → Claude Desktop / Cursor / 任意 MCP Client 直接调用
  ├── Planner Agent: 独立 LLM Agent, 规划分析路径
  │     → 分析问题 → 分解子任务 → 调度 Analyst → 聚合结果
  ├── Reviewer Agent: 独立 LLM Agent (当前是 Python 正则)
  │     → 理解分析上下文 → 语义校验 → 反事实推演
  └── Rule Engine: 可执行 YAML 规则 (当前为 Markdown 文档)
        → 热加载规则 → 三级校验 (BLOCKER/WARNING/INFO) → 自动重试

Memory 层升级:
  ├── Short-Term Memory: Session 内上下文缓存
  ├── Long-Term Memory: 带评分的洞察库 + 自动去重 + 时间衰减
  ├── 向量检索: embedding → 语义相似度检索 (替代当前 Top-5 recency)
  └── 策略效果追踪: 记录策略 → KPI 结果 → 反馈到 Memory 评分
```

**新增文件（规划）：**
```
src/
├── mcp_server.py             # MCP Server (DuckDB Tools)
├── planner_agent.py          # 独立 Planner Agent
├── reviewer_agent.py         # 独立 Reviewer Agent (LLM)
├── rule_engine.py            # 可执行规则引擎
├── memory/
│   ├── short_term.py         # Session 内记忆
│   ├── long_term.py          # 带评分的长期记忆
│   ├── scoring.py            # 重要性评分
│   ├── dedup.py              # 语义去重
│   └── retrieval.py          # 向量检索
└── strategy_tracker.py       # 策略效果追踪
```

#### V4 — Knowledge Base & RAG 🔮 Vision

```
新增:
  ├── 分析模板库: 常见分析问题的 SQL 模板 + 最佳分析路径
  ├── 策略效果库: 历史策略 → KPI 实际效果 → ROI 排序
  ├── 领域知识图谱: 电商指标关系图 (如 加购↑ → 购买率↑)
  └── RAG 检索: 用户问题 → 检索相关 Memory + 模板 → 增强 prompt

技术栈新增: ChromaDB / Pinecone (向量数据库), LangChain/LlamaIndex (RAG)
```

#### V5 — Real-time Streaming Analytics 🔮 Vision

```
新增:
  ├── 实时行为流: Kafka → Flink → 实时特征计算
  ├── 在线推理: 用户实时分群 → 即时策略推荐
  ├── A/B 实验框架: 策略组 vs 对照组 → 统计检验 → 自动上报
  └── 实时告警: 指标异常 (3σ) → 自动触发分析 Agent

技术栈新增: Kafka, Flink, Redis (特征存储), Prometheus + Grafana (监控)
```

---

### 15.5 版本能力矩阵

| 能力维度 | V1 (Current) | V2 (Design) | V3 (Vision) | V4 (Vision) | V5 (Vision) |
|----------|:---:|:---:|:---:|:---:|:---:|
| **数据更新** | Static | Daily Batch | Daily Batch | Daily Batch | Real-time |
| **数据质量** | Audit Docs | Auto Checks | Auto Checks | Auto Checks | Auto Checks + Alerts |
| **Agent 规划** | Prompt-embedded | Prompt-embedded | Planner Agent | Planner Agent | Planner + Auto-trigger |
| **Agent 校验** | Regex Rules | Regex Rules | LLM Reviewer | LLM Reviewer | LLM + Stats |
| **工具调用** | Python dispatch | Python dispatch | MCP Server | MCP Server | MCP + Streaming |
| **Memory 存储** | JSON File | JSON File | JSON + Embedding | Vector DB | Vector DB + Graph |
| **Memory 评分** | — | — | Scoring Model | Scoring + Feedback | Automated |
| **Memory 检索** | Top-5 Recency | Top-5 Recency | Vector Similarity | RAG | RAG + Context |
| **规则执行** | Document | YAML Engine | YAML Engine | Hot-reload | Self-evolving |
| **策略追踪** | — | — | Manual Track | Auto Track | Auto + A/B Test |
| **可视化** | Power BI | Power BI | Power BI + Agent | Dashboard + Chat | Full-stack |
| **部署方式** | CLI | CLI + Scheduler | MCP + Scheduler | SaaS | Cloud-native |

---

### 15.6 工程化原则

```
1. Backward Compatible
   V2 的数据管道必须兼容 V1 的静态数据集 → 历史回填模式

2. Incremental Adoption
   不推倒重来。V2 新增 incremental_load.py, 与现有 run_all.py 并存
   V3 新增 mcp_server.py, 现有 agent.py 保持不变

3. Observable
   每层有质量检查, 每个 pipeline run 有日志, 每个 Agent 输出有校验

4. Testable
   Memory → 可审计 (audit_memory 脚本)
   Rule → 可回归测试 (规则变更后重跑历史分析验证)
   Pipeline → 可回滚 (失败分区自动回滚)

5. Documented
   每个版本更新 README 能力矩阵
   每个新模块有 docstring + usage example
```

---

## 16. 关键文件索引

### 当前实现

| 类别 | 文件 | 说明 |
|------|------|------|
| **Agent** | `src/agent.py` | Single-Agent + LLM 抽象层 |
| **Agent** | `src/multi_agent.py` | Multi-Agent (Analyst → Reviewer → Strategist) |
| **Agent** | `src/tools.py` | DuckDB Tool Layer (6 工具) |
| **Agent** | `src/memory.py` | Memory 系统 (extract/save/load/format) |
| **Rules** | `rules/metric_rules.md` | 30+ 指标定义与计算公式 |
| **Rules** | `rules/analysis_rules.md` | 7 大分析 SOP + 10 条禁止行为 |
| **Rules** | `rules/review_rules.md` | 17 条可执行校验规则 + Reviewer Prompt |
| **Rules** | `rules/strategy_rules.md` | 8 群体策略映射 + 4 套内容模板 |
| **Rules** | `rules/memory_rules.md` | Memory 写入/去重/评分/审计规范 |
| **Prompts** | `src/prompts/system.md` | Analyst System Prompt |
| **Prompts** | `src/prompts/metrics.md` | 表结构速查 + 已知结论 + SQL 路径 |
| **Pipeline** | `sql/run_all.py` | 全流程编排器 (断点续跑) |
| **ETL** | `sql/data_cleaning.py` | 数据清洗入口 |
| **ML** | `src/user_clustering.py` | KMeans 聚类 |
| **BI** | `src/export_for_powerbi.py` | Power BI 工作簿导出 |
| **Dashboard** | `docs/powerbi_dashboard_design.md` | Power BI 设计方案 |
| **Data Dict** | `docs/data_dictionary.md` | 21 表 74 字段完整字典 |
