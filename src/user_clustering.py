"""
user_clustering.py — 用户聚类模块
===============================
职责：读取特征宽表 → 特征工程 → KMeans聚类 → 输出聚类标签

用法:
    python src/user_clustering.py

输入:
    data/features/user_features.parquet

输出:
    data/mart/user_cluster_result.parquet  (user_id, cluster)
"""

import os
import sys
import numpy as np
import pandas as pd
import duckdb
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

# ── 路径 ────────────────────────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FEATURE_PATH = os.path.join(PROJECT_ROOT, "data", "features", "user_features.parquet")
RESULT_PATH = os.path.join(PROJECT_ROOT, "data", "mart", "user_cluster_result.parquet")
DB_PATH = os.path.join(PROJECT_ROOT, "data", "analysis.db")

# ── 聚类特征分组 ─────────────────────────────────────────
# 排除：user_id (标识), is_buyer (标签), favorite_category (需编码)
CLUSTER_FEATURES = {
    "行为量级":     ["pv_cnt", "fav_cnt", "cart_cnt", "buy_cnt"],
    "转化率":       ["fav_rate", "cart_rate", "buy_rate", "cart_to_buy_rate"],
    "活跃度":       ["active_days", "buy_days", "buy_days_ratio",
                     "active_hours", "active_weekdays"],
    "行为强度":     ["avg_daily_actions", "avg_daily_buy", "avg_daily_cart"],
    "兴趣广度":     ["category_diversity", "item_diversity"],
    "时间偏好":     ["weekend_ratio", "night_ratio", "morning_ratio",
                     "afternoon_ratio", "evening_ratio", "hour_concentration",
                     "buy_weekend_ratio"],
    "行为稳定性":   ["lifecycle_days", "active_weeks", "weekly_volatility",
                     "recent_7d_actions_pct", "recent_30d_actions_pct",
                     "days_since_last_active"],
}

# log1p 变换的列（严重右偏的计数类特征）
LOG1P_COLS = [
    "pv_cnt", "fav_cnt", "cart_cnt", "buy_cnt",
    "active_days", "buy_days", "active_hours", "active_weekdays",
    "lifecycle_days", "active_weeks",
    "category_diversity", "item_diversity",
]


def load_data(path: str) -> pd.DataFrame:
    """加载特征宽表"""
    df = pd.read_parquet(path)
    print(f"[LOAD] {df.shape[0]:,} users x {df.shape[1]} features")
    return df


def check_data(df: pd.DataFrame, feature_list: list) -> pd.DataFrame:
    """数据质量检查"""
    X = df[feature_list].copy()

    # 缺失值
    null_count = X.isnull().sum().sum()
    if null_count > 0:
        print(f"[CHECK] WARNING: {null_count} null values found, filling with 0")
        X = X.fillna(0)

    # 无穷值
    inf_count = np.isinf(X.values).sum()
    if inf_count > 0:
        print(f"[CHECK] WARNING: {inf_count} inf values found, replacing with 0")
        X = X.replace([np.inf, -np.inf], 0)

    print(f"[CHECK] nulls=0, infs=0 (after cleaning)")
    return X


def encode_category(df: pd.DataFrame) -> pd.Series:
    """favorite_category: Frequency Encoding (类目流行度)"""
    freq = df["favorite_category"].value_counts(normalize=True)
    encoded = df["favorite_category"].map(freq)
    print(f"[ENCODE] favorite_category: {len(freq):,} unique values -> frequency encoding")
    return encoded.fillna(0).astype(np.float64)


def apply_log1p(X: pd.DataFrame) -> pd.DataFrame:
    """对右偏特征做 log1p 变换"""
    X_t = X.copy()
    cols = [c for c in LOG1P_COLS if c in X_t.columns]
    for col in cols:
        X_t[col] = np.log1p(X_t[col].clip(lower=0))
    print(f"[LOG1P] {len(cols)} columns transformed")
    return X_t


def scale_features(X: pd.DataFrame) -> tuple:
    """StandardScaler 标准化"""
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    print(f"[SCALE] mean={X_scaled.mean():.6f}, std={X_scaled.std():.6f}")
    return X_scaled, scaler


def search_optimal_k(X: np.ndarray, k_range: range = range(2, 11)) -> dict:
    """Elbow Method + Silhouette Score 选择最优 K"""
    inertias = []
    sil_scores = []

    print(f"[SEARCH] K=2..10 ...")
    for k in k_range:
        km = KMeans(n_clusters=k, random_state=42, n_init=10, max_iter=300)
        labels = km.fit_predict(X)
        inertias.append(km.inertia_)
        sil = silhouette_score(X, labels, sample_size=min(10000, len(X)))
        sil_scores.append(sil)
        print(f"  K={k:2d}  inertia={km.inertia_:>12,.0f}  silhouette={sil:.4f}")

    best_k = list(k_range)[np.argmax(sil_scores)]

    # Business constraint: minimum 5 clusters for meaningful personas
    # If all silhouette scores are very close (low variance in user behavior),
    # prefer K=5 or K=6 for interpretability
    candidates = {k: s for k, s in zip(k_range, sil_scores)}
    best_k = max(best_k, 5)  # at least 5 clusters
    if best_k > 6 and candidates.get(6, 0) >= max(sil_scores) - 0.03:
        best_k = 6
    elif best_k > 5 and candidates.get(5, 0) >= max(sil_scores) - 0.03:
        best_k = 5

    print(f"[SEARCH] Best K = {best_k}")
    return {"best_k": best_k, "inertias": inertias, "silhouette_scores": sil_scores, "k_range": list(k_range)}


def train_kmeans(X: np.ndarray, k: int) -> tuple:
    """训练最终 KMeans 模型"""
    km = KMeans(n_clusters=k, random_state=42, n_init=10, max_iter=300)
    labels = km.fit_predict(X)
    clusters, counts = np.unique(labels, return_counts=True)

    print(f"[TRAIN] K={k}, inertia={km.inertia_:,.0f}, iterations={km.n_iter_}")
    for c, cnt in zip(clusters, counts):
        print(f"  Cluster {c}: {cnt:>8,} users ({100*cnt/len(labels):5.1f}%)")
    return km, labels


def save_result(df: pd.DataFrame, labels: np.ndarray, path: str) -> None:
    """保存聚类标签"""
    result = pd.DataFrame({
        "user_id": df["user_id"],
        "cluster": labels.astype(np.int32),
    })
    os.makedirs(os.path.dirname(path), exist_ok=True)
    result.to_parquet(path, index=False)
    print(f"[SAVE] {path} ({len(result):,} rows)")


def main():
    print("=" * 60)
    print(" User Clustering Pipeline")
    print("=" * 60)

    # 1. 加载数据
    df = load_data(FEATURE_PATH)

    # 2. 特征列表
    feature_list = []
    for feats in CLUSTER_FEATURES.values():
        feature_list.extend([f for f in feats if f in df.columns])

    # 3. 数据检查
    X = check_data(df, feature_list)

    # 4. 类别编码
    if "favorite_category" in df.columns:
        encoded = encode_category(df)
        X["favorite_category_freq"] = encoded
        feature_list.append("favorite_category_freq")
        print(f"[FEATURE] Total: {len(feature_list)} features")

    # 5. log1p 变换
    X = apply_log1p(X)

    # 6. 标准化
    X_scaled, scaler = scale_features(X)

    # 7. 搜索最优 K
    search_result = search_optimal_k(X_scaled)
    best_k = search_result["best_k"]

    # 8. 训练 KMeans
    km, labels = train_kmeans(X_scaled, best_k)

    # 9. 保存结果
    save_result(df, labels, RESULT_PATH)

    # 10. 输出聚类概要
    print("\n" + "=" * 60)
    print(" Clustering Complete")
    print(f"  K = {best_k}")
    print(f"  Features = {len(feature_list)}")
    print(f"  Result = {RESULT_PATH}")
    print("=" * 60)


if __name__ == "__main__":
    main()
