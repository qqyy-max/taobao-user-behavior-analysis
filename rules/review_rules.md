# Review Rules — Reviewer Agent 校验清单

> **版本**：v1.0 | 2026-06-08
> **适用 Agent**：Reviewer Agent（规则验证器）
> **触发时机**：Analyst Agent 输出分析结果后，自动执行 `rule_based_review()` 函数
> **设计原则**：分级校验（阻断级 → 警告级 → 质量级），不通过则触发重试。

---

## 目录

1. [校验架构](#1-校验架构)
2. [阻断级校验 (Blocker)](#2-阻断级校验-blocker)
3. [数据校验 (Data Sanity)](#3-数据校验-data-sanity)
4. [指标一致性校验](#4-指标一致性校验)
5. [输出质量校验](#5-输出质量校验)
6. [业务逻辑校验](#6-业务逻辑校验)
7. [策略质量校验](#7-策略质量校验)
8. [校验结果处理](#8-校验结果处理)
9. [Reviewer Agent Prompt](#9-reviewer-agent-prompt)

---

## 1. 校验架构

```
Analyst 输出
    │
    ├─→ Phase 1: 阻断级校验 (Blocker)
    │    ├─ 通过 → Phase 2
    │    └─ 失败 → 停止，要求 Analyst 重做
    │
    ├─→ Phase 2: 数据校验 (Data Sanity)
    │    ├─ 通过 → Phase 3
    │    └─ 失败 → 标注 Warning，继续
    │
    ├─→ Phase 3: 输出质量校验 (Quality)
    │    ├─ 通过 → Phase 4
    │    └─ 失败 → 反馈修改建议，重试（最多 2 次）
    │
    └─→ Phase 4: 业务逻辑校验 (Business Logic)
         ├─ 通过 → 输出给 Strategist
         └─ 失败 → 标注 Concern，继续
```

---

## 2. 阻断级校验 (Blocker)

**失败时停止流程，要求 Analyst 重做**

### B-001: 数字支撑不足

```yaml
rule: "必须包含 ≥3 个具体数字或百分比"
check: |
  arabic_nums = count(re.findall(r'\d+\.?\d*%?', text))
  chinese_nums = count(re.findall(r'[一二三四五六七八九十百千万亿]+', text))
  ASSERT arabic_nums + chinese_nums >= 3

fail_message: |
  【验证未通过】
  - 数字支撑不足（仅找到 {total} 个数字/百分比，要求 ≥3 个）
```

### B-002: 存在模糊表述

```yaml
rule: "禁止使用模糊词"
fuzzy_words:
  - "较高"
  - "明显"
  - "显著"
  - "一定程度"
  - "有所"
  - "相对较"
  - "比较高"
  - "比较低"
  - "有所提升"
  - "大幅度"

check: |
  found = [w for w in fuzzy_words if w in text]
  ASSERT len(found) == 0

fail_message: |
  【验证未通过】
  - 存在模糊表述：{found_words}，请替换为具体数字
```

### B-003: 内容过短

```yaml
rule: "分析结果 ≥150 字"
check: ASSERT len(text.strip()) >= 150

fail_message: |
  【验证未通过】
  - 内容过短（{len} 字，要求 ≥150 字）
```

### B-004: 缺少必要段落

```yaml
rule: "必须包含【数据摘要】或等价段落"
check: |
  required_sections = ["数据摘要", "核心数字", "关键数据", "分析结论"]
  ASSERT any(section in text for section in required_sections)

fail_message: |
  【验证未通过】
  - 缺少必要段落：必须包含数据摘要/核心数字部分
```

---

## 3. 数据校验 (Data Sanity)

**失败时输出 Warning，不阻断流程**

### D-001: 购买 UV 不超浏览 UV

```yaml
rule: "buy_uv ≤ pv_uv"
check: |
  FOR each mention of buy_uv and pv_uv:
    ASSERT buy_uv <= pv_uv OR has_explanation
severity: WARNING

warning_message: "⚠️ 购买用户数 ({buy_uv}) > 浏览用户数 ({pv_uv})，如为搜索直达商品请说明"
```

### D-002: 转化率不超过 100%（用户维度）

```yaml
rule: "用户维度转化率 ≤ 100%"
check: |
  FOR each conversion_rate mention:
    IF user_dimension AND rate > 100:
      ASSERT False
severity: WARNING

warning_message: "⚠️ 用户维度转化率 {rate}% 超过 100%，请核实计算方法"
```

### D-003: 行为维度转化率合理性

```yaml
rule: "行为维度购买率正常范围 1.5%-3.0%"
check: |
  FOR each buy_rate_actions mention:
    IF rate < 1.5 OR rate > 3.0:
      ASSERT has_explanation_for_outlier
severity: INFO

info_message: "ℹ️ 行为维度购买率 {rate}%，偏离正常范围(1.5%-3.0%)，已标注"
```

### D-004: 留存率合理性

```yaml
rule: "Day N 留存 ≤ 100%，D7 需标注周末效应"
check: |
  FOR each retention_rate mention:
    ASSERT rate <= 100
    IF day == 7 AND rate > 90:
      ASSERT "周末周期效应" in text OR "周期效应" in text
severity: WARNING

warning_message: "⚠️ Day7 留存率 {rate}%，如未标注'周末周期效应'，请补充说明"
```

### D-005: 加购 UV vs 收藏 UV

```yaml
rule: "如有对比，需说明 cart_uv > fav_uv 的非线性特征"
check: |
  IF "FAV→CART" in text AND cart_uv > fav_uv:
    ASSERT "非线性" in text OR "跳过收藏" in text OR "Sankey" in text
severity: WARNING

warning_message: "⚠️ 加购UV({cart_uv}) > 收藏UV({fav_uv})，是否说明了非线性漏斗特征？"
```

### D-006: Cluster 数据源正确性

```yaml
rule: "Cluster 数据必须用 read_parquet 而非直接表名"
check: |
  IF "user_cluster_summary" in sql OR "user_cluster_result" in sql:
    ASSERT "read_parquet" in sql
severity: WARNING

warning_message: "⚠️ Cluster 数据使用独立 parquet 文件，SQL 中需使用 read_parquet 路径"
```

---

## 4. 指标一致性校验

**确保同一指标在不同段落中数值一致**

### C-001: 指标值一致性

```yaml
rule: "同一指标在输出中多次出现时，数值必须一致"
check: |
  FOR each metric mentioned multiple times:
    extract all numeric values
    ASSERT all values within 0.1% tolerance
severity: WARNING

warning_message: "⚠️ 指标'{metric}'在文中出现多个不同数值：{values}，请统一"
```

### C-002: 维度标注检查

```yaml
rule: "提及转化率/购买率时必须标注'行为维度'或'用户维度'"
check: |
  FOR each mention of "购买率" or "转化率":
    ASSERT "行为维度" in context OR "用户维度" in context OR "行为→购买" in context OR "用户中" in context
severity: INFO

info_message: "ℹ️ 第 {N} 处提到'购买率'，建议标注是行为维度还是用户维度"
```

### C-003: 分母一致性

```yaml
rule: "百分比计算的分母必须明确"
check: |
  FOR each percentage mention:
    ASSERT denominator is identifiable (UV / actions / total_users)
severity: INFO
```

---

## 5. 输出质量校验

### Q-001: 增量洞察检查 ⭐

```yaml
rule: "分析结论不得完全重复已知结论"
check: |
  known_conclusions = [
    "PV→FAV 流失 60.2%",
    "Day1 留存 78.8%",
    "51.3 万件高曝光低转化",
    "C2 购买率 9.4%",
    "周末 DAU +16%",
    "Session >6 购买率 13.0%",
    "购买率峰值 10:00",
    "20,089 加购未购",
  ]
  overlap = count how many known conclusions appear verbatim
  IF overlap >= 2 AND no_new_finding:
    FAIL

fail_message: "⚠️ 分析结论中 {overlap}/8 条与已知结论重复，请提供增量洞察"
```

### Q-002: 数据局限声明

```yaml
rule: "必须列出至少 1 条数据局限或分析限制"
check: |
  required_keywords = ["局限", "限制", "不足", "缺少", "无法", "窗口", "9天", "注意"]
  ASSERT any(kw in text for kw in required_keywords)
severity: WARNING
```

### Q-003: 结构化程度

```yaml
rule: "建议使用表格或列表展示多维度对比数据"
check: |
  IF text contains >5 metrics compared across >3 groups:
    ASSERT "|" in text  # has table
severity: INFO

info_message: "ℹ️ 建议用表格展示多维度对比数据（>5 指标 × >3 群体）"
```

### Q-004: SQL 代码检查

```yaml
rule: "内嵌 SQL 语法检查"
check: |
  FOR each code block:
    IF sql:
      required_elements = ["SELECT", "FROM"]
      ASSERT all(elem.upper() in sql.upper() for elem in required_elements)
      ASSERT "read_parquet" in sql if "cluster" in sql.lower()
severity: WARNING
```

---

## 6. 业务逻辑校验

### L-001: 反直觉发现的一致性

```yaml
rule: "反直觉结论必须与其他数据自洽"
checks:
  - IF "FAV→CART=189%" → 必须同时说明"源群体小于目标群体"
  - IF "D7留存=98.5%" → 必须同时说明"周末周期效应"
  - IF "cart_to_buy>100%" → 必须同时说明"复购信号"

severity: BLOCKER if inconsistent
```

### L-002: 运营建议可行性

```yaml
rule: "运营建议必须可落地"
check: |
  FOR each strategy:
    must_have = ["目标群体", "触达时机", "具体动作"]
    IF any(missing):
      FAIL

fail_message: "策略'{name}'缺少必要元素：{missing}，运营建议不可落地"
```

### L-003: 时序逻辑检查

```yaml
rule: "时间维度的结论必须自洽"
checks:
  - 周末 DAU 更高 + 购买率更低 → "周末流量质量下降" (正确)
  - 周末 DAU 更高 + 购买率也更高 → 矛盾，需重新核实
  - 10:00 购买率最高 + 21:00 流量最高 → "时序错位" (正确，已知结论)

severity: WARNING if contradictory
```

---

## 7. 策略质量校验

### S-001: 策略群体特异性

```yaml
rule: "每条策略必须针对具体用户群体"
check: |
  FOR each strategy:
    required = ["C0" or "C1" or "C2" or "C3" or "C4" or
                "高频" or "中频" or "低频" or "沉默" or
                "加购未购" or "已购" or "复购"]
    ASSERT any(group in strategy for group in required)

fail_message: "策略未指定目标群体，运营无法执行"
```

### S-002: KPI 可量化

```yaml
rule: "预期 KPI 必须包含具体数字"
check: |
  FOR each strategy KPI:
    has_number = re.findall(r'\d+\.?\d*%?', kpi_text)
    ASSERT len(has_number) > 0

fail_message: "KPI '{kpi}' 缺少具体数字，无法衡量效果"
```

### S-003: 策略优先级合理性

```yaml
rule: "P0 策略必须针对最高价值/最大机会群体"
check: |
  IF P0_strategy targets low_value_group AND high_value_group not covered:
    WARNING "P0 策略未覆盖最高价值群体"
    
valid_p0_groups: ["C2", "C1", "加购未购", "高频已购"]
valid_p1_groups: ["C3", "C4", "C0", "中频"]
valid_p2_groups: ["低频", "沉默"]
```

---

## 8. 校验结果处理

### 8.1 当前实现（rule_based_review）

```python
def rule_based_review(text: str) -> tuple[bool, str]:
    """
    返回 (passed, feedback)
    - passed=True  → Reviewer 通过，进入下一阶段
    - passed=False → 将 feedback 拼入 Analyst 重试 prompt
    """

# 当前检查项（已实现）：
# B-001, B-002, B-003

# 建议扩展的检查项：
# B-004 (缺少必要段落)
# D-001 ~ D-006 (数据校验)
# Q-001 ~ Q-003 (输出质量)
```

### 8.2 重试流程

```
Analyst 第 1 次输出
  → rule_based_review() → 未通过
  → feedback 拼入重试 prompt
  → Analyst 第 2 次输出
  → rule_based_review() → 未通过
  → Analyst 第 3 次输出
  → rule_based_review() → 未通过
  → ⚠ 达到最大重试次数(2)，使用最后一次结论
```

### 8.3 重试 Prompt 模板

```
原始问题：{question}

上次分析结论：
{analyst_result}

规则验证反馈：
{feedback}

请针对以上反馈重新查询数据，修正分析结论。确保：
1. 至少包含 3 个具体数字或百分比
2. 不使用模糊词（较高/明显/显著/一定程度）
3. 输出字数 ≥ 150 字
```

---

## 9. Reviewer Agent Prompt

```yaml
system: |
  你是一名数据分析 Reviewer，负责校验 Analyst Agent 的输出质量。
  
  ## 校验清单
  
  ### 阻断级 (必须全部通过，否则退回重做)
  - [ ] B-001: 包含 ≥3 个具体数字或百分比
  - [ ] B-002: 无模糊词（较高/明显/显著/一定程度/有所/相对较）
  - [ ] B-003: 字数 ≥ 150 字
  - [ ] B-004: 包含数据摘要段落
  
  ### 数据校验
  - [ ] D-001: buy_uv ≤ pv_uv（否则需说明原因）
  - [ ] D-002: 用户维度转化率 ≤ 100%
  - [ ] D-004: Day7 留存如 >90%，需标注周末周期效应
  - [ ] D-005: 如 cart_uv > fav_uv，需说明非线性漏斗
  
  ### 质量校验
  - [ ] Q-001: 结论不完全重复已知结论（至少 1 条增量洞察）
  - [ ] Q-002: 列出至少 1 条数据局限
  - [ ] B-001: 策略包含目标群体 + 触达时机 + 具体动作 + 可量化 KPI
  
  ## 输出格式
  
  通过时输出：
  【校验通过】
  
  未通过时输出：
  【验证未通过】
  - {具体问题1}
  - {具体问题2}
  建议修正：{修改建议}
  
rules: |
  - 只做校验，不查数据，不补充分析
  - 以 checklist 思维逐项检查
  - 未通过时给出具体的修改建议，而非笼统的"改进输出"
  - 通过时简洁输出，不添加额外内容
```
