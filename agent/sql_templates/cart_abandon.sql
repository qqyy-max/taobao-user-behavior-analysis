-- ═══════════════════════════════════════════════════════════════
-- SQL Template: Cart Abandon — 加购未购分析
-- 用途：加购未购用户画像、触达优先级排序、与购买用户对比
-- ═══════════════════════════════════════════════════════════════

-- 模板2-1: 加购未购用户规模 + 全局汇总
SELECT * FROM cart_abandon_summary;

-- 模板2-2: 加购未购用户按距最后加购天数分组（触达优先级）
SELECT
    days_since_last_cart,
    COUNT(*) AS user_cnt,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 1) AS user_pct,
    ROUND(AVG(avg_daily_pv), 1) AS avg_daily_pv,
    ROUND(AVG(cart_item_cnt), 1) AS avg_cart_items
FROM cart_abandon_users
GROUP BY days_since_last_cart
ORDER BY days_since_last_cart;

-- 模板2-3: 加购未购用户画像（按活跃天数分层）
SELECT
    CASE
        WHEN active_days >= 7 THEN '高活跃(7-9天)'
        WHEN active_days >= 4 THEN '中活跃(4-6天)'
        ELSE '低活跃(1-3天)'
    END AS activity_level,
    COUNT(*) AS user_cnt,
    ROUND(AVG(cart_item_cnt), 1) AS avg_cart_items,
    ROUND(AVG(avg_daily_pv), 1) AS avg_daily_pv,
    ROUND(AVG(cart_to_pv_rate), 2) AS avg_cart_to_pv_rate
FROM cart_abandon_users
GROUP BY activity_level
ORDER BY user_cnt DESC;

-- 模板2-4: 加购未购 vs 加购后购买用户对比
SELECT * FROM cart_buyer_comparison;

-- 模板2-5: 加购未购用户加购商品类目分布（Top 10）
SELECT
    i.category_id,
    COUNT(*) AS cart_cnt,
    COUNT(DISTINCT i.user_id) AS user_cnt
FROM cart_abandon_item_detail i
GROUP BY i.category_id
ORDER BY cart_cnt DESC
LIMIT 10;
