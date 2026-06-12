"""
export_for_powerbi.py — Power BI Dashboard 数据导出（单工作簿 v2.0）
================================
职责：将 BI 所需的聚合表合并导出到一个 Excel 工作簿（13 Sheet），
      自动预处理百分比、字段重命名、中文标签、编码修复。

用法:
    python src/export_for_powerbi.py                  # 默认：导出 13 Sheet 到 Excel
    python src/export_for_powerbi.py --force          # 强制覆盖
    python src/export_for_powerbi.py --quiet          # 静默模式
    python src/export_for_powerbi.py --list           # 列出导出清单，不执行

输出:
    exports/user_behavior_dashboard.xlsx  （单工作簿，第1页=_metadata）

预处理规则（自动）:
    - 所有 _pct / _rate 后缀列 ÷ 100 → Power BI 原生百分比格式
    - cart_to_buy_rate → cart_to_buy_action_ratio（避免误解为用户转化率）
    - session_length_group → 中文标签
    - strategies 字段 GBK 乱码修复
    - cohort_date → datetime 类型
    - 新增 day_type_cn 列（weekday_behavior_summary）
    - profiling_summary 过滤为 KPI 行
    - category_conversion → TOP50（高+低各 25）

3 页精简看板:
    Page 1 — 经营概览与转化健康度
    Page 2 — 时段与行为模式分析
    Page 3 — 用户分层与运营策略

依赖:
    pip install pandas openpyxl pyarrow duckdb
"""

import os
import sys
import logging
import argparse
from pathlib import Path
from datetime import datetime

import pandas as pd
import duckdb

# ── 常量 ──────────────────────────────────────────────────
EXCEL_SHEET_NAME_MAX = 31       # Excel sheet 名最大字符数
EXCEL_MAX_ROWS = 1_048_576      # 单 sheet 绝对上限
EXCEL_SAFE_ROWS = 1_000_000     # 安全上限

# ── 路径配置 ──────────────────────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MART_DIR = os.path.join(PROJECT_ROOT, "data", "mart")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "exports")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "user_behavior_dashboard.xlsx")
DB_PATH = os.path.join(PROJECT_ROOT, "data", "analysis.db")
LOG_PATH = os.path.join(PROJECT_ROOT, "experiment_log.md")

# ── 导出清单 ──────────────────────────────────────────────
#   aggregate = 聚合小表，直接导出
#   detail    = 明细大表，仅 --all 模式导出（可能超大）
#   page      = 对应的 Dashboard 页面
# ── 13 Sheet 精简清单（Day 5 改造）───────────────────────────
#   source="parquet"  → 从 data/mart/*.parquet 读取
#   source="duckdb"   → 从 DuckDB 实时查询（表未导出为 parquet）
#   postprocess       → 需要特殊预处理（pct/100、字段改名、中文标签等）
EXPORT_MANIFEST = [
    # Sheet  1: _元数据（手写）
    {"file": "_metadata",                        "type": "handwritten", "desc": "看板说明与指标口径",          "page": "全局"},
    # Sheet  2: dim_date
    {"file": "dim_date",                         "type": "aggregate",   "desc": "日期维度表",                  "page": "全局"},
    # Sheet  3: profiling_kpi（从 profiling_summary 过滤 KPI 行）
    {"file": "profiling_summary",                "type": "aggregate",   "desc": "经营概览 KPI 卡片数据",       "page": "Page 1",
     "postprocess": "profiling_kpi"},
    # Sheet  4: user_conversion
    {"file": "user_conversion_summary",          "type": "aggregate",   "desc": "用户转化渗透率汇总",           "page": "Page 1"},
    # Sheet  5: funnel_summary
    {"file": "funnel_summary",                   "type": "aggregate",   "desc": "行为渗透率 4 阶段",            "page": "Page 1"},
    # Sheet  6: daily_behavior
    {"file": "daily_behavior_summary",           "type": "aggregate",   "desc": "日度 DAU × 购买率趋势",       "page": "Page 1/2"},
    # Sheet  7: hourly_behavior
    {"file": "hourly_behavior_summary",          "type": "aggregate",   "desc": "24 小时流量 × 购买率分布",     "page": "Page 2"},
    # Sheet  8: weekday_compare
    {"file": "weekday_behavior_summary",         "type": "aggregate",   "desc": "周末 vs 工作日对比",           "page": "Page 2",
     "postprocess": "weekday_cn"},
    # Sheet  9: session_stats
    {"file": "session_stats",                    "type": "aggregate",   "desc": "Session 深度 × 购买率阶梯",    "page": "Page 2",
     "postprocess": "session_cn"},
    # Sheet 10: user_segment（规则分层，DuckDB 直查 segment_summary）
    {"file": "segment_summary",                  "type": "aggregate",   "desc": "5 层规则分层（P0-P3+REF）",     "page": "Page 3",
     "source": "duckdb"},
    # Sheet 11: user_cluster
    {"file": "user_cluster_summary",             "type": "aggregate",   "desc": "KMeans 5 聚类画像",            "page": "Page 3",
     "postprocess": "cluster_fix"},
    # Sheet 12: cohort_retention
    {"file": "cohort_retention_summary",         "type": "aggregate",   "desc": "短周期回访衰减曲线 (D0-D8)",    "page": "Page 2"},
    # Sheet 13: category_top50
    {"file": "category_conversion",              "type": "aggregate",   "desc": "类目转化 Top50（高+低各 25）",  "page": "Page 2",
     "postprocess": "category_top50"},
]

# ── dashboard_metadata 内容 ────────────────────────────────
# 用于工作簿第 1 个 Sheet，服务于 Power BI 开发说明和项目交接
# ── _metadata 内容（3 页精简看板说明）─────────────────────────
DASHBOARD_METADATA = [
    {
        "page_name": "Page 1 — 经营概览与转化健康度",
        "question": "平台整体流量质量怎样？转化卡在哪里？",
        "kpi_cards": "总用户 28.7 万 · 用户购买率 67.97% · 行为购买率 2.01%",
        "charts": (
            "1) DAU 日趋势 + 购买率双轴折线，标注周末底色；"
            "2) 行为类型占比横条图（PV 89.5% / CART 5.4% / FAV 3.1% / BUY 2.0%）；"
            "3) 4 阶段行为渗透率条形漏斗"
        ),
        "insight": "用户路径以'浏览→加购→购买'为主，收藏不是必要环节。优化重点：加购未购转化，而非提升收藏率。",
        "primary_tables": "profiling_summary, user_conversion_summary, funnel_summary, daily_behavior_summary",
    },
    {
        "page_name": "Page 2 — 时段与行为模式分析",
        "question": "什么时候用户更愿意买？Session 深度如何影响转化？",
        "kpi_cards": "购买率峰值 10:00 (2.62%) · 流量峰值 21:00 (1.73%) · 周末 DAU +16% 但购买率 -10%",
        "charts": (
            "1) 24h 流量柱 + 购买率折线双轴，标注 10:00/21:00；"
            "2) 工作日 vs 周末分组柱状图（DAU/购买率/加购率）；"
            "3) Session 长度 × 购买率阶梯折线（1→5→6-20→21-50→50+次）；"
            "4) 类目转化 TOP50 对比"
        ),
        "insight": "促销 Push 应在 9:30 推送（购买率高峰前）。前 5 个推荐位必须命中兴趣——突破 6 次行为后购买率从 7.5% 翻倍至 13.0%。",
        "primary_tables": "hourly_behavior_summary, weekday_behavior_summary, session_stats, cohort_retention_summary, category_conversion",
    },
    {
        "page_name": "Page 3 — 用户分层与运营策略",
        "question": "4 类运营人群各有多少？优先触达谁、怎么触达？",
        "kpi_cards": "加购未购 6.1 万 (P1) · 高浏览弱购买 3,321 (P2) · 重复购买 12.9 万 (P0)",
        "charts": (
            "1) 用户分层气泡图（X: 人均 PV / Y: 购买率 / 气泡大小: 人数，P0-P3+REF）；"
            "2) KMeans 5 聚类分组柱状图（购买率/人均 PV/活跃天数对比）；"
            "3) 策略卡片（P1: 加购 48h 限时券 / P2: 首单券+品类收窄 / P0: 关联推荐）"
        ),
        "insight": "最高优先级：P1（6.1万加购未购），加购后 48h 内发限时折扣券；P2（高浏览弱购买）用首单券撬动，触达时机在浏览峰值时段。",
        "primary_tables": "segment_summary, user_cluster_summary",
    },
]


# ── 中文标签映射 ────────────────────────────────────────────
SESSION_LENGTH_CN = {
    "1次":   "1次",
    "2-5次":  "2-5次",
    "6-20次": "6-20次",
    "21-50次":"21-50次",
    "50+次":  "50+次",
    # 英文 fallback
    "1 action":      "1次",
    "2-5 actions":   "2-5次",
    "6-20 actions":  "6-20次",
    "21-50 actions": "21-50次",
    "50+ actions":   "50+次",
}

# KMeans 中文映射（从独立 UTF-8 文件导入，避免 GBK 编码污染）
import importlib.util
_cn_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cluster_labels_cn.py")
_cn_spec = importlib.util.spec_from_file_location("cluster_labels_cn", _cn_path)
_cn_mod = importlib.util.module_from_spec(_cn_spec)
_cn_spec.loader.exec_module(_cn_mod)
CLUSTER_STRATEGIES_CN = _cn_mod.CLUSTER_STRATEGIES_CN
CLUSTER_CHANNEL_CN = _cn_mod.CLUSTER_CHANNEL_CN
CLUSTER_PERSONA_CN = _cn_mod.CLUSTER_PERSONA_CN

# profiling_summary 中保留为 KPI 卡片的 metric 列表
PROFILING_KPI_METRICS = [
    "total_users", "total_rows", "buy_uv", "buy_pct", "cart_uv",
    "fav_uv", "pv_uv", "pv_pct", "cart_pct", "fav_pct",
    "date_range", "total_items", "total_categories",
]

# ── 预处理函数 ──────────────────────────────────────────────
def _pct_cols_to_decimal(df: pd.DataFrame) -> pd.DataFrame:
    """将所有 _pct / _rate 后缀列从百分数（39.62）转为小数（0.3962）。"""
    df = df.copy()
    for col in df.columns:
        if col.endswith("_pct") or col.endswith("_rate"):
            # 跳过已 <1 的值（已转换过）和非数值列
            try:
                if pd.api.types.is_numeric_dtype(df[col]):
                    sample = df[col].dropna().head(5)
                    if len(sample) > 0 and sample.max() > 1.0:
                        df[col] = df[col] / 100.0
            except (ValueError, TypeError):
                pass
    return df


def postprocess_profiling_kpi(df: pd.DataFrame) -> pd.DataFrame:
    """过滤 profiling_summary 为 KPI 卡片行，新增 value_type 列。"""
    df = df.copy()
    # 标记 value_type
    numeric_metrics = [
        "total_users", "total_rows", "buy_cnt", "buy_uv", "cart_cnt", "cart_uv",
        "fav_cnt", "fav_uv", "pv_cnt", "pv_uv", "total_items", "total_categories",
    ]
    pct_metrics = ["buy_pct", "cart_pct", "fav_pct", "pv_pct"]
    other_metrics = ["date_range", "ts_min", "ts_max"]

    def _classify(m):
        if m in numeric_metrics:
            return "count"
        if m in pct_metrics:
            return "pct"
        if m in other_metrics:
            return "label"
        if m.startswith("user_actions_p"):
            return "percentile"
        return "other"

    df["value_type"] = df["metric"].apply(_classify)
    # 只保留 KPI 相关行
    keep_metrics = PROFILING_KPI_METRICS + [
        m for m in df["metric"].unique()
        if m.startswith("user_actions_p50") or m.startswith("user_actions_p75")
    ]
    keep_metrics = [m for m in keep_metrics if m in df["metric"].values]
    df = df[df["metric"].isin(keep_metrics)].reset_index(drop=True)

    # 百分比值转小数
    for idx, row in df.iterrows():
        if row["value_type"] == "pct":
            try:
                df.at[idx, "value"] = float(row["value"]) / 100.0
            except (ValueError, TypeError):
                pass
    return df


def postprocess_weekday_cn(df: pd.DataFrame) -> pd.DataFrame:
    """新增 day_type_cn 列。"""
    df = df.copy()
    cn_map = {0: "工作日", 1: "周末"}
    # 尝试匹配 is_weekend 列或 day_type 列
    if "is_weekend" in df.columns:
        df["day_type_cn"] = df["is_weekend"].map(cn_map).fillna("未知")
    elif "day_type" in df.columns:
        # 如果已经是中文则保留
        already_cn = df["day_type"].isin(["工作日", "周末"]).all()
        if not already_cn:
            df["day_type_cn"] = df["day_type"].map(
                {"工作日": "工作日", "周末": "周末"}
            ).fillna(df["day_type"])
        else:
            df["day_type_cn"] = df["day_type"]
    return df


def postprocess_session_cn(df: pd.DataFrame) -> pd.DataFrame:
    """session_length_group 转为中文标签。"""
    df = df.copy()
    if "session_length_group" in df.columns:
        df["session_length_group"] = df["session_length_group"].map(
            SESSION_LENGTH_CN
        ).fillna(df["session_length_group"])
    return df


def postprocess_cluster_fix(df: pd.DataFrame) -> pd.DataFrame:
    """修复 user_cluster_summary 的 GBK 编码和字段命名。"""
    df = df.copy()
    # 1. 删除 icon 列（Power BI 无法渲染 emoji）
    if "icon" in df.columns:
        df = df.drop(columns=["icon"])
    # 2. cart_to_buy_rate → cart_to_buy_action_ratio
    if "cart_to_buy_rate" in df.columns:
        df = df.rename(columns={"cart_to_buy_rate": "cart_to_buy_action_ratio"})
    # 3. persona_name GBK 乱码修复
    if "persona_name" in df.columns:
        df["persona_name"] = df["cluster"].map(CLUSTER_PERSONA_CN).fillna(df["persona_name"])
    # 4. strategies 乱码修复
    if "strategies" in df.columns:
        df["strategies"] = df["cluster"].map(CLUSTER_STRATEGIES_CN).fillna(df["strategies"])
    # 5. channel 乱码修复
    if "channel" in df.columns:
        df["channel"] = df["cluster"].map(CLUSTER_CHANNEL_CN).fillna(df["channel"])
    return df


def postprocess_category_top50(df: pd.DataFrame) -> pd.DataFrame:
    """只保留转化率最高 25 + 最低 25 个类目（共 50 行）。"""
    df = df.copy()
    if "buy_rate_pct" not in df.columns or len(df) <= 50:
        return df
    # 只保留有购买的类目
    df_with_buy = df[df["buy_cnt"] > 0].copy()
    if len(df_with_buy) < 50:
        return df_with_buy
    top25 = df_with_buy.nlargest(25, "buy_rate_pct")
    bottom25 = df_with_buy.nsmallest(25, "buy_rate_pct")
    result = pd.concat([top25, bottom25]).drop_duplicates(subset=["category_id"])
    return result.reset_index(drop=True)


# 后处理注册表
POSTPROCESS_REGISTRY = {
    "profiling_kpi":   postprocess_profiling_kpi,
    "weekday_cn":      postprocess_weekday_cn,
    "session_cn":      postprocess_session_cn,
    "cluster_fix":     postprocess_cluster_fix,
    "category_top50":  postprocess_category_top50,
}
def setup_logging(quiet: bool = False) -> logging.Logger:
    logger = logging.getLogger("export_for_powerbi")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.WARNING if quiet else logging.INFO)

    file_handler = logging.FileHandler(LOG_PATH, mode="a", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console.setFormatter(fmt)
    file_handler.setFormatter(fmt)

    logger.addHandler(console)
    logger.addHandler(file_handler)

    return logger


# ── Sheet 名称清洗 ─────────────────────────────────────────
def make_sheet_name(name: str) -> str:
    """将表名转为合法的 Excel Sheet 名称（≤31 字符，无特殊字符）。"""
    # 替换非法字符
    illegal = r'[]:*?/\\'
    for ch in illegal:
        name = name.replace(ch, "_")
    # 截断到 31 字符
    return name[:EXCEL_SHEET_NAME_MAX]


# ── 文件解析 ──────────────────────────────────────────────
def resolve_files(
    manifest: list[dict],
    mart_dir: str,
    include_detail: bool = False,
    db_path: str | None = None,
) -> tuple[list[dict], list[dict], list[dict]]:
    """
    返回 (就绪表列表, 缺失表列表, 跳过的大表列表)。

    include_detail=False 时跳过 type='detail' 的表。
    source="duckdb" 的条目从 DuckDB 实时查询。
    type="handwritten" 的条目跳过文件检查，直接在 main() 中生成。
    """
    mart_path = Path(mart_dir)

    ready: list[dict] = []
    missing: list[dict] = []
    oversized: list[dict] = []

    for entry in manifest:
        # 手写表：跳过文件检查
        if entry.get("type") == "handwritten":
            entry["_rows"] = len(DASHBOARD_METADATA)
            entry["_df"] = pd.DataFrame(DASHBOARD_METADATA)
            ready.append(entry)
            continue

        # DuckDB 直查
        if entry.get("source") == "duckdb":
            if not db_path or not os.path.exists(db_path):
                entry["_reason"] = "DB not found"
                missing.append(entry)
                continue
            try:
                con = duckdb.connect(db_path)
                table_name = entry["file"]
                df = con.execute(
                    f'SELECT * FROM "{table_name}"'
                ).fetchdf()
                con.close()
                rows = len(df)
                entry["_rows"] = rows
                entry["_df"] = df
                ready.append(entry)
            except Exception as e:
                entry["_reason"] = f"duckdb error: {e}"
                missing.append(entry)
            continue

        # Parquet 文件
        filepath = mart_path / f"{entry['file']}.parquet"

        if not filepath.exists():
            entry["_reason"] = "file missing"
            missing.append(entry)
            continue

        if entry["type"] == "detail" and not include_detail:
            entry["_reason"] = "detail table (use --all to include)"
            oversized.append(entry)
            continue

        try:
            df = pd.read_parquet(filepath)
            rows = len(df)
            entry["_rows"] = rows
        except Exception:
            entry["_reason"] = "read error"
            missing.append(entry)
            continue

        if rows > EXCEL_SAFE_ROWS:
            entry["_reason"] = f"too large ({rows:,} rows > {EXCEL_SAFE_ROWS:,})"
            oversized.append(entry)
            continue

        entry["_df"] = df
        entry["_path"] = filepath
        ready.append(entry)

    return ready, missing, oversized


# ── 类型适配 ──────────────────────────────────────────────
def prepare_for_excel(df: pd.DataFrame) -> pd.DataFrame:
    """将 DataFrame 字段适配为 Excel 兼容格式，并做百分比转换。"""
    df = df.copy()

    # 1. 百分比列 ÷ 100 → Power BI 原生格式
    df = _pct_cols_to_decimal(df)

    # 2. 类型适配
    for col in df.columns:
        dtype = df[col].dtype
        if isinstance(dtype, pd.DatetimeTZDtype):
            df[col] = df[col].dt.tz_localize(None)
        elif pd.api.types.is_datetime64_any_dtype(dtype):
            pass  # 保持 datetime64
        elif isinstance(dtype, pd.CategoricalDtype):
            df[col] = df[col].astype(str)
    return df


# ── 主流程 ────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Export BI dashboard tables to a single Excel workbook",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="include detail tables (item_conversion, user_cluster_result)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="force overwrite existing output file",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="reduce console output",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="list all tables in manifest, then exit",
    )
    parser.add_argument(
        "--input-dir",
        type=str,
        default=None,
        metavar="DIR",
        help=f"custom input dir (default: {MART_DIR})",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        metavar="FILE",
        help=f"custom output file path (default: {OUTPUT_FILE})",
    )
    args = parser.parse_args()

    mart_dir = args.input_dir or MART_DIR
    output_path = args.output or OUTPUT_FILE

    logger = setup_logging(quiet=args.quiet)
    start_time = datetime.now()

    # ── --list ──
    if args.list:
        print()
        print("=" * 80)
        print(" Power BI Dashboard — 13 Sheet 导出清单 (v2.0)")
        print("=" * 80)
        print(f"  {'Sheet':38s} {'来源':12s} {'行数':>9s}  {'说明'}")
        print(f"  {'-'*38}  {'-'*12}  {'-'*9}  {'-'*25}")
        for i, entry in enumerate(EXPORT_MANIFEST, 1):
            source = entry.get("source", "parquet")
            if entry.get("type") == "handwritten":
                status = "   (手写)"
            elif source == "duckdb":
                status = " (DuckDB)"
            elif (Path(mart_dir) / f"{entry['file']}.parquet").exists():
                try:
                    df = pd.read_parquet(Path(mart_dir) / f"{entry['file']}.parquet")
                    status = f"{len(df):>9,}"
                except Exception:
                    status = f"{'ERR':>9}"
            else:
                status = f"{'MISS':>9}"
            pp = f" [后处理:{entry['postprocess']}]" if entry.get("postprocess") else ""
            print(f"  {entry['file']:38s} {source:12s} {status}  {entry['desc']}{pp}")
        print("=" * 80)
        print()
        return

    # ── 头部打印 ──
    logger.info(f"export_for_powerbi.py v2.0 start — {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"input : {mart_dir}")
    logger.info(f"output: {output_path}")
    logger.info(f"db    : {DB_PATH}")

    if not args.quiet:
        print("=" * 60)
        print(" Power BI Dashboard Export v2.0")
        print(f" input : {mart_dir}")
        print(f" output: {output_path}")
        print("=" * 60)

    # ── 1. 解析清单 ──
    try:
        ready_entries, missing_entries, oversized_entries = resolve_files(
            EXPORT_MANIFEST, mart_dir, include_detail=False, db_path=DB_PATH,
        )
    except FileNotFoundError as e:
        logger.error(str(e))
        print(f"\n[error] {e}")
        sys.exit(1)

    if not ready_entries:
        print("\n[error] no exportable tables found")
        sys.exit(1)

    logger.info(f"manifest: {len(EXPORT_MANIFEST)} tables, "
                f"{len(ready_entries)} ready, "
                f"{len(missing_entries)} missing, "
                f"{len(oversized_entries)} oversized")

    if not args.quiet:
        print(f"\nManifest:  {len(EXPORT_MANIFEST)} tables defined")
        print(f"Exporting: {len(ready_entries)} sheets")
        if missing_entries:
            print(f"Missing:   {len(missing_entries)} files:")
            for m in missing_entries:
                print(f"  ! {m['file']}  ({m['desc']}) — {m.get('_reason', '')}")
        if oversized_entries:
            print(f"Skipped:   {len(oversized_entries)} files:")
            for o in oversized_entries:
                print(f"  - {o['file']}  ({o['desc']}) — {o.get('_reason', '')}")
        print()

    # ── 2. 检查是否已存在 ──
    if not args.force and os.path.exists(output_path):
        src_mtime = max(
            (e.get("_path", Path()).stat().st_mtime
             for e in ready_entries if "_path" in e and e.get("_path")),
            default=0,
        )
        if src_mtime > 0 and os.path.getmtime(output_path) > src_mtime:
            if not args.quiet:
                print(f"[SKIP] {output_path} is up-to-date. Use --force to overwrite.")
            logger.info("output up-to-date, skipped")
            return

    # ── 3. 创建输出目录 ──
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # ── 4. 写入工作簿 ──
    if not args.quiet:
        print(f"Writing to {output_path} ...")
        print()

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:

        # ── 4a. 第 1 个 Sheet：_metadata（3 页看板说明）──
        meta_df = pd.DataFrame(DASHBOARD_METADATA)
        meta_df.to_excel(writer, sheet_name="_metadata", index=False)
        if not args.quiet:
            print(f"  [ 1] _metadata  ({len(meta_df)} rows — 3 页看板说明)")

        # ── 4b. 后续 Sheet：每个表一个（跳过 handwritten 类型）──
        sheet_count = 1
        skipped_in_write = 0

        for i, entry in enumerate(ready_entries, 1):
            # 跳过 _metadata（已在 4a 写入）
            if entry.get("type") == "handwritten":
                continue

            sheet_name = make_sheet_name(entry["file"])
            df = entry.get("_df")
            if df is None:
                try:
                    df = pd.read_parquet(entry["_path"])
                except Exception as e:
                    logger.error(f"read failed {entry['file']}: {e}")
                    if not args.quiet:
                        print(f"  [{i+1:>2}] {entry['file']}  [FAIL] read error")
                    skipped_in_write += 1
                    continue

            # ── 后处理 ──
            pp_key = entry.get("postprocess")
            if pp_key and pp_key in POSTPROCESS_REGISTRY:
                try:
                    df = POSTPROCESS_REGISTRY[pp_key](df)
                    if not args.quiet:
                        print(f"  [··] {entry['file']}: applied postprocess '{pp_key}' "
                              f"→ {len(df)} rows")
                except Exception as e:
                    logger.error(f"postprocess failed {entry['file']}[{pp_key}]: {e}")
                    if not args.quiet:
                        print(f"  [!!] postprocess '{pp_key}' error: {e}")

            rows = len(df)

            if rows > EXCEL_SAFE_ROWS:
                logger.warning(f"skip {entry['file']}: {rows:,} rows exceeds safe limit")
                if not args.quiet:
                    print(f"  [{i+1:>2}] {entry['file']}  [SKIP] {rows:,} rows > {EXCEL_SAFE_ROWS:,}")
                skipped_in_write += 1
                continue

            # 类型适配 + 百分比转换
            try:
                df = prepare_for_excel(df)
            except Exception as e:
                logger.error(f"dtype conversion failed {entry['file']}: {e}")

            # 写入
            try:
                df.to_excel(writer, sheet_name=sheet_name, index=False)
                sheet_count += 1
                if not args.quiet:
                    pp_note = f" [{entry.get('postprocess', '')}]" if entry.get("postprocess") else ""
                    print(f"  [{sheet_count:>2}] {sheet_name:31s}  {rows:>10,} rows  ({entry['desc']}){pp_note}")
            except Exception as e:
                logger.error(f"write failed {entry['file']}: {e}")
                if not args.quiet:
                    print(f"  [{i+1:>2}] {entry['file']}  [FAIL] {e}")
                skipped_in_write += 1
                continue

    # ── 5. 打印最终信息 ──
    output_size_mb = os.path.getsize(output_path) / (1024 * 1024)
    elapsed = (datetime.now() - start_time).total_seconds()

    print()
    print("=" * 60)
    print(f" Exported {sheet_count} sheets to: {output_path}")
    print(f"   Size: {output_size_mb:.1f} MB  |  Elapsed: {elapsed:.1f}s")
    if skipped_in_write:
        print(f"   Skipped during write: {skipped_in_write}")
    if oversized_entries:
        print(f"   Not exported (use --all for detail tables):")
        for o in oversized_entries:
            print(f"     - {o['file']}.parquet ({o.get('_reason', '')})")
    print("=" * 60)

    logger.info(
        f"export done — {sheet_count} sheets -> {output_path} "
        f"({output_size_mb:.1f} MB, {elapsed:.1f}s)"
    )


if __name__ == "__main__":
    main()
