import re
import duckdb
import json
import sys
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use("Agg")
from pathlib import Path

DB_PATH = "data/analysis.db"
FIG_DIR = Path("outputs/figures/agent")
FIG_DIR.mkdir(parents=True, exist_ok=True)

# 动态解析 clean_data.parquet 的绝对路径，避免 CWD 依赖
_ROOT = Path(__file__).parent.parent
CLEAN_DATA_PATH = str(_ROOT / "data" / "clean_data.parquet")

# 注入 agent/ 目录到 sys.path，确保可 import agent.reviewer
_AGENT_DIR = str(_ROOT)
if _AGENT_DIR not in sys.path:
    sys.path.insert(0, _AGENT_DIR)


# ── 原有工具 ──────────────────────────────────────────────

def list_tables() -> str:
    with duckdb.connect(DB_PATH, read_only=True) as con:
        df = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchdf()
    return df.to_json(orient="records", force_ascii=False)


def get_table_schema(table_name: str) -> str:
    try:
        with duckdb.connect(DB_PATH, read_only=True) as con:
            df = con.execute(f"DESCRIBE {table_name}").fetchdf()
        return df.to_json(orient="records", force_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def query_duckdb(sql: str) -> str:
    with duckdb.connect(DB_PATH, read_only=True) as con:
        try:
            df = con.execute(sql).fetchdf()
            if len(df) > 200:
                df = df.head(200)
            return df.to_json(orient="records", force_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)


def plot_bar(title: str, x_col: str, y_col: str, sql: str) -> str:
    """查询数据并生成柱状图，返回文件路径"""
    try:
        with duckdb.connect(DB_PATH, read_only=True) as con:
            df = con.execute(sql).fetchdf()

        fig, ax = plt.subplots(figsize=(10, 5))
        ax.bar(df[x_col].astype(str), df[y_col], color="#4C8BF5", edgecolor="white")
        ax.set_title(title, fontsize=13, fontweight="bold")
        ax.set_xlabel(x_col)
        ax.set_ylabel(y_col)
        fig.tight_layout()

        fname = FIG_DIR / f"{title[:20].replace(' ', '_')}.png"
        fig.savefig(fname, dpi=120)
        plt.close(fig)
        return str(fname)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ── 新增工具 ──────────────────────────────────────────────

def get_business_context() -> str:
    """返回数据库表业务含义、已知结论和 clean_data 字段说明"""
    context = {
        "tables": {
            # ── 漏斗 & 留存 ──────────────────────────────────────
            "funnel_summary": {
                "desc": "转化漏斗汇总：PV→FAV→CART→BUY 各阶段 UV 和转化率（stage/stage_cn/uv/actions/conversion_rate_pct）",
                "use_case": "分析各环节流失率，找断裂点"
            },
            "funnel_path_detail": {
                "desc": "用户实际行为路径流量：path_from/source/target/user_cnt，展示 Sankey 图数据",
                "use_case": "分析非线性漏斗路径（如跳过收藏直接加购的用户数）"
            },
            "user_conversion_summary": {
                "desc": "全量用户转化汇总（注意：不是 user_cluster_summary）：total_users/pv_users/fav_users/cart_users/buy_users 及各行为渗透率",
                "use_case": "获取整体转化漏斗的用户数基准"
            },
            "cohort_retention_detail": {
                "desc": "按首次活跃日期分 Cohort 的留存明细：cohort_date/retention_day/retained_users/total_users/retention_rate_pct",
                "use_case": "分析具体 Cohort 的留存曲线，识别周末周期效应"
            },
            "cohort_retention_summary": {
                "desc": "所有 Cohort 汇总后的平均留存率：retention_day/avg_retention_rate_pct",
                "use_case": "看整体 Day1/Day3/Day7 留存趋势"
            },
            # ── 行为时序 ──────────────────────────────────────────
            "daily_behavior_summary": {
                "desc": "按日期汇总：dt/dau/total_actions/pv_cnt/fav_cnt/cart_cnt/buy_cnt/buy_rate_pct/avg_actions_per_user",
                "use_case": "分析日度趋势、工作日 vs 周末差异"
            },
            "hourly_behavior_summary": {
                "desc": "按小时汇总：hour/actions/pv_cnt/fav_cnt/cart_cnt/buy_cnt/buy_rate_pct/uv",
                "use_case": "找购买率峰值时段，优化 Push 时机"
            },
            "weekday_behavior_summary": {
                "desc": "工作日 vs 周末对比：is_weekend/day_type/day_cnt/avg_dau/avg_buy_rate_pct",
                "use_case": "量化周末流量陷阱"
            },
            # ── Session ───────────────────────────────────────────
            "session_stats": {
                "desc": "按 Session 行为数分组汇总：session_length_group/session_cnt/buy_rate_pct/avg_duration_min",
                "use_case": "分析行为深度与转化率关系，找关键阈值（6 行为临界点）"
            },
            "session_summary": {
                "desc": "每个 Session 明细：session_id/user_id/session_start/session_end/session_duration_min/action_cnt/buy_cnt/cart_cnt/fav_cnt/pv_cnt/has_buy/session_date",
                "use_case": "分析个体 Session 行为序列，找购买前的行为模式"
            },
            # ── 商品 & 类目 ───────────────────────────────────────
            "category_conversion": {
                "desc": "按类目汇总：category_id/pv_cnt/buy_cnt/buy_rate_pct/exposure_rank/conversion_rank",
                "use_case": "找高曝光低转化类目"
            },
            "item_conversion": {
                "desc": "按商品 ID 汇总：item_id/category_id/pv_cnt/buy_cnt/buy_rate_pct/exposure_rank",
                "use_case": "商品级转化分析"
            },
            "high_exposure_low_conversion_items": {
                "desc": "高曝光低转化商品：item_id/category_id/pv_cnt/buy_rate_pct/exposure_conversion_gap",
                "use_case": "量化无效曝光问题商品（51.3 万件）"
            },
            "search_direct_items": {
                "desc": "搜索直达商品（有购买但无 PV 记录的商品）",
                "use_case": "识别搜索直达型商品，应增加搜索曝光"
            },
            "search_direct_by_category": {
                "desc": "按类目汇总的搜索直达商品数量",
                "use_case": "找哪些类目更多通过搜索直达购买"
            },
            # ── 用户画像 & 分群 ────────────────────────────────────
            "user_segment_summary": {
                "desc": "按行为频率分组汇总：freq_group/user_cnt/user_pct/avg_buy_per_user/buyer_rate_pct",
                "use_case": "RFM 风格用户频率分层的整体统计"
            },
            "user_frequency_segment": {
                "desc": "每个用户的频率分组明细：user_id/total_actions/buy_cnt/active_days/freq_group/buyer_group",
                "use_case": "找某个 freq_group 的具体用户 ID，用于 JOIN 其他表"
            },
            "user_profile": {
                "desc": "每个用户的行为汇总画像：user_id/total_actions/pv_cnt/fav_cnt/cart_cnt/buy_cnt/active_days/buy_rate_pct/category_diversity/lifecycle_days/is_buyer等",
                "use_case": "分析个体用户特征，JOIN cluster 数据分析 C0 等群体"
            },
            "user_features": {
                "desc": "用于聚类的 35 维特征宽表：user_id/pv_cnt/buy_rate/cart_to_buy_rate/weekend_ratio/night_ratio/morning_ratio/category_diversity/hour_concentration等",
                "use_case": "分析各 Cluster 的特征差异，JOIN cluster_temporal_profile"
            },
            "cluster_temporal_profile": {
                "desc": "各 Cluster 的时间偏好画像：cluster/user_cnt/avg_weekend_ratio_pct/avg_morning_ratio_pct/avg_afternoon_ratio_pct/avg_evening_ratio_pct/avg_night_ratio_pct/avg_buy_weekend_ratio_pct",
                "use_case": "分析各群体的时段分布，制定精准触达时机"
            },
            # ── 其他 ──────────────────────────────────────────────
            "profiling_summary": {
                "desc": "全局基准指标：metric/metric_cn/value",
                "use_case": "快速获取总用户数、总行为数等全局数字"
            },
            "category_base_stats": {
                "desc": "类目基础统计（中间表）：category_id 级别的基础数据",
                "use_case": "类目分析的基础数据源"
            },
            "user_base_metrics": {
                "desc": "用户基础指标（中间表），被 user_profile/user_features 等引用",
                "use_case": "一般不直接查，通过 user_profile 使用"
            },
            "dim_date": {
                "desc": "日期维度表：dt/year/month/day/weekday/is_weekend",
                "use_case": "日期维度 JOIN"
            }
        },
        "cluster_parquet": {
            "WARNING": (
                "analysis.db 里没有 user_cluster_summary 表！"
                "Cluster 数据在独立 parquet 文件里，必须用 read_parquet 路径查询，不能直接写表名"
            ),
            "user_cluster_result": {
                "path": "data/mart/user_cluster_result.parquet",
                "fields": "user_id(BIGINT) / cluster(INTEGER, 值为0/1/2/3/4)",
                "use_case": "获取每个用户的 cluster 标签，JOIN user_profile 做群体特征分析",
                "sample_sql": (
                    "SELECT cr.cluster, AVG(up.pv_cnt) as avg_pv, AVG(up.buy_rate_pct) as avg_buy_rate, "
                    "AVG(up.category_diversity) as avg_cat_diversity, COUNT(*) as user_cnt "
                    "FROM read_parquet('data/mart/user_cluster_result.parquet') cr "
                    "JOIN user_profile up ON cr.user_id = up.user_id "
                    "GROUP BY cr.cluster ORDER BY cr.cluster"
                )
            },
            "user_cluster_summary": {
                "path": "data/mart/user_cluster_summary.parquet",
                "fields": (
                    "cluster/persona_name/icon/priority/user_cnt/user_pct/buy_rate_pct/"
                    "avg_pv/avg_active_days/avg_lifecycle_days/category_diversity/"
                    "cart_to_buy_rate/recent_7d_pct/weekly_volatility/strategies/channel"
                ),
                "use_case": "直接获取各 Cluster 的画像汇总（buy_rate_pct/avg_pv/category_diversity等）",
                "sample_sql": "SELECT * FROM read_parquet('data/mart/user_cluster_summary.parquet') ORDER BY cluster"
            }
        },
        "known_conclusions": [
            "PV→FAV 流失 60.2%（FAV UV 仅 113,717 vs PV UV 285,815），但这是非线性漏斗——加购 UV 215,167 远超收藏，用户路径以 PV→CART→BUY 为主",
            "Day1 留存 78.8%（最大 Cohort 11/25），Day7 留存 98.5% 是周末周期效应而非真实高留存，9 天窗口无法评估真实长期留存",
            "51.3 万件商品属于高曝光低转化（PV≥P75 且购买率=0%）",
            "C2 购买率 9.4%/人均 PV 71，C0 人均 PV 198 但购买率仅 2.0%，C0 类目广度 43.6 远超其他群体",
            "周末 DAU +16% 但购买率低于工作日（周末以逛为主）",
            "Session 行为数超过 6 个后，购买率从 7.5% 翻倍至 13.0%",
            "购买率峰值在 10:00（2.62%），流量峰值在 21:00——时序错位",
            "20,089 个用户加购未购，是最接近转化的群体",
            "819 名超级用户（0.29%）人均 564 次行为、购买率 81.8%"
        ],
        "clean_data_schema": {
            "path": CLEAN_DATA_PATH,
            "fields": {
                "user_id": "用户 ID（脱敏整数）",
                "item_id": "商品 ID（脱敏整数）",
                "category_id": "类目 ID（脱敏整数）",
                "behavior_type": "行为类型：pv/fav/cart/buy",
                "ts": "Unix 时间戳（秒）",
                "dt": "日期字符串 YYYY-MM-DD",
                "hour": "小时 0-23（整数）",
                "weekday": "星期 0=周一 … 6=周日",
                "is_weekend": "是否周末 True/False"
            },
            "note": "使用 query_raw 查询，SQL 里用 read_parquet('{path}') 作为数据源".format(
                path=CLEAN_DATA_PATH.replace("\\", "/")
            )
        }
    }
    return json.dumps(context, ensure_ascii=False, indent=2)



# 缓存连接对象，避免重复打开与关闭
_RAW_CONN = None

def query_raw(sql: str) -> str:
    """对原始数据执行即席查询。优先连本地 DB_PATH 读带索引物理表，不存在则 fallback 到内存 Parquet 视图"""
    global _RAW_CONN
    try:
        if _RAW_CONN is None:
            try:
                # 尝试连本地持久化数据库以复用物理表与索引
                conn = duckdb.connect(DB_PATH, read_only=True)
                conn.execute("SELECT 1 FROM clean LIMIT 1")
                _RAW_CONN = conn
            except Exception:
                # 防御性 Fallback：内存连接 + 临时 Parquet 视图
                _RAW_CONN = duckdb.connect(":memory:")
                clean_path = CLEAN_DATA_PATH.replace("\\", "/")
                _RAW_CONN.execute(f"CREATE OR REPLACE VIEW clean AS SELECT * FROM read_parquet('{clean_path}')")
                _RAW_CONN.execute("SET search_path=main")
            
        df = _RAW_CONN.execute(sql).fetchdf()
        truncated = len(df) > 500
        if truncated:
            df = df.head(500)
        result = df.to_json(orient="records", force_ascii=False)
        if truncated:
            return json.dumps({
                "warning": "结果超过 500 行，已截断",
                "data": json.loads(result)
            }, ensure_ascii=False)
        return result
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)



def rule_based_review(text: str) -> tuple[bool, str]:
    """
    规则验证（内部调用，不作为 LLM tool）。
    返回 (passed: bool, feedback: str)

    v2.0 — 增强版，委托到 agent/reviewer.py 执行完整校验：
      - B-001~B-004: 数字支撑、模糊词、字数、必要段落（阻断级）
      - D-001~D-006: 禁止用语、Day7周末效应、维度标注、逻辑检查、窗口限制
      - 兼容旧接口 (passed, feedback) tuple
    """
    try:
        from agent.reviewer import rule_based_review as _enhanced_review
        return _enhanced_review(text)
    except Exception as e:
        # Fallback: 旧版简单检查
        pass

    issues = []

    # 1. 数字数量检查
    arabic = re.findall(r"\d+\.?\d*%?", text)
    chinese_num = re.findall(r"[一二三四五六七八九十百千万亿]+", text)
    total_nums = len(arabic) + len(chinese_num)
    if total_nums < 3:
        issues.append(f"数字支撑不足（仅找到 {total_nums} 个数字/百分比，要求 ≥3 个）")

    # 2. 模糊词检查
    fuzzy_words = ["较高", "明显", "显著", "一定程度", "有所", "相对较", "比较高", "比较低"]
    found_fuzzy = [w for w in fuzzy_words if w in text]
    if found_fuzzy:
        issues.append(f"存在模糊表述：{'、'.join(found_fuzzy)}，请替换为具体数字")

    # 3. 长度检查
    if len(text.strip()) < 150:
        issues.append(f"内容过短（{len(text.strip())} 字，要求 ≥150 字）")

    if issues:
        feedback = "【验证未通过】\n" + "\n".join(f"- {i}" for i in issues)
        return False, feedback
    return True, "【验证通过】"


# ── Tool definitions（OpenAI 格式，DeepSeek 兼容）────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_tables",
            "description": "列出数据库中所有分析结果表",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_table_schema",
            "description": "获取指定表的字段结构，在查询前必须先了解 schema",
            "parameters": {
                "type": "object",
                "properties": {
                    "table_name": {"type": "string", "description": "表名"}
                },
                "required": ["table_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_duckdb",
            "description": "查询 analysis.db 中的预计算聚合表，最多返回 200 行。优先用此工具回答能从聚合表得到的问题。",
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {"type": "string", "description": "SQL 语句，表名直接用聚合表名"}
                },
                "required": ["sql"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "plot_bar",
            "description": "查询数据并生成柱状图，返回图片路径",
            "parameters": {
                "type": "object",
                "properties": {
                    "title":  {"type": "string"},
                    "x_col":  {"type": "string", "description": "X 轴字段名"},
                    "y_col":  {"type": "string", "description": "Y 轴字段名"},
                    "sql":    {"type": "string", "description": "查询 SQL"},
                },
                "required": ["title", "x_col", "y_col", "sql"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_business_context",
            "description": (
                "获取所有表的业务含义、已知核心结论列表和 clean_data.parquet 字段说明。"
                "每次分析任务开始时必须首先调用此工具，了解哪些结论已知、哪些需要增量探索。"
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_raw",
            "description": (
                "对 clean_data.parquet 执行即席 SQL 查询（2900 万行原始数据），结果超 500 行截断。"
                "SQL 里用 read_parquet('{path}') 作为数据源。"
                "仅在聚合表无法满足分析需求时使用（如需要原始行级特征、个体行为序列等）。"
            ).format(path=CLEAN_DATA_PATH.replace("\\", "/")),
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": (
                            "SQL 语句，数据源写 read_parquet('{path}')，"
                            "字段：user_id/item_id/category_id/behavior_type/ts/dt/hour/weekday/is_weekend"
                        ).format(path=CLEAN_DATA_PATH.replace("\\", "/"))
                    }
                },
                "required": ["sql"],
            },
        },
    },
]

DISPATCH = {
    "list_tables":          lambda a: list_tables(),
    "get_table_schema":     lambda a: get_table_schema(a["table_name"]),
    "query_duckdb":         lambda a: query_duckdb(a["sql"]),
    "plot_bar":             lambda a: plot_bar(a["title"], a["x_col"], a["y_col"], a["sql"]),
    "get_business_context": lambda a: get_business_context(),
    "query_raw":            lambda a: query_raw(a["sql"]),
}