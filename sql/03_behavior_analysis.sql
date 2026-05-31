-- ============================================================
-- 03_behavior_analysis.sql — 行为分析层
-- ============================================================
-- 职责：日度/小时/周末行为趋势 + Session 分析（30分钟规则）
-- 输出表：
--   daily_behavior_summary    — Power BI 日度趋势图
--   hourly_behavior_summary   — Power BI 时段热力图
--   weekday_behavior_summary  — 周末 vs 工作日对比
--   session_summary           — 每个 Session 明细（事实表）
--   session_stats             — Session 分组转化统计
-- 依赖：00_init.sql（提供 clean 视图）
-- ============================================================

-- ============================================================
-- 1. daily_behavior_summary — 日度行为汇总
-- ============================================================
DROP TABLE IF EXISTS daily_behavior_summary;
CREATE TABLE daily_behavior_summary AS
SELECT
    dt,
    COUNT(DISTINCT user_id)                                                     AS dau,
    COUNT(*)                                                                    AS total_actions,
    SUM(CASE WHEN behavior_type = 'pv'   THEN 1 ELSE 0 END)                    AS pv_cnt,
    SUM(CASE WHEN behavior_type = 'fav'  THEN 1 ELSE 0 END)                    AS fav_cnt,
    SUM(CASE WHEN behavior_type = 'cart' THEN 1 ELSE 0 END)                    AS cart_cnt,
    SUM(CASE WHEN behavior_type = 'buy'  THEN 1 ELSE 0 END)                    AS buy_cnt,
    ROUND(100.0 * SUM(CASE WHEN behavior_type = 'buy' THEN 1 ELSE 0 END)
                / NULLIF(COUNT(*), 0), 2)                                      AS buy_rate_pct,
    ROUND(100.0 * SUM(CASE WHEN behavior_type = 'fav' THEN 1 ELSE 0 END)
                / NULLIF(COUNT(*), 0), 2)                                      AS fav_rate_pct,
    ROUND(100.0 * SUM(CASE WHEN behavior_type = 'cart' THEN 1 ELSE 0 END)
                / NULLIF(COUNT(*), 0), 2)                                      AS cart_rate_pct,
    ROUND(1.0 * COUNT(*) / NULLIF(COUNT(DISTINCT user_id), 0), 1)              AS avg_actions_per_user
FROM clean
GROUP BY dt
ORDER BY dt;


-- ============================================================
-- 2. hourly_behavior_summary — 小时行为分布
-- ============================================================
DROP TABLE IF EXISTS hourly_behavior_summary;
CREATE TABLE hourly_behavior_summary AS
SELECT
    CAST(hour AS INTEGER)               AS hour,
    COUNT(*)                            AS actions,
    SUM(CASE WHEN behavior_type = 'pv'   THEN 1 ELSE 0 END) AS pv_cnt,
    SUM(CASE WHEN behavior_type = 'fav'  THEN 1 ELSE 0 END) AS fav_cnt,
    SUM(CASE WHEN behavior_type = 'cart' THEN 1 ELSE 0 END) AS cart_cnt,
    SUM(CASE WHEN behavior_type = 'buy'  THEN 1 ELSE 0 END) AS buy_cnt,
    ROUND(100.0 * SUM(CASE WHEN behavior_type = 'buy' THEN 1 ELSE 0 END)
                / NULLIF(COUNT(*), 0), 2)                   AS buy_rate_pct,
    COUNT(DISTINCT user_id)                                  AS uv
FROM clean
GROUP BY hour
ORDER BY hour;


-- ============================================================
-- 3. weekday_behavior_summary — 周末 vs 工作日
-- ============================================================
DROP TABLE IF EXISTS weekday_behavior_summary;
CREATE TABLE weekday_behavior_summary AS
SELECT
    is_weekend,
    CASE WHEN is_weekend = 1 THEN '周末' ELSE '工作日' END AS day_type,
    COUNT(DISTINCT dt)                                                       AS day_cnt,
    ROUND(AVG(daily_dau), 0)                                                 AS avg_dau,
    ROUND(AVG(daily_actions), 0)                                             AS avg_actions,
    ROUND(AVG(daily_buy), 0)                                                 AS avg_buy,
    ROUND(AVG(daily_buy_rate), 2)                                            AS avg_buy_rate_pct,
    ROUND(AVG(daily_cart_rate), 2)                                           AS avg_cart_rate_pct
FROM (
    SELECT
        dt,
        is_weekend,
        COUNT(DISTINCT user_id) AS daily_dau,
        COUNT(*)                AS daily_actions,
        SUM(CASE WHEN behavior_type = 'buy'  THEN 1 ELSE 0 END) AS daily_buy,
        100.0 * SUM(CASE WHEN behavior_type = 'buy'  THEN 1 ELSE 0 END)
              / NULLIF(COUNT(*), 0) AS daily_buy_rate,
        100.0 * SUM(CASE WHEN behavior_type = 'cart' THEN 1 ELSE 0 END)
              / NULLIF(COUNT(*), 0) AS daily_cart_rate
    FROM clean
    GROUP BY dt, is_weekend
) sub
GROUP BY is_weekend
ORDER BY is_weekend;


-- ============================================================
-- 4. session_summary — Session 明细（30分钟无行为规则）
-- ============================================================
DROP TABLE IF EXISTS session_summary;
CREATE TABLE session_summary AS
WITH
ordered AS (
    SELECT
        user_id,
        ts,
        behavior_type,
        dt,
        LAG(ts) OVER (PARTITION BY user_id ORDER BY ts) AS prev_ts
    FROM clean
),
session_boundary AS (
    SELECT
        *,
        CASE
            WHEN prev_ts IS NULL THEN 1
            WHEN DATE_DIFF('minute', prev_ts, ts) > 30 THEN 1
            ELSE 0
        END AS is_new_session
    FROM ordered
),
session_numbered AS (
    SELECT
        *,
        SUM(is_new_session) OVER (
            PARTITION BY user_id
            ORDER BY ts
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS session_seq
    FROM session_boundary
)
SELECT
    user_id || '_' || session_seq                     AS session_id,
    user_id,
    MIN(ts)                                           AS session_start,
    MAX(ts)                                           AS session_end,
    ROUND(DATE_DIFF('second', MIN(ts), MAX(ts)) / 60.0, 1) AS session_duration_min,
    COUNT(*)                                          AS action_cnt,
    SUM(CASE WHEN behavior_type = 'buy'  THEN 1 ELSE 0 END) AS buy_cnt,
    SUM(CASE WHEN behavior_type = 'cart' THEN 1 ELSE 0 END) AS cart_cnt,
    SUM(CASE WHEN behavior_type = 'fav'  THEN 1 ELSE 0 END) AS fav_cnt,
    SUM(CASE WHEN behavior_type = 'pv'   THEN 1 ELSE 0 END) AS pv_cnt,
    CASE WHEN SUM(CASE WHEN behavior_type = 'buy' THEN 1 ELSE 0 END) > 0 THEN 1 ELSE 0 END AS has_buy,
    CAST(MIN(dt) AS DATE)                             AS session_date
FROM session_numbered
GROUP BY user_id, session_seq;


-- ============================================================
-- 5. session_stats — Session 分组转化统计
-- ============================================================
DROP TABLE IF EXISTS session_stats;
CREATE TABLE session_stats AS
WITH session_groups AS (
    SELECT
        *,
        CASE
            WHEN action_cnt = 1                     THEN '1次'
            WHEN action_cnt BETWEEN  2 AND  5       THEN '2-5次'
            WHEN action_cnt BETWEEN  6 AND 20       THEN '6-20次'
            WHEN action_cnt BETWEEN 21 AND 50       THEN '21-50次'
            WHEN action_cnt > 50                    THEN '50+次'
        END AS session_length_group
    FROM session_summary
)
SELECT
    session_length_group,
    COUNT(*)                                                         AS session_cnt,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 2)               AS session_pct,
    SUM(has_buy)                                                     AS buy_session_cnt,
    ROUND(100.0 * SUM(has_buy) / NULLIF(COUNT(*), 0), 2)            AS buy_rate_pct,
    ROUND(AVG(action_cnt), 1)                                       AS avg_actions,
    ROUND(AVG(session_duration_min), 1)                             AS avg_duration_min
FROM session_groups
GROUP BY session_length_group
ORDER BY MIN(action_cnt);


-- ============================================================
-- 验证输出
-- ============================================================
SELECT '=== 03_behavior_analysis 执行完成 ===' AS status;
SELECT 'daily_behavior_summary'   AS tbl, COUNT(*) AS rows FROM daily_behavior_summary
UNION ALL SELECT 'hourly_behavior_summary', COUNT(*) FROM hourly_behavior_summary
UNION ALL SELECT 'weekday_behavior_summary', COUNT(*) FROM weekday_behavior_summary
UNION ALL SELECT 'session_summary', COUNT(*) FROM session_summary
UNION ALL SELECT 'session_stats', COUNT(*) FROM session_stats;
