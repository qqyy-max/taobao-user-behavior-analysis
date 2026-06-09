"""
multi_agent.py — 三Agent协作分析系统（重构版）
=============================================
用法:
    python src/multi_agent.py -q "分析用户留存"
    python src/multi_agent.py --report
    python src/multi_agent.py --provider anthropic -q "..."
"""

import os
import json
import argparse
from pathlib import Path
from datetime import datetime
from agent import run_agent, LLMClient, _save_interaction
from tools import rule_based_review
from memory import format_memory_context, load_memory


# ══════════════════════════════════════════════════════════
# 各 Agent 的 System Prompt
# ══════════════════════════════════════════════════════════

ANALYST_PROMPT = """
你是一名电商数据分析师，专注淘宝用户行为分析（2017-11-25 ~ 12-03，2900万行）。

## 已知核心结论（不要重复发现，只做增量分析）

- PV→FAV 流失 60.2%，但这是非线性漏斗——加购 UV(215,167) 远超收藏 UV(113,717)，真实路径是 PV→CART→BUY
- Day1 留存 78.8%（最大 Cohort），Day7 留存 98.5% 是周末周期效应，非真实高留存
- 51.3 万件商品高曝光零转化（PV≥P75 且购买率=0%）
- C2 购买率 9.4%/人均 PV 71；C0 人均 PV 198 但购买率仅 2.0%，类目广度 43.6
- 周末 DAU +16% 但购买率低于工作日；购买率峰值 10:00（2.62%）
- Session 超 6 个行为后购买率从 7.5% 翻倍至 13.0%
- 20,089 用户加购未购；819 名超级用户购买率 81.8%

## 分析原则

1. **每次任务开始，必须先调用 get_business_context()** 了解表结构和已知结论
2. 能用聚合表回答的优先用 query_duckdb；需要原始行为序列时用 query_raw
3. 每个结论必须有具体数字，禁止使用"较高"、"明显"、"显著"、"一定程度"等模糊词
4. 发现数据异常或局限必须标注

## 输出格式（严格遵守）

【数据摘要】列出本次查询的关键数字（≥3个具体数字）
【增量洞察】超出已知结论的新发现，说明与已知结论的关系
【数据局限】本次分析缺少什么，结论的适用范围
""".strip()


STRATEGIST_PROMPT = """
你是运营策略师，基于已验证的数据结论制定差异化运营策略。

## 规则

- **严禁查数据**，只基于输入的分析结论制定策略
- 每条策略必须针对具体用户群体（引用 Cluster ID 如 C0/C2 或 freq_group 如高频/沉默）
- 策略数量：3-5 条，按 P0→P1→P2 优先级排序
- 禁止无法落地的建议（如"提升用户体验"、"优化算法"这类空话）

## 每条策略必须包含

- **目标群体**：具体 Cluster ID 或频率分组 + 人数/占比
- **触达时机**：具体时间（如"周六 10:00"而非"周末"）
- **具体动作**：渠道 + 内容 + 触发条件（如"加购后 48h 未购买发送 Push"）
- **预期 KPI**：可量化的目标（如"购买转化率 +25%"而非"提升转化"）

## 输出格式

【P0】策略名称
  - 目标群体：
  - 触达时机：
  - 具体动作：
  - 预期 KPI：
""".strip()


# ══════════════════════════════════════════════════════════
# 核心：带规则验证的 Analyst
# ══════════════════════════════════════════════════════════

def run_analyst(question: str, llm: LLMClient, max_retry: int = 2, memory_context: str = "") -> str:
    """Analyst 查数据，rule_based_review 验证，不通过则带 feedback 重试"""

    current_question = question

    for attempt in range(max_retry + 1):
        if attempt > 0:
            print(f"    [重试 {attempt}/{max_retry}]")

        # Analyst 查数据
        print("  → Analyst 查询数据...")
        analyst_result = run_agent(
            question=current_question,
            llm=llm,
            system=ANALYST_PROMPT,
            save=False,
            memory_context=memory_context,
        )

        # rule_based_review 验证
        passed, feedback = rule_based_review(analyst_result)

        if passed:
            print("  ✓ 规则验证通过")
            return analyst_result

        # 未通过：把 feedback 拼入下一轮 prompt
        print(f"  ✗ 规则验证未通过 → {feedback.splitlines()[0]}")
        current_question = f"""
原始问题：{question}

上次分析结论：
{analyst_result}

规则验证反馈：
{feedback}

请针对以上反馈重新查询数据，修正分析结论。确保：
1. 至少包含 3 个具体数字或百分比
2. 不使用模糊词（较高/明显/显著/一定程度）
3. 输出字数 ≥ 150 字
""".strip()

    print("  ⚠ 达到最大重试次数，使用最后一次结论")
    return analyst_result


def run_pipeline(question: str, llm: LLMClient, verbose: bool = True, memory_context: str = "") -> dict:
    """
    完整两段式 pipeline：Analyst（含规则重试）→ Strategist
    返回 {"question", "analysis", "strategy"}
    """
    print(f"\n{'='*60}")
    print(f"问题：{question}")
    print(f"{'='*60}")

    # Stage 1: Analyst + 规则验证
    analyst_result = run_analyst(question, llm, memory_context=memory_context)

    # Stage 2: Strategist
    print("  → Strategist 生成运营策略...")
    strategy_input = f"""
基于以下数据分析结论，制定差异化运营策略：

{analyst_result}
""".strip()

    strategy_result = run_agent(
        question=strategy_input,
        llm=llm,
        system=STRATEGIST_PROMPT,
        save=False,
    )
    print("  ✓ 策略生成完成")

    result = {
        "question": question,
        "analysis": analyst_result,
        "strategy": strategy_result,
    }

    _save_interaction(
        question=question,
        answer=f"【分析结论】\n{analyst_result}\n\n【运营策略】\n{strategy_result}",
        provider=llm.provider,
        source="multi_agent",
        llm_client=llm,
    )

    return result


# ══════════════════════════════════════════════════════════
# 报告生成
# ══════════════════════════════════════════════════════════

def _load_report_questions() -> list[dict]:
    """从 src/prompts/report_questions.json 加载，fallback 到硬编码"""
    q_path = Path("src/prompts/report_questions.json")
    if q_path.exists():
        return json.loads(q_path.read_text(encoding="utf-8"))
    # fallback
    return [
        {
            "title": "转化漏斗深度分析",
            "question": "聚焦 PV→FAV 断裂原因，结合 session_stats 数据分析不同行为深度用户的转化差异，已知加购 UV 大于收藏 UV，找出增量洞察"
        },
        {
            "title": "留存与首单转化关系",
            "question": "分析 Day1-Day3 留存率与首单转化的关系，结合 session_stats 看前几次 session 的行为模式"
        },
        {
            "title": "用户群体增量洞察",
            "question": "基于 user_cluster_summary 和 user_segment_summary 找出超出 README 已有结论的增量发现"
        },
        {
            "title": "原始数据即席探索",
            "question": "用 query_raw 查询 clean_data.parquet 原始数据，发现聚合表看不到的规律（如用户行为序列模式、特定时段的用户行为分布等）"
        },
    ]


def generate_report(llm: LLMClient):
    out_dir = Path("reports")
    out_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    report_path = out_dir / f"multi_agent_report_{ts}.md"

    questions = _load_report_questions()
    lines = [
        "# 淘宝用户行为分析报告（Multi-Agent）\n",
        f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}  ",
        f"> 架构: Analyst（规则验证重试）→ Strategist  ",
        f"> Provider: {llm.provider} / {llm.model}\n",
        "---\n",
    ]

    for i, q in enumerate(questions, 1):
        title, question = q["title"], q["question"]
        print(f"\n[{i}/{len(questions)}] {title}")
        result = run_pipeline(question, llm)

        lines += [
            f"## {i}. {title}\n",
            "### 【数据分析】\n",
            result["analysis"] + "\n",
            "### 【运营策略】\n",
            result["strategy"] + "\n",
            "---\n",
        ]

    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n✓ 报告已保存: {report_path}")
    return report_path


# ══════════════════════════════════════════════════════════
# 入口
# ══════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-q", "--question", type=str)
    parser.add_argument("--report", action="store_true")
    parser.add_argument(
        "--provider",
        choices=["deepseek", "anthropic"],
        default=os.getenv("AGENT_PROVIDER", "deepseek"),
    )
    args = parser.parse_args()

    llm = LLMClient(args.provider)

    memory_ctx = format_memory_context(max_items=5)
    if memory_ctx:
        print(f"  🧠 已加载 {len(load_memory())} 条历史记忆")

    print(f"[Multi-Agent] provider={args.provider}, model={llm.model}")

    if args.report:
        generate_report(llm)

    elif args.question:
        result = run_pipeline(args.question, llm, memory_context=memory_ctx)
        print("\n【分析结论】")
        print(result["analysis"])
        print("\n【运营策略】")
        print(result["strategy"])

    else:
        print("交互模式（quit退出，report生成报告）")
        while True:
            q = input("\n> ").strip()
            if q == "quit":
                break
            if q == "report":
                generate_report(llm)
                continue
            if q:
                result = run_pipeline(q, llm, memory_context=memory_ctx)
                print("\n【分析结论】")
                print(result["analysis"])
                print("\n【运营策略】")
                print(result["strategy"])


if __name__ == "__main__":
    main()