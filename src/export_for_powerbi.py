"""
export_for_powerbi.py — Power BI Dashboard 数据导出（单工作簿）
================================
职责：将 BI 所需的聚合表合并导出到一个 Excel 工作簿，每个表一个 Sheet，
      并在最前面插入 dashboard_metadata Sheet 用于项目交接。

用法:
    python src/export_for_powerbi.py                  # 默认：导出聚合表到单工作簿
    python src/export_for_powerbi.py --all            # 包含明细大表（可能超 Excel 行数限制）
    python src/export_for_powerbi.py --force          # 强制覆盖
    python src/export_for_powerbi.py --quiet          # 静默模式
    python src/export_for_powerbi.py --list           # 列出导出清单，不执行

输出:
    exports/user_behavior_dashboard.xlsx  （单工作簿，第1页=dashboard_metadata）

Sheet 命名规则:
    Excel 限制 31 字符，超出部分截断
    第 1 页: dashboard_metadata
    后续页: 对应的表名（如 funnel_summary, daily_behavior_summary ...）

依赖:
    pip install pandas openpyxl pyarrow
"""

import os
import sys
import logging
import argparse
from pathlib import Path
from datetime import datetime

import pandas as pd

# ── 常量 ──────────────────────────────────────────────────
EXCEL_SHEET_NAME_MAX = 31       # Excel sheet 名最大字符数
EXCEL_MAX_ROWS = 1_048_576      # 单 sheet 绝对上限
EXCEL_SAFE_ROWS = 1_000_000     # 安全上限

# ── 路径配置 ──────────────────────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MART_DIR = os.path.join(PROJECT_ROOT, "data", "mart")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "exports")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "user_behavior_dashboard.xlsx")
LOG_PATH = os.path.join(PROJECT_ROOT, "experiment_log.md")

# ── 导出清单 ──────────────────────────────────────────────
#   aggregate = 聚合小表，直接导出
#   detail    = 明细大表，仅 --all 模式导出（可能超大）
#   page      = 对应的 Dashboard 页面
EXPORT_MANIFEST = [
    # === 维度表 ===
    {"file": "dim_date",                         "type": "aggregate", "desc": "日期维度",                    "page": "全局"},
    {"file": "dim_category",                     "type": "aggregate", "desc": "类目维度",                    "page": "全局"},
    # === Page 1: Executive Overview ===
    {"file": "profiling_summary",                "type": "aggregate", "desc": "数据画像 KPI 汇总",            "page": "Executive Overview"},
    {"file": "user_conversion_summary",          "type": "aggregate", "desc": "用户转化渗透率",               "page": "Executive Overview"},
    # === Page 2: Funnel & Retention ===
    {"file": "funnel_summary",                   "type": "aggregate", "desc": "行为转化漏斗(4阶段)",          "page": "Funnel & Retention"},
    {"file": "funnel_path_detail",               "type": "aggregate", "desc": "多路径Sankey流向(新增)",     "page": "Funnel & Retention"},
    {"file": "cohort_retention_detail",          "type": "aggregate", "desc": "Cohort 留存明细(热力图)",      "page": "Funnel & Retention"},
    {"file": "cohort_retention_summary",         "type": "aggregate", "desc": "留存曲线汇总(D0-D8)",          "page": "Funnel & Retention"},
    # === Page 3: User Behavior ===
    {"file": "daily_behavior_summary",           "type": "aggregate", "desc": "DAU 日度行为趋势",             "page": "User Behavior"},
    {"file": "hourly_behavior_summary",          "type": "aggregate", "desc": "24h 购买vs流量双轴(新增)",   "page": "User Behavior"},
    {"file": "weekday_behavior_summary",         "type": "aggregate", "desc": "周末 vs 工作日对比",           "page": "User Behavior"},
    {"file": "session_stats",                    "type": "aggregate", "desc": "Session 长度×购买率阶梯(替换)","page": "User Behavior"},
    # === Page 4: Product Analysis ===
    {"file": "category_conversion",              "type": "aggregate", "desc": "类目转化排行(8788 类目)",      "page": "Product Analysis"},
    {"file": "high_exposure_low_conversion_items","type": "aggregate", "desc": "高曝光低转化商品(51.3 万件)", "page": "Product Analysis"},
    {"file": "search_direct_by_category",        "type": "aggregate", "desc": "搜索直达商品类目分布(新增)",  "page": "Product Analysis"},
    # === Page 5: User Segmentation ===
    {"file": "user_cluster_summary",             "type": "aggregate", "desc": "KMeans 聚类画像与策略(5 类)",   "page": "User Segmentation"},
    {"file": "user_segment_summary",             "type": "aggregate", "desc": "频次分群汇总",                 "page": "User Segmentation"},
    {"file": "cluster_temporal_profile",         "type": "aggregate", "desc": "分群×周末/工作日偏好(新增)", "page": "User Segmentation"},
    # === 明细大表（仅 --all 模式） ===
    {"file": "item_conversion",                  "type": "detail",    "desc": "商品转化明细(258 万行)",       "page": "Product Analysis"},
    {"file": "user_cluster_result",              "type": "detail",    "desc": "个体用户聚类标签(28.7 万行)",   "page": "User Segmentation"},
]

# ── dashboard_metadata 内容 ────────────────────────────────
# 用于工作簿第 1 个 Sheet，服务于 Power BI 开发说明和项目交接
DASHBOARD_METADATA = [
    {
        "page_name": "Executive Overview",
        "description": (
            "高管概览页。展示平台核心健康度：总用户 28.7 万、整体购买率 67.97%(用户维度)、"
            "行为→购买 2.01%(行为维度)。4 个核心图表：转化漏斗(概览)、DAU 双轴趋势、"
            "留存衰减曲线、用户分群概览。回答: 平台整体健康度如何。"
        ),
        "primary_tables": "profiling_summary, user_conversion_summary, funnel_summary, daily_behavior_summary, cohort_retention_summary, user_cluster_summary",
    },
    {
        "page_name": "Funnel & Retention",
        "description": (
            "漏斗与留存诊断页。定位转化链断裂点：PV→FAV 流失 60.2%(核心瓶颈)、"
            "FAV→CART 流失 24.7%、CART→BUY 流失 31.7%。Cohort 留存热力图 + "
            "留存衰减曲线揭示：D1 留存仅 53%，D7 骤降至 7.6%，前 3 天为激活黄金窗口。"
            "回答: 用户在哪个环节流失、为什么流失。"
        ),
        "primary_tables": "funnel_summary, funnel_path_detail, user_conversion_summary, cohort_retention_detail, cohort_retention_summary",
    },
    {
        "page_name": "User Behavior",
        "description": (
            "用户行为分析页。从时间维度揭示行为规律：日均 DAU ~2.5 万、周末 DAU +122%、"
            "活跃峰值 20-22 点。68% Session 仅 1-5 个行为——突破'5 行为冷漠期'是提升转化的关键。"
            "回答: 用户什么时候活跃、行为模式如何影响转化。"
        ),
        "primary_tables": "daily_behavior_summary, hourly_behavior_summary, weekday_behavior_summary, session_stats",
    },
    {
        "page_name": "Product Analysis",
        "description": (
            "商品与类目分析页。诊断流量分配效率：8,788 个类目的波士顿矩阵(曝光 vs 转化)、"
            "51.3 万件高曝光低转化问题商品(PV≥P75 且 购买率≤中位数)。"
            "识别被低估的高转化类目和曝光的资源浪费。预计优化推荐权重可提升整体转化率 5-10%。"
            "回答: 哪些商品在浪费流量、高转化商品是否获得足够曝光。"
        ),
        "primary_tables": "category_conversion, high_exposure_low_conversion_items, search_direct_by_category, item_conversion",
    },
    {
        "page_name": "User Segmentation",
        "description": (
            "用户分群与运营策略页。基于 KMeans(K=5) 将 28.7 万用户分 5 类："
            "C2 核心高价值(20.1%, 购买率 9.4%)、C1 高价值(11.1%, 5.2%)、"
            "C4 潜力转化(19.2%, 4.2%)、C0 探索型浏览(20.3%, 2.0%)、"
            "C3 高浏览低转化(29.3%, 0.8%)。每群配有运营策略、触达渠道、KPI 目标。"
            "回答: 哪类用户最值得运营、采取什么策略提升 GMV。"
        ),
        "primary_tables": "user_cluster_summary, user_segment_summary, cluster_temporal_profile, user_cluster_result",
    },
]


# ── 日志配置 ──────────────────────────────────────────────
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
) -> tuple[list[dict], list[dict], list[dict]]:
    """
    返回 (就绪表列表, 缺失表列表, 跳过的大表列表)。

    include_detail=False 时跳过 type='detail' 的表。
    检查行数，超过 EXCEL_SAFE_ROWS 的表标记为超大并跳过。
    """
    mart_path = Path(mart_dir)
    if not mart_path.exists():
        raise FileNotFoundError(f"mart dir not found: {mart_dir}")

    ready: list[dict] = []
    missing: list[dict] = []
    oversized: list[dict] = []

    for entry in manifest:
        filepath = mart_path / f"{entry['file']}.parquet"

        # 检查文件是否存在
        if not filepath.exists():
            entry["_reason"] = "file missing"
            missing.append(entry)
            continue

        # 明细表 + 未开 --all → 跳过
        if entry["type"] == "detail" and not include_detail:
            entry["_reason"] = "detail table (use --all to include)"
            oversized.append(entry)
            continue

        # 检查行数
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

        # 预读 DataFrame 缓存
        entry["_df"] = df
        entry["_path"] = filepath
        ready.append(entry)

    return ready, missing, oversized


# ── 类型适配 ──────────────────────────────────────────────
def prepare_for_excel(df: pd.DataFrame) -> pd.DataFrame:
    """将 DataFrame 字段适配为 Excel 兼容格式。"""
    df = df.copy()
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
        print(" Power BI Dashboard — 导出清单")
        print("=" * 80)
        print(f"  {'文件':48s} {'类型':10s} {'行数':>9s}  {'Dashboard 页面'}")
        print(f"  {'-'*48}  {'-'*10}  {'-'*9}  {'-'*20}")
        for entry in EXPORT_MANIFEST:
            filepath = Path(mart_dir) / f"{entry['file']}.parquet"
            type_tag = entry["type"]
            if filepath.exists():
                try:
                    df = pd.read_parquet(filepath)
                    rows = len(df)
                except Exception:
                    rows = -1
                status = f"{rows:>9,}" if rows >= 0 else f"{'ERR':>9}"
            else:
                status = f"{'MISS':>9}"
            note = ""
            if entry["type"] == "detail" and not args.all:
                note = "  [use --all]"
            print(f"  {entry['file']+'.parquet':48s} {type_tag:10s} {status}  {entry['page']}{note}")
        print("=" * 80)
        print()
        return

    # ── 头部打印 ──
    logger.info(f"export_for_powerbi.py start — {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"input : {mart_dir}")
    logger.info(f"output: {output_path}")
    logger.info(f"detail: {'included' if args.all else 'excluded (use --all)'}")

    if not args.quiet:
        print("=" * 60)
        print(" Power BI Dashboard Export")
        print(f" input : {mart_dir}")
        print(f" output: {output_path}")
        print(f" detail: {'included' if args.all else 'excluded'}")
        print("=" * 60)

    # ── 1. 解析清单 ──
    try:
        ready_entries, missing_entries, oversized_entries = resolve_files(
            EXPORT_MANIFEST, mart_dir, include_detail=args.all
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
                print(f"  ! {m['file']}.parquet  ({m['desc']}) — {m.get('_reason', '')}")
        if oversized_entries:
            print(f"Skipped:   {len(oversized_entries)} files (too large or detail):")
            for o in oversized_entries:
                print(f"  - {o['file']}.parquet  ({o['desc']}) — {o.get('_reason', '')}")
        print()

    # ── 2. 检查是否已存在 ──
    if not args.force and os.path.exists(output_path):
        src_mtime = max(
            (e["_path"].stat().st_mtime for e in ready_entries if "_path" in e),
            default=0,
        )
        if os.path.getmtime(output_path) > src_mtime:
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

        # ── 4a. 第 1 个 Sheet：dashboard_metadata ──
        meta_df = pd.DataFrame(DASHBOARD_METADATA)
        meta_df.to_excel(writer, sheet_name="dashboard_metadata", index=False)
        if not args.quiet:
            print(f"  [ 1] dashboard_metadata  ({len(meta_df)} rows)")

        # ── 4b. 后续 Sheet：每个表一个 ──
        sheet_count = 1  # 已写入 metadata
        skipped_in_write = 0

        for i, entry in enumerate(ready_entries, 1):
            sheet_name = make_sheet_name(entry["file"])
            df = entry.get("_df")
            if df is None:
                # 未预读，现读
                try:
                    df = pd.read_parquet(entry["_path"])
                except Exception as e:
                    logger.error(f"read failed {entry['file']}: {e}")
                    if not args.quiet:
                        print(f"  [{i+1:>2}] {entry['file']}  [FAIL] read error")
                    skipped_in_write += 1
                    continue

            rows = len(df)

            # 二次检查行数
            if rows > EXCEL_SAFE_ROWS:
                logger.warning(f"skip {entry['file']}: {rows:,} rows exceeds safe limit")
                if not args.quiet:
                    print(f"  [{i+1:>2}] {entry['file']}  [SKIP] {rows:,} rows > {EXCEL_SAFE_ROWS:,}")
                skipped_in_write += 1
                continue

            # 类型适配
            try:
                df = prepare_for_excel(df)
            except Exception as e:
                logger.error(f"dtype conversion failed {entry['file']}: {e}")
                # 非致命

            # 写入
            try:
                df.to_excel(writer, sheet_name=sheet_name, index=False)
                sheet_count += 1
                if not args.quiet:
                    print(f"  [{sheet_count:>2}] {sheet_name:31s}  {rows:>10,} rows  ({entry['desc']})")
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
