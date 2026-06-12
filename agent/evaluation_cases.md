# Agent 测试问题集与评估标准

> **版本**：v1.0 | 2026-06-11
> **用途**：Agent 输出质量自动化验证，覆盖 8 个核心业务场景

---

## T1: 指标口径查询

```yaml
question: "购买率怎么算的？行为维度和用户维度有什么区别？"
expected_tools:
  - get_business_context
  - query_duckdb (user_conversion_summary + daily_behavior_summary)
expected_output:
  - 明确区分行为维度购买率(~2.0%)和用户维度购买率(~68.0%)
  - 给出两种口径的计算公式
  - 标注"行为维度"和"用户维度"标签
  - ≥3 个具体数字
reviewer_checks:
  - B-001: 数字≥3 ✓
  - B-002: 无模糊词 ✓
  - B-003: ≥150字 ✓
  - D-维度: 提及购买率时标注维度 ✓
```

---

## T2: 加购未购用户分析

```yaml
question: "加购未购买的用户有多少？他们有什么特征？"
expected_tools:
  - get_business_context
  - query_duckdb (cart_abandon_summary + cart_abandon_users)
expected_output:
  - 用户数: 60,891 (精确)
  - 占加购用户比例: ~28.3%
  - 行为特征: avg_cart_items, avg_active_days, avg_daily_pv
  - 触达优先级: days_since_last_cart分布
  - ≥3 个具体数字
reviewer_checks:
  - B-001: 数字≥3 ✓
  - B-002: 无模糊词 ✓
  - B-003: ≥150字 ✓
  - D-窗口: 标注"窗口内"限制 ✓
  - D-禁止词: 无"流失"/"购物车放弃率" ✓
```

---

## T3: 用户分层查询

```yaml
question: "4 类运营分层各有多少人？购买率差异如何？"
expected_tools:
  - query_duckdb (segment_summary)
expected_output:
  - 5层规模 (P0-P3+REF)
  - 各层buyer_rate_pct
  - 使用segment_summary表（而非user_cluster_summary）
  - ≥3 个具体数字
reviewer_checks:
  - B-001: 数字≥3 ✓
  - B-002: 无模糊词 ✓
  - C-来源: 使用规则分层(segment_summary)而非KMeans聚类 ✓
  - D-禁止词: 不推断"生命周期阶段" ✓
```

---

## T4: 周末异动归因

```yaml
question: "周末购买率为什么比工作日低？"
expected_tools:
  - query_duckdb (weekend_anomaly_summary, daily_behavior_summary)
expected_output:
  - 周末DAU变化: +16%
  - 购买率变化: -10%
  - 维度拆解: 行为类型占比变化 / 人均PV变化
  - 原因假设: "逛型流量增加"
  - 运营建议: 周末推内容而非促销
  - ≥3 个具体数字
reviewer_checks:
  - B-001: 数字≥3 ✓
  - B-002: 无模糊词 ✓
  - D-逻辑: 原因假设与数据一致 ✓
```

---

## T5: 时段分析

```yaml
question: "为什么夜间流量高但购买少？上午反而购买多？"
expected_tools:
  - query_duckdb (hourly_behavior_summary, hourly_anomaly_summary)
expected_output:
  - 流量峰值: 21:00
  - 购买率峰值: 10:00 (2.62%)
  - 购买率谷值: 21:00 (1.73%)
  - 时段分组对比(上午/下午/晚间/深夜)
  - 建议: Push排期调整到9:30
  - ≥3 个具体数字
reviewer_checks:
  - B-001: 数字≥3 ✓
  - B-002: 无模糊词 ✓
  - D-逻辑: 时序错位解释合理 ✓
```

---

## T6: 商品效率

```yaml
question: "高曝光低转化的商品有多少？什么特征？"
expected_tools:
  - query_duckdb (high_exposure_low_conversion_items + product_efficiency_anomaly_summary)
expected_output:
  - 商品数: 51.3万件
  - 阈值: PV≥P75 (动态)，buy_rate≤MEDIAN
  - 类目分布Top N
  - 搜索直达商品: 11,781件
  - 约束声明: 缺少曝光来源字段，不直接等同于推荐降权
  - ≥3 个具体数字
reviewer_checks:
  - B-001: 数字≥3 ✓
  - D-约束: 标注缺少曝光来源字段 ✓
  - C-来源: 使用high_exposure_low_conversion_items表 ✓
```

---

## T7: 策略生成

```yaml
question: "针对加购未购用户，设计一个运营策略"
expected_tools:
  - query_duckdb (cart_abandon_summary)
  - Strategist生成策略
expected_output:
  - 策略四要素:
    - 目标群体: 加购未购用户(60,891人)，优先触达days_since_last_cart≤2
    - 触达时机: 加购后24-48h
    - 具体动作: Push推送 + 限时折扣券
    - 可量化KPI: 目标购买转化10-15%
  - ≥3 个具体数字
reviewer_checks:
  - S-001: 目标群体明确 ✓
  - S-002: KPI可量化 ✓
  - S-003: 四要素齐全 ✓
  - D-声明: 标注"窗口内"限制 ✓
```

---

## T8: 实验设计

```yaml
question: "帮我设计一个加购未购用户的 A/B 实验方案"
expected_tools:
  - query_duckdb (cart_abandon_users + cart_abandon_summary)
expected_output:
  - 实验分组: 至少2组(实验组+对照组)
  - 核心指标: 购买转化率
  - 观察窗口: 7天
  - 显著性检验方法: χ²检验或Fisher精确检验
  - ⚠️ 标注"离线数据设计方案，非实际实验结果"
  - ≥3 个具体数字
reviewer_checks:
  - B-001: 数字≥3 ✓
  - D-声明: 标注"离线数据设计方案" ✓
  - S-002: KPI可量化 ✓
  - B-002: 无模糊词 ✓
```

---

## 评估标准

| 维度 | 合格标准 | 权重 |
|------|---------|------|
| SQL 正确性 | 查询无语法错误、返回预期结果 | 20% |
| 指标口径一致性 | 与 metrics_dictionary.md 定义一致 | 20% |
| 9 天窗口约束 | 不使用"长期留存/复购/生命周期/流失" | 15% |
| 非线性路径约束 | 不使用"漏斗转化率" | 10% |
| 数字支撑 | 每个结论至少引用 1 个具体数字，全文 ≥ 3 个 | 15% |
| 策略可执行性 | 包含目标群体、触达时机、具体动作、KPI | 10% |
| 离线声明 | 策略验证类问题明确说明"设计方案，非实际结果" | 10% |

---

## 通过标准

- **优秀**: 8/8 通过 Reviewer 阻断级检查
- **合格**: ≥6/8 通过
- **不合格**: <6/8 通过

测试结果记录在 `agent/test_results.json` (自动生成)。
