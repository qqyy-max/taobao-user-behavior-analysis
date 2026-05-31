# 淘宝用户行为分析与转化优化策略

> **从海量行为日志到可落地的运营策略 — 端到端数据分析项目**
>
> DuckDB SQL → Python (sklearn) → Power BI → 业务建议

---

## 1. 业务问题

淘宝平台面临一个关键矛盾：**浏览行为占比接近 90%，但收藏与加购转化率极低，用户在「兴趣形成→购买决策」环节存在严重流失。**

本项目围绕以下核心问题进行端到端分析：

| # | 问题 | 分析方法 | 输出 |
|---|------|----------|------|
| 1 | 用户在转化漏斗的哪个阶段流失最严重？ | 漏斗分析 + 用户渗透率 | 漏斗图 |
| 2 | 不同品类/商品的转化率差异有多大？ | 类目 & 商品维度转化分析 | 问题商品清单 |
| 3 | 用户首次访问后能留存多久？ | Cohort 留存分析 | 留存曲线 & 热力图 |
| 4 | 哪些用户群体转化率最高/最低？ | 用户分群 + KMeans 聚类 | 用户画像 |
| 5 | 如何差异化运营不同特征的用户？ | 特征重要性 + 策略映射 | 运营建议 |

---

## 2. 数据概览

### 2.1 数据源

- **来源**：阿里天池 — User Behavior Data from Taobao
- **时间范围**：2017-11-25 ~ 2017-12-03（9 天）
- **规模**：98.7 万用户 × 416 万商品 × 9,439 类目 × 2,900 万+ 行为记录

### 2.2 数据模型

| 字段 | 类型 | 说明 |
|------|------|------|
| `user_id` | BIGINT | 用户 ID（脱敏） |
| `item_id` | BIGINT | 商品 ID（脱敏） |
| `category_id` | BIGINT | 类目 ID（脱敏） |
| `behavior_type` | VARCHAR | pv / fav / cart / buy |
| `ts` | TIMESTAMP | 行为时间戳 |

### 2.3 行为分布

| 行为 | 含义 | 记录数 | 占比 |
|------|------|--------|------|
| **pv** | 浏览 | ~2,600 万 | ~89.6% |
| **fav** | 收藏 | ~84.5 万 | ~2.9% |
| **cart** | 加购 | ~162 万 | ~5.6% |
| **buy** | 购买 | ~58.4 万 | ~2.0% |

> **关键发现**：仅 2% 的行为事件是购买，且收藏行为（2.9%）远低于加购（5.6%），说明用户更倾向于直接加购而非收藏。

---

## 3. 技术架构

### 3.1 数据流

```
Raw Data (CSV)
  │
  ├─ data_cleaning.py        # ETL: 类型转换、去重、派生日期字段
  │
  ▼
data/clean_data.parquet      # Clean Layer (337 MB, ZSTD)
  │
  ├─ 00_init.sql             # 共享基础层 (clean 视图 + user_base_metrics)
  ├─ 01_profiling.sql        # 数据画像
  ├─ 02_funnel_retention.sql # 漏斗 & 留存
  ├─ 03_behavior_analysis.sql# 行为分析
  ├─ 04_product_analysis.sql # 商品 & 类目分析
  ├─ 05_user_analysis.sql    # 用户画像 & 分群
  ├─ 06_feature_mart.sql     # 特征宽表 (28 维 → sklearn)
  ├─ 07_export_mart.sql      # 统一导出 → Parquet
  │
  ▼
data/mart/*.parquet           → Power BI (15 张表)
data/features/user_features.parquet → Python (KMeans / PCA)
```

### 3.2 分层架构（数据仓库思想）

| 层 | 目录/格式 | 内容 | 消费者 |
|----|-----------|------|--------|
| **Raw** | `data/raw/` (CSV) | 原始数据，只读 | ETL |
| **Clean** | `data/` (Parquet) | 清洗 + 日期派生，单表 | SQL |
| **Analysis** | `analysis.db` (DuckDB) | 聚合结果表 | SQL 内依赖 |
| **Mart** | `data/mart/` (Parquet) | 宽表，可直接消费 | Power BI |
| **Feature** | `data/features/` (Parquet) | 28 维数值特征 | Python ML |

### 3.3 中间表设计（避免重复计算）

| 中间表 | 粒度 | 被引用方 | 避免扫描量 |
|--------|------|----------|-----------|
| `user_base_metrics` | user_id | 02 / 05 / 06 | ~5,800 万行 |
| `category_base_stats` | category_id | 04 | ~2,900 万行 |

---

## 4. 核心分析发现

### 4.1 转化漏斗：浏览→收藏是最大断裂点

| 阶段 | 用户数 | 渗透率 |
|------|--------|--------|
| 浏览 (PV) | 285,816 | 100% |
| 收藏 (FAV) | 113,717 | **39.8%** ← 最大流失 |
| 加购 (CART) | 215,167 | 75.3% |
| 购买 (BUY) | 195,078 | 68.3% |

> **洞察**：从浏览到收藏流失了 60%，从加购到购买流失了 32%。收藏行为是「兴趣形成」的关键瓶颈。

### 4.2 用户留存：D1 留存仅 53%

- **Day 1 留存**：53.2%（近一半用户次日不再回来）
- **Day 7 留存**：骤降至 5~8%
- 用户生命周期中位数为 **3 天**

### 4.3 高曝光低转化商品：51 万件问题商品

- 有 **51.3 万** 件商品 PV 在前 25% 但购买转化率在后 50%
- 这些商品占用了大量曝光资源但转化效率极低

### 4.4 用户分群：尾部用户占多数

| 频次分组 | 用户占比 | 购买率 |
|----------|----------|--------|
| 1 次 | 13.2% | 0% |
| 2-5 次 | 27.8% | ~14% |
| 6-20 次 | 29.1% | ~38% |
| 21-100 次 | 21.6% | ~67% |
| 101-500 次 | 7.3% | ~86% |
| 500+ 次 | 1.0% | ~94% |

> **洞察**：约 70% 用户行为次数 ≤ 20 次，属于低活跃用户。但中高频用户（21+）购买率从 67% 跃升至 94%，说明「习惯养成」是关键转化点。

---

## 5. 策略建议

### 5.1 产品侧：修复漏斗断裂点

1. **增强收藏转化**：对收藏后 24h 未加购的用户推送限时优惠
2. **缩短决策路径**：在商品详情页强化「立即购买」入口
3. **减少无效曝光**：对高曝光低转化商品降权，释放流量给高转化商品

### 5.2 运营侧：分群差异化策略

| 用户分群 | 运营策略 |
|----------|----------|
| 低频浏览型 (1-5 次) | 新用户首单补贴、首页个性化推荐 |
| 中等活跃型 (6-20 次) | 品类偏好推荐、签到奖励 |
| 高频转化型 (21-100 次) | 会员权益、复购优惠券 |
| 超级用户 (100+) | VIP 专属客服、新品优先体验 |

### 5.3 推荐侧：算法优化方向

1. **召回层**：提高用户兴趣类目（favorite_category）的召回权重
2. **排序层**：将商品转化率（buy_rate_pct）作为排序特征
3. **冷启动**：对 Session 前 3 个行为优先展示高转化商品

---

## 6. 项目结构

```
project/
├── README.md                          # 本文档
├── experiment_log.md                  # 执行日志（自动生成）
│
├── data/
│   ├── raw/                           # 原始数据
│   │   └── user_data.csv              # (1.0 GB) 天池原始 CSV
│   ├── clean_data.parquet             # (337 MB) Clean Layer
│   ├── analysis.db                    # (353 MB) DuckDB 分析库
│   ├── mart/                          # ★ Power BI 数据源 (15 张 Parquet)
│   │   ├── profiling_summary.parquet       # 数据画像
│   │   ├── funnel_summary.parquet          # 转化漏斗
│   │   ├── user_conversion_summary.parquet # 用户转化 KPI
│   │   ├── cohort_retention_detail.parquet # 留存热力图
│   │   ├── cohort_retention_summary.parquet# 留存曲线
│   │   ├── daily_behavior_summary.parquet  # DAU 趋势
│   │   ├── hourly_behavior_summary.parquet # 时段分布
│   │   ├── weekday_behavior_summary.parquet# 周末 vs 工作日
│   │   ├── category_conversion.parquet     # 类目转化排行
│   │   ├── item_conversion.parquet         # 商品转化明细
│   │   ├── high_exposure_low_conversion_items.parquet  # 问题商品
│   │   ├── user_segment_summary.parquet    # 用户分群
│   │   ├── session_stats.parquet           # Session 转化
│   │   ├── dim_date.parquet               # ★ 日期维度
│   │   └── dim_category.parquet           # ★ 类目维度
│   └── features/
│       └── user_features.parquet       # ★ Python ML 特征 (28 维)
│
├── sql/
│   ├── data_preview.sql               # ETL: 数据预览
│   ├── data_cleaning.sql              # ETL: 清洗 + 派生字段
│   ├── data_cleaning.py               # ETL: 编排入口
│   ├── 00_init.sql                    # 共享基础层（中间表）
│   ├── 01_profiling.sql               # 数据画像
│   ├── 02_funnel_retention.sql        # 漏斗 & 留存
│   ├── 03_behavior_analysis.sql       # 日度/小时/Session
│   ├── 04_product_analysis.sql        # 商品 & 类目
│   ├── 05_user_analysis.sql           # 用户画像 & 分群
│   ├── 06_feature_mart.sql            # 特征宽表 (28 维)
│   ├── 07_export_mart.sql             # 统一导出 Parquet
│   └── run_all.py                     # ★ 全流程编排器
│
└── notebooks/                         # (可选) Jupyter 分析笔记
```

---

## 7. 快速开始

### 7.1 环境

```bash
pip install duckdb pandas pyarrow scikit-learn scipy
```

### 7.2 执行全流程

```bash
# Step 1: ETL（首次运行）
python sql/data_cleaning.py all

# Step 2: 全量 SQL 分析 + 自动导出
python sql/run_all.py

# Step 3: 查看业务表
python sql/run_all.py --show-tables
python sql/run_all.py --show funnel_summary
```

### 7.3 Python 聚类

```python
import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans

# 读取特征（28 维，全数值化，零空值）
df = pd.read_parquet("data/features/user_features.parquet")

# 分离特征和标签
feature_cols = df.drop(columns=["user_id", "is_buyer"]).columns
X = StandardScaler().fit_transform(df[feature_cols])

# KMeans 聚类
kmeans = KMeans(n_clusters=5, random_state=42, n_init=10)
df["cluster"] = kmeans.fit_predict(X)

# 分析各簇的用户画像
print(df.groupby("cluster")[["is_buyer", "buy_to_pv_ratio", "active_days"]].mean())
```

### 7.4 Power BI 接入

Power BI Desktop → 获取数据 → Parquet → 选择 `data/mart/` 目录：

**星型模型设计**：

```
dim_date (日期维度)
    │
    ├── daily_behavior_summary (事实: 日度行为)
    ├── cohort_retention_detail  (事实: 留存)
    │
dim_category (类目维度)
    │
    ├── category_conversion (事实: 类目转化)
    ├── item_conversion      (事实: 商品转化)
    │
user_segment_summary (事实: 用户分群)
funnel_summary         (事实: 漏斗)
```

---

## 8. 特征宽表字段说明 (user_features)

| # | 字段 | 类型 | 维度 | 说明 |
|----|------|------|------|------|
| 1 | user_id | BIGINT | 标识 | 用户 ID（不入模） |
| 2-5 | pv/fav/cart/buy_cnt | BIGINT | 行为计数 | 四类行为次数 |
| 6-10 | active_days, buy_days, avg_actions_per_day, lifecycle_days, active_weeks | - | 活跃度 | 活跃天数/购买天数/生命周数 |
| 11-17 | weekend/morning/afternoon/evening/night_ratio, hour_concentration, peak_hour | DOUBLE | 时间偏好 | 各时段行为占比 + HHI 集中度 |
| 18-21 | favorite_category, category/item_diversity, category_concentration | - | 品类偏好 | 最常交互类目 + 广度 + 集中度 |
| 22-25 | cart/fav/buy_to_pv_ratio, buy_to_cart_ratio | DOUBLE | 转化深度 | 行为转化漏斗（用户粒度） |
| 26-28 | recent_7d/30d_actions_pct, days_since_last_active | DOUBLE | 近期活跃 ★ | 活跃衰减趋势 |
| 29 | weekly_volatility | DOUBLE | 行为稳定 ★ | 周行为变异系数 |
| 30 | is_buyer | INTEGER | 标签 | 是否购买（聚类时排除） |

> **28 个特征** 覆盖 6 个维度：行为量级、活跃度、时间偏好、品类偏好、转化深度、行为稳定性。

---

## 9. 技术亮点

- **SQL-first 架构**：核心分析逻辑在 SQL 中完成，Python 仅做 ML，Power BI 仅做可视化
- **中间表设计**：`user_base_metrics` 避免 5,800 万行重复扫描
- **特征工程完整**：28 维特征覆盖 6 个行为维度，零空值，可直接 sklearn
- **分层持久化**：Raw → Clean → Analysis → Mart → Feature，各层独立、可回溯
- **工程化编排**：`run_all.py` 支持断点续跑、表验证、日志记录、自动导出
- **星型模型**：为 Power BI 设计了 `dim_date` + `dim_category` 维度表

---

## 10. 局限性与下一步

### 当前局限性

- **时间窗口短**：仅 9 天数据，无法分析月度和季节性趋势
- **无用户画像字段**：缺少年龄、性别、地域等人口统计学特征
- **无商品属性**：缺少价格、品牌、评分等商品元数据
- **行为序列浅**：缺少商品详情页停留时长、搜索词等深度行为信号

### 下一步扩展方向

1. **实时特征**：对接 Flink/Kafka 实现实时用户行为特征
2. **推荐模型**：基于 `user_features` + `item_features` 构建 CTR/CVR 预估模型
3. **A/B 实验**：设计实验框架验证运营策略效果
4. **因果推断**：使用 DML (Double ML) 估计「收藏→购买」的因果效应
