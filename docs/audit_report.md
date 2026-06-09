# 数据质量审计报告 (Data Quality Audit Report)

**项目**：淘宝用户行为分析与转化优化
**审计日期**：2026-06-01
**审计范围**：全链路数据质量 — 原始数据 → 清洗层 → 特征层 → 聚合层 → BI 导出
**严重等级**：🔴 高 — 清洗过滤条件过宽，时间窗口从 9 天膨胀为 82 天

---

## 第一部分：数据链路追踪

### 完整数据流

```
data/user_data.csv (CSV, 2,900 万行)
        │
        ▼  [data_cleaning.sql §1]
  raw_data (VIEW) — 直接映射 CSV 列
        │
        ▼  [data_cleaning.sql §2]  ★ 问题发生点
  clean_data (TABLE) — 过滤 + 类型转换
        │  raw_timestamp BETWEEN 1483228800 AND 1514736000
        │  = 保留 2017-01-01 ~ 2017-12-31 全部数据
        │
        ▼  [data_cleaning.sql §3]
  clean_data_enriched (TABLE) — 添加 dt, hour, weekday, is_weekend, month
        │
        ▼  [data_cleaning.sql §4]  去重
  clean_data_enriched (deduplicated)
        │
        ├─► COPY TO data/clean_data.parquet      ← 持久化存储 (337 MB)
        │
        ▼  [00_init.sql §1]
  clean (VIEW) — read_parquet('data/clean_data.parquet')
        │
        ├─► [00_init.sql §2]  dim_date            ← 82 天 (预期 9 天)
        ├─► [00_init.sql §3]  user_base_metrics    ← 用户粒度聚合
        ├─► [00_init.sql §4]  category_base_stats  ← 类目粒度聚合
        │
        ├─► [01_profiling.sql]     profiling_summary
        │
        ├─► [02_funnel_retention.sql]
        │     ├─ funnel_summary
        │     ├─ user_conversion_summary
        │     ├─ cohort_retention_detail     ← 73 个 Cohort (预期 ~9 个)
        │     └─ cohort_retention_summary    ← retention_day 0~236 (预期 0~8)
        │
        ├─► [03_behavior_analysis.sql]
        │     ├─ daily_behavior_summary      ← 82 天 (预期 9 天)
        │     ├─ hourly_behavior_summary
        │     ├─ weekday_behavior_summary
        │     └─ session_stats
        │
        ├─► [04_product_analysis.sql]
        │     ├─ category_conversion
        │     ├─ item_conversion
        │     └─ high_exposure_low_conversion_items
        │
        ├─► [05_user_analysis.sql]
        │     ├─ user_profile
        │     └─ user_segment_summary
        │
        ├─► [06_feature_mart.sql]
        │     └─ user_features (35 维) → src/user_clustering.py
        │           └─ user_cluster_result  →  src/cluster_analysis.py
        │                 └─ user_cluster_summary
        │
        └─► [07_export_mart.sql]  → data/mart/*.parquet (15 张)
              └─ src/export_for_powerbi.py  → exports/user_behavior_dashboard.xlsx
```

### 依赖关系树

```
raw_data (CSV)
  └─ clean_data ──► clean_data_enriched ──► clean (view)
        │                                      │
        │                    ┌──────────────────┼──────────────────┐
        │                    │                  │                  │
        │                    ▼                  ▼                  ▼
        │              dim_date          user_base_metrics   category_base_stats
        │              (82 天 ❌)         (287,004 用户)      (8,788 类目)
        │                    │                  │                  │
        │                    │    ┌─────────────┼──────┬───────────┤
        │                    │    │             │      │           │
        │                    │    ▼             ▼      ▼           ▼
        │                    │  02_funnel    05_user  06_feature  04_product
        │                    │    │             │      │           │
        │                    │    ▼             ▼      ▼           ▼
        │                    │  cohort_*     segment  features   category_*
        │                    │  (受影响 🔴)  (受影响 🟡) (受影响 🟡) (受影响 🟢)
        │                    │    │             │      │           │
        │                    │    │             │      ▼           │
        │                    │    │             │  clustering      │
        │                    │    │             │      │           │
        │                    │    │             │      ▼           │
        │                    │    │             │  cluster_summary │
        │                    │    │             │  (受影响 🟡)     │
        │                    │    │             │                  │
        │                    └────┼─────────────┴──────────────────┘
        │                         │
        │                         ▼
        │                   03_behavior
        │                         │
        │                         ▼
        │                   daily_behavior_summary (82 天 ❌)
        │                   hourly_* | weekday_* | session_*
        │
        └──────────────────────────┘
```

---

## 第二部分：异常时间来源定位

### 2.1 原始数据时间戳审计

**原始 CSV 时间戳范围**：

| 指标 | 值 |
|------|-----|
| 总行数 | 29,132,492 |
| 最小 raw_timestamp | -2,034,497,153 (对应 1905-07-13) |
| 最大 raw_timestamp | 2,122,867,355 (对应 2037-04-09) |
| 合法时间戳去重数 | 789,787 |

### 2.2 按时间区间分布

| 区间 | 行数 | 占比 | 判定 |
|------|------|------|------|
| 负数时间戳 (<0) | 56 | 0.0002% | 异常，应过滤 |
| < 2017-01-01 | 86 | 0.0003% | 异常，应过滤 |
| 2017-01-01 ~ 2017-11-24 | **15,090** | **0.0518%** | ⚠️ 问题数据，当前被错误保留 |
| **2017-11-25 ~ 2017-12-03** | **29,116,721** | **99.9467%** | ✅ 预期窗口 |
| 2017-12-04 ~ 2017-12-31 | 257 | 0.0009% | ⚠️ 超出窗口，当前被错误保留 |
| > 2017-12-31 | 282 | 0.0010% | 异常，应过滤 |

### 2.3 结论

> **原始数据质量极高**：99.95% 的记录落在预期 9 天窗口内。仅 15,347 条 (0.05%) 记录在窗口外。**问题根因不在原始数据，而在清洗过滤条件。**

---

## 第三部分：清洗逻辑审查

### 3.1 当前过滤条件

**位置**：`sql/data_cleaning.sql` 第 37 行

```sql
AND raw_timestamp BETWEEN 1483228800 AND 1514736000;
```

| 时间戳 | 对应日期 (CST) | 说明 |
|--------|---------------|------|
| `1483228800` | **2017-01-01 08:00:00** | 2017 年第一天 |
| `1514736000` | **2018-01-01 00:00:00** | 2018 年第一天（即 2017 年最后一刻） |

### 3.2 为什么覆盖天数是 82 天？

**根因**：过滤条件保留了整个 2017 年，而不是仅保留 9 天窗口。

数据中实际存在的日期的来源：
- **2017-04-11 ~ 2017-10-31**（48 天，231 行）：极稀疏的噪声数据，每天 1~5 个用户，应该是时间戳异常或测试数据
- **2017-11-01 ~ 2017-11-23**（23 天，3,081 行）：11 月初开始的预热数据，用户数每日递增（5 → 1,031）
- **2017-11-24**（1 天，11,778 行，9,744 用户）：数据正式开始前一天的高密度数据
- **2017-11-25 ~ 2017-12-03**（9 天，29,116,721 行）：✅ 预期窗口
- **2017-12-04 ~ 2017-12-31**（6 天，257 行）：窗口后的稀疏残留

### 3.3 是否错误保留了窗口外数据？

**是的。** 证据如下：

| 证据 | 来源 |
|------|------|
| clean_data 包含 2017-04-11 ~ 2017-12-31 共 82 个不同日期 | `SELECT COUNT(DISTINCT dt) FROM clean_data` = 82 |
| 2017-04-11 有 1 个用户的 9 条行为记录 | 与"9 天数据集"理论窗口完全无关 |
| dim_date 表包含 82 行 | 导致 Power BI 日期维度跨 8 个月 |
| cohort_retention_detail 包含 73 个 cohort_date | 每天有用户"首次活跃"就会产生一个 Cohort |

### 3.4 是否应该限制为官方窗口？

**是的，强烈建议。** 理由：

1. 官方数据集文档明确声明时间范围为 **2017-11-25 ~ 2017-12-03（9 天）**
2. 99.95% 的数据在窗口内，0.05% 在窗口外
3. 窗口外数据（Apr-Oct 的 231 行）是孤立的噪声点，不构成有效分析基础
4. 11-24 的 11,778 行是窗口前一天的数据，可能是数据导出时的边界效应

---

## 第四部分：影响范围分析

### 4.1 严重度定义

| 等级 | 含义 |
|------|------|
| 🔴 严重影响 | 表中大部分行无效，直接导致分析结论错误 |
| 🟡 轻微影响 | 聚合值被 0.05% 额外数据稀释，对整体结论影响小但不可忽略 |
| 🟢 无影响 | 表结构不受日期窗口影响，或行数极少不受稀释 |

### 4.2 逐表评估

| 表名 | 行数 | 影响等级 | 原因 |
|------|------|----------|------|
| **dim_date** | 82 | 🔴 **严重** | 82 天 vs 预期 9 天。Power BI 日期筛选器显示 8 个月的日期范围，73/82 行(89%)为噪声。 |
| **cohort_retention_detail** | 704 | 🔴 **严重** | 73 个 Cohort vs 预期 ~9 个。651/704 行(92%)为无效 Cohort。retention_day 最大 236（用户从 4 月活跃到 12 月），Day 7 留存率被稀释。 |
| **cohort_retention_summary** | 149 | 🔴 **严重** | retention_day 0~236，而有效窗口仅 9 天，最大 retention_day 应为 8。全部超过 Day 8 的数据都是虚假的。 |
| **daily_behavior_summary** | 82 | 🔴 **严重** | 73/82 天(89%)在窗口外。2017-04-11 的 DAU=1（1 个用户 9 条行为），毫无业务意义。Power BI 趋势图被严重污染。 |
| **hourly_behavior_summary** | 24 | 🟢 无影响 | 按小时聚合，与日期窗口无关。额外 0.05% 数据不影响时段分布。 |
| **weekday_behavior_summary** | 2 | 🟢 无影响 | 周末 vs 工作日对比，聚合级数据，0.05% 影响可忽略。 |
| **session_stats** | 5 | 🟢 无影响 | Session 分组统计，5 行固定分组，0.05% 不影响结论。 |
| **funnel_summary** | 4 | 🟡 轻微 | UV 被额外用户抬升。购买 UV 从 ~195,000 变为 195,078（+78），差异 0.04%。 |
| **user_conversion_summary** | 1 | 🟡 轻微 | 总用户数从 ~287,000 变为 287,004（含 2017-04-11 的 1 个用户等）。 |
| **category_conversion** | 8,788 | 🟢 无影响 | 类目级聚合，排名基于全量数据，0.05% 不改变 Top/Bottom 排行。 |
| **high_exposure_low_conversion_items** | 512,812 | 🟡 轻微 | P75 阈值可能被微量数据略微偏移，差值在个位数内。 |
| **user_cluster_summary** | 5 | 🟡 轻微 | 额外用户进入聚类池（~200 个极稀疏用户从 Apr-Oct + 9,744 个从 11-24 进入），可能略微影响聚类中心和边界用户的归属。但从数据量级看（287k 用户中的 ~10k），影响有限。 |
| **user_segment_summary** | 6 | 🟡 轻微 | 频次分群，额外低活跃用户可能略微改变低频段的占比。 |
| **profiling_summary** | 33 | 🟡 轻微 | 总行数显示 29,132,068（含窗口外 15,347 行）。date_range 显示 2017-04-11 ~ 2017-12-31，与预期不符。 |
| **item_conversion** | 2,585,541 | 🟢 无影响 | 商品级聚合，0.05% 额外数据不影响排名。 |

---

## 第五部分：修复方案

### 5.1 修改文件列表

| 文件 | 修改内容 | 影响范围 |
|------|----------|----------|
| `sql/data_cleaning.sql` 第 37 行 | 收紧时间戳过滤条件 | 源头修复，所有下游表自动纠正 |

### 5.2 修改位置

**文件**：`sql/data_cleaning.sql`
**行号**：第 37 行

**当前代码**：
```sql
-- 去掉离谱时间戳（限制在 2017 年内）
AND raw_timestamp BETWEEN 1483228800 AND 1514736000;
```

**修改为**：
```sql
-- 仅保留官方数据集窗口：2017-11-25 ~ 2017-12-03 (CST, UTC+8)
-- 注：raw_timestamp 为本地时间(CST)的 Unix 秒数
-- 1511539200 = 2017-11-25 00:00:00 CST
-- 1512345600 = 2017-12-04 00:00:00 CST (不含，严格小于)
AND raw_timestamp >= 1511539200
AND raw_timestamp <  1512345600;
```

### 5.3 时间戳验证

| 时间戳 | 日期 (CST) | 
|--------|-----------|
| `1511539200` | 2017-11-25 00:00:00 |
| `1512345600` | 2017-12-04 00:00:00 |

使用 `>=` 和 `<` 确保包含 2017-11-25 全天至 2017-12-03 全天，共 9 天。

### 5.4 是否需要重跑

| 层级 | 文件 | 需要重跑 | 原因 |
|------|------|----------|------|
| **清洗层** | `data_cleaning.sql` | ✅ 必须 | 源头修复 |
| **基础层** | `00_init.sql` | ✅ 必须 | clean 视图引用了 clean_data.parquet |
| **聚合层** | `01~05_*.sql` | ✅ 必须 | 所有聚合表都依赖 clean |
| **特征层** | `06_feature_mart.sql` | ✅ 必须 | user_features 依赖 clean → user_base_metrics |
| **聚类** | `src/user_clustering.py` | ✅ 必须 | 特征表变化，需重新聚类 |
| **聚类分析** | `src/cluster_analysis.py` | ✅ 必须 | 聚类结果变化 |
| **可视化** | `src/visualization.py` | ✅ 建议 | 图表数据更新 |
| **BI 导出** | `07_export_mart.sql` + `export_for_powerbi.py` | ✅ 必须 | |
| **Excel 导出** | `src/export_for_powerbi.py` | ✅ 必须 | |

### 5.5 预计耗时

| 步骤 | 预计耗时 |
|------|----------|
| 修改 `data_cleaning.sql` | 1 分钟 |
| 重跑 `data_cleaning.py clean` | ~5 分钟 |
| 重跑 `00_init.sql` | ~2 分钟 |
| 重跑 `01~07` SQL 分析 | ~10 分钟 |
| 重跑 `user_clustering.py` | ~3 分钟 |
| 重跑 `cluster_analysis.py` | ~1 分钟 |
| 重跑 `export_for_powerbi.py` | ~2 分钟 |
| **总计** | **~25 分钟** |

---

## 第六部分：验证清单

修复后应逐条验证：

### 6.1 清洗层

- [ ] `clean_data` 行数 = 29,116,721（原始数据的 99.95%）
- [ ] `clean_data_enriched` 时间范围 = 2017-11-25 ~ 2017-12-03
- [ ] 覆盖天数 = 9
- [ ] 覆盖月份 = 2（11 月和 12 月）

### 6.2 基础层

- [ ] `dim_date` 行数 = 9（仅 2017-11-25 ~ 2017-12-03）
- [ ] `dim_date.dt` 连续无断点
- [ ] `user_base_metrics.user_cnt` ≈ 285,800（原 287,004 减去窗口外用户）

### 6.3 聚合层

- [ ] `daily_behavior_summary` 行数 = 9
- [ ] `daily_behavior_summary.dt` 仅包含 2017-11-25 ~ 2017-12-03
- [ ] `cohort_retention_detail.cohort_date` 数量 ≈ 8~9 个
- [ ] `cohort_retention_detail.retention_day` 最大值 = 8
- [ ] `cohort_retention_summary` 行数 ≤ 9
- [ ] `funnel_summary` UV 值在预期范围内（约 285,800）
- [ ] `profiling_summary.date_range` 显示 2017-11-25 ~ 2017-12-03

### 6.4 用户分析层

- [ ] `user_cluster_summary` 用户总数 ≈ 285,800
- [ ] 聚类结果与修复前基本一致（仅边界用户可能迁移）
- [ ] `user_segment_summary` 频次分布无明显漂移

### 6.5 Power BI 导出

- [ ] `exports/user_behavior_dashboard.xlsx` 中所有日期字段在预期窗口内
- [ ] `dashboard_metadata` Sheet 正常
- [ ] 总 Sheet 数 = 16（1 metadata + 15 data）
- [ ] 所有指标与 9 天数据一致

---

## 附录 A：审计执行记录

```
审计时间: 2026-06-01 17:00~17:30
审计方法: DuckDB 直接查询 raw_data CSV + clean_data.parquet + 所有 mart/*.parquet
数据版本: 当前 data/ 目录下的持久化文件
审计结论: 🔴 清洗过滤条件过宽，需要修复后重跑全链路
```

## 附录 B：原始日志证据

```
数据清洗日志 (experiment_log.md):
- 覆盖天数: 82
- 覆盖月份: 8
- clean_data_enriched 行数: 29,132,068

预期值:
- 覆盖天数: 9
- 覆盖月份: 2
- clean_data_enriched 行数: 29,116,721 (29,132,068 - 15,347)
```
