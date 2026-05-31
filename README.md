# 淘宝用户行为分析与转化优化 — 端到端数据项目

[![Python](https://img.shields.io/badge/Python-3.11-blue)](https://www.python.org/)
[![DuckDB](https://img.shields.io/badge/DuckDB-1.0-yellow)](https://duckdb.org/)
[![Scikit-learn](https://img.shields.io/badge/Scikit--learn-1.5-orange)](https://scikit-learn.org/)
[![Power BI](https://img.shields.io/badge/Power%20BI-Dashboard-gold)](https://powerbi.microsoft.com/)

> **从 2,900 万行用户行为日志 → 5 类用户画像 → 差异化运营策略**
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
| **时间范围** | 2017-11-25 ~ 2017-12-03（9 天） |
| **规模** | 2,900 万+ 行为记录 |
| **用户数** | 98.7 万（去重） |
| **商品数** | 416 万 |
| **类目数** | 9,439 |

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
                       │   1.0 GB, 2,900 万行   │
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

### 5.1 转化漏斗：浏览→收藏是最大断裂点

| 阶段 | 用户数 | 渗透率 | 流失率 |
|------|--------|--------|--------|
| 浏览 (PV) | 285,816 | 100% | — |
| 收藏 (FAV) | 113,717 | **39.8%** | **60.2%** ← 最大流失 |
| 加购 (CART) | 215,167 | 75.3% | 24.7% |
| 购买 (BUY) | 195,078 | 68.3% | 31.7% |

> **洞察**：PV→FAV 流失 60%，说明推荐结果与用户兴趣匹配度不足。FAV→CART→BUY 的转化链相对健康。

### 5.2 用户留存：次日留存仅 53%

- **Day 1 留存**：53.2% — 近一半新用户次日不回访
- **Day 7 留存**：骤降至 5~8%
- 用户生命周期中位数：**3 天**

> **洞察**：短期（3 天）内未能让用户完成首单，流失概率大幅上升。需要在首次访问的前 3 个 Session 内促成转化。

### 5.3 商品分析：51.3 万件高曝光低转化商品

- 定义：PV ≥ P75 **且** 购买转化率 ≤ 中位数
- 占用了大量曝光资源但转化极低
- 需在下一次推荐排序中降权或替换

### 5.4 用户聚类：5 类用户画像

使用 **KMeans (K=5)** 对 287,004 名用户基于 32 维行为特征进行聚类：

| Cluster | 占比 | 购买率 | 人均PV | 活跃天 | 用户画像 |
|---------|------|--------|--------|--------|----------|
| **C2** | 20.1% | **9.4%** | 71 | 7.6 | 核心高价值用户 |
| **C1** | 11.1% | **5.2%** | 41 | 4.9 | 高价值用户 |
| **C4** | 19.2% | 4.2% | 30 | 5.3 | 潜力转化用户 |
| **C0** | 20.3% | 2.0% | **198** | 8.4 | 探索型浏览用户 |
| **C3** | 29.3% | **0.8%** | 89 | 7.8 | 高浏览低转化用户 |

> **关键洞察**：Cluster 0 人均 PV 高达 198，类目广度 43.6（远超其他群体），但购买率仅 2.0% — 他们是"逛"的用户，而非"买"的用户。需要品类引导+首单激励双管齐下。

---

## 6. 运营策略建议

### 6.1 按用户分群差异化运营

| 用户分群 | 优先级 | 核心策略 | 触达渠道 | 目标KPI |
|----------|--------|----------|----------|---------|
| 核心高价值 (20%) | P0 | 会员权益升级、新品优先体验、专属客服、复购激励 | Push+短信+站内信 | 复购率+10% |
| 高价值用户 (11%) | P0 | 会员等级升级、关联品类推荐、VIP活动 | Push+站内信 | ARPU+15% |
| 潜力转化 (19%) | P1 | 加购未购商品限时折扣、品类优惠券 | Push+站内信 | 购买转化+25% |
| 探索型浏览 (20%) | P2 | 新品类发现推荐、个性化首页、品类组合优惠 | 站内推荐+Push | 首购率+15% |
| 高浏览低转化 (29%) | P1 | 首单大额券、浏览商品降价提醒、社交推荐 | Push+站内弹窗 | 首购转化+30% |

### 6.2 产品与算法优化

1. **修复漏斗断裂点**：对收藏后 24 小时内未加购用户推送限时优惠
2. **减少无效曝光**：对 51.3 万件高曝光低转化商品降权
3. **优化冷启动**：Session 前 3 个推荐位优先展示高转化率商品
4. **缩短转化路径**：在商品详情页强化"立即购买"入口

---

## 7. Power BI Dashboard

基于 15 张 Parquet 宽表构建 5 页交互式仪表盘：

| 页面 | KPI | 图表 |
|------|-----|------|
| **Executive Overview** | 总用户、购买率、漏斗转化率 | 漏斗图、KPI 卡片 |
| **Funnel & Retention** | 阶段渗透率、D1/D7 留存 | 漏斗图、留存热力图、留存曲线 |
| **User Behavior** | DAU、购买率、平均行为数 | 趋势折线图、时段热力图 |
| **Product Analysis** | 类目排行、问题商品数 | 排行榜、散点图（曝光vs转化） |
| **User Segmentation** | 分群人数、分群购买率 | 柱状图、用户画像卡片 |

> 详细设计方案见 `docs/powerbi_dashboard_design.md`

---

## 8. 项目亮点

1. **SQL-First 架构**：核心分析在 SQL 中完成，Python 仅做 ML，Power BI 仅做可视化 — 层次分明，可维护性强
2. **数据仓库分层**：Raw → Clean → DWD → DWS → ADS → Feature，各层独立，可回溯
3. **中间表设计**：`user_base_metrics` 避免 5,800 万行重复扫描，显著提升性能
4. **完整特征工程**：35 维用户特征覆盖 6 大行为维度，零空值，直接支持 sklearn 建模
5. **业务驱动聚类**：不是跑模型就结束，每个 Cluster 都有业务画像、优先级和运营策略
6. **工程化编排**：`run_all.py` 支持断点续跑、表验证、日志记录、自动导出 Parquet

---

## 9. 项目结构

```
taobao-user-behavior-analysis/
│
├── README.md                         # 项目文档（本文档）
├── docs/
│   ├── analysis_report.md            # 正式分析报告（3000+ 字）
│   └── powerbi_dashboard_design.md   # Power BI 仪表盘设计方案
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
│   ├── data_cleaning.py              # ETL 入口
│   ├── data_cleaning.sql             # ETL SQL
│   ├── data_preview.sql              # 数据预览
│   └── run_all.py                    # ★ 全流程编排器
│
├── src/                              # Python 分析模块
│   ├── user_clustering.py            # 用户聚类（KMeans）
│   ├── cluster_analysis.py           # 聚类分析 & 用户画像
│   └── visualization.py              # 可视化（6 张图表）
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

## 10. 快速开始

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

## 11. 局限性与下一步

| 局限 | 改进方向 |
|------|----------|
| 仅 9 天数据，无法分析月度/季节性趋势 | 接入更长时间窗口的数据 |
| 缺少用户人口统计学特征 | 补充年龄、性别、地域等画像字段 |
| 缺少商品属性（价格、品牌、评分） | 接入商品信息表做联合分析 |
| 无实时行为流数据 | 对接 Flink/Kafka 做实时特征和推荐 |
| 策略建议未经 A/B 实验验证 | 设计实验框架，量化策略效果 |
