"""
visualization.py — 聚类可视化模块
=================================
职责：生成聚类分析图表，适合直接放入项目报告

用法:
    python src/visualization.py

输入:
    data/features/user_features.parquet
    data/mart/user_cluster_result.parquet
    data/mart/user_cluster_summary.parquet

输出:
    outputs/figures/
        cluster_distribution.png    — 聚类分布
        cluster_pca.png             — PCA 二维投影
        cluster_radar.png           — 特征雷达图
        cluster_comparison.png      — 关键指标对比
        cluster_funnel.png          — 转化漏斗对比
        feature_importance.png      — 特征重要性
"""

import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIG_DIR = os.path.join(PROJECT_ROOT, "outputs", "figures")
os.makedirs(FIG_DIR, exist_ok=True)

# ── 全局样式 ────────────────────────────────────────────
plt.rcParams.update({
    "font.sans-serif": ["SimHei", "Microsoft YaHei", "DejaVu Sans"],
    "axes.unicode_minus": False,
    "figure.dpi": 120,
    "savefig.dpi": 150,
    "savefig.bbox": "tight",
})

# 聚类使用的特征（与 user_clustering.py 一致）
CLUSTER_FEATURES = [
    # 行为量级
    "pv_cnt", "fav_cnt", "cart_cnt", "buy_cnt",
    # 转化率
    "fav_rate", "cart_rate", "buy_rate", "cart_to_buy_rate",
    # 活跃度
    "active_days", "buy_days", "buy_days_ratio", "active_hours", "active_weekdays",
    # 行为强度
    "avg_daily_actions", "avg_daily_buy", "avg_daily_cart",
    # 兴趣广度
    "category_diversity", "item_diversity",
    # 时间偏好
    "weekend_ratio", "night_ratio", "morning_ratio", "afternoon_ratio",
    "evening_ratio", "hour_concentration", "buy_weekend_ratio",
    # 稳定性
    "lifecycle_days", "active_weeks", "weekly_volatility",
    "recent_7d_actions_pct", "recent_30d_actions_pct", "days_since_last_active",
    # 编码后
    "favorite_category_freq",
]

LOG1P_COLS = {
    "pv_cnt", "fav_cnt", "cart_cnt", "buy_cnt",
    "active_days", "buy_days", "active_hours", "active_weekdays",
    "lifecycle_days", "active_weeks",
    "category_diversity", "item_diversity",
}


def load_and_prepare():
    """加载数据并做与聚类一致的预处理"""
    features = pd.read_parquet(
        os.path.join(PROJECT_ROOT, "data", "features", "user_features.parquet")
    )
    clusters = pd.read_parquet(
        os.path.join(PROJECT_ROOT, "data", "mart", "user_cluster_result.parquet")
    )
    df = features.merge(clusters, on="user_id", how="inner")

    # 编码 favorite_category
    if "favorite_category" in df.columns:
        freq = df["favorite_category"].value_counts(normalize=True)
        df["favorite_category_freq"] = df["favorite_category"].map(freq).fillna(0)

    # 特征列表
    feature_list = [f for f in CLUSTER_FEATURES if f in df.columns]
    X = df[feature_list].copy().fillna(0)

    # log1p
    for col in LOG1P_COLS:
        if col in X.columns:
            X[col] = np.log1p(X[col].clip(lower=0))

    # StandardScaler
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    X_scaled_df = pd.DataFrame(X_scaled, columns=X.columns, index=X.index)

    print(f"[PREP] {X_scaled_df.shape[1]} features, {X_scaled_df.shape[0]:,} samples")
    return df, X_scaled_df, feature_list


def plot_cluster_distribution(df: pd.DataFrame):
    """聚类样本分布图"""
    counts = df["cluster"].value_counts().sort_index()
    colors = plt.cm.Set2(np.linspace(0, 1, len(counts)))

    fig, ax = plt.subplots(figsize=(10, 6))
    bars = ax.bar(counts.index, counts.values, color=colors, edgecolor="white", linewidth=1.2)
    for bar, cnt in zip(bars, counts.values):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + len(df) * 0.005,
                f"{cnt:,}\n({100*cnt/len(df):.1f}%)", ha="center", fontsize=9, fontweight="bold")
    ax.set_xlabel("Cluster", fontsize=12, fontweight="bold")
    ax.set_ylabel("Users", fontsize=12, fontweight="bold")
    ax.set_title("Cluster Distribution", fontsize=14, fontweight="bold")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x/1000:.0f}k"))
    ax.set_xticks(range(len(counts)))
    fig.tight_layout()
    fig.savefig(os.path.join(FIG_DIR, "cluster_distribution.png"))
    plt.close(fig)
    print("[FIG] cluster_distribution.png")


def plot_pca(X_scaled_df: pd.DataFrame, df: pd.DataFrame):
    """PCA 二维降维图"""
    pca = PCA(n_components=2, random_state=42)
    X_pca = pca.fit_transform(X_scaled_df.values)
    k = df["cluster"].nunique()
    colors = plt.cm.Set2(np.linspace(0, 1, k))

    fig, ax = plt.subplots(figsize=(10, 8))
    for c in range(k):
        mask = df["cluster"] == c
        n_sample = min(mask.sum(), 2000)
        idx = np.random.RandomState(42).choice(np.where(mask)[0], size=n_sample, replace=False)
        ax.scatter(X_pca[idx, 0], X_pca[idx, 1], c=[colors[c]], label=f"Cluster {c}",
                   alpha=0.5, s=6)

    ax.set_xlabel(f"PC1 ({pca.explained_variance_ratio_[0]:.1%})", fontsize=11)
    ax.set_ylabel(f"PC2 ({pca.explained_variance_ratio_[1]:.1%})", fontsize=11)
    ax.set_title(f"PCA Projection (K={k})", fontsize=14, fontweight="bold")
    ax.legend(markerscale=3, fontsize=8)
    ax.grid(True, alpha=0.2)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG_DIR, "cluster_pca.png"))
    plt.close(fig)
    print(f"[FIG] cluster_pca.png (PC1+PC2 = {pca.explained_variance_ratio_.sum():.1%})")


def plot_cluster_comparison(df: pd.DataFrame):
    """聚类关键指标对比柱状图"""
    metrics = [
        ("buy_rate", "Purchase Rate (%)"),
        ("cart_rate", "Cart Rate (%)"),
        ("active_days", "Active Days"),
        ("category_diversity", "Category Diversity"),
        ("weekend_ratio", "Weekend Ratio (%)"),
        ("recent_7d_actions_pct", "Recent 7D Activity (%)"),
    ]
    metrics = [(m, l) for m, l in metrics if m in df.columns]
    k = df["cluster"].nunique()
    colors = plt.cm.Set2(np.linspace(0, 1, k))

    fig, axes = plt.subplots(2, 3, figsize=(16, 10))
    axes = axes.flatten()
    x = np.arange(k)

    for i, (metric, label) in enumerate(metrics):
        ax = axes[i]
        values = [df[df["cluster"] == c][metric].mean() for c in range(k)]
        bars = ax.bar(x, values, 0.6, color=colors, edgecolor="white", linewidth=1)
        best = np.argmax(values)
        bars[best].set_edgecolor("black")
        bars[best].set_linewidth(2)
        ax.set_xticks(x)
        ax.set_xticklabels([f"C{c}" for c in range(k)])
        ax.set_title(label, fontsize=10, fontweight="bold")
        ax.axhline(y=df[metric].mean(), color="gray", ls="--", lw=0.8, alpha=0.5)

    for i in range(len(metrics), len(axes)):
        axes[i].set_visible(False)

    fig.suptitle(f"Cluster Comparison (K={k})", fontsize=14, fontweight="bold")
    fig.tight_layout()
    fig.savefig(os.path.join(FIG_DIR, "cluster_comparison.png"))
    plt.close(fig)
    print("[FIG] cluster_comparison.png")


def plot_cluster_radar(X_scaled_df: pd.DataFrame, df: pd.DataFrame):
    """聚类特征雷达图"""
    # 选择 4 组特征做 4 个雷达图
    radar_groups = [
        ("Behavior Volume", ["pv_cnt", "fav_cnt", "cart_cnt", "buy_cnt"]),
        ("Conversion", ["fav_rate", "cart_rate", "buy_rate", "cart_to_buy_rate"]),
        ("Activity", ["active_days", "active_hours", "active_weeks", "lifecycle_days"]),
        ("Diversity & Recency", ["category_diversity", "item_diversity",
                                  "recent_7d_actions_pct", "weekly_volatility"]),
    ]
    k = df["cluster"].nunique()
    colors = plt.cm.Set2(np.linspace(0, 1, k))

    fig, axes = plt.subplots(2, 2, figsize=(14, 14), subplot_kw=dict(polar=True))
    axes = axes.flatten()

    for idx, (title, feats) in enumerate(radar_groups):
        ax = axes[idx]
        valid = [f for f in feats if f in X_scaled_df.columns]
        n = len(valid)
        angles = np.linspace(0, 2 * np.pi, n, endpoint=False).tolist()
        angles += angles[:1]

        for c in range(k):
            mask = df["cluster"] == c
            vals = X_scaled_df.loc[mask, valid].mean().values
            vals = np.append(vals, vals[0])
            ax.fill(angles, vals, alpha=0.08, color=colors[c])
            ax.plot(angles, vals, "o-", lw=1.5, ms=3, color=colors[c], label=f"C{c}")

        ax.set_xticks(angles[:-1])
        ax.set_xticklabels(valid, fontsize=7)
        ax.set_title(title, fontsize=11, fontweight="bold", pad=15)
        if idx == 0:
            ax.legend(loc="upper right", bbox_to_anchor=(1.35, 1.0), fontsize=7)

    fig.suptitle(f"Cluster Radar Charts (K={k})", fontsize=14, fontweight="bold", y=1.02)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG_DIR, "cluster_radar.png"))
    plt.close(fig)
    print("[FIG] cluster_radar.png")


def plot_cluster_funnel(df: pd.DataFrame):
    """聚类转化漏斗对比"""
    k = df["cluster"].nunique()
    colors = plt.cm.Set2(np.linspace(0, 1, k))

    stages = ["PV", "FAV", "CART", "BUY"]
    stage_cols = ["pv_cnt", "fav_cnt", "cart_cnt", "buy_cnt"]

    fig, ax = plt.subplots(figsize=(10, 6))
    for c in range(k):
        cdf = df[df["cluster"] == c]
        total = len(cdf)
        vals = [(cdf[col] > 0).sum() / total * 100 for col in stage_cols]
        ax.plot(stages, vals, "o-", lw=2, ms=7, color=colors[c], label=f"Cluster {c}")

    ax.set_ylabel("User Penetration (%)", fontsize=12)
    ax.set_title(f"Conversion Funnel by Cluster (K={k})", fontsize=14, fontweight="bold")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(FIG_DIR, "cluster_funnel.png"))
    plt.close(fig)
    print("[FIG] cluster_funnel.png")


def plot_feature_importance(df: pd.DataFrame, feature_list: list):
    """特征重要性图：每个特征的簇间方差 / 总方差"""
    features = [f for f in feature_list if f in df.columns]
    k = df["cluster"].nunique()

    # 计算每个特征的 F-statistic (簇间方差/簇内方差)
    global_mean = df[features].mean()
    scores = {}
    for f in features:
        between_var = sum(
            len(df[df["cluster"] == c]) * (df[df["cluster"] == c][f].mean() - global_mean[f]) ** 2
            for c in range(k)
        ) / (k - 1)
        within_var = sum(
            ((df[df["cluster"] == c][f] - df[df["cluster"] == c][f].mean()) ** 2).sum()
            for c in range(k)
        ) / (len(df) - k)
        scores[f] = between_var / (within_var + 1e-10) if within_var > 0 else 0

    scores_sorted = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:20]
    names, vals = zip(*scores_sorted)

    fig, ax = plt.subplots(figsize=(10, 8))
    colors = plt.cm.viridis(np.linspace(0.2, 0.9, len(names)))
    ax.barh(range(len(names)), vals, color=colors, edgecolor="white")
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names, fontsize=9)
    ax.set_xlabel("F-statistic (cluster separation power)", fontsize=11)
    ax.set_title("Top 20 Feature Importance for Clustering", fontsize=13, fontweight="bold")
    ax.invert_yaxis()
    fig.tight_layout()
    fig.savefig(os.path.join(FIG_DIR, "feature_importance.png"))
    plt.close(fig)
    print("[FIG] feature_importance.png")


def main():
    print("=" * 60)
    print(" Cluster Visualization")
    print("=" * 60)

    df, X_scaled_df, feature_list = load_and_prepare()

    plot_cluster_distribution(df)
    plot_pca(X_scaled_df, df)
    plot_cluster_comparison(df)
    plot_cluster_radar(X_scaled_df, df)
    plot_cluster_funnel(df)
    plot_feature_importance(df, feature_list)

    print(f"\n[ DONE ] 6 figures saved to {FIG_DIR}/")


if __name__ == "__main__":
    main()
