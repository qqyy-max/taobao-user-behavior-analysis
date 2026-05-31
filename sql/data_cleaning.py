"""
淘宝用户行为数据 — DuckDB 数据预览与清洗入口

用法:
    python sql/data_cleaning.py preview     # 仅预览
    python sql/data_cleaning.py clean       # 仅清洗
    python sql/data_cleaning.py all         # 预览 + 清洗（默认）

输出：
    data/clean_data.csv       — 清洗后 CSV (2.5 GB)
    data/clean_data.parquet   — 清洗后 Parquet (337 MB, ZSTD)
    → 作为 00_init.sql 的数据源
"""

import sys
import pandas as pd
import duckdb


SQL_DIR = "sql"
DATA_DIR = "data"


def run_sql_file(con: duckdb.DuckDBPyConnection, path: str) -> None:
    """按语句逐条执行 SQL 文件，每条结果即时输出。"""
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # 按分号切分，过滤空语句和纯注释块
    statements = []
    for s in content.split(";"):
        s = s.strip()
        if not s:
            continue
        # 去掉纯注释行后如果为空则跳过
        code_lines = [l for l in s.split("\n") if l.strip() and not l.strip().startswith("--")]
        if not code_lines:
            continue
        statements.append(s)

    for i, stmt in enumerate(statements):
        print(f"\n{'='*60}")
        print(f"[执行] {path}  [{i+1}/{len(statements)}]")
        print(f"{'='*60}")
        try:
            result = con.execute(stmt)
            if result.description:
                df = result.fetchdf()
                pd.set_option("display.max_columns", 20)
                pd.set_option("display.width", 200)
                pd.set_option("display.max_rows", 60)
                print(df.to_string(index=False))
            else:
                print("(执行完毕，无返回值)")
        except Exception as e:
            print(f"[错误] {e}")


def preview(con: duckdb.DuckDBPyConnection) -> None:
    print("\n" + "█"*60)
    print(" 阶段 1：数据预览")
    print("█"*60)
    run_sql_file(con, f"{SQL_DIR}/data_preview.sql")


def clean(con: duckdb.DuckDBPyConnection) -> None:
    print("\n" + "█"*60)
    print(" 阶段 2：数据清洗")
    print("█"*60)
    run_sql_file(con, f"{SQL_DIR}/data_cleaning.sql")


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"

    con = duckdb.connect()
    try:
        if cmd in ("preview", "all"):
            preview(con)
        if cmd in ("clean", "all"):
            clean(con)
    finally:
        con.close()


if __name__ == "__main__":
    main()
