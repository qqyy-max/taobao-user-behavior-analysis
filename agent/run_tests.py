"""
Agent 自动化测试脚本 — 8 个 T1-T8 测试问题
===========================================
用法:
    python agent/run_tests.py                    # 离线模式 (预置样本测试 Reviewer)
    python agent/run_tests.py --online           # 在线模式 (需要 LLM API Key)
    python agent/run_tests.py --dry-run          # Reviewer 单元测试 (不调 LLM)
    python agent/run_tests.py --test T1          # 仅运行单个测试

输出: agent/test_results.json (测试结果 + 通过率)
"""

import sys
import os

# Windows 终端默认 GBK，强制 utf-8 输出
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

import json
import argparse
import time
from pathlib import Path
from datetime import datetime

# 确保项目根目录与 src 目录在 sys.path 中，防止 tools/memory 模块导入失败
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

# ══════════════════════════════════════════════════════════
# 1. 测试问题定义 (T1-T8)
# ══════════════════════════════════════════════════════════

TEST_CASES = [
    {
        "id": "T1",
        "title": "指标口径查询",
        "question": "购买率怎么算的？行为维度和用户维度有什么区别？",
        "type": "metrics_query",
        "expected_tools": ["get_business_context", "query_duckdb"],
        "reviewer_checks": {
            "B-001": "数字≥3",
            "B-002": "无模糊词",
            "B-003": "≥150字",
            "D-003": "标注维度(行为维度/用户维度)",
        },
    },
    {
        "id": "T2",
        "title": "加购未购用户分析",
        "question": "加购未购买的用户有多少？他们有什么特征？",
        "type": "analysis",
        "expected_tools": ["get_business_context", "query_duckdb"],
        "reviewer_checks": {
            "B-001": "数字≥3",
            "B-002": "无模糊词",
            "B-003": "≥150字",
            "D-001": "无禁止用语(留存率/复购率/流失)",
            "D-005": "标注窗口内限制",
        },
    },
    {
        "id": "T3",
        "title": "用户分层查询",
        "question": "4 类运营分层各有多少人？购买率差异如何？",
        "type": "analysis",
        "expected_tools": ["query_duckdb"],
        "reviewer_checks": {
            "B-001": "数字≥3",
            "B-002": "无模糊词",
            "B-003": "≥150字",
            "D-001": "不推断生命周期阶段",
        },
    },
    {
        "id": "T4",
        "title": "周末异动归因",
        "question": "周末购买率为什么比工作日低？",
        "type": "attribution",
        "expected_tools": ["query_duckdb"],
        "reviewer_checks": {
            "B-001": "数字≥3",
            "B-002": "无模糊词",
            "B-003": "≥150字",
            "未过度推断": "原因假设可验证",
        },
    },
    {
        "id": "T5",
        "title": "时段效率分析",
        "question": "为什么夜间流量高但购买少？上午反而购买多？",
        "type": "attribution",
        "expected_tools": ["query_duckdb"],
        "reviewer_checks": {
            "B-001": "数字≥3",
            "B-002": "无模糊词",
            "B-003": "≥150字",
            "D-003": "标注行为维度",
        },
    },
    {
        "id": "T6",
        "title": "商品效率查询",
        "question": "高曝光低转化的商品有多少？什么特征？",
        "type": "analysis",
        "expected_tools": ["query_duckdb"],
        "reviewer_checks": {
            "B-001": "数字≥3",
            "B-002": "无模糊词",
            "B-003": "≥150字",
            "D-001": "标注缺少曝光来源字段",
        },
    },
    {
        "id": "T7",
        "title": "运营策略生成",
        "question": "针对加购未购用户，设计一个运营策略",
        "type": "strategy",
        "expected_tools": ["query_duckdb"],
        "reviewer_checks": {
            "S-001": "策略四要素齐全",
            "S-002": "KPI可量化",
            "B-001": "数字≥3",
        },
    },
    {
        "id": "T8",
        "title": "A/B 实验设计",
        "question": "帮我设计一个加购未购用户的 A/B 实验方案",
        "type": "validation",
        "expected_tools": ["query_duckdb"],
        "reviewer_checks": {
            "S-003": "标注离线设计方案",
            "S-001": "实验分组/指标/检验方法",
            "B-001": "数字≥3",
        },
    },
]

# ══════════════════════════════════════════════════════════
# 2. 预置样本（用于 offline 模式，无需 LLM API）
# ══════════════════════════════════════════════════════════

SAMPLE_RESPONSES = {
    "T1": """【数据摘要】
- 行为维度购买率：全天行为中购买行为的占比 = buy_cnt / total_actions，约 2.0%（来源：daily_behavior_summary.buy_rate_pct）
- 用户维度购买率：至少购买过1次的用户占全量用户的比例 = is_buyer=1的用户 / 全部用户，约 68.0%（来源：user_conversion_summary.buy_rate_pct）
- 全量用户 287,004 人，购买用户约 195,000 人

【增量洞察】
行为维度和用户维度是完全不同的概念。行为维度表示购买动作的稀有度（每100次行为中约2次是购买），用户维度表示有多少用户至少在窗口内完成过1次购买。两者均为窗口内数据，不外推。

【数据局限】
仅 9 天窗口，无法推断长期购买习惯。行为维度受 PV 量级影响大——PV 越多分母越大。
""",

    "T2": """【数据摘要】
- 加购未购用户数：60,891 人（来源：cart_abandon_summary.total_cart_abandon_users）
- 占加购用户比例：28.3%（60,891 / 215,167）
- 人均加购商品 5.9 件，跨越 3.9 个类目
- 66.91% 在最近1天有加购行为，82.15% 在最近3天有加购行为
- 人均活跃天数 6.7 天，人均日均 PV 11.5 次

【增量洞察】
加购未购用户活跃度不低（6.7天），说明他们持续在平台浏览但未完成购买。超过 2/3 在最近1天有加购行为，建议在加购后 24-48h 内触达。窗口内数据表明存在短周期转化机会。

【数据局限】
仅 9 天窗口，"未购"仅指窗口内未购买。用户可能在其他平台已完成购买。加购可能是收藏替代行为。
""",

    "T3": """【数据摘要】
- P0 (window_repeat_buyer)：窗口内购买≥2次，buyer_rate_pct = 79.3%
- P1 (cart_abandon_user)：加购但未购买，60,891人 (21.2%)，buyer_rate_pct = 0%（定义约束）
- P2 (high_browse_weak_buy_signal)：高浏览未购买，buyer_rate_pct = 0%（定义约束）
- P3 (low_active_no_purchase)：其余未购买用户，buyer_rate_pct = 0%（定义约束）
- REF (single_purchase_user)：单次购买用户(参照组)，buyer_rate_pct = 100%（定义约束）

【增量洞察】
各层购买率差距源自定义约束：P1-P3 层因定义 is_buyer=0 所以 buyer_rate_pct 严格为 0%。分层主要比较的是规模和人均 PV、活跃天数等行为特征。P0 层和 REF 层合计占用户约 68%（即全体购买用户）。

【数据局限】
分层基于 9 天窗口内行为，不推断长期价值。P1-P3 层购买率均为 0% 是定义使然，不反映真实转化潜力。
""",

    "T4": """【数据摘要】
- 周末 DAU 较工作日 + 16%（来源：weekday_behavior_summary）
- 周末行为级购买率较工作日下降约 -10%
- 周末人均 PV 更高，行为类型中浏览占比提升
- 周末加购率略低于工作日

【增量洞察】
周末用户行为模式偏向浏览（"逛"型流量增加），人均行为次数提升但购买决策速度下降。3个周末日 vs 6个工作日样本不平衡是需要注意的限制。建议周末推内容型运营（直播/短视频）而非硬促销。

【数据局限】
仅 3 个周末日 vs 6 个工作日样本，统计检验效力有限。无法区分"周末专属用户"和"全周期活跃用户"的行为模式切换。第 2 个周末的延迟购买不可观测（窗口末尾）。
""",

    "T5": """【数据摘要】
- 流量峰值：21:00（约 243 万次行为）
- 购买率峰值：10:00（行为维度 2.62%）
- 购买率谷值：21:00（行为维度 1.73%）
- 时段分组：上午(6-11)购买率最高，晚间(18-21)流量最高但购买率低

【增量洞察】
存在时序错位——流量峰值与购买率峰值不在同一时段。夜间用户以"逛"为主（睡前打发时间），上午用户目的明确（买了就走）。建议促销 Push 调整至 9:30（购买率窗口前），限时秒杀安排在 10:00-11:00 和 14:00-15:00。

【数据局限】
无法区分主动搜索和被动推荐来源的流量差异。小时数据按行为维度计算，与用户维度购买率含义不同。
""",

    "T6": """【数据摘要】
- 高曝光低转化商品：51.3 万件（来源：product_efficiency_anomaly_summary.helc_item_cnt）
- 阈值定义：PV ≥ P75（动态计算）且购买率 ≤ MEDIAN
- 搜索直达商品：11,781 件（buy>0 且 pv=0）
- 全局商品 2,584,912 件，89.12% 为窗口内零购买商品

【增量洞察】
高曝光低转化商品是用户行为层面的曝光效率异常线索。当前数据缺少曝光来源字段，无法区分自然推荐与商业化推广，因此不直接将高曝光低购买信号等同于推荐降权决策。搜索直达商品 11,781 件可能存在数据采集差异——某些场景的浏览行为未被记录为 pv。

【数据局限】
无商品价格/评分/详情页质量数据。无曝光来源字段，无法区分自然推荐与商业化推广。阈值（P75/中位数）为动态计算，不同数据窗口可能不同。
""",

    "T7": """【数据摘要】
基于加购未购用户数据（60,891人，占加购用户28.3%），设计如下运营策略：

【P0】加购未购用户限时折扣触达
  - 目标群体：加购未购用户（60,891人），优先 days_since_last_cart ≤ 2 的用户
  - 触达时机：加购后 24-48h 未购买时
  - 具体动作：Push 推送"您加购的商品库存紧张" + 48h后发放 5% 限时折扣券（有效期 24h）
  - 预期KPI：触达后购买转化率达到 10-15%（行业加购召回转化基准）

【P1】加购未购用户加购商品降价提醒
  - 目标群体：加购未购用户中活跃天数 ≥ 5 的用户
  - 触达时机：工作日 9:30（购买率窗口前）
  - 具体动作：站内信发送加购商品列表 + "大家都在买"社交推荐
  - 预期KPI：点击率 ≥ 8%，购买转化率 ≥ 5%

【数据局限】
无真实价格数据，ROI 为估算。策略为离线设计方案，非实际业务执行结果。窗口内数据可能高估加购未购规模（延迟购买）。
""",

    "T8": """【数据摘要】
基于加购未购用户（60,891人），设计 A/B 实验方案：

【实验设计】
- 实验对象：加购未购用户中 days_since_last_cart ≤ 3 的用户
- 分组方式：随机分为 A/B/C 3 组，每组约 16,600 人
- A 组（实验组1）：加购 48h 后发放 5% 限时折扣券（有效期 24h）
- B 组（实验组2）：加购 48h 后 Push "您的加购商品还在等您"（无折扣）
- C 组（对照组）：不做任何干预

【核心指标】
- 主指标：触达后 7 天窗口内购买转化率（目标：A组 ≥ 15%, B组 ≥ 8%）
- 辅助指标：Push 打开率、优惠券核销率、客单价
- 显著性检验：χ² 检验（转化率差异），α = 0.05，power ≥ 0.8

【数据局限】
⚠️ 这是离线设计方案，非实际实验结果。离线数据无法执行真实 A/B 测试。无真实价格数据，ROI 评估需假设客单价。窗口限制（9天）可能影响观察窗口设计。
""",
}


# ══════════════════════════════════════════════════════════
# 3. 测试执行
# ══════════════════════════════════════════════════════════

def run_online_test(test_case: dict, provider: str = "deepseek") -> dict:
    """在线模式：实际调用 LLM 进行测试"""
    try:
        from core_agent import LLMClient, load_system_prompt
        from multi_agent import run_analyst

        llm = LLMClient(provider)
        system = load_system_prompt()

        print(f"    [LLM] 调用 {provider}/{llm.model}...")
        t0 = time.time()

        result = run_analyst(
            question=test_case["question"],
            llm=llm,
            max_retry=2,
        )

        elapsed = time.time() - t0

        # Reviewer 验证
        from agent.reviewer import review as reviewer_review
        review_result = reviewer_review(result, mode="analyst")

        return {
            "test_id": test_case["id"],
            "test_title": test_case["title"],
            "question": test_case["question"],
            "response": result,
            "response_length": len(result),
            "elapsed_sec": round(elapsed, 1),
            "reviewer_passed": review_result.passed,
            "reviewer_feedback": review_result.feedback,
            "reviewer_stats": review_result.stats,
            "reviewer_warnings": review_result.warnings,
            "mode": "online",
        }

    except Exception as e:
        return {
            "test_id": test_case["id"],
            "test_title": test_case["title"],
            "question": test_case["question"],
            "response": "",
            "error": str(e),
            "mode": "online",
            "reviewer_passed": False,
        }


def run_offline_test(test_case: dict) -> dict:
    """离线模式：使用预置样本测试 Reviewer 引擎"""
    test_id = test_case["id"]
    sample = SAMPLE_RESPONSES.get(test_id, "")

    if not sample:
        return {
            "test_id": test_id,
            "test_title": test_case["title"],
            "response": "",
            "error": f"无预置样本 (T{test_id})",
            "mode": "offline",
            "reviewer_passed": False,
        }

    from agent.reviewer import review as reviewer_review

    # 根据测试类型选择 review mode
    mode = "analyst"
    if test_case["type"] in ("strategy", "validation"):
        mode = "pipeline"

    review_result = reviewer_review(sample, mode=mode)

    # 额外：策略专项检查 (T7, T8)
    if test_case["type"] in ("strategy", "validation"):
        from agent.reviewer import review_strategy_only
        strategy_result = review_strategy_only(sample)
    else:
        strategy_result = None

    return {
        "test_id": test_id,
        "test_title": test_case["title"],
        "question": test_case["question"],
        "response": sample,
        "response_length": len(sample),
        "elapsed_sec": 0,
        "reviewer_passed": review_result.passed,
        "reviewer_feedback": review_result.feedback,
        "reviewer_stats": review_result.stats,
        "reviewer_warnings": review_result.warnings,
        "strategy_review": (
            {"passed": strategy_result.passed, "feedback": strategy_result.feedback}
            if strategy_result else None
        ),
        "mode": "offline",
    }


# ══════════════════════════════════════════════════════════
# 4. 结果格式化
# ══════════════════════════════════════════════════════════

def print_summary(results: list[dict]):
    """打印测试结果汇总表"""
    print("\n" + "=" * 80)
    print(" Agent 测试结果汇总")
    print("=" * 80)

    header = f"  {'ID':<4} {'测试名称':<20} {'模式':<8} {'字数':>6} {'耗时':>8} {'Reviewer':>10} {'状态':<6}"
    print(header)
    print("  " + "-" * 76)

    passed_count = 0
    failed_tests = []

    for r in results:
        rid = r["test_id"]
        title = r["test_title"][:18]
        mode = r.get("mode", "?")
        length = r.get("response_length", 0)
        elapsed = f"{r.get('elapsed_sec', 0)}s" if r.get("elapsed_sec") else "-"
        reviewer = "PASS" if r.get("reviewer_passed") else "FAIL"
        status = "✓" if r.get("reviewer_passed") else "✗"

        print(f"  {rid:<4} {title:<20} {mode:<8} {length:>6} {elapsed:>8} {reviewer:>10} {status:<6}")

        if r.get("reviewer_passed"):
            passed_count += 1
        else:
            failed_tests.append(rid)
            if r.get("error"):
                print(f"         ⚠️ 错误: {r['error'][:80]}")

    print("  " + "-" * 76)
    pass_rate = round(100.0 * passed_count / len(results), 1) if results else 0
    print(f"  通过: {passed_count}/{len(results)} ({pass_rate}%)")
    print("=" * 80)

    if failed_tests:
        print(f"\n  未通过测试: {', '.join(failed_tests)}")
        print(f"  详细 feedback 见下方:\n")
        for r in results:
            if not r.get("reviewer_passed"):
                print(f"  [{r['test_id']}] {r['test_title']}")
                print(f"  {r.get('reviewer_feedback', r.get('error', 'N/A'))}")
                if r.get("reviewer_warnings"):
                    for w in r["reviewer_warnings"]:
                        print(f"     ⚠️ {w[:100]}")
                print()

    # 评级
    if pass_rate == 100:
        grade = "优秀"
    elif pass_rate >= 75:
        grade = "合格"
    else:
        grade = "不合格"
    print(f"  最终评级: {grade}")

    return pass_rate


# ══════════════════════════════════════════════════════════
# 5. 入口
# ══════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Agent 自动化测试 (T1-T8)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Reviewer 单元测试（仅校验 reviewer.py 逻辑，不调 LLM）")
    parser.add_argument("--offline", action="store_true",
                        help="离线模式（使用预置样本测试 Reviewer，默认）")
    parser.add_argument("--online", action="store_true",
                        help="在线模式（实际调用 LLM API）")
    parser.add_argument("--test", type=str, default=None,
                        help="仅运行指定测试 (如 --test T1)")
    parser.add_argument("--provider", choices=["deepseek", "anthropic"],
                        default="deepseek",
                        help="LLM Provider（默认 deepseek）")
    args = parser.parse_args()

    # 默认：离线模式
    if not args.online and not args.dry_run:
        args.offline = True

    # 过滤测试
    if args.test:
        test_cases = [tc for tc in TEST_CASES if tc["id"] == args.test]
        if not test_cases:
            print(f"[错误] 未找到测试: {args.test}")
            sys.exit(1)
    else:
        test_cases = TEST_CASES

    print("\n" + "=" * 80)
    print(f" Agent 测试执行 — {len(test_cases)} 个测试")
    print(f" 模式: {'在线(LLM)' if args.online else '离线(预置样本)' if args.offline else 'Dry-run'}")
    print(f" Provider: {args.provider}")
    print("=" * 80)

    # Dry-run: 仅测试 reviewer 引擎逻辑
    if args.dry_run:
        print("\n[Reviewer 单元测试]")
        from agent.reviewer import review as reviewer_review

        test_texts = [
            ("正常输出", "【数据摘要】\n用户总数287004人，购买用户占比68.0%。日活用户约10万，行为维度购买率2.0%。\n【数据局限】仅9天窗口。"),
            ("模糊词", "购买率较高，用户明显较多。"),
            ("数字不足", "用户很多，购买率还可以。"),
            ("禁止用语", "用户留存率78.8%，复购率较高，存在流失用户。"),
            ("策略测试", "策略：[P0]针对加购未购用户60,891人，在加购后48h推送10%限时折扣券，目标购买转化率提升至15%。"),
        ]

        for label, text in test_texts:
            result = reviewer_review(text, mode="analyst")
            status = "✓" if result.passed else "✗"
            print(f"  {status} {label}: {result.feedback.split(chr(10))[0]}")
        print()
        return

    # 执行测试
    results = []
    for tc in test_cases:
        print(f"\n[{tc['id']}] {tc['title']}")
        print(f"  问题: {tc['question']}")

        if args.online:
            result = run_online_test(tc, provider=args.provider)
        else:
            result = run_offline_test(tc)

        results.append(result)

        status = "✓ PASS" if result.get("reviewer_passed") else "✗ FAIL"
        print(f"  结果: {status}")
        if result.get("error"):
            print(f"  错误: {result['error']}")

    # 汇总
    pass_rate = print_summary(results)

    # 保存结果
    output_path = Path("agent/test_results.json")
    output_data = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "mode": "online" if args.online else "offline",
        "provider": args.provider if args.online else "N/A",
        "total_tests": len(results),
        "passed": sum(1 for r in results if r.get("reviewer_passed")),
        "pass_rate_pct": pass_rate,
        "results": results,
    }
    output_path.write_text(
        json.dumps(output_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n测试结果已保存: {output_path}")

    # 返回码
    sys.exit(0 if pass_rate >= 75 else 1)


if __name__ == "__main__":
    main()
