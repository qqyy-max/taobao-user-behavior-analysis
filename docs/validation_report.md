# 验证报告 (Validation Report)

**日期**：2026-06-01
**背景**：修复 `data_cleaning.sql` 时间过滤条件后，全链路重跑并验证

---

## 时间范围验证

| 指标 | 修复前 | 修复后 | 期望值 | 状态 |
|------|--------|--------|--------|------|
| 最小日期 | 2017-04-11 | **2017-11-25** | 2017-11-25 | ✅ PASS |
| 最大日期 | 2017-12-31 | **2017-12-03** | 2017-12-03 | ✅ PASS |
| 覆盖天数 | 82 | **9** | 9 | ✅ PASS |
| 覆盖月份 | 8 | **2** | 2 | ✅ PASS |
| 窗口外记录数 | 15,347 | **0** | 0 | ✅ PASS |

---

## 关键表验证

| 表名 | 行数 | 关键指标 | 状态 |
|------|------|----------|------|
| `dim_date` | 9 | 9 天，2017-11-25 ~ 2017-12-03 | ✅ PASS |
| `cohort_retention_detail` | 44 | 8 cohorts, retention_day 0~8 | ✅ PASS |
| `cohort_retention_summary` | 9 | retention_day 0~8 | ✅ PASS |
| `daily_behavior_summary` | 9 | 仅 9 天，无窗口外日期 | ✅ PASS |

---

## Power BI 导出表验证

| 表名 | 行数 | 状态 |
|------|------|------|
| `profiling_summary` | 33 | ✅ |
| `user_conversion_summary` | 1 | ✅ |
| `funnel_summary` | 4 | ✅ |
| `daily_behavior_summary` | 9 | ✅ |
| `hourly_behavior_summary` | 24 | ✅ |
| `weekday_behavior_summary` | 2 | ✅ |
| `session_stats` | 5 | ✅ |
| `category_conversion` | 8,787 | ✅ |
| `high_exposure_low_conversion_items` | 512,540 | ✅ |
| `user_cluster_summary` | 5 | ✅ |
| `user_segment_summary` | 6 | ✅ |
| **Excel 工作簿** | **16 Sheets** | ✅ |

---

## 异常检查

| 检查项 | 结果 | 状态 |
|--------|------|------|
| 早于 2017-11-25 的记录 | 0 | ✅ PASS |
| 晚于 2017-12-03 的记录 | 0 | ✅ PASS |
| Cohort 超过 Day 8 | 0（最大=8） | ✅ PASS |

---

## 最终结论

> **PASS — 项目已恢复到官方 9 天数据窗口**
>
> 所有 11 张 Power BI 聚合表、2 张维度表、1 个 Excel 工作簿均通过验证。
