# Memory Rules — Memory 写入规范

> **版本**：v1.0 | 2026-06-08
> **适用系统**：`src/memory.py` — 跨 Session 知识积累
> **设计原则**：Memory 不是日志，是知识库。每个 insight 必须增量、可复用、可去重。

---

## 目录

1. [Memory 架构](#1-memory-架构)
2. [写入准入规则](#2-写入准入规则)
3. [去重规则](#3-去重规则)
4. [重要性评分规则](#4-重要性评分规则)
5. [Memory 衰退与清理](#5-memory-衰退与清理)
6. [Memory 格式规范](#6-memory-格式规范)
7. [Prompt 注入规则](#7-prompt-注入规则)
8. [长期运营知识库构建](#8-长期运营知识库构建)
9. [Memory 质量审计](#9-memory-质量审计)

---

## 1. Memory 架构

```
Session N 分析完成
    │
    ▼
extract_insights()
    提取 3-5 条数字结论
    │
    ▼
写入准入检查
    长度 >100 字？含数字？增量？
    │
    ▼
去重检查
    与已有 memory 相似度 < 阈值？
    │
    ▼
重要性评分
    P0 (核心发现) → 永久保留
    P1 (重要)     → 长期保留
    P2 (常规)     → 限定数量
    │
    ▼
写入 insights.json
    │
    ▼
下次 Session 启动
    → format_memory_context(max_items=5)
    → 注入 Agent prompt
```

---

## 2. 写入准入规则

### 2.1 准入门槛

| 条件 | 规则 | 理由 |
|------|------|------|
| **长度** | 分析结果 ≥ 100 字 | 过短的分析不值得记忆 |
| **数字密度** | 包含 ≥ 3 个具体数字或百分比 | Memory 的价值在于可复用的数据事实 |
| **增量性** | 不完全重复已知核心结论 | 见去重规则 |
| **时效性** | 分析时间在最近 30 天内 | 超过 30 天的分析可能已过时 |

### 2.2 准入白名单（以下类型的 insight 优先保存）

| 类型 | 示例 | 优先级 |
|------|------|--------|
| **新发现的数字规律** | "某个类目购买率是平均值的 3 倍" | P0 |
| **用户群体行为特征** | "C3 群体 67.4% 行为在周末" | P0 |
| **反直觉结论** | "加购 UV 远超收藏 UV，收藏非必要环节" | P0 |
| **时序发现** | "购买率峰值 10:00 vs 流量峰值 21:00" | P1 |
| **商品/类目异常** | "某类目高曝光低转化，曝光-转化差距 >50 万" | P1 |
| **策略效果预估** | "C3 购买率每 +1pp = 840 新购买用户" | P1 |
| **数据局限标注** | "9 天窗口无法评估长期留存" | P2 |

### 2.3 准入黑名单（以下类型的 insight 不保存）

| 类型 | 示例 | 理由 |
|------|------|------|
| **已知核心结论** | "PV→FAV 流失 60.2%" | 已在 `get_business_context()` 中声明 |
| **纯 SQL 查询** | "查询了 funnel_summary 表" | 不是业务洞察 |
| **过程性输出** | "正在分析..." / "数据加载中" | 不是分析结论 |
| **无数字的泛泛结论** | "用户行为比较活跃" | 模糊不可复用 |
| **单次查询的瞬时结果** | "SELECT * FROM daily_behavior_summary 返回 9 行" | 不是洞察 |
| **策略描述** | 策略内容由 Strategist 生成，不属于 Analyst 记忆 | 分离关注点 |

---

## 3. 去重规则

### 3.1 三层去重

```
Layer 1: 精确匹配
  IF new.topic == existing.topic:
    → 内容有增量更新？更新 existing。否则跳过。

Layer 2: 语义相似度（基于 key_findings 的 overlap）
  overlap = len(set(new.findings) ∩ set(existing.findings)) / len(new.findings)
  IF overlap > 0.7 (70% findings 相同):
    → DUPLICATE: 不写入新 insight，可选择更新 existing 的 timestamp

Layer 3: 主题模糊匹配
  IF topic keywords overlap > 80%:
    → SIMILAR: 标注为"相关分析"，在新 insight 中添加 related_to 字段
```

### 3.2 去重示例

```
已有 Memory:
  topic: "购买率峰值时段分析"
  findings: ["购买率最高 10:00 (2.62%)", "流量峰值 21:00", ...]

新分析:
  topic: "哪个小时购买率最高"
  findings: ["10:00 购买率 2.62% 为全天最高", ...]

去重结果:
  overlap = 80% → DUPLICATE
  操作：更新已有 memory 的 timestamp，不新增条目
```

### 3.3 增量更新规则

当新 insight 与已有 memory **部分重叠** 但有新发现时：

```yaml
action: "更新已有 memory"
rules:
  - 追加新的 key_finding（不重复的）
  - 更新 timestamp 为当前时间
  - 追加 source 标签（如已有）
  - 保持原有的 id 不变
```

---

## 4. 重要性评分规则

### 4.1 评分维度

| 维度 | 权重 | 评分逻辑 |
|------|------|----------|
| **数据密度** | 30% | key_findings 中具体数字的数量 (3=0.5, 5=1.0) |
| **增量程度** | 25% | 与已知核心结论的重叠度 (重叠越低分数越高) |
| **可复用性** | 20% | insight 是否能直接用于未来分析 (通用性强=高分) |
| **行动价值** | 15% | 是否能直接推导运营策略 |
| **规模影响** | 10% | 涉及的群体规模 (大群体=高分) |

### 4.2 评分公式

```
Score = 0.30 × DataDensity
      + 0.25 × NoveltyScore
      + 0.20 × Reusability
      + 0.15 × Actionability
      + 0.10 × ScaleImpact
```

### 4.3 分级存储

| Score | 层级 | 存储策略 |
|-------|------|----------|
| ≥ 0.80 | P0-核心 | 永久保留，不受条数限制 |
| 0.50-0.79 | P1-重要 | 保留最近 20 条 |
| 0.30-0.49 | P2-常规 | 保留最近 10 条 |
| < 0.30 | — | 不写入 Memory |

---

## 5. Memory 衰退与清理

### 5.1 衰退规则

```yaml
decay_rules:
  - rule: "时间衰退"
    logic: |
      IF (now - timestamp) > 30 days:
        score *= 0.7  # 30天后重要性降低30%
      IF (now - timestamp) > 90 days:
        score *= 0.3  # 90天后几乎不考虑

  - rule: "重复验证后提升"
    logic: |
      IF 不同 Session 独立验证了同一 finding:
        score *= 1.2  # 被多次验证的结论重要性提升
        verified_count += 1

  - rule: "矛盾检测后降级"
    logic: |
      IF 新 insight 与已有 memory 矛盾:
        已有 memory.score *= 0.5  # 可能是过时/错误的
        新 insight 标注 conflict_with: [旧 insight.id]
```

### 5.2 清理规则

```yaml
cleanup_triggers:
  - trigger: "总条数 > 50"
    action: "移除 score < 0.3 的条目"

  - trigger: "P2 条数 > 10"
    action: "保留最近 10 条 P2，移除更早的"

  - trigger: "时间 > 90 天"
    action: "强制清理所有超过 90 天未更新的条目"
```

---

## 6. Memory 格式规范

### 6.1 Insight 数据结构

```json
{
  "id": "20260608_162320",
  "topic": "一句话描述分析主题（≤30 字）",
  "key_findings": [
    "结论1（含具体数字）",
    "结论2（含具体数字）",
    "结论3（含具体数字）"
  ],
  "timestamp": "2026-06-08 16:23:20",
  "source": "agent | multi_agent",
  "score": 0.75,
  "verified_count": 1,
  "related_to": ["other_insight_id"],
  "tags": ["funnel", "C3", "weekend"]
}
```

### 6.2 字段规范

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | str | ✓ | `YYYYMMDD_HHMMSS` 格式 |
| `topic` | str | ✓ | ≤30 字，必须是分析主题而非问题本身 |
| `key_findings` | list[str] | ✓ | 3-5 条，每条含至少 1 个数字 |
| `timestamp` | str | ✓ | `YYYY-MM-DD HH:MM:SS` 格式 |
| `source` | str | ✓ | "agent" 或 "multi_agent" |
| `score` | float | 可选 | 0-1 重要性评分 |
| `verified_count` | int | 可选 | 被独立验证的次数 |
| `related_to` | list[str] | 可选 | 关联的 insight ID |
| `tags` | list[str] | 可选 | 分类标签 |

### 6.3 Topic 命名规范

```yaml
rules:
  - pattern: "{分析维度} + {核心发现}"
    examples:
      GOOD: "购买率峰值时段分析"
      GOOD: "C0 探索型用户行为特征"
      GOOD: "高曝光低转化商品规模与类目分布"
      BAD:  "list_tables"  # 这是函数名不是分析主题
      BAD:  "分析"         # 太笼统
      BAD:  "查询结果"     # 没有信息量

  - pattern: "禁止在 topic 中放问题原文"
    BAD:  "购买率最高的小时是哪个"  # 这是问题
    GOOD: "购买率峰值时段分析"      # 这是主题
```

---

## 7. Prompt 注入规则

### 7.1 注入时机

在 Agent 启动时，`format_memory_context(max_items=5)` 读取最近 5 条 memory，注入到用户问题前面。

### 7.2 注入格式

```markdown
## 已有分析结论（不要重复发现这些）

- **{topic}**：{finding_1}；{finding_2}；{finding_3}
- **{topic_2}**：{finding_1}；{finding_2}
```

### 7.3 注入规则

```yaml
rules:
  - rule: "仅注入最近 max_items 条"
  - rule: "仅注入 score ≥ 0.3 的条目"
  - rule: "按 score 降序，同分按 timestamp 降序"
  - rule: "注入文本不含 id/timestamp/source 等元数据"
  - rule: "如果 memory 为空，注入空字符串（不改变原有 prompt）"
```

---

## 8. 长期运营知识库构建

### 8.1 知识库分层

```
Layer 1: 事实层 (Facts)
  来自 Memory 的 key_findings
  例："购买率峰值 10:00（2.62%）"

Layer 2: 洞察层 (Insights)
  跨 Memory 的交叉分析
  例："购买率峰值的时段与流量峰值的时段存在 11 小时错位"

Layer 3: 策略层 (Strategies)
  从洞察推导的运营规则
  例："Push 应在购买率峰值前 30 分钟触达（9:30），而非流量峰值前"

Layer 4: 知识层 (Knowledge)
  跨项目可复用的方法论
  例："电商平台的用户行为模式通常呈现'逛'与'买'的时间错位"
```

### 8.2 从 Memory 到策略的演进路径

```
Session 1: 发现 10:00 购买率 2.62% → Memory
Session 2: 发现 21:00 流量最高 → Memory
Session 3: 交叉分析 → 时序错位洞察 → Strategy: 9:30 Push
Session 4: 验证策略有效性 → Knowledge: "购买高峰前 30 分钟触达" 方法论
```

### 8.3 知识库文件建议

```
reports/memory/
├── insights.json          # Memory 主文件（自动写入）
├── insights.archive.json  # 归档（已衰退 ≤0.3 的条目）
├── knowledge.md           # 人工/LLM 整理的长期知识库
└── knowledge_index.json   # 知识库索引（按主题/标签/日期）
```

**knowledge.md 维护规则**：
- 每积累 10 条 memory → 做 1 次 knowledge 合并
- 合并时检查：哪些 findings 被多次验证？哪些被推翻？
- 人工审核：去除噪声，提炼可复用的方法论

---

## 9. Memory 质量审计

### 9.1 审计指标

| 指标 | 目标值 | 检查方式 |
|------|--------|----------|
| Memory 条数 | 10-30 条 | 过多 → 清理，过少 → 检查写入门槛是否太高 |
| 去重率 | <10% 重复 | 每次写入前计算 overlap |
| 数字密度 | ≥3 数字/条 | 审计脚本检查 |
| 平均 Score | ≥0.5 | 审计脚本检查 |
| Topic 可读性 | 100% 不超过 30 字 | 审计脚本检查 |
| Source 分布 | agent:multi_agent ≈ 60:40 | 不强制，仅供参考 |

### 9.2 审计脚本（建议实现）

```python
def audit_memory(memory_path: str) -> dict:
    """审计 memory 质量"""
    insights = load_memory()
    if not insights:
        return {"status": "empty", "message": "No memory entries"}

    report = {
        "total": len(insights),
        "by_source": {},
        "avg_findings_count": 0,
        "avg_topic_length": 0,
        "duplicate_pairs": [],
        "low_score_items": [],
        "stale_items": [],
    }

    for i in insights:
        report["by_source"][i.get("source", "unknown")] = \
            report["by_source"].get(i.get("source", "unknown"), 0) + 1

    report["avg_findings_count"] = \
        sum(len(i.get("key_findings", [])) for i in insights) / len(insights)

    report["avg_topic_length"] = \
        sum(len(i.get("topic", "")) for i in insights) / len(insights)

    # 检查重复
    for i in range(len(insights)):
        for j in range(i+1, len(insights)):
            overlap = len(set(insights[i]["key_findings"]) &
                         set(insights[j]["key_findings"]))
            if overlap >= 2:
                report["duplicate_pairs"].append((i, j, overlap))

    # 检查低分条目
    report["low_score_items"] = [
        i["id"] for i in insights if i.get("score", 0) < 0.3
    ]

    return report
```

### 9.3 质量告警阈值

| 告警 | 条件 | 建议操作 |
|------|------|----------|
| 🟡 条数不足 | <5 条 | 降低写入门槛，增加分析多样性 |
| 🟡 条数过多 | >50 条 | 触发清理，移除低分条目 |
| 🔴 高度重复 | >3 对重复 | 加强去重逻辑 |
| 🟡 平均数字少 | <3 数字/条 | 提高 LLM 提取质量 |
| 🟡 单一来源 | 100% 来自同一 source | 增加 multi_agent 分析任务 |
