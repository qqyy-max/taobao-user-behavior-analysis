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
import re
from pathlib import Path
from datetime import datetime
from core_agent import run_agent, LLMClient, _save_interaction
from tools import rule_based_review
from agent.reviewer import review as reviewer_review
from memory import format_memory_context, load_memory


# ══════════════════════════════════════════════════════════
# 各 Agent 的 System Prompt (v2.0 — 从 agent/prompts/ 加载)
# ══════════════════════════════════════════════════════════

def _load_prompt_file(filename: str) -> str:
    """从 agent/prompts/ 加载 prompt 文件，fallback 到硬编码"""
    p = Path(f"agent/prompts/{filename}")
    if p.exists():
        return p.read_text(encoding="utf-8").strip()
    return ""


def _get_analyst_prompt() -> str:
    """加载 Analyst System Prompt，优先使用 agent/prompts/analyst.md"""
    prompt = _load_prompt_file("analyst.md")
    if prompt:
        return prompt
    # fallback
    return ANALYST_PROMPT_FALLBACK


def _get_strategist_prompt() -> str:
    """加载 Strategist System Prompt，优先使用 agent/prompts/strategist.md"""
    prompt = _load_prompt_file("strategist.md")
    if prompt:
        return prompt
    # fallback
    return STRATEGIST_PROMPT_FALLBACK


# ── Fallback prompts (agent/prompts/ 不存在时使用) ──

ANALYST_PROMPT_FALLBACK = """
你是一名电商数据分析师，专注淘宝用户行为分析（2017-11-25 ~ 12-03，2900万行）。

## 已知核心结论（不要重复发现，只做增量分析）

- PV→FAV 流失 60.2%，但这是非线性漏斗——加购 UV(215,167) 远超收藏 UV(113,717)，真实路径是 PV→CART→BUY
- Day1 留存 78.8%（最大 Cohort），Day7 留存 98.5% 是周末周期效应，非真实高留存
- 51.3 万件商品高曝光零转化（PV≥P75 且购买率=0%）
- C2 购买率 9.4%/人均 PV 71；C0 人均 PV 198 但购买率仅 2.0%，类目广度 43.6
- 周末 DAU +16% 但购买率低于工作日；购买率峰值 10:00（2.62%）
- Session 超 6 个行为后购买率从 7.5% 翻倍至 13.0%
- 60,891 用户加购未购；819 名超级用户购买率 81.8%

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


STRATEGIST_PROMPT_FALLBACK = """
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
# 核心：意图分类与带规则验证的 Analyst
# ══════════════════════════════════════════════════════════

def classify_query_by_regex(question: str) -> str:
    """
    通过正则匹配对用户的 Query 进行意图分类：
    - STRATEGY_DESIGN: 涉及运营策略、实验设计等
    - DEEP_ANALYSIS: 涉及深度下钻归因、时段或聚类特征分析
    - METRIC_QUERY: 简单指标、数据提取（默认）
    """
    # 策略类关键词
    strategy_keywords = r"策略|方案|实验|A/B|AB测试|运营|召回|触达|设计|优化建议"
    # 归因/深度分析类关键词
    analysis_keywords = r"为什么|归因|分析|原因|特征|偏好|时序|关联|规律|异动"

    if re.search(strategy_keywords, question, re.IGNORECASE):
        return "STRATEGY_DESIGN"
    elif re.search(analysis_keywords, question, re.IGNORECASE):
        return "DEEP_ANALYSIS"
    else:
        return "METRIC_QUERY"


def classify_query_by_llm(question: str, llm: LLMClient) -> str:
    """
    使用 LLM 对用户的提问进行意图分类分流：
    - STRATEGY_DESIGN: 涉及运营策略、活动方案、A/B测试方案设计等
    - DEEP_ANALYSIS: 涉及深度下钻归因、时段、聚类或关联分析特征等
    - METRIC_QUERY: 简单指标、数据提取或数值查询
    """
    system_prompt = """
    你是一个意图分类器。根据用户对淘宝用户行为数据的分析提问，只输出以下三者之一的关键字，严禁输出任何多余字符、标点或解释：
    - METRIC_QUERY: 简单的数据提取、表结构查询、特定日期的指标数值查询（例如：“购买率怎么算”、“行为购买率和用户购买率的区别”、“有多少人加购了”、“C0用户有多少人”）。
    - DEEP_ANALYSIS: 涉及异动分析、原因下钻、用户特征画像归因（例如：“为什么周末购买率低”、“加购未购用户有什么特征”、“分析时段分布规律”、“高曝光低转化商品分析”）。
    - STRATEGY_DESIGN: 明确要求设计运营策略、活动方案、A/B测试方案（例如：“针对加购未购用户设计一个运营策略”、“帮我设计一个实验方案”、“针对该特征给出策略”）。
    """.strip()
    
    messages = [{"role": "user", "content": f"提问: {question}"}]
    try:
        print("  → 正在使用 LLM 进行意图识别分类...")
        if llm.provider == "deepseek":
            all_messages = [{"role": "system", "content": system_prompt}] + messages
            resp = llm.client.chat.completions.create(
                model=llm.model,
                messages=all_messages,
                max_tokens=20,
                temperature=0.0
            )
            reply = resp.choices[0].message.content
        elif llm.provider == "anthropic":
            resp = llm.client.messages.create(
                model=llm.model,
                max_tokens=20,
                system=system_prompt,
                messages=messages,
                temperature=0.0
            )
            reply = "".join(b.text for b in resp.content if hasattr(b, "text"))
        else:
            reply = "METRIC_QUERY"
    except Exception as e:
        print(f"  ⚠ LLM 意图分类失败: {e}，将自动降级使用正则分类")
        return classify_query_by_regex(question)
        
    intent = reply.strip().upper()
    if "STRATEGY_DESIGN" in intent:
        return "STRATEGY_DESIGN"
    elif "DEEP_ANALYSIS" in intent:
        return "DEEP_ANALYSIS"
    elif "METRIC_QUERY" in intent:
        return "METRIC_QUERY"
    
    # 兜底关键字匹配
    if "STRATEGY" in intent or "策略" in intent or "方案" in intent or "设计" in intent:
        return "STRATEGY_DESIGN"
    elif "ANALYSIS" in intent or "分析" in intent or "归因" in intent or "特征" in intent:
        return "DEEP_ANALYSIS"
        
    return classify_query_by_regex(question)



def run_analyst(question: str, llm: LLMClient, max_retry: int = 2, memory_context: str = "", mode: str = "analyst") -> str:
    """Analyst 查数据，reviewer_review 验证，不通过则带 feedback 重试"""

    current_question = question

    for attempt in range(max_retry + 1):
        if attempt > 0:
            print(f"    [重试 {attempt}/{max_retry}]")

        # Analyst 查数据
        print("  → Analyst 查询数据...")
        analyst_result = run_agent(
            question=current_question,
            llm=llm,
            system=_get_analyst_prompt(),
            save=False,
            memory_context=memory_context,
        )

        # reviewer_review 验证
        review_result = reviewer_review(analyst_result, mode=mode)
        passed = review_result.passed
        feedback = review_result.feedback

        if passed:
            print("  ✓ 规则验证通过")
            return analyst_result

        # 未通过：使用 agent/reviewer.py 的格式化重试 prompt
        print(f"  ✗ 规则验证未通过，详细反馈：\n{feedback}")
        try:
            from agent.reviewer import format_retry_prompt
            current_question = format_retry_prompt(question, analyst_result, feedback)
        except Exception:
            # fallback
            current_question = f"""
原始问题：{question}

上次分析结论：
{analyst_result}

规则验证反馈：
{feedback}

请针对以上反馈重新查询数据，修正分析结论。确保：
1. 至少包含 3 个具体数字或百分比（标注来源表）
2. 不使用模糊词（较高/明显/显著/一定程度/有所）
3. 输出字数 ≥ 150 字
4. 必须有【数据摘要】段落
5. 禁止使用"留存率"(用"短周期回访率")、"复购率"(用"窗口内重复购买率")
6. 提及购买率时必须标注"行为维度"或"用户维度"
""".strip()

    print("  ⚠ 达到最大重试次数，使用最后一次结论")
    return analyst_result


def run_pipeline(question: str, llm: LLMClient, verbose: bool = True, memory_context: str = "") -> dict:
    """
    三角色协作 Pipeline 重构版：
    根据 classify_query_by_regex 分类：
    - METRIC_QUERY: 轻量规则 Analyst 查数（不运行 Strategist）
    - DEEP_ANALYSIS: 完整规则 Analyst 分析（不运行 Strategist）
    - STRATEGY_DESIGN: 完整规则 Analyst 分析 ➔ Strategist 生成策略
    """
    print(f"\n{'='*60}")
    print(f"问题：{question}")
    print(f"{'='*60}")

    query_type = classify_query_by_llm(question, llm)
    print(f"  📌 [分类路由结果]: {query_type}")

    # 确定 Analyst 的校验模式
    analyst_mode = "analyst_light" if query_type == "METRIC_QUERY" else "analyst"

    # Stage 1: Analyst
    analyst_result = run_analyst(question, llm, memory_context=memory_context, mode=analyst_mode)

    # Stage 2: Strategist (条件激活)
    if query_type == "STRATEGY_DESIGN":
        print("  → Strategist 生成运营策略...")
        strategy_input = f"""
基于以下数据分析结论，制定差异化运营策略：

{analyst_result}
""".strip()

        strategy_result = run_agent(
            question=strategy_input,
            llm=llm,
            system=_get_strategist_prompt(),
            save=False,
        )
        print("  ✓ 策略生成完成")
    else:
        strategy_result = (
            "💡 当前查询类型为指标提取或深度分析，未激活运营策略生成。如需生成策略，请在提问中包含‘策略’、‘方案’或‘触达’等关键词。"
        )
        print("  ✓ 跳过 Strategist 策略生成")

    result = {
        "question": question,
        "analysis": analyst_result,
        "strategy": strategy_result,
        "query_type": query_type,
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