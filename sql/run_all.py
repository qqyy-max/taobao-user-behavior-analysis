"""
淘宝用户行为分析 — 全流程 SQL 编排器 (v2.0)
==============================================
按分层顺序执行 8 个 SQL 文件：
  00_init.sql            → 共享基础层（clean 视图 + user_base_metrics）
  01_profiling.sql       → profiling_summary
  02_funnel_retention.sql → funnel_summary, cohort_retention_detail
  03_behavior_analysis.sql → daily/hourly/session 表
  04_product_analysis.sql  → category/item_conversion
  05_user_analysis.sql     → user_profile, user_segment_summary
  06_feature_mart.sql      → user_features (→ Python sklearn)
  07_export_mart.sql       → 统一导出 Parquet (→ Power BI)

用法:
    python sql/run_all.py                      # 全部执行 + 自动导出
    python sql/run_all.py --show-tables        # 列出所有业务表
    python sql/run_all.py --show funnel_summary # 查看指定表内容
    python sql/run_all.py --skip-export        # 跳过导出层
    python sql/run_all.py --step 03            # 仅执行到 03
    python sql/run_all.py --from 04            # 从 04 开始执行（断点续跑）
    python sql/run_all.py --dry-run            # 仅打印执行计划
    python sql/run_all.py --quiet              # 减少输出
"""

import sys
import os
import time
import argparse
import logging
from datetime import datetime
import duckdb

# ── 路径配置 ──────────────────────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SQL_DIR = os.path.join(PROJECT_ROOT, "sql")
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
DB_PATH = os.path.join(DATA_DIR, "analysis.db")
LOG_PATH = os.path.join(PROJECT_ROOT, "experiment_log.md")

# 确保必要目录存在
for d in ["data/mart", "data/features", "data/processed", "data/raw"]:
    os.makedirs(os.path.join(PROJECT_ROOT, d), exist_ok=True)

# ── SQL 文件定义（按执行顺序）───────────────────────────────
SQL_FILES = [
    ("00_init.sql",             "共享基础层"),
    ("01_profiling.sql",        "数据画像层"),
    ("02_funnel_retention.sql", "漏斗 & 留存层"),
    ("03_behavior_analysis.sql","行为分析层"),
    ("04_product_analysis.sql", "商品 & 类目分析层"),
    ("05_user_analysis.sql",    "用户分析层"),
    ("06_feature_mart.sql",     "特征宽表层 (→ Python)"),
    ("07_export_mart.sql",      "统一导出层 (→ Power BI)"),
]

# 各 SQL 文件的输出表（用于依赖验证）
EXPECTED_TABLES = {
    "00_init.sql":             ["dim_date", "user_base_metrics", "category_base_stats"],
    "01_profiling.sql":        ["profiling_summary"],
    "02_funnel_retention.sql": ["funnel_summary", "user_conversion_summary",
                                 "cohort_retention_detail", "cohort_retention_summary"],
    "03_behavior_analysis.sql":["daily_behavior_summary", "hourly_behavior_summary",
                                 "weekday_behavior_summary", "session_summary", "session_stats"],
    "04_product_analysis.sql": ["category_conversion", "item_conversion",
                                 "high_exposure_low_conversion_items"],
    "05_user_analysis.sql":    ["user_profile", "user_frequency_segment", "user_segment_summary"],
    "06_feature_mart.sql":     ["user_features"],
    "07_export_mart.sql":      [],  # 导出层，不创建表
}


# ── 日志配置 ──────────────────────────────────────────────
def setup_logging(quiet: bool = False):
    """配置双通道日志：控制台 + experiment_log.md"""
    logger = logging.getLogger("run_all")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    # 控制台 handler
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.WARNING if quiet else logging.INFO)

    # 文件 handler（追加模式）
    file_handler = logging.FileHandler(LOG_PATH, mode="a", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)

    fmt = logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    console.setFormatter(fmt)
    file_handler.setFormatter(fmt)

    logger.addHandler(console)
    logger.addHandler(file_handler)
    return logger


# ── SQL 解析 ──────────────────────────────────────────────
def parse_statements(content: str) -> list:
    """将 SQL 文件内容按分号拆分为独立语句，过滤纯注释块和空语句。"""
    statements = []
    for s in content.split(";"):
        s = s.strip()
        if not s:
            continue
        code_lines = [
            l for l in s.split("\n")
            if l.strip() and not l.strip().startswith("--")
        ]
        if not code_lines:
            continue
        statements.append(s)
    return statements


# ── 表格渲染 ──────────────────────────────────────────────
def _format_table(result, max_rows: int = 30) -> str:
    """将 DuckDB 查询结果格式化为对齐的表格字符串。"""
    if not result.description:
        return ""

    col_names = [d[0] for d in result.description]
    rows = result.fetchmany(max_rows + 1)
    if not rows:
        return "  (空结果)"

    more = len(rows) > max_rows
    if more:
        rows = rows[:max_rows]

    str_rows = [[str(v) if v is not None else "NULL" for v in row] for row in rows]

    col_widths = [len(c) for c in col_names]
    for row in str_rows:
        for j, val in enumerate(row):
            col_widths[j] = max(col_widths[j], min(len(val), 40))

    def fmt_row(vals):
        cells = []
        for j, v in enumerate(vals):
            if len(v) > 40:
                v = v[:37] + "..."
            cells.append(v.ljust(col_widths[j]))
        return "  | " + " | ".join(cells) + " |"

    lines = [
        fmt_row(col_names),
        "  |-" + "-|-".join("-" * w for w in col_widths) + "-|",
    ]
    for row in str_rows:
        lines.append(fmt_row(row))

    if more:
        lines.append(f"  (仅显示前 {max_rows} 行...)")

    return "\n".join(lines)


# ── SQL 文件执行 ──────────────────────────────────────────
def run_sql_file(
    con: duckdb.DuckDBPyConnection,
    filename: str,
    label: str,
    verbose: bool = True,
    logger: logging.Logger | None = None,
) -> tuple:
    """
    执行单个 SQL 文件，返回 (success, elapsed_sec, error_message)。
    """
    filepath = os.path.join(SQL_DIR, filename)
    if not os.path.exists(filepath):
        msg = f"文件不存在: {filepath}"
        if logger:
            logger.error(msg)
        return False, 0, msg

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    statements = parse_statements(content)
    if not statements:
        msg = "无有效 SQL 语句"
        if logger:
            logger.warning(f"[{filename}] {msg}")
        return False, 0, msg

    t0 = time.time()
    success_count = 0
    errors = []

    for i, stmt in enumerate(statements, 1):
        try:
            result = con.execute(stmt)
            success_count += 1
            if verbose and result.description:
                table_str = _format_table(result)
                if table_str:
                    print(f"  [结果] 语句 {i}:")
                    print(table_str)
                    print()
        except Exception as e:
            err_msg = f"语句 {i}/{len(statements)} 失败: {str(e)[:150]}"
            errors.append(err_msg)
            if logger:
                logger.error(f"[{filename}] {err_msg}")
            if verbose:
                print(f"  [错误] {err_msg}")

    elapsed = time.time() - t0

    if errors:
        msg = f"{len(errors)}/{len(statements)} 条语句失败"
        if logger:
            logger.error(f"[{filename}] {msg}")
        return False, elapsed, msg

    return True, elapsed, None


# ── 表验证 ────────────────────────────────────────────────
def verify_tables(con: duckdb.DuckDBPyConnection, filename: str, logger: logging.Logger) -> bool:
    """验证 SQL 文件的预期输出表是否已创建。"""
    expected = EXPECTED_TABLES.get(filename, [])
    if not expected:
        return True

    existing = set(
        row[0] for row in
        con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    )
    missing = [t for t in expected if t not in existing]
    if missing:
        logger.warning(f"[{filename}] 缺少预期表: {missing}")
        return False
    return True


# ── 表浏览 ────────────────────────────────────────────────
def show_tables(con: duckdb.DuckDBPyConnection, table_name: str | None = None):
    """列出所有表或显示指定表内容。"""
    tables = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()

    if table_name:
        try:
            result = con.execute(f'SELECT * FROM "{table_name}"')
            table_str = _format_table(result, max_rows=50)
            if table_str:
                print(f"\n[{table_name}]")
                print(table_str)
            row_count = con.execute(
                f'SELECT count(*) FROM "{table_name}"'
            ).fetchone()[0]
            print(f"  总行数: {row_count:,}")
        except Exception as e:
            print(f"[错误] 查询表 {table_name} 失败: {e}")
    else:
        print("\n" + "=" * 70)
        print(" 数据库分析表一览")
        print("=" * 70)
        print(f"  {'表名':<40} {'行数':>12}")
        print("  " + "-" * 54)
        for (name,) in tables:
            try:
                row_count = con.execute(
                    f'SELECT count(*) FROM "{name}"'
                ).fetchone()[0]
            except Exception:
                row_count = "?"
            print(f"  {name:<40} {str(row_count):>12}")
        print("=" * 70)
        print(f"  共 {len(tables)} 张表")
        print("\n  使用 --show <表名> 查看具体表内容")


# ── 主流程 ────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="淘宝用户行为分析 SQL 全流程编排器 v2.0")
    parser.add_argument("--dry-run", action="store_true",
                        help="仅打印执行计划，不实际执行")
    parser.add_argument("--step", type=str, default=None,
                        help="仅执行到指定步骤（如 --step 03）")
    parser.add_argument("--from", dest="from_step", type=str, default=None,
                        help="从指定步骤开始执行，用于断点续跑（如 --from 04）")
    parser.add_argument("--skip-export", action="store_true",
                        help="跳过 07_export_mart 导出层")
    parser.add_argument("--quiet", action="store_true",
                        help="减少输出（不打印 SELECT 结果）")
    parser.add_argument("--no-verify", action="store_true",
                        help="跳过表验证")
    parser.add_argument("--show-tables", action="store_true",
                        help="列出数据库中所有业务表及行数")
    parser.add_argument("--show", type=str, default=None, metavar="TABLE",
                        help="显示指定表内容（如 --show funnel_summary）")
    args = parser.parse_args()

    # ── 日志 ──
    logger = setup_logging(quiet=args.quiet)
    logger.info("=" * 60)
    logger.info(f"run_all.py 启动 — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # ── 数据库路径 ──
    os.chdir(PROJECT_ROOT)

    # ── 浏览模式 ──
    if args.show_tables or args.show:
        if not os.path.exists(DB_PATH):
            print(f"[错误] 数据库不存在: {DB_PATH}\n请先运行 python sql/run_all.py 生成数据。")
            sys.exit(1)
        con = duckdb.connect(DB_PATH)
        try:
            show_tables(con, args.show)
        finally:
            con.close()
        return

    # ── 确定执行列表 ──
    if args.skip_export:
        files_to_run = [(f, l) for f, l in SQL_FILES if not f.startswith("07")]
    else:
        files_to_run = list(SQL_FILES)

    if args.from_step:
        from_num = int(args.from_step)
        files_to_run = [(f, l) for f, l in files_to_run if int(f[:2]) >= from_num]
        if not files_to_run:
            print(f"[错误] 未找到 >= {args.from_step} 的 SQL 文件")
            sys.exit(1)

    if args.step:
        step_num = int(args.step)
        files_to_run = [(f, l) for f, l in files_to_run if int(f[:2]) <= step_num]
        if not files_to_run:
            print(f"[错误] 未找到匹配 --step {args.step} 的 SQL 文件")
            sys.exit(1)

    # ── Dry-run ──
    if args.dry_run:
        print("\n" + "=" * 70)
        print(" DRY RUN — 将按以下顺序执行 SQL 文件:")
        print("=" * 70)
        for i, (filename, label) in enumerate(files_to_run, 1):
            print(f"  {i}. [{filename}] {label}")
        print("=" * 70)
        return

    # ── 执行 ──
    print("\n" + "=" * 70)
    print(" 淘宝用户行为分析 — SQL 分层执行 v2.0")
    print(f" 数据库: {DB_PATH}")
    print(f" 日志:   {LOG_PATH}")
    print("=" * 70)

    con = duckdb.connect(DB_PATH)
    total_start = time.time()
    results = []

    try:
        for i, (filename, label) in enumerate(files_to_run, 1):
            print(f"\n[{i}/{len(files_to_run)}] {filename} — {label}")
            print("-" * 50)
            logger.info(f"[{i}/{len(files_to_run)}] 开始执行 {filename} ({label})")

            success, elapsed, error = run_sql_file(
                con, filename, label, verbose=not args.quiet, logger=logger
            )
            results.append((filename, label, success, elapsed, error))

            if success:
                print(f"  [OK] 完成 ({elapsed:.1f}s)")
                logger.info(f"[{filename}] 成功 ({elapsed:.1f}s)")

                # 验证输出表
                if not args.no_verify:
                    tables_ok = verify_tables(con, filename, logger)
                    if not tables_ok:
                        logger.warning(f"[{filename}] 表验证未通过，继续执行...")
            else:
                print(f"  [FAIL] 失败 ({elapsed:.1f}s): {error}")
                logger.error(f"[{filename}] 失败 ({elapsed:.1f}s): {error}")

                # 00~05 任一层失败中断；06/07 失败不阻断（前面数据已就绪）
                if filename.startswith("06") or filename.startswith("07"):
                    print("  (特征层/导出层失败不影响前序输出，继续...)")
                    logger.warning(f"[{filename}] 非关键层失败，继续执行")
                else:
                    print("\n[中断] 基础层执行失败，请检查数据和 SQL。")
                    logger.critical(f"[{filename}] 基础层失败，流程中断")
                    break

        # ── 汇总报告 ──
        total_elapsed = time.time() - total_start
        print("\n" + "=" * 70)
        print(" 执行汇总")
        print("=" * 70)
        success_count = 0
        fail_count = 0
        for filename, label, success, elapsed, error in results:
            status = "[OK]" if success else "[FAIL]"
            print(f"  {status} [{filename}] {label}  ({elapsed:.1f}s)")
            if error:
                print(f"      错误: {error}")
            if success:
                success_count += 1
            else:
                fail_count += 1
        print("-" * 70)
        print(f"  成功: {success_count} | 失败: {fail_count} | 总耗时: {total_elapsed:.1f}s")
        print("=" * 70)

        logger.info(f"执行完成 — 成功:{success_count} 失败:{fail_count} 总耗时:{total_elapsed:.1f}s")

        # ── 下一步提示 ──
        print("""
下一步:
  * Power BI:  导入 data/mart/*.parquet（13 张表 + 2 张维度表）
  * Python 聚类: df = pd.read_parquet("data/features/user_features.parquet")
  * 查看表:     python sql/run_all.py --show-tables
  * 导出 CSV:   python -c "import duckdb; duckdb.connect('data/analysis.db').execute(
                \\\"COPY <table> TO 'data/<table>.csv' (HEADER true)\\\")"
""")

    finally:
        con.close()
        logger.info("数据库连接已关闭\n")


if __name__ == "__main__":
    main()
