"""
cluster_analysis.py — 聚类分析与用户画像
=======================================
职责：读取聚类结果 → 统计聚类特征 → 生成用户画像 → 输出运营建议

用法:
    python src/cluster_analysis.py

输入:
    data/features/user_features.parquet
    data/mart/user_cluster_result.parquet

输出:
    data/mart/user_cluster_summary.parquet
"""

import os
import numpy as np
import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── 聚类特征定义 ──────────────────────────────────────────
PROFILE_METRICS = {
    "pv_cnt":    ("PV均值",        "mean"),
    "fav_cnt":   ("收藏均值",      "mean"),
    "cart_cnt":  ("加购均值",      "mean"),
    "buy_cnt":   ("购买均值",      "mean"),
    "fav_rate":  ("收藏率(%)",     "mean"),
    "cart_rate": ("加购率(%)",      "mean"),
    "buy_rate":  ("购买率(%)",     "mean"),
    "cart_to_buy_rate": ("加购→购买率(%)", "mean"),
    "active_days":     ("活跃天数",      "mean"),
    "buy_days":        ("购买天数",      "mean"),
    "buy_days_ratio":  ("购买天数占比",   "mean"),
    "active_hours":    ("活跃小时数",    "mean"),
    "active_weekdays": ("活跃星期数",    "mean"),
    "avg_daily_actions": ("日均行为数",  "mean"),
    "avg_daily_buy":     ("日均购买数",  "mean"),
    "avg_daily_cart":    ("日均加购数",  "mean"),
    "category_diversity":    ("类目广度",     "mean"),
    "item_diversity":        ("商品广度",     "mean"),
    "category_concentration":("类目集中度",   "mean"),
    "weekend_ratio":   ("周末占比(%)",     "mean"),
    "night_ratio":     ("夜间占比(%)",     "mean"),
    "buy_weekend_ratio":("周末购买占比(%)", "mean"),
    "hour_concentration":("时段集中度",     "mean"),
    "lifecycle_days":      ("生命周期(天)",  "mean"),
    "active_weeks":        ("活跃周数",     "mean"),
    "weekly_volatility":   ("行为稳定性",   "mean"),
    "recent_7d_actions_pct": ("近7日活跃(%)", "mean"),
    "days_since_last_active":("距末次活跃(天)", "mean"),
    "is_buyer":         ("购买用户占比(%)", "mean"),
}

DISPLAY_ORDER = [
    "购买率(%)", "PV均值", "购买均值", "加购均值", "收藏均值",
    "活跃天数", "生命周期(天)", "活跃周数",
    "加购率(%)", "收藏率(%)", "加购→购买率(%)",
    "类目广度", "商品广度", "类目集中度",
    "周末占比(%)", "夜间占比(%)", "周末购买占比(%)",
    "近7日活跃(%)", "距末次活跃(天)", "行为稳定性",
]


def load_data():
    """加载特征和聚类标签"""
    features = pd.read_parquet(
        os.path.join(PROJECT_ROOT, "data", "features", "user_features.parquet")
    )
    clusters = pd.read_parquet(
        os.path.join(PROJECT_ROOT, "data", "mart", "user_cluster_result.parquet")
    )
    df = features.merge(clusters, on="user_id", how="inner")
    print(f"[LOAD] {df.shape[0]:,} users x {df.shape[1]} columns")
    return df


def compute_cluster_profile(df: pd.DataFrame) -> pd.DataFrame:
    """计算每个聚类的关键指标"""
    k = df["cluster"].nunique()

    records = []
    for c in range(k):
        cdf = df[df["cluster"] == c]
        record = {"cluster": c, "user_cnt": len(cdf), "user_pct": round(100 * len(cdf) / len(df), 1)}

        for col, (label, agg) in PROFILE_METRICS.items():
            if col not in cdf.columns:
                continue
            val = cdf[col].mean()
            if agg == "mean" and col == "is_buyer":
                val = val * 100  # 转百分比
            record[label] = round(val, 3)

        records.append(record)

    profile = pd.DataFrame(records).set_index("cluster")
    print(f"[PROFILE] {k} clusters profiled")
    return profile


def generate_persona(profile: pd.DataFrame) -> list:
    """基于相对位置自动生成用户画像"""
    personas = []

    rankings = profile.rank(pct=True)  # percentile rank within clusters

    for c in profile.index:
        row = profile.loc[c]
        buy_rate = row["购买率(%)"]
        pv = row["PV均值"]
        active = row["活跃天数"]
        lifecycle = row["生命周期(天)"]
        recent = row["近7日活跃(%)"]
        cat_div = row["类目广度"]
        buy_cnt = row["购买均值"]
        cart_cnt = row["加购均值"]
        user_cnt = int(row["user_cnt"])
        user_pct = row["user_pct"]

        # Rank-based classification (relative to 5 clusters)
        buy_rank = rankings.loc[c, "购买率(%)"]
        pv_rank = rankings.loc[c, "PV均值"]
        active_rank = rankings.loc[c, "活跃天数"]
        cat_rank = rankings.loc[c, "类目广度"]

        # Differentiate by combining buy_rate + pv + active_days
        if buy_rank >= 0.8:
            persona_name = "高价值核心用户"
            icon = "[CORE]"
            priority = "P0-维护"
            strategies = "会员权益升级、新品优先体验、专属客服、复购激励"
            channel = "Push + 短信 + 站内信"
        elif buy_rank >= 0.6 and pv_rank >= 0.4:
            persona_name = "高效转化用户"
            icon = "[HIGH]"
            priority = "P1-重点"
            strategies = "加购未购商品限时折扣、关联品类推荐、会员等级激励"
            channel = "Push + 站内信"
        elif pv_rank >= 0.6 and buy_rank < 0.4:
            persona_name = "高浏览低转化用户"
            icon = "[BROWSE]"
            priority = "P1-转化"
            strategies = "首单大额券、浏览商品降价提醒、简化购买路径、社交推荐"
            channel = "Push + 站内弹窗"
        elif pv_rank < 0.3 and active_rank < 0.4:
            persona_name = "低频轻度用户"
            icon = "[LIGHT]"
            priority = "P2-激活"
            strategies = "签到打卡、热门爆品推荐、首单补贴"
            channel = "Push + 站内推荐"
        elif cat_rank >= 0.6 and pv_rank >= 0.4:
            persona_name = "探索型浏览用户"
            icon = "[EXPLORE]"
            priority = "P2-引导"
            strategies = "新品类发现推荐、个性化首页、品类组合优惠"
            channel = "站内推荐 + Push"
        elif buy_rank >= 0.4:
            persona_name = "潜力转化用户"
            icon = "[POTENTIAL]"
            priority = "P1-转化"
            strategies = "加购未购商品限时折扣、关联品类推荐"
            channel = "Push + 站内信"
        else:
            persona_name = "普通活跃用户"
            icon = "[NORMAL]"
            priority = "P3-维持"
            strategies = "日常签到奖励、偏好品类推荐、季节性促销"
            channel = "站内推荐"

        personas.append({
            "cluster": int(c),
            "persona_name": persona_name,
            "icon": icon,
            "priority": priority,
            "user_cnt": user_cnt,
            "user_pct": user_pct,
            "buy_rate_pct": round(buy_rate, 1),
            "avg_pv": round(pv, 0),
            "avg_active_days": round(active, 1),
            "avg_lifecycle_days": round(lifecycle, 0),
            "category_diversity": round(cat_div, 1),
            "cart_to_buy_rate": round(row.get("加购→购买率(%)", 0), 1),
            "recent_7d_pct": round(recent, 1),
            "weekly_volatility": round(row["行为稳定性"], 3),
            "strategies": strategies,
            "channel": channel,
        })

    return sorted(personas, key=lambda p: p["buy_rate_pct"], reverse=True)


def print_report(profile: pd.DataFrame, personas: list) -> None:
    """打印聚类分析报告"""
    print("\n" + "=" * 80)
    print(" 用户聚类分析报告")
    print("=" * 80)
    for p in personas:
        print(f"\n  {p['icon']} Cluster {p['cluster']} — {p['persona_name']}")
        print(f"  {'─' * 60}")
        print(f"    用户数:      {p['user_cnt']:>8,} ({p['user_pct']:.1f}%)")
        print(f"    购买率:      {p['buy_rate_pct']:>8.1f}%")
        print(f"    人均PV:      {p['avg_pv']:>8.0f}")
        print(f"    活跃天数:    {p['avg_active_days']:>8.1f}")
        print(f"    生命周期:    {p['avg_lifecycle_days']:>8.0f} 天")
        print(f"    类目广度:    {p['category_diversity']:>8.1f}")
        print(f"    加购→购买:   {p['cart_to_buy_rate']:>8.1f}%")
        print(f"    近7日活跃:   {p['recent_7d_pct']:>8.1f}%")
        print(f"    运营优先级:  {p['priority']}")
        print(f"    触达渠道:    {p['channel']}")
        print(f"    推荐策略:    {p['strategies']}")

    total_users = sum(p["user_cnt"] for p in personas)
    print(f"\n{'='*60}")
    print(f"  总用户数: {total_users:,}")
    print(f"{'='*60}")


def main():
    print("=" * 60)
    print(" Cluster Analysis & Persona Generation")
    print("=" * 60)

    df = load_data()
    profile = compute_cluster_profile(df)
    personas = generate_persona(profile)

    # 保存 summary
    summary_path = os.path.join(PROJECT_ROOT, "data", "mart", "user_cluster_summary.parquet")
    summary_df = pd.DataFrame(personas)
    summary_df.to_parquet(summary_path, index=False)
    print(f"\n[SAVE] {summary_path}")

    # 打印报告
    print_report(profile, personas)

    return profile, personas


if __name__ == "__main__":
    main()
