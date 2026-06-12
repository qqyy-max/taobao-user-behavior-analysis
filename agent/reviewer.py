"""
Reviewer Agent — Python 规则校验引擎 (非 LLM)
================================================
对 Analyst/Strategist 输出进行确定性规则检查，确保输出遵守：
  - 指标口径约束（agent/metrics_dictionary.md）
  - 9 天数据窗口限制（禁止使用长期留存/复购/流失等词）
  - 非线性漏斗约束（禁止"漏斗转化率"表述）
  - 数字支撑和模糊词约束
  - 策略四要素完整性

用法:
    from agent.reviewer import review, rule_based_review
    passed, feedback, warnings = review(text, mode="analyst")
    passed, feedback = rule_based_review(text)  # 兼容旧接口
"""

import re
from dataclasses import dataclass, field
from typing import Optional


# ══════════════════════════════════════════════════════════
# 1. 检查结果数据结构
# ══════════════════════════════════════════════════════════

@dataclass
class CheckResult:
    """单条检查结果"""
    check_id: str
    passed: bool
    severity: str          # "blocker" | "warning" | "info"
    message: str
    category: str          # "blocker" | "data_sanity" | "strategy" | "quality"


@dataclass
class ReviewResult:
    """整体 Review 结果"""
    passed: bool
    feedback: str
    warnings: list[str] = field(default_factory=list)
    checks: list[CheckResult] = field(default_factory=list)
    stats: dict = field(default_factory=dict)


# ══════════════════════════════════════════════════════════
# 2. 阻断级校验 (Blocker)
# ══════════════════════════════════════════════════════════

# B-001: 模糊词列表
FUZZY_WORDS = [
    "较高", "明显", "显著", "一定程度", "有所", "相对较",
    "比较高", "比较低", "有所提升", "大幅度", "较大", "较小",
    "比较多", "比较少", "较快", "较慢", "偏高", "偏低",
]

# B-004: 必要段落关键词
REQUIRED_SECTIONS = ["数据摘要", "核心数字", "关键数据", "分析结论", "核心指标"]

# 禁止用语 → 正确表述映射
FORBIDDEN_TERMS = {
    "留存率": "短周期回访率",
    "复购率": "窗口内重复购买率",
    "漏斗转化率": "渗透率/行为覆盖率",
    "流失用户": "低活跃未购买用户",
    "流失": "低活跃未购买",
    "长期留存": "短周期回访",
    "长期复购": "窗口内重复购买",
    "用户生命周期": "窗口内行为特征",
}


def _check_blockers(text: str, mode: str = "analyst") -> list[CheckResult]:
    """阻断级检查：B-001 ~ B-004"""
    results = []

    # B-001: 数字支撑 ≥ 3
    arabic = re.findall(r"\d+\.?\d*%?", text)
    chinese_num = re.findall(r"[一二三四五六七八九十百千万亿]+", text)
    total_nums = len(arabic) + len(chinese_num)
    results.append(CheckResult(
        check_id="B-001",
        passed=total_nums >= 3,
        severity="blocker",
        category="blocker",
        message=f"数字支撑: 找到 {total_nums} 个数字/百分比（要求 ≥3 个）"
    ))

    # B-002: 模糊词检查
    found_fuzzy_raw = [w for w in FUZZY_WORDS if w in text]
    # 排除统计学术语：显著性检验/显著性水平 中的"显著"
    found_fuzzy = []
    for w in found_fuzzy_raw:
        if w == "显著":
            # "显著性检验"、"显著性水平" 是统计学术语，不视为模糊词
            if "显著性检验" in text or "显著性水平" in text:
                # 检查是否有非统计用途的"显著"
                text_no_technical = text.replace("显著性检验", "").replace("显著性水平", "")
                if w not in text_no_technical:
                    continue
        found_fuzzy.append(w)
    results.append(CheckResult(
        check_id="B-002",
        passed=len(found_fuzzy) == 0,
        severity="warning",
        category="blocker",
        message=f"模糊表述: {'; '.join(found_fuzzy) if found_fuzzy else '无'}"
    ))

    # B-003: 长度检查 ≥ 150 字
    text_len = len(text.strip())
    results.append(CheckResult(
        check_id="B-003",
        passed=text_len >= 150,
        severity="blocker",
        category="blocker",
        message=f"内容长度: {text_len} 字（要求 ≥150 字）"
    ))

    # B-004: 必要段落
    has_section = any(section in text for section in REQUIRED_SECTIONS)
    results.append(CheckResult(
        check_id="B-004",
        passed=has_section,
        severity="blocker",
        category="blocker",
        message=f"必要段落: {'包含' if has_section else '缺少数据摘要/核心数字段落'}"
    ))

    return results


# ══════════════════════════════════════════════════════════
# 3. 数据校验 (Data Sanity & Consistency)
# ══════════════════════════════════════════════════════════

def _check_data_sanity(text: str, mode: str = "analyst") -> list[CheckResult]:
    """数据与口径一致性校验"""
    results = []

    # D-001: 禁止用语检查 (留存率/复购率/漏斗转化率/流失)
    found_forbidden = []
    for term, replacement in FORBIDDEN_TERMS.items():
        if term in text:
            found_forbidden.append(f"「{term}」应为「{replacement}」")
    results.append(CheckResult(
        check_id="D-001",
        passed=len(found_forbidden) == 0,
        severity="warning",
        category="data_sanity",
        message="禁止用语: " + ("; ".join(found_forbidden) if found_forbidden else "无")
    ))

    # D-002: Day7 回访率标注检查
    day7_pattern = re.search(r"(?:Day\s*7|D7|day7).*?(\d+\.?\d*)%", text, re.IGNORECASE)
    if day7_pattern:
        rate = float(day7_pattern.group(1))
        if rate > 90:
            has_weekend_note = any(kw in text for kw in ["周末周期效应", "周期效应", "周末效应"])
            results.append(CheckResult(
                check_id="D-002",
                passed=has_weekend_note,
                severity="warning",
                category="data_sanity",
                message=f"Day7回访率 {rate}% >90%，{'已标注' if has_weekend_note else '⚠️ 缺少「周末周期效应」标注'}"
            ))
        else:
            results.append(CheckResult(
                check_id="D-002",
                passed=True,
                severity="info",
                category="data_sanity",
                message=f"Day7回访率 {rate}%，未触发周末效应检查"
            ))
    else:
        results.append(CheckResult(
            check_id="D-002",
            passed=True,
            severity="info",
            category="data_sanity",
            message="未提及Day7回访率"
        ))

    # D-003: 维度标注检查（购买率/转化率 必须标注维度）
    buy_rate_pattern = re.findall(r"(?:购买率|转化率)", text)
    if buy_rate_pattern:
        has_dimension = any(kw in text for kw in ["行为维度", "用户维度"])
        results.append(CheckResult(
            check_id="D-003",
            passed=has_dimension,
            severity="warning",
            category="data_sanity",
            message=f"维度标注: 提及购买率/转化率 {len(buy_rate_pattern)} 次，" +
                    ("已标注维度" if has_dimension else "⚠️ 未标注「行为维度」或「用户维度」")
        ))
    else:
        results.append(CheckResult(
            check_id="D-003",
            passed=True,
            severity="info",
            category="data_sanity",
            message="未提及购买率/转化率"
        ))

    # D-004: buy_uv > pv_uv 逻辑检查
    buy_uv_vals = re.findall(r"buy[_\s]*uv[^\d]*(\d+)", text, re.IGNORECASE)
    pv_uv_vals = re.findall(r"pv[_\s]*uv[^\d]*(\d+)", text, re.IGNORECASE)
    if buy_uv_vals and pv_uv_vals:
        buy_uv = int(buy_uv_vals[0])
        pv_uv = int(pv_uv_vals[0])
        if buy_uv > pv_uv:
            has_explanation = any(kw in text for kw in ["搜索直达", "数据采集差异", "NULLIF"])
            results.append(CheckResult(
                check_id="D-004",
                passed=has_explanation,
                severity="warning",
                category="data_sanity",
                message=f"buy_uv({buy_uv}) > pv_uv({pv_uv})，{'已说明原因' if has_explanation else '⚠️ 需说明是否为搜索直达商品'}"
            ))
        else:
            results.append(CheckResult(
                check_id="D-004",
                passed=True,
                severity="info",
                category="data_sanity",
                message=f"buy_uv({buy_uv}) ≤ pv_uv({pv_uv})，正常"
            ))
    else:
        results.append(CheckResult(
            check_id="D-004",
            passed=True,
            severity="info",
            category="data_sanity",
            message="未同时提及buy_uv和pv_uv"
        ))

    # D-005: 窗口限制标注（提及"购买率""活跃"时,检查是否有"窗口内"标注）
    has_context_terms = any(kw in text for kw in ["window", "窗口内", "9天", "短周期", "9 天"])
    has_potential_overclaim = any(kw in text for kw in ["购买率", "活跃", "转化"])
    if has_potential_overclaim and not has_context_terms:
        results.append(CheckResult(
            check_id="D-005",
            passed=False,
            severity="warning",
            category="data_sanity",
            message="⚠️ 提及分析结论但未标注「窗口内/9天」限制"
        ))
    else:
        results.append(CheckResult(
            check_id="D-005",
            passed=True,
            severity="info",
            category="data_sanity",
            message="窗口限制标注: OK" if has_context_terms else "无需窗口标注"
        ))

    # D-006: "流失"相关词检查
    churn_words = ["流失", "沉淀", "沉寂", "僵尸用户"]
    found_churn = [w for w in churn_words if w in text]
    results.append(CheckResult(
        check_id="D-006",
        passed=len(found_churn) == 0,
        severity="warning",
        category="data_sanity",
        message=f"流失类词: {'; '.join(found_churn) if found_churn else '无'}，9天窗口不足以判定"
    ))

    return results


# ══════════════════════════════════════════════════════════
# 4. 策略校验 (Strategy Quality)
# ══════════════════════════════════════════════════════════

def _check_strategy(text: str) -> list[CheckResult]:
    """策略质量校验：四要素完整性"""
    results = []

    # S-001: 检查策略四要素
    four_elements = {
        "目标群体": any(kw in text for kw in ["目标群体", "目标人群", "用户群", "P0", "P1", "P2", "P3",
                                              "cart_abandon", "window_repeat", "high_browse",
                                              "C0", "C1", "C2", "C3", "C4", "加购未购", "高浏览",
                                              "单次购买", "重复购买"]),
        "触达时机": any(kw in text for kw in ["触达时机", "时间", "小时内", "天内", "推送时间",
                                              "h", "10:00", "9:30", "24h", "48h", "小时"]),
        "具体动作": any(kw in text for kw in ["具体动作", "动作", "Push", "推送", "优惠券", "折扣",
                                              "短信", "推荐", "触达", "发送", "发放"]),
        "可量化KPI": bool(re.findall(r"(?:KPI|目标|预期|提升|转化率|购买率|核销率).*?\d+\.?\d*%?", text)),
    }

    missing = [k for k, v in four_elements.items() if not v]
    results.append(CheckResult(
        check_id="S-001",
        passed=len(missing) == 0,
        severity="blocker",
        category="strategy",
        message=f"策略四要素: {'齐全' if not missing else '缺少: ' + ', '.join(missing)}"
    ))

    # S-002: KPI 可量化（有具体数字）
    kpi_numbers = re.findall(r"(?:KPI|预期|目标)[^。]*?\d+\.?\d*%?", text)
    results.append(CheckResult(
        check_id="S-002",
        passed=len(kpi_numbers) >= 1,
        severity="warning",
        category="strategy",
        message=f"可量化KPI: 找到 {len(kpi_numbers)} 个含数字的KPI描述"
    ))

    # S-003: 离线声明检查（策略验证类输出必须标注）
    has_offline_note = any(kw in text for kw in [
        "离线", "设计方案", "非实际", "不可验证", "无法执行", "假设", "估算"
    ])
    is_validation_type = any(kw in text for kw in [
        "A/B", "AB测试", "实验", "验证方案", "对照组", "实验组"
    ])
    if is_validation_type:
        results.append(CheckResult(
            check_id="S-003",
            passed=has_offline_note,
            severity="warning",
            category="strategy",
            message=f"离线声明: {'已标注' if has_offline_note else '⚠️ 实验/验证类输出需标注「离线设计方案，非实际结果」'}"
        ))
    else:
        results.append(CheckResult(
            check_id="S-003",
            passed=True,
            severity="info",
            category="strategy",
            message="非实验设计类输出，无需离线声明"
        ))

    return results


# ══════════════════════════════════════════════════════════
# 5. 质量校验 (Quality)
# ══════════════════════════════════════════════════════════

def _check_quality(text: str) -> list[CheckResult]:
    """输出质量校验"""
    results = []

    # Q-001: 增量洞察检查（非完全重复已知结论）
    known_conclusions = [
        "PV→FAV 流失 60.2%",
        "Day1 留存 78.8%",
        "51.3 万件高曝光低转化",
        "C2 购买率 9.4%",
        "周末 DAU +16%",
        "Session >6 购买率 13.0%",
        "购买率峰值 10:00",
        "20,089 加购未购",
        "加购渗透率 75.3%",
        "收藏渗透率 39.8%",
    ]
    overlap = sum(1 for kc in known_conclusions if kc in text)
    results.append(CheckResult(
        check_id="Q-001",
        passed=overlap <= 2 or len(text) > 500,
        severity="info",
        category="quality",
        message=f"已知结论重复: {overlap} 条（≤2正常）"
    ))

    # Q-002: 数据局限声明
    has_limitation = any(kw in text for kw in [
        "局限", "限制", "不足", "缺少", "无法", "窗口", "9天", "注意", "不能"
    ])
    results.append(CheckResult(
        check_id="Q-002",
        passed=has_limitation,
        severity="warning",
        category="quality",
        message=f"数据局限声明: {'已声明' if has_limitation else '⚠️ 建议至少声明1条数据局限'}"
    ))

    return results


# ══════════════════════════════════════════════════════════
# 6. 统一审核函数
# ══════════════════════════════════════════════════════════

def review(text: str, mode: str = "analyst") -> ReviewResult:
    """
    对 Analyst/Strategist 输出进行完整规则校验。

    Args:
        text: Analyst 或 Strategist 的完整输出文本
        mode: "analyst" | "analyst_light" | "strategist" | "pipeline"

    Returns:
        ReviewResult: 包含 passed, feedback, warnings, checks, stats
    """
    all_checks: list[CheckResult] = []

    # Phase 1: 阻断级校验
    if mode != "analyst_light":
        blocker_checks = _check_blockers(text, mode)
        all_checks.extend(blocker_checks)

    # Phase 2: 数据校验
    data_checks = _check_data_sanity(text, mode)
    all_checks.extend(data_checks)

    # Phase 3: 策略校验（仅strategist或pipeline模式）
    if mode in ("strategist", "pipeline"):
        strategy_checks = _check_strategy(text)
        all_checks.extend(strategy_checks)

    # Phase 4: 质量校验
    quality_checks = _check_quality(text)
    all_checks.extend(quality_checks)

    # ── 汇总结果 ──
    blockers_failed = [c for c in all_checks if c.severity == "blocker" and not c.passed]
    warnings_triggered = [c for c in all_checks if c.severity == "warning" and not c.passed]

    # 阻断级失败 → 整体不通过
    overall_passed = len(blockers_failed) == 0

    # 构建 feedback
    if not overall_passed:
        feedback_lines = ["【验证未通过 — 阻断级问题】"]
        for c in blockers_failed:
            feedback_lines.append(f"- [{c.check_id}] {c.message}")
        feedback_lines.append(f"\n共 {len(blockers_failed)} 个阻断级问题需修复。")
    else:
        feedback_lines = ["【验证通过 ✓】"]
        if warnings_triggered:
            feedback_lines.append(f"⚠️ {len(warnings_triggered)} 个警告项:")
            for c in warnings_triggered:
                feedback_lines.append(f"  - [{c.check_id}] {c.message}")

    feedback = "\n".join(feedback_lines)

    # 统计
    total_checks = len(all_checks)
    passed_checks = sum(1 for c in all_checks if c.passed)
    blocker_count = sum(1 for c in all_checks if c.severity == "blocker")
    blocker_pass = sum(1 for c in all_checks if c.severity == "blocker" and c.passed)

    stats = {
        "total_checks": total_checks,
        "passed_checks": passed_checks,
        "pass_rate": round(100.0 * passed_checks / total_checks, 1) if total_checks else 0,
        "blocker_total": blocker_count,
        "blocker_passed": blocker_pass,
        "warnings": len(warnings_triggered),
    }

    return ReviewResult(
        passed=overall_passed,
        feedback=feedback,
        warnings=[c.message for c in warnings_triggered],
        checks=all_checks,
        stats=stats,
    )


def review_strategy_only(text: str) -> ReviewResult:
    """
    对 Strategist 输出进行策略专项校验。
    用于 pipeline 中仅校验策略部分的场景。
    """
    all_checks = _check_strategy(text)
    all_checks.extend(_check_blockers(text, "strategist"))

    blockers_failed = [c for c in all_checks if c.severity == "blocker" and not c.passed]
    overall_passed = len(blockers_failed) == 0

    feedback_lines = []
    if not overall_passed:
        feedback_lines.append("【策略验证未通过】")
        for c in blockers_failed:
            feedback_lines.append(f"- [{c.check_id}] {c.message}")
    else:
        feedback_lines.append("【策略验证通过 ✓】")

    warnings_triggered = [c for c in all_checks if c.severity == "warning" and not c.passed]
    if warnings_triggered:
        feedback_lines.append(f"⚠️ {len(warnings_triggered)} 个警告:")
        for c in warnings_triggered:
            feedback_lines.append(f"  - [{c.check_id}] {c.message}")

    return ReviewResult(
        passed=overall_passed,
        feedback="\n".join(feedback_lines),
        warnings=[c.message for c in warnings_triggered],
        checks=all_checks,
        stats={
            "total_checks": len(all_checks),
            "passed_checks": sum(1 for c in all_checks if c.passed),
        },
    )


# ══════════════════════════════════════════════════════════
# 7. 兼容旧接口 (tools.py 中的 rule_based_review)
# ══════════════════════════════════════════════════════════

def rule_based_review(text: str) -> tuple[bool, str]:
    """
    规则验证（兼容旧接口，供 multi_agent.py 调用）。
    返回 (passed: bool, feedback: str)

    在原有 3 项检查基础上，增加了：
    - B-004: 必要段落检查
    - D-001: 禁止用语（留存率→回访率等）
    - D-002: Day7 周末周期效应
    - D-003: 维度标注
    - D-005: 窗口限制标注
    """
    result = review(text, mode="analyst")
    return result.passed, result.feedback


# ══════════════════════════════════════════════════════════
# 8. 便捷函数：reformat_feedback_for_retry
# ══════════════════════════════════════════════════════════

def format_retry_prompt(question: str, last_output: str, feedback: str) -> str:
    """
    生成带 Reviewer feedback 的重试 prompt。
    用于 multi_agent.py 中 Analyst 未通过校验时的重试。
    """
    return f"""
原始问题：{question}

上次分析结论：
{last_output}

规则验证反馈：
{feedback}

请针对以上反馈重新查询数据，修正分析结论。确保：
1. 至少包含 3 个具体数字或百分比（标注来源表）
2. 不使用模糊词（较高/明显/显著/一定程度/有所）
3. 输出字数 ≥ 150 字
4. 必须有【数据摘要】段落
5. 禁止使用"留存率"(用"短周期回访率")、"复购率"(用"窗口内重复购买率")、"漏斗转化率"(用"渗透率")
6. 提及购买率时必须标注"行为维度"或"用户维度"
""".strip()


# ══════════════════════════════════════════════════════════
# 9. CLI 调试入口
# ══════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        text = sys.argv[1]
    else:
        text = sys.stdin.read()

    result = review(text)
    print(result.feedback)
    print(f"\n统计: {result.stats}")
