-- ============================================================================
-- 游戏行业付费意图预测 ETL SQL 方案（无 WITH 语法版本）
-- ============================================================================
-- 目标：构建正负样本特征宽表，用于大模型预测付费意图
-- 正样本：3月11日-3月17日有捕鱼游戏付费的用户（从 ads_pps_user_base_indicator_dm 判断）
-- 负样本：大盘随机1000用户（排除正样本）
-- 输出：一个用户一行，包含画像特征、APP行为序列、广告事件序列
-- 时间切分：特征数据取3月10日之前，避免与标签期（3月11-17日）重叠
-- ID映射：did=adid，通过 dwd_pty_combine_device_up_bind_ds 映射到 usid
-- ============================================================================

-- ============================================================================
-- 阶段 1：样本池构建（分步骤创建临时表）
-- ============================================================================

-- Step 1.1: 正样本 = 3月11-17日有捕鱼游戏付费的用户（直接采样，最多10000个）
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260317_positive_samples;
CREATE TABLE IF NOT EXISTS adhoctemp.tmp_l00527489_20260317_positive_samples (
    usid STRING COMMENT '用户标识',
    sample_label STRING COMMENT '样本标签',
    total_payment_amt_7d DOUBLE COMMENT '7天总付费金额（3月11-17日）',
    total_payment_cnt_7d BIGINT COMMENT '7天总付费次数（3月11-17日）'
) COMMENT '正样本：标签期捕鱼游戏付费用户（最多10000个）';

INSERT INTO adhoctemp.tmp_l00527489_20260317_positive_samples
SELECT
    usid,
    'positive' AS sample_label,
    total_payment_amt_7d,
    total_payment_cnt_7d
FROM (
    SELECT
        bind.usid,
        SUM(COALESCE(ind.total_task_cnvr_target_cnvr_cnt, 0)) AS total_payment_amt_7d,
        SIZE(COLLECT_SET(ind.pt_d)) AS total_payment_cnt_7d
    FROM pps.ads_pps_user_base_indicator_dm ind
    INNER JOIN (
        SELECT dsid, usid
        FROM bicoredata.dwd_pty_combine_device_up_bind_ds
        WHERE pt_d = '20260304'
    ) bind ON ind.did = bind.dsid
    INNER JOIN (
        SELECT promote_app_name
        FROM pps.dim_pps_metric_promoted_app_info_hs
        WHERE pt_h = '2026031023'
          AND promote_app_name LIKE '%捕鱼%'
    ) app_info ON ind.promote_app_name = app_info.promote_app_name
    WHERE ind.pt_d >= '20260311' AND ind.pt_d <= '20260317'
      AND ind.event_type = 'paid'
      AND bind.usid IS NOT NULL
    GROUP BY bind.usid
    HAVING SUM(COALESCE(ind.total_task_cnvr_target_cnvr_cnt, 0)) > 0
) t
DISTRIBUTE BY RAND()
SORT BY RAND()
LIMIT 10000;

-- Step 1.2: 负样本 = 大盘随机用户（排除正样本，直接采样，最多10000个）
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260317_negative_samples;
CREATE TABLE IF NOT EXISTS adhoctemp.tmp_l00527489_20260317_negative_samples (
    usid STRING COMMENT '用户标识',
    sample_label STRING COMMENT '样本标签',
    total_payment_amt_7d DOUBLE COMMENT '7天总付费金额（3月11-17日）',
    total_payment_cnt_7d BIGINT COMMENT '7天总付费次数（3月11-17日）'
) COMMENT '负样本：随机用户（最多10000个）';

INSERT INTO adhoctemp.tmp_l00527489_20260317_negative_samples
SELECT
    usid,
    'negative' AS sample_label,
    0 AS total_payment_amt_7d,
    0 AS total_payment_cnt_7d
FROM biads.ads_usidpersona_inf_game_payment_intention_new_dm
WHERE pt_d = '20260310'
  AND usid NOT IN (SELECT usid FROM adhoctemp.tmp_l00527489_20260317_positive_samples)
DISTRIBUTE BY RAND()
SORT BY RAND()
LIMIT 10000;

-- Step 1.3: 合并正负样本
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260317_game_payment_sample_pool;
CREATE TABLE IF NOT EXISTS adhoctemp.tmp_l00527489_20260317_game_payment_sample_pool (
    usid STRING COMMENT '用户标识',
    sample_label STRING COMMENT '样本标签：positive/negative',
    total_payment_amt_7d DOUBLE COMMENT '7天总付费金额（3月11-17日）',
    total_payment_cnt_7d BIGINT COMMENT '7天总付费次数（3月11-17日）'
) COMMENT '样本池：正负样本合并';

INSERT INTO adhoctemp.tmp_l00527489_20260317_game_payment_sample_pool
SELECT usid, sample_label, total_payment_amt_7d, total_payment_cnt_7d
FROM adhoctemp.tmp_l00527489_20260317_positive_samples
UNION ALL
SELECT usid, sample_label, total_payment_amt_7d, total_payment_cnt_7d
FROM adhoctemp.tmp_l00527489_20260317_negative_samples;


-- ============================================================================
-- 阶段 2：用户画像特征表（使用3月10日快照，避免标签泄露）
-- ============================================================================

DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260317_game_payment_user_profile;
CREATE TABLE IF NOT EXISTS adhoctemp.tmp_l00527489_20260317_game_payment_user_profile (
    usid STRING COMMENT '用户标识',
    user_profile_features STRING COMMENT '用户画像特征（key:value;key:value格式）'
) COMMENT '用户画像特征表';

INSERT INTO adhoctemp.tmp_l00527489_20260317_game_payment_user_profile
SELECT
    usid,
    CONCAT_WS(';',
        -- 基础属性
        CONCAT('性别:', COALESCE(CAST(gender_new_dev AS STRING), 'unknown')),
        CONCAT('年龄:', COALESCE(CAST(forecast_age_dev AS STRING), 'unknown')),
        CONCAT('学历:', COALESCE(CAST(education_dev AS STRING), 'unknown')),

        -- 设备属性
        CONCAT('设备价格:', COALESCE(CAST(price_new_dev AS STRING), '0')),
        CONCAT('设备品牌:', COALESCE(CAST(brand_new_dev AS STRING), 'unknown')),
        CONCAT('设备系列:', COALESCE(CAST(series_new_dev AS STRING), 'unknown')),
        CONCAT('激活天数:', COALESCE(CAST(active_duration_dev AS STRING), '0')),
        CONCAT('月在线天数:', COALESCE(CAST(push_online_days_30d_dev AS STRING), '0')),

        -- 经济属性
        CONCAT('有房:', COALESCE(CAST(owner_house_flag_dev AS STRING), 'unknown')),
        CONCAT('有车:', COALESCE(CAST(owner_cars_user_dev AS STRING), 'unknown')),
        CONCAT('消费频率:', COALESCE(CAST(consume_frequency_dev AS STRING), 'unknown')),
        CONCAT('信用卡使用:', COALESCE(CAST(consume_credit_card_level_dev AS STRING), 'unknown')),

        -- 游戏付费（30天）
        CONCAT('30天现金付费金额:', COALESCE(CAST(sum_cashpay_amt_30d AS STRING), '0')),
        CONCAT('30天现金付费次数:', COALESCE(CAST(cashpay_cnt_30d AS STRING), '0')),
        CONCAT('30天优惠券付费金额:', COALESCE(CAST(sum_couponpay_amt_30d AS STRING), '0')),
        CONCAT('30天优惠券付费次数:', COALESCE(CAST(couponpay_cnt_30d AS STRING), '0')),

        -- 游戏付费（60天）
        CONCAT('60天现金付费金额:', COALESCE(CAST(sum_cashpay_amt_60d AS STRING), '0')),
        CONCAT('60天现金付费次数:', COALESCE(CAST(cashpay_cnt_60d AS STRING), '0')),
        CONCAT('60天优惠券付费金额:', COALESCE(CAST(sum_couponpay_amt_60d AS STRING), '0')),
        CONCAT('60天优惠券付费次数:', COALESCE(CAST(couponpay_cnt_60d AS STRING), '0')),

        -- 游戏行为
        CONCAT('7天游戏搜索TOP10:', COALESCE(game_search_tfidf_7d_list, 'none')),
        CONCAT('30天游戏搜索TOP10:', COALESCE(game_search_tfidf_30d_list, 'none')),
        CONCAT('端侧浏览应用包名:', COALESCE(ha_view_packages, 'none')),
        CONCAT('搜索关键词:', COALESCE(search_keywords_dev, 'none')),

        -- 游戏分类付费
        CONCAT('30天游戏分类付费:', COALESCE(game_category_pay_30days, 'none')),
        CONCAT('90天游戏分类付费:', COALESCE(game_category_pay_90days, 'none')),

        -- 用户等级
        CONCAT('游戏用户生命周期:', COALESCE(CAST(game_interest_user_lifetime_u AS STRING), 'unknown')),
        CONCAT('游戏大R等级:', COALESCE(CAST(game_fact_rmb_user_u AS STRING), 'unknown')),
        CONCAT('游戏大R等级_二级分类:', COALESCE(CAST(game_fact_sedclass_rmb_user_u AS STRING), 'unknown')),
        CONCAT('游戏大R等级_三级分类:', COALESCE(CAST(game_fact_thirdclass_rmb_user_u AS STRING), 'unknown')),

        -- 内容偏好
        CONCAT('内容关键词:', COALESCE(content_keywords_dev, 'none'))
    ) AS user_profile_features
FROM biads.ads_usidpersona_inf_game_payment_intention_new_dm
WHERE pt_d = '20260310'
  AND usid IN (SELECT usid FROM adhoctemp.tmp_l00527489_20260317_game_payment_sample_pool);


-- ============================================================================
-- 阶段 3：APP 行为数据表（特征期：2月9日-3月10日，30天）
-- ============================================================================

-- Step 3.1: 提取 APP 事件明细（合并使用行为和安装卸载行为）
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260317_app_events;
CREATE TABLE IF NOT EXISTS adhoctemp.tmp_l00527489_20260317_app_events (
    usid STRING COMMENT '用户标识',
    event_date STRING COMMENT '事件日期',
    event_type STRING COMMENT '事件类型：appUsage/appInstall/appUninstall/appUpdate',
    app_name STRING COMMENT '应用名称',
    package_name STRING COMMENT '包名',
    usage_duration BIGINT COMMENT '使用时长（秒，仅appUsage有值）',
    app_category STRING COMMENT '应用分类'
) COMMENT 'APP事件明细表（合并使用和安装卸载数据）';

-- 插入使用行为数据
INSERT INTO adhoctemp.tmp_l00527489_20260317_app_events
SELECT
    bind.usid,
    app.pt_d AS event_date,
    'appUsage' AS event_type,
    COALESCE(app_info.promote_app_name, app.package_name) AS app_name,
    app.package_name,
    CAST(COALESCE(app.total_time, 0) / 1000 AS BIGINT) AS usage_duration,
    COALESCE(app_info.category_level3, 'unknown') AS app_category
FROM pps.dwd_pps_appdata_appusage_dm app
INNER JOIN (
    SELECT dsid, usid
    FROM bicoredata.dwd_pty_combine_device_up_bind_ds
    WHERE pt_d = '20260304'
) bind ON app.adid = bind.dsid
LEFT JOIN (
    SELECT promote_app_pkg, promote_app_name, category_level3
    FROM pps.dim_pps_metric_promoted_app_info_hs
    WHERE pt_h = '2026031023'
) app_info ON app.package_name = app_info.promote_app_pkg
WHERE app.pt_d >= '20260209' AND app.pt_d <= '20260310'
  AND bind.usid IN (SELECT usid FROM adhoctemp.tmp_l00527489_20260317_game_payment_sample_pool);

-- 插入安装/卸载/更新行为数据
INSERT INTO adhoctemp.tmp_l00527489_20260317_app_events
SELECT
    bind.usid,
    iu.pt_d AS event_date,
    iu.event_type,
    COALESCE(app_info.promote_app_name, iu.package_name) AS app_name,
    iu.package_name,
    0 AS usage_duration,
    COALESCE(app_info.category_level3, 'unknown') AS app_category
FROM pps.dwd_pps_appdata_install_uninstall_update_dm iu
INNER JOIN (
    SELECT dsid, usid
    FROM bicoredata.dwd_pty_combine_device_up_bind_ds
    WHERE pt_d = '20260304'
) bind ON iu.adid = bind.dsid
LEFT JOIN (
    SELECT promote_app_pkg, promote_app_name, category_level3
    FROM pps.dim_pps_metric_promoted_app_info_hs
    WHERE pt_h = '2026031023'
) app_info ON iu.package_name = app_info.promote_app_pkg
WHERE iu.pt_d >= '20260209' AND iu.pt_d <= '20260310'
  AND bind.usid IN (SELECT usid FROM adhoctemp.tmp_l00527489_20260317_game_payment_sample_pool);

-- Step 3.2: 构建 APP 行为序列
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260317_game_payment_app_behavior;
CREATE TABLE IF NOT EXISTS adhoctemp.tmp_l00527489_20260317_game_payment_app_behavior (
    usid STRING COMMENT '用户标识',
    app_behavior_seq STRING COMMENT 'APP行为序列（时间倒序）'
) COMMENT 'APP行为序列表';

INSERT INTO adhoctemp.tmp_l00527489_20260317_game_payment_app_behavior
SELECT
    usid,
    CONCAT_WS(' -> ',
        SORT_ARRAY(
            COLLECT_LIST(
                CONCAT(
                    '[', event_date, '][', event_type, '] ',
                    '应用名:', app_name, ' ',
                    '包名:', package_name, ' ',
                    '时长:', CAST(usage_duration AS STRING), 's ',
                    '分类:', app_category
                )
            ),
            FALSE
        )
    ) AS app_behavior_seq
FROM adhoctemp.tmp_l00527489_20260317_app_events
GROUP BY usid;


-- ============================================================================
-- 阶段 4：广告事件数据表（特征期：2月9日-3月10日，避免标签泄露）
-- ============================================================================

-- Step 4.1: 远期汇总（2月9日-2月28日）- 按周汇总
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260317_historical_events;
CREATE TABLE IF NOT EXISTS adhoctemp.tmp_l00527489_20260317_historical_events (
    usid STRING COMMENT '用户标识',
    event_period STRING COMMENT '事件周期（周）',
    period_type STRING COMMENT '周期类型：historical',
    impression_cnt BIGINT COMMENT '曝光次数',
    impression_industries STRING COMMENT '曝光行业',
    impression_positions STRING COMMENT '曝光版位',
    click_cnt BIGINT COMMENT '点击次数',
    click_industries STRING COMMENT '点击行业',
    click_positions STRING COMMENT '点击版位',
    conversion_cnt BIGINT COMMENT '转化次数',
    conversion_industries STRING COMMENT '转化行业',
    conversion_targets STRING COMMENT '转化标的'
) COMMENT '历史广告事件汇总表（按周）';

INSERT INTO adhoctemp.tmp_l00527489_20260317_historical_events
SELECT
    bind.usid,
    CONCAT(SUBSTR(ind.pt_d, 1, 4), '-W',
           LPAD(CAST(WEEKOFYEAR(FROM_UNIXTIME(UNIX_TIMESTAMP(ind.pt_d, 'yyyyMMdd'))) AS STRING), 2, '0')
    ) AS event_period,
    'historical' AS period_type,
    SUM(COALESCE(ind.received_total_imp, 0)) AS impression_cnt,
    CONCAT_WS(',', COLLECT_SET(CASE WHEN ind.received_total_imp > 0 THEN CONCAT(COALESCE(ind.cust_industry_level1, '未知'), '-', COALESCE(ind.cust_industry_level2, '未知')) ELSE NULL END)) AS impression_industries,
    CONCAT_WS(',', COLLECT_SET(CASE WHEN ind.received_total_imp > 0 THEN ind.position_name ELSE NULL END)) AS impression_positions,
    SUM(COALESCE(ind.received_total_click, 0)) AS click_cnt,
    CONCAT_WS(',', COLLECT_SET(CASE WHEN ind.received_total_click > 0 THEN CONCAT(COALESCE(ind.cust_industry_level1, '未知'), '-', COALESCE(ind.cust_industry_level2, '未知')) ELSE NULL END)) AS click_industries,
    CONCAT_WS(',', COLLECT_SET(CASE WHEN ind.received_total_click > 0 THEN ind.position_name ELSE NULL END)) AS click_positions,
    SUM(CASE WHEN ind.event_type NOT IN ('repeatedImp','skip','playStart','playPause','webclose','intentSuccess','appOpen','webopen') THEN COALESCE(ind.total_task_cnvr_target_cnvr_cnt, 0) ELSE 0 END) AS conversion_cnt,
    CONCAT_WS(',', COLLECT_SET(CASE WHEN ind.event_type NOT IN ('repeatedImp','skip','playStart','playPause','webclose','intentSuccess','appOpen','webopen') AND ind.total_task_cnvr_target_cnvr_cnt > 0 THEN CONCAT(COALESCE(ind.cust_industry_level1, '未知'), '-', COALESCE(ind.cust_industry_level2, '未知')) ELSE NULL END)) AS conversion_industries,
    CONCAT_WS(',', COLLECT_SET(CASE WHEN ind.event_type NOT IN ('repeatedImp','skip','playStart','playPause','webclose','intentSuccess','appOpen','webopen') AND ind.total_task_cnvr_target_cnvr_cnt > 0 THEN ind.promote_app_name ELSE NULL END)) AS conversion_targets
FROM pps.ads_pps_user_base_indicator_dm ind
INNER JOIN (
    SELECT dsid, usid
    FROM bicoredata.dwd_pty_combine_device_up_bind_ds
    WHERE pt_d = '20260304'
) bind ON ind.did = bind.dsid
WHERE ind.pt_d >= '20260209' AND ind.pt_d <= '20260228'
  AND bind.usid IN (SELECT usid FROM adhoctemp.tmp_l00527489_20260317_game_payment_sample_pool)
  AND (ind.received_total_imp > 0 OR ind.received_total_click > 0
       OR (ind.event_type NOT IN ('repeatedImp','skip','playStart','playPause','webclose','intentSuccess','appOpen','webopen')
           AND ind.total_task_cnvr_target_cnvr_cnt > 0))
GROUP BY bind.usid,
         CONCAT(SUBSTR(ind.pt_d, 1, 4), '-W',
                LPAD(CAST(WEEKOFYEAR(FROM_UNIXTIME(UNIX_TIMESTAMP(ind.pt_d, 'yyyyMMdd'))) AS STRING), 2, '0'));

-- Step 4.2: 近期明细（3月1日-3月10日）- 保留每日明细，避免标签泄露
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260317_recent_events;
CREATE TABLE IF NOT EXISTS adhoctemp.tmp_l00527489_20260317_recent_events (
    usid STRING COMMENT '用户标识',
    event_period STRING COMMENT '事件周期（日）',
    period_type STRING COMMENT '周期类型：recent',
    impression_cnt BIGINT COMMENT '曝光次数',
    impression_industries STRING COMMENT '曝光行业',
    impression_positions STRING COMMENT '曝光版位',
    click_cnt BIGINT COMMENT '点击次数',
    click_industries STRING COMMENT '点击行业',
    click_positions STRING COMMENT '点击版位',
    conversion_cnt BIGINT COMMENT '转化次数',
    conversion_industries STRING COMMENT '转化行业',
    conversion_targets STRING COMMENT '转化标的'
) COMMENT '近期广告事件明细表（按天）';

INSERT INTO adhoctemp.tmp_l00527489_20260317_recent_events
SELECT
    bind.usid,
    ind.pt_d AS event_period,
    'recent' AS period_type,
    SUM(COALESCE(ind.received_total_imp, 0)) AS impression_cnt,
    CONCAT_WS(',', COLLECT_SET(CASE WHEN ind.received_total_imp > 0 THEN CONCAT(COALESCE(ind.cust_industry_level1, '未知'), '-', COALESCE(ind.cust_industry_level2, '未知')) ELSE NULL END)) AS impression_industries,
    CONCAT_WS(',', COLLECT_SET(CASE WHEN ind.received_total_imp > 0 THEN ind.position_name ELSE NULL END)) AS impression_positions,
    SUM(COALESCE(ind.received_total_click, 0)) AS click_cnt,
    CONCAT_WS(',', COLLECT_SET(CASE WHEN ind.received_total_click > 0 THEN CONCAT(COALESCE(ind.cust_industry_level1, '未知'), '-', COALESCE(ind.cust_industry_level2, '未知')) ELSE NULL END)) AS click_industries,
    CONCAT_WS(',', COLLECT_SET(CASE WHEN ind.received_total_click > 0 THEN ind.position_name ELSE NULL END)) AS click_positions,
    SUM(CASE WHEN ind.event_type NOT IN ('repeatedImp','skip','playStart','playPause','webclose','intentSuccess','appOpen','webopen') THEN COALESCE(ind.total_task_cnvr_target_cnvr_cnt, 0) ELSE 0 END) AS conversion_cnt,
    CONCAT_WS(',', COLLECT_SET(CASE WHEN ind.event_type NOT IN ('repeatedImp','skip','playStart','playPause','webclose','intentSuccess','appOpen','webopen') AND ind.total_task_cnvr_target_cnvr_cnt > 0 THEN CONCAT(COALESCE(ind.cust_industry_level1, '未知'), '-', COALESCE(ind.cust_industry_level2, '未知')) ELSE NULL END)) AS conversion_industries,
    CONCAT_WS(',', COLLECT_SET(CASE WHEN ind.event_type NOT IN ('repeatedImp','skip','playStart','playPause','webclose','intentSuccess','appOpen','webopen') AND ind.total_task_cnvr_target_cnvr_cnt > 0 THEN ind.promote_app_name ELSE NULL END)) AS conversion_targets
FROM pps.ads_pps_user_base_indicator_dm ind
INNER JOIN (
    SELECT dsid, usid
    FROM bicoredata.dwd_pty_combine_device_up_bind_ds
    WHERE pt_d = '20260304'
) bind ON ind.did = bind.dsid
WHERE ind.pt_d >= '20260301' AND ind.pt_d <= '20260310'
  AND bind.usid IN (SELECT usid FROM adhoctemp.tmp_l00527489_20260317_game_payment_sample_pool)
  AND (ind.received_total_imp > 0 OR ind.received_total_click > 0
       OR (ind.event_type NOT IN ('repeatedImp','skip','playStart','playPause','webclose','intentSuccess','appOpen','webopen')
           AND ind.total_task_cnvr_target_cnvr_cnt > 0))
GROUP BY bind.usid, ind.pt_d;

-- Step 4.3: 合并历史和近期事件
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260317_all_events;
CREATE TABLE IF NOT EXISTS adhoctemp.tmp_l00527489_20260317_all_events (
    usid STRING COMMENT '用户标识',
    event_period STRING COMMENT '事件周期',
    period_type STRING COMMENT '周期类型',
    impression_cnt BIGINT COMMENT '曝光次数',
    impression_industries STRING COMMENT '曝光行业',
    impression_positions STRING COMMENT '曝光版位',
    click_cnt BIGINT COMMENT '点击次数',
    click_industries STRING COMMENT '点击行业',
    click_positions STRING COMMENT '点击版位',
    conversion_cnt BIGINT COMMENT '转化次数',
    conversion_industries STRING COMMENT '转化行业',
    conversion_targets STRING COMMENT '转化标的'
) COMMENT '合并广告事件表';

INSERT INTO adhoctemp.tmp_l00527489_20260317_all_events
SELECT usid, event_period, period_type, impression_cnt, impression_industries, impression_positions,
       click_cnt, click_industries, click_positions, conversion_cnt, conversion_industries, conversion_targets
FROM adhoctemp.tmp_l00527489_20260317_historical_events
UNION ALL
SELECT usid, event_period, period_type, impression_cnt, impression_industries, impression_positions,
       click_cnt, click_industries, click_positions, conversion_cnt, conversion_industries, conversion_targets
FROM adhoctemp.tmp_l00527489_20260317_recent_events;

-- Step 4.4: 构建事件序列字符串
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260317_event_sequences;
CREATE TABLE IF NOT EXISTS adhoctemp.tmp_l00527489_20260317_event_sequences (
    usid STRING COMMENT '用户标识',
    event_period STRING COMMENT '事件周期',
    event_str STRING COMMENT '事件字符串'
) COMMENT '广告事件序列字符串表';

INSERT INTO adhoctemp.tmp_l00527489_20260317_event_sequences
SELECT
    usid,
    event_period,
    CONCAT_WS(' | ',
        CASE WHEN impression_cnt > 0 THEN
            CONCAT('[曝光] 次数:', CAST(impression_cnt AS STRING),
                   ' 行业:', COALESCE(impression_industries, 'unknown'),
                   ' 版位:', COALESCE(impression_positions, 'unknown'))
        ELSE NULL END,
        CASE WHEN click_cnt > 0 THEN
            CONCAT('[点击] 次数:', CAST(click_cnt AS STRING),
                   ' 行业:', COALESCE(click_industries, 'unknown'),
                   ' 版位:', COALESCE(click_positions, 'unknown'))
        ELSE NULL END,
        CASE WHEN conversion_cnt > 0 THEN
            CONCAT('[转化] 次数:', CAST(conversion_cnt AS STRING),
                   ' 行业:', COALESCE(conversion_industries, 'unknown'),
                   ' 标的:', COALESCE(conversion_targets, 'unknown'))
        ELSE NULL END
    ) AS event_str
FROM adhoctemp.tmp_l00527489_20260317_all_events;

-- Step 4.5: 按用户聚合，构建时间倒序序列
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260317_game_payment_ad_events;
CREATE TABLE IF NOT EXISTS adhoctemp.tmp_l00527489_20260317_game_payment_ad_events (
    usid STRING COMMENT '用户标识',
    ad_event_seq STRING COMMENT '广告事件序列（时间倒序）'
) COMMENT '广告事件序列表';

INSERT INTO adhoctemp.tmp_l00527489_20260317_game_payment_ad_events
SELECT
    usid,
    CONCAT_WS(' -> ',
        SORT_ARRAY(
            COLLECT_LIST(
                CONCAT('[', event_period, '] ', event_str)
            ),
            FALSE
        )
    ) AS ad_event_seq
FROM adhoctemp.tmp_l00527489_20260317_event_sequences
GROUP BY usid;


-- ============================================================================
-- 阶段 5：最终宽表 JOIN
-- ============================================================================

DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260317_game_payment_final_wide_table;
CREATE TABLE IF NOT EXISTS adhoctemp.tmp_l00527489_20260317_game_payment_final_wide_table (
    usid STRING COMMENT '用户标识',
    sample_label STRING COMMENT '样本标签：positive/negative',
    total_payment_amt_7d DOUBLE COMMENT '7天总付费金额（标签期：3月11-17日）',
    total_payment_cnt_7d BIGINT COMMENT '7天总付费次数（标签期：3月11-17日）',
    user_profile_features STRING COMMENT '用户画像特征（特征期：3月10日快照）',
    app_behavior_seq STRING COMMENT 'APP行为序列（特征期：2月9日-3月10日，30天）',
    ad_event_seq STRING COMMENT '广告事件序列（特征期：2月9日-3月10日，30天）',
    create_time STRING COMMENT '创建时间'
) COMMENT '最终特征宽表（特征期与标签期严格分离）';

INSERT INTO adhoctemp.tmp_l00527489_20260317_game_payment_final_wide_table
SELECT
    s.usid,
    s.sample_label,
    s.total_payment_amt_7d,
    s.total_payment_cnt_7d,
    COALESCE(p.user_profile_features, '') AS user_profile_features,
    COALESCE(a.app_behavior_seq, '') AS app_behavior_seq,
    COALESCE(e.ad_event_seq, '') AS ad_event_seq,
    FROM_UNIXTIME(UNIX_TIMESTAMP()) AS create_time
FROM adhoctemp.tmp_l00527489_20260317_game_payment_sample_pool s
LEFT JOIN adhoctemp.tmp_l00527489_20260317_game_payment_user_profile p ON s.usid = p.usid
LEFT JOIN adhoctemp.tmp_l00527489_20260317_game_payment_app_behavior a ON s.usid = a.usid
LEFT JOIN adhoctemp.tmp_l00527489_20260317_game_payment_ad_events e ON s.usid = e.usid;


-- ============================================================================
-- 验证 SQL
-- ============================================================================

-- 1. 样本分布验证
SELECT
    sample_label,
    COUNT(*) AS cnt,
    ROUND(AVG(total_payment_amt_7d), 2) AS avg_payment_amt,
    ROUND(AVG(total_payment_cnt_7d), 2) AS avg_payment_cnt
FROM adhoctemp.tmp_l00527489_20260317_game_payment_sample_pool
GROUP BY sample_label;

-- 2. 特征完整性验证
SELECT
    COUNT(*) AS total_users,
    COUNT(CASE WHEN user_profile_features != '' THEN 1 END) AS with_profile,
    COUNT(CASE WHEN app_behavior_seq != '' THEN 1 END) AS with_app_behavior,
    COUNT(CASE WHEN ad_event_seq != '' THEN 1 END) AS with_ad_events,
    ROUND(COUNT(CASE WHEN user_profile_features != '' THEN 1 END) * 100.0 / COUNT(*), 2) AS profile_coverage_pct,
    ROUND(COUNT(CASE WHEN app_behavior_seq != '' THEN 1 END) * 100.0 / COUNT(*), 2) AS app_behavior_coverage_pct,
    ROUND(COUNT(CASE WHEN ad_event_seq != '' THEN 1 END) * 100.0 / COUNT(*), 2) AS ad_event_coverage_pct
FROM adhoctemp.tmp_l00527489_20260317_game_payment_final_wide_table;

-- 3. 数据质量检查 - 正样本付费验证
SELECT
    '正样本付费验证' AS check_name,
    COUNT(*) AS invalid_cnt
FROM adhoctemp.tmp_l00527489_20260317_game_payment_final_wide_table
WHERE sample_label = 'positive' AND total_payment_amt_7d = 0;

-- 4. 数据质量检查 - 正负样本不重叠验证
SELECT
    '正负样本不重叠验证' AS check_name,
    COUNT(*) AS invalid_cnt
FROM adhoctemp.tmp_l00527489_20260317_game_payment_final_wide_table
WHERE sample_label = 'negative' AND usid IN (
    SELECT usid FROM adhoctemp.tmp_l00527489_20260317_game_payment_final_wide_table WHERE sample_label = 'positive'
);

-- 5. 样本数据预览（前10条）
SELECT
    usid,
    sample_label,
    total_payment_amt_7d,
    total_payment_cnt_7d,
    SUBSTR(user_profile_features, 1, 100) AS profile_preview,
    SUBSTR(app_behavior_seq, 1, 100) AS app_behavior_preview,
    SUBSTR(ad_event_seq, 1, 100) AS ad_event_preview
FROM adhoctemp.tmp_l00527489_20260317_game_payment_final_wide_table
LIMIT 10;
