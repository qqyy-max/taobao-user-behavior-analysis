"""
memory.py — 跨 Session 知识积累
===============================
每次分析后自动提取关键洞察，下次启动时注入 prompt 避免重复分析。
"""

import json
from pathlib import Path
from datetime import datetime

MEMORY_PATH = Path("reports/memory/insights.json")


# ══════════════════════════════════════════════════════════
# 1. 读写 Memory 文件
# ══════════════════════════════════════════════════════════

def load_memory() -> list[dict]:
    """读取 insights.json，文件不存在时返回空列表"""
    if not MEMORY_PATH.exists():
        return []
    try:
        data = json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        return []
    except (json.JSONDecodeError, ValueError):
        return []


def save_memory(insights: list[dict]) -> None:
    """将完整 insights 列表写入 insights.json"""
    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    MEMORY_PATH.write_text(
        json.dumps(insights, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ══════════════════════════════════════════════════════════
# 2. LLM 简单调用（不带 tool，仅用于洞察提取）
# ══════════════════════════════════════════════════════════

def _chat_openai_simple(client, system: str, user_msg: str) -> str:
    """DeepSeek/OpenAI 简单 chat，不传 tools"""
    resp = client.client.chat.completions.create(
        model=client.model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ],
        max_tokens=800,
        temperature=0.3,
    )
    return resp.choices[0].message.content or ""


def _chat_anthropic_simple(client, system: str, user_msg: str) -> str:
    """Anthropic 简单 messages.create，不传 tools"""
    resp = client.client.messages.create(
        model=client.model,
        max_tokens=800,
        system=system,
        messages=[{"role": "user", "content": user_msg}],
    )
    text = next((b.text for b in resp.content if hasattr(b, "text")), "")
    return text


# ══════════════════════════════════════════════════════════
# 3. 洞察提取
# ══════════════════════════════════════════════════════════

EXTRACT_SYSTEM_PROMPT = """你是信息提取助手。从分析结果中提取3-5条最重要的数字结论，
用JSON格式返回，不要输出任何其他内容。
格式：
{
  "topic": "一句话描述分析主题",
  "key_findings": ["结论1（含具体数字）", "结论2", ...]
}"""


def extract_insights(question: str, result: str, llm_client, source: str) -> dict | None:
    """用 LLM 从分析结果中提取结构化洞察，失败时返回 None"""
    user_msg = f"分析问题：{question}\n\n分析结果：\n{result[:2000]}"

    try:
        if llm_client.provider == "deepseek":
            raw = _chat_openai_simple(llm_client, EXTRACT_SYSTEM_PROMPT, user_msg)
        else:
            raw = _chat_anthropic_simple(llm_client, EXTRACT_SYSTEM_PROMPT, user_msg)

        # 清理可能的 markdown 代码块包裹
        raw = raw.strip()
        if raw.startswith("```"):
            # 去掉 ```json ... ``` 包裹
            lines = raw.split("\n")
            lines = [l for l in lines if not l.startswith("```")]
            raw = "\n".join(lines).strip()

        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            return None
        if "topic" not in parsed or "key_findings" not in parsed:
            return None

        ts = datetime.now()
        return {
            "id": ts.strftime("%Y%m%d_%H%M%S"),
            "topic": str(parsed["topic"]),
            "key_findings": [str(f) for f in parsed["key_findings"]],
            "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
            "source": source,
        }
    except Exception:
        return None


# ══════════════════════════════════════════════════════════
# 4. Memory Context 格式化
# ══════════════════════════════════════════════════════════

def format_memory_context(max_items: int = 5) -> str:
    """读取最近 max_items 条 memory，格式化为注入 prompt 用的字符串"""
    all_insights = load_memory()
    if not all_insights:
        return ""

    recent = all_insights[-max_items:]

    lines = ["## 已有分析结论（不要重复发现这些）\n"]
    for insight in recent:
        topic = insight.get("topic", "未知主题")
        findings = insight.get("key_findings", [])
        findings_str = "；".join(findings)
        lines.append(f"- **{topic}**：{findings_str}")

    return "\n".join(lines) + "\n"
