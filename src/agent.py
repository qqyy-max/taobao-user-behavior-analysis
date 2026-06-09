"""
数据分析 Agent v2
================
用法:
    python src/agent.py                            # 交互模式
    python src/agent.py -q "分析漏斗转化"           # 单次提问
    python src/agent.py --report                   # 生成完整报告
    python src/agent.py --provider anthropic -q .. # 切换provider
"""

import config  # 注入 API 凭证（src/config.py）
import os
import sys

# Windows 终端默认 GBK，强制 utf-8 输出
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")
import json
import argparse
from pathlib import Path
from datetime import datetime
from tools import TOOLS, DISPATCH
from memory import extract_insights, format_memory_context, load_memory, save_memory


# ══════════════════════════════════════════════════════════
# 1. Provider 抽象层
# ══════════════════════════════════════════════════════════

class LLMClient:
    """统一接口，屏蔽DeepSeek/Anthropic差异"""

    def __init__(self, provider: str):
        self.provider = provider

        if provider == "deepseek":
            from openai import OpenAI
            self.client = OpenAI(
                api_key=os.environ["DEEPSEEK_API_KEY"],
                base_url="https://api.deepseek.com",
            )
            self.model = "deepseek-chat"

        elif provider == "anthropic":
            import anthropic
            base_url = os.getenv("ANTHROPIC_BASE_URL")
            self.client = anthropic.Anthropic(
                api_key=os.environ["ANTHROPIC_API_KEY"],
                **({"base_url": base_url} if base_url else {}),
            )
            self.model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")

        else:
            raise ValueError(f"Unknown provider: {provider}")

    def chat(self, messages: list, system: str) -> tuple[str | None, list]:
        """
        发送请求，返回 (text_reply, tool_calls)
        tool_calls: [{"id": ..., "name": ..., "args": {...}}]
        """
        if self.provider == "deepseek":
            return self._chat_openai(messages, system)
        else:
            return self._chat_anthropic(messages, system)

    def _chat_openai(self, messages, system):
        all_messages = [{"role": "system", "content": system}] + messages
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=all_messages,
            tools=TOOLS,
            tool_choice="auto",
            max_tokens=4096,
        )
        msg = resp.choices[0].message
        finish = resp.choices[0].finish_reason

        if finish == "tool_calls":
            calls = [
                {
                    "id":   tc.id,
                    "name": tc.function.name,
                    "args": json.loads(tc.function.arguments),
                }
                for tc in msg.tool_calls
            ]
            return None, calls

        return msg.content, []

    def _chat_anthropic(self, messages, system):
        # 把OpenAI格式tools转成Anthropic格式
        anthropic_tools = [
            {
                "name": t["function"]["name"],
                "description": t["function"]["description"],
                "input_schema": t["function"]["parameters"],
            }
            for t in TOOLS
        ]
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system,
            tools=anthropic_tools,
            messages=messages,
        )
        if resp.stop_reason == "tool_use":
            calls = [
                {
                    "id":   b.id,
                    "name": b.name,
                    "args": b.input,
                }
                for b in resp.content
                if b.type == "tool_use"
            ]
            return None, calls

        text = next((b.text for b in resp.content if hasattr(b, "text")), "")
        return text, []


# ══════════════════════════════════════════════════════════
# 2. Prompt 加载
# ══════════════════════════════════════════════════════════

def load_system_prompt() -> str:
    prompt_dir = Path("src/prompts")
    parts = []
    for fname in ["system.md", "metrics.md"]:
        p = prompt_dir / fname
        if p.exists():
            parts.append(p.read_text(encoding="utf-8"))
    if parts:
        return "\n\n---\n\n".join(parts)
    # fallback
    return (
        "你是一名电商数据分析师。分析淘宝用户行为数据，"
        "给出数据支撑的业务洞察和可执行运营建议。"
        "每个结论必须引用具体数字。"
    )


# ══════════════════════════════════════════════════════════
# 2.5. 交互结果自动保存
# ══════════════════════════════════════════════════════════

def _save_interaction(question: str, answer: str, provider: str = "", source: str = "agent", llm_client=None):
    """每次问答自动保存到 reports/interactions/"""
    out_dir = Path("reports/interactions")
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_q = "".join(c for c in question[:50] if c.isalnum() or c in " _-").strip()
    if not safe_q:
        safe_q = "query"
    fname = out_dir / f"{ts}_{source}_{safe_q}.md"
    content = f"""# {question}

> 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
> Provider: {provider}
> Source: {source}

---

{answer}
"""
    fname.write_text(content, encoding="utf-8")
    print(f"  💾 已保存: {fname.name}")

    # 新增：提取并保存memory
    if llm_client is not None and answer and len(answer) > 100:
        insight = extract_insights(question, answer, llm_client, source)
        if insight:
            existing = load_memory()
            existing.append(insight)
            save_memory(existing)
            print(f"  🧠 Memory已更新: {insight['topic']}")


# ══════════════════════════════════════════════════════════
# 3. Agent 核心循环
# ══════════════════════════════════════════════════════════

def run_agent(
    question: str,
    llm: LLMClient,
    system: str,
    max_turns: int = 12,
    verbose: bool = True,
    save: bool = True,
    memory_context: str = "",
) -> str:
    """
    单次分析循环。
    消息格式统一用OpenAI风格，Anthropic在LLMClient内部转换。
    """
    if memory_context:
        full_question = f"{memory_context}\n\n---\n\n当前问题：{question}"
    else:
        full_question = question
    messages = [{"role": "user", "content": full_question}]

    for turn in range(max_turns):
        text, tool_calls = llm.chat(messages, system)

        if not tool_calls:
            # 最终回答
            final_text = text or ""
            if save and final_text:
                _save_interaction(question, final_text, provider=llm.provider, source="agent")
            return final_text

        # 把assistant的tool_calls追加到历史
        if llm.provider == "deepseek":
            # openai格式：assistant message含tool_calls字段
            messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": json.dumps(tc["args"], ensure_ascii=False),
                        },
                    }
                    for tc in tool_calls
                ],
            })
        else:
            # anthropic格式在LLMClient内部处理，这里存原始结构即可
            messages.append({
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": tc["id"],
                     "name": tc["name"], "input": tc["args"]}
                    for tc in tool_calls
                ],
            })

        # 执行工具并收集结果
        tool_results = []
        for tc in tool_calls:
            if verbose:
                args_preview = str(tc["args"])[:80]
                print(f"    -> [{tc['name']}] {args_preview}")

            result = DISPATCH.get(tc["name"], lambda _: '{"error":"unknown tool"}')\
                             (tc["args"])

            tool_results.append({"id": tc["id"], "name": tc["name"], "result": result})

        # 把工具结果追加到消息
        if llm.provider == "deepseek":
            for tr in tool_results:
                messages.append({
                    "role": "tool",
                    "tool_call_id": tr["id"],
                    "content": tr["result"],
                })
        else:
            messages.append({
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": tr["id"], "content": tr["result"]}
                    for tr in tool_results
                ],
            })

    return "达到最大轮次，分析未完成"


# ══════════════════════════════════════════════════════════
# 4. 报告生成
# ══════════════════════════════════════════════════════════

def _load_report_questions() -> list[dict]:
    """从 src/prompts/report_questions.json 加载问题列表，fallback 到硬编码"""
    q_path = Path("src/prompts/report_questions.json")
    if q_path.exists():
        import json as _json
        return _json.loads(q_path.read_text(encoding="utf-8"))
    # fallback
    return [
        {"title": "转化漏斗分析", "question": "分析PV→FAV→CART→BUY的转化漏斗，找出流失最严重的环节，用具体数字说明原因"},
        {"title": "用户留存分析", "question": "分析Day1和Day7留存率，结合用户生命周期数据，给出促首单的具体策略"},
        {"title": "用户分群洞察", "question": "分析5个KMeans聚类的核心差异，给出差异化运营策略"},
        {"title": "商品质量问题", "question": "分析高曝光低转化商品的规模和特征，给出推荐算法的优化方向"},
    ]


def generate_report(llm: LLMClient, system: str):
    out_dir = Path("reports")
    out_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    report_path = out_dir / f"agent_report_{ts}.md"

    sections = _load_report_questions()
    lines = [
        f"# 淘宝用户行为分析报告\n",
        f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}  ",
        f"> Provider: {llm.provider} / {llm.model}\n",
    ]

    for i, sec in enumerate(sections, 1):
        title, question = sec["title"], sec["question"]
        print(f"\n[{i}/{len(sections)}] {title}")
        result = run_agent(question, llm, system)
        lines.append(f"## {i}. {title}\n")
        lines.append(result + "\n")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n✓ 报告已保存: {report_path}")


# ══════════════════════════════════════════════════════════
# 5. 入口
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
    system = load_system_prompt()

    memory_ctx = format_memory_context(max_items=5)
    if memory_ctx:
        print(f"  🧠 已加载 {len(load_memory())} 条历史记忆")

    print(f"[Agent] provider={args.provider}, model={llm.model}")

    if args.report:
        generate_report(llm, system)

    elif args.question:
        result = run_agent(args.question, llm, system, memory_context=memory_ctx, save=False)
        print(result)
        _save_interaction(args.question, result, provider=args.provider,
                          source="agent", llm_client=llm)

    else:
        # 交互模式
        print("输入问题开始分析（quit退出，report生成报告）")
        while True:
            q = input("\n> ").strip()
            if q == "quit":
                break
            if q == "report":
                generate_report(llm, system)
                continue
            if q:
                result = run_agent(q, llm, system, memory_context=memory_ctx, save=False)
                print(result)
                _save_interaction(q, result, provider=args.provider,
                                  source="agent", llm_client=llm)


if __name__ == "__main__":
    main()