-- ============================================================================
-- 游戏行业付费意图预测 ETL SQL 方案（无 WITH 语法版本）
-- ============================================================================
-- 目标：构建正负样本特征宽表，用于大模型预测付费意图
-- 正样本：3月17号近7天（3月11日-3月17日）有卡片游戏（捕鱼类）付费的用户
-- 负样本：大盘随机1000用户（排除正样本）
-- 输出：一个用户一行，包含画像特征、APP行为序列、广告事件序列
-- 时间切分：特征数据取3月10日之前，避免与标签期（3月11-17日）重叠
-- ============================================================================

-- ============================================================================
-- 阶段 1：样本池构建（分步骤创建临时表）
-- ============================================================================

-- Step 1.1: 识别3月11日-3月17日有付费的用户（标签期）
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260317_paid_users;
CREATE TABLE adhoctemp.tmp_l00527489_20260317_paid_users (
    usid STRING COMMENT '用户标识',
    total_payment_amt_7d DOUBLE COMMENT '7天总付费金额（3月11-17日）',
    total_payment_cnt_7d BIGINT COMMENT '7天总付费次数（3月11-17日）'
) COMMENT '标签期（3月11-17日）有付费的用户';

INSERT INTO adhoctemp.tmp_l00527489_20260317_paid_users
SELECT
    usid,
    SUM(COALESCE(daily_cashpay_amt, 0) + COALESCE(daily_couponpay_amt, 0)) AS total_payment_amt_7d,
    SUM(COALESCE(daily_cashpay_cnt, 0) + COALESCE(daily_couponpay_cnt, 0)) AS total_payment_cnt_7d
FROM biads.ads_usidpersona_inf_game_payment_intention_new_dm
WHERE pt_d >= '20260311' AND pt_d <= '20260317'
GROUP BY usid
HAVING SUM(COALESCE(daily_cashpay_amt, 0) + COALESCE(daily_couponpay_amt, 0)) > 0;

-- Step 1.2: 识别捕鱼游戏用户（通过推广应用名称，标签期内）
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260317_fishing_game_users;
CREATE TABLE adhoctemp.tmp_l00527489_20260317_fishing_game_users (
    usid STRING COMMENT '用户标识'
) COMMENT '标签期内捕鱼游戏用户';

INSERT INTO adhoctemp.tmp_l00527489_20260317_fishing_game_users
SELECT DISTINCT app.adid AS usid
FROM pps.dwd_pps_appdata_appusage_dm app
JOIN pps.dim_pps_metric_promoted_app_info_hs app_info
    ON app.package_name = app_info.promote_app_pkg
WHERE app.pt_d >= '20260311' AND app.pt_d <= '20260317'
  AND app.event_type = 'appUsage'
  AND app_info.promote_app_name LIKE '%捕鱼%'
  AND app_info.pt_h = '2026031023';

-- Step 1.3: 正样本 = 付费用户 ∩ 捕鱼游戏用户（限制最多10000个）
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260317_positive_samples;
CREATE TABLE adhoctemp.tmp_l00527489_20260317_positive_samples (
    usid STRING COMMENT '用户标识',
    sample_label STRING COMMENT '样本标签',
    total_payment_amt_7d DOUBLE COMMENT '7天总付费金额（3月11-17日）',
    total_payment_cnt_7d BIGINT COMMENT '7天总付费次数（3月11-17日）'
) COMMENT '正样本：标签期付费+捕鱼游戏用户（最多10000个）';

INSERT INTO adhoctemp.tmp_l00527489_20260317_positive_samples
SELECT
    p.usid,
    'positive' AS sample_label,
    p.total_payment_amt_7d,
    p.total_payment_cnt_7d
FROM adhoctemp.tmp_l00527489_20260317_paid_users p
INNER JOIN adhoctemp.tmp_l00527489_20260317_fishing_game_users f ON p.usid = f.usid
DISTRIBUTE BY RAND()
SORT BY RAND()
LIMIT 10000;

-- Step 1.4: 负样本 = 大盘随机用户（排除正样本，限制最多10000个）
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260317_negative_samples;
CREATE TABLE adhoctemp.tmp_l00527489_20260317_negative_samples (
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
FROM (
    SELECT usid
    FROM biads.ads_usidpersona_inf_game_payment_intention_new_dm
    WHERE pt_d = '20260310'
      AND usid NOT IN (SELECT usid FROM adhoctemp.tmp_l00527489_20260317_positive_samples)
    DISTRIBUTE BY RAND()
    SORT BY RAND()
    LIMIT 10000
) t;

-- Step 1.5: 合并正负样本
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260317_game_payment_sample_pool;
CREATE TABLE adhoctemp.tmp_l00527489_20260317_game_payment_sample_pool (
    usid STRING COMMENT '用户标识',
    sample_label STRING COMMENT '样本标签：positive/negative',
    total_payment_amt_7d DOUBLE COMMENT '7天总付费金额（3月11-17日）',
    total_payment_cnt_7d BIGINT COMMENT '7天总付费次数（3月11-17日）'
) COMMENT '样本池：正负样本合并';

INSERT INTO adhoctemp.tmp_l00527489_20260317_game_payment_sample_pool
SELECT * FROM adhoctemp.tmp_l00527489_20260317_positive_samples
UNION ALL
SELECT * FROM adhoctemp.tmp_l00527489_20260317_negative_samples;


-- ============================================================================
-- 阶段 2：用户画像特征表（使用3月10日快照，避免标签泄露）
-- ============================================================================

DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260317_game_payment_user_profile;
CREATE TABLE adhoctemp.tmp_l00527489_20260317_game_payment_user_profile (
    usid STRING COMMENT '用户标识',
    user_profile_features STRING COMMENT '用户画像特征（key:value;key:value格式）'
) COMMENT '用户画像特征表';

INSERT INTO adhoctemp.tmp_l00527489_20260317_game_payment_user_profile
SELECT
    usid,
    CONCAT_WS(';',
        -- 基础属性
        CONCAT('gender:', COALESCE(CAST(gender AS STRING), 'unknown')),
        CONCAT('age:', COALESCE(CAST(age AS STRING), 'unknown')),
        CONCAT('education:', COALESCE(CAST(education AS STRING), 'unknown')),

        -- 设备属性
        CONCAT('device_price:', COALESCE(CAST(device_price AS STRING), '0')),
        CONCAT('device_brand:', COALESCE(CAST(device_brand AS STRING), 'unknown')),
        CONCAT('device_series:', COALESCE(CAST(device_series AS STRING), 'unknown')),
        CONCAT('active_days:', COALESCE(CAST(active_days AS STRING), '0')),
        CONCAT('monthly_online_days:', COALESCE(CAST(monthly_online_days AS STRING), '0')),

        -- 经济属性
        CONCAT('has_house:', COALESCE(CAST(has_house AS STRING), 'unknown')),
        CONCAT('has_car:', COALESCE(CAST(has_car AS STRING), 'unknown')),
        CONCAT('consumption_freq:', COALESCE(CAST(consumption_freq AS STRING), 'unknown')),
        CONCAT('credit_card_usage:', COALESCE(CAST(credit_card_usage AS STRING), 'unknown')),

        -- 游戏付费（30天）
        CONCAT('cashpay_amt_30d:', COALESCE(CAST(sum_cashpay_amt_30d AS STRING), '0')),
        CONCAT('cashpay_cnt_30d:', COALESCE(CAST(sum_cashpay_cnt_30d AS STRING), '0')),
        CONCAT('couponpay_amt_30d:', COALESCE(CAST(sum_couponpay_amt_30d AS STRING), '0')),
        CONCAT('couponpay_cnt_30d:', COALESCE(CAST(sum_couponpay_cnt_30d AS STRING), '0')),

        -- 游戏付费（60天）
        CONCAT('cashpay_amt_60d:', COALESCE(CAST(sum_cashpay_amt_60d AS STRING), '0')),
        CONCAT('cashpay_cnt_60d:', COALESCE(CAST(sum_cashpay_cnt_60d AS STRING), '0')),
        CONCAT('couponpay_amt_60d:', COALESCE(CAST(sum_couponpay_amt_60d AS STRING), '0')),
        CONCAT('couponpay_cnt_60d:', COALESCE(CAST(sum_couponpay_cnt_60d AS STRING), '0')),

        -- 游戏行为
        CONCAT('game_search_top10_7d:', COALESCE(game_search_top10_7d, 'none')),
        CONCAT('game_search_top10_30d:', COALESCE(game_search_top10_30d, 'none')),
        CONCAT('client_browse_pkg:', COALESCE(client_browse_pkg, 'none')),
        CONCAT('search_keywords:', COALESCE(search_keywords, 'none')),

        -- 游戏分类付费
        CONCAT('game_category_pay_30d:', COALESCE(game_category_pay_30d, 'none')),
        CONCAT('game_category_pay_90d:', COALESCE(game_category_pay_90d, 'none')),

        -- 用户等级
        CONCAT('game_lifecycle:', COALESCE(CAST(game_lifecycle AS STRING), 'unknown')),
        CONCAT('big_r_level_1:', COALESCE(CAST(big_r_level_1 AS STRING), 'unknown')),
        CONCAT('big_r_level_2:', COALESCE(CAST(big_r_level_2 AS STRING), 'unknown')),
        CONCAT('big_r_level_3:', COALESCE(CAST(big_r_level_3 AS STRING), 'unknown')),

        -- 内容偏好
        CONCAT('content_keywords:', COALESCE(content_keywords, 'none'))
    ) AS user_profile_features
FROM biads.ads_usidpersona_inf_game_payment_intention_new_dm
WHERE pt_d = '20260310'
  AND usid IN (SELECT usid FROM adhoctemp.tmp_l00527489_20260317_game_payment_sample_pool);


-- ============================================================================
-- 阶段 3：APP 行为数据表（特征期：2月9日-3月10日，30天）
-- ============================================================================

-- Step 3.1: 提取 APP 事件明细（合并使用行为和安装卸载行为）
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260317_app_events;
CREATE TABLE adhoctemp.tmp_l00527489_20260317_app_events (
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
    app.adid AS usid,
    app.pt_d AS event_date,
    'appUsage' AS event_type,
    COALESCE(app_info.promote_app_name, app.package_name) AS app_name,
    app.package_name,
    COALESCE(app.usage_duration, 0) AS usage_duration,
    COALESCE(app_info.promote_app_category, 'unknown') AS app_category
FROM pps.dwd_pps_appdata_appusage_dm app
LEFT JOIN pps.dim_pps_metric_promoted_app_info_hs app_info
    ON app.package_name = app_info.promote_app_pkg
    AND app_info.pt_h = '2026031023'
WHERE app.pt_d >= '20260209' AND app.pt_d <= '20260310'
  AND app.adid IN (SELECT usid FROM adhoctemp.tmp_l00527489_20260317_game_payment_sample_pool);

-- 插入安装/卸载/更新行为数据
INSERT INTO adhoctemp.tmp_l00527489_20260317_app_events
SELECT
    iu.adid AS usid,
    iu.pt_d AS event_date,
    iu.event_type,
    COALESCE(app_info.promote_app_name, iu.package_name) AS app_name,
    iu.package_name,
    0 AS usage_duration,
    COALESCE(app_info.promote_app_category, 'unknown') AS app_category
FROM pps.dwd_pps_appdata_install_uninstall_update_dm iu
LEFT JOIN pps.dim_pps_metric_promoted_app_info_hs app_info
    ON iu.package_name = app_info.promote_app_pkg
    AND app_info.pt_h = '2026031023'
WHERE iu.pt_d >= '20260209' AND iu.pt_d <= '20260310'
  AND iu.adid IN (SELECT usid FROM adhoctemp.tmp_l00527489_20260317_game_payment_sample_pool);

-- Step 3.2: 构建 APP 行为序列
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260317_game_payment_app_behavior;
CREATE TABLE adhoctemp.tmp_l00527489_20260317_game_payment_app_behavior (
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
CREATE TABLE adhoctemp.tmp_l00527489_20260317_historical_events (
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
    did AS usid,
    CONCAT(SUBSTR(pt_d, 1, 4), '-W',
           LPAD(CAST(WEEKOFYEAR(FROM_UNIXTIME(UNIX_TIMESTAMP(pt_d, 'yyyyMMdd'))) AS STRING), 2, '0')
    ) AS event_period,
    'historical' AS period_type,
    SUM(CASE WHEN received_total_imp > 0 THEN received_total_imp ELSE 0 END) AS impression_cnt,
    CONCAT_WS(',', COLLECT_SET(CASE WHEN received_total_imp > 0 THEN CONCAT(COALESCE(cust_industry_level1, '未知'), '-', COALESCE(cust_industry_level2, '未知')) ELSE NULL END)) AS impression_industries,
    CONCAT_WS(',', COLLECT_SET(CASE WHEN received_total_imp > 0 THEN position_name ELSE NULL END)) AS impression_positions,
    SUM(CASE WHEN received_total_click > 0 THEN received_total_click ELSE 0 END) AS click_cnt,
    CONCAT_WS(',', COLLECT_SET(CASE WHEN received_total_click > 0 THEN CONCAT(COALESCE(cust_industry_level1, '未知'), '-', COALESCE(cust_industry_level2, '未知')) ELSE NULL END)) AS click_industries,
    CONCAT_WS(',', COLLECT_SET(CASE WHEN received_total_click > 0 THEN position_name ELSE NULL END)) AS click_positions,
    SUM(CASE WHEN event_type NOT IN ('repeatedImp','skip','playStart','playPause','webclose','intentSuccess','appOpen','webopen') AND total_task_cnvr_target_cnvr_cnt > 0 THEN total_task_cnvr_target_cnvr_cnt ELSE 0 END) AS conversion_cnt,
    CONCAT_WS(',', COLLECT_SET(CASE WHEN event_type NOT IN ('repeatedImp','skip','playStart','playPause','webclose','intentSuccess','appOpen','webopen') AND total_task_cnvr_target_cnvr_cnt > 0 THEN CONCAT(COALESCE(cust_industry_level1, '未知'), '-', COALESCE(cust_industry_level2, '未知')) ELSE NULL END)) AS conversion_industries,
    CONCAT_WS(',', COLLECT_SET(CASE WHEN event_type NOT IN ('repeatedImp','skip','playStart','playPause','webclose','intentSuccess','appOpen','webopen') AND total_task_cnvr_target_cnvr_cnt > 0 THEN promote_app_name ELSE NULL END)) AS conversion_targets
FROM pps.ads_pps_user_base_indicator_dm
WHERE pt_d >= '20260209' AND pt_d <= '20260228'
  AND did IN (SELECT usid FROM adhoctemp.tmp_l00527489_20260317_game_payment_sample_pool)
GROUP BY did,
         CONCAT(SUBSTR(pt_d, 1, 4), '-W',
                LPAD(CAST(WEEKOFYEAR(FROM_UNIXTIME(UNIX_TIMESTAMP(pt_d, 'yyyyMMdd'))) AS STRING), 2, '0'));

-- Step 4.2: 近期明细（3月1日-3月10日）- 保留每日明细，避免标签泄露
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260317_recent_events;
CREATE TABLE adhoctemp.tmp_l00527489_20260317_recent_events (
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
    did AS usid,
    pt_d AS event_period,
    'recent' AS period_type,
    SUM(CASE WHEN received_total_imp > 0 THEN received_total_imp ELSE 0 END) AS impression_cnt,
    CONCAT_WS(',', COLLECT_SET(CASE WHEN received_total_imp > 0 THEN CONCAT(COALESCE(cust_industry_level1, '未知'), '-', COALESCE(cust_industry_level2, '未知')) ELSE NULL END)) AS impression_industries,
    CONCAT_WS(',', COLLECT_SET(CASE WHEN received_total_imp > 0 THEN position_name ELSE NULL END)) AS impression_positions,
    SUM(CASE WHEN received_total_click > 0 THEN received_total_click ELSE 0 END) AS click_cnt,
    CONCAT_WS(',', COLLECT_SET(CASE WHEN received_total_click > 0 THEN CONCAT(COALESCE(cust_industry_level1, '未知'), '-', COALESCE(cust_industry_level2, '未知')) ELSE NULL END)) AS click_industries,
    CONCAT_WS(',', COLLECT_SET(CASE WHEN received_total_click > 0 THEN position_name ELSE NULL END)) AS click_positions,
    SUM(CASE WHEN event_type NOT IN ('repeatedImp','skip','playStart','playPause','webclose','intentSuccess','appOpen','webopen') AND total_task_cnvr_target_cnvr_cnt > 0 THEN total_task_cnvr_target_cnvr_cnt ELSE 0 END) AS conversion_cnt,
    CONCAT_WS(',', COLLECT_SET(CASE WHEN event_type NOT IN ('repeatedImp','skip','playStart','playPause','webclose','intentSuccess','appOpen','webopen') AND total_task_cnvr_target_cnvr_cnt > 0 THEN CONCAT(COALESCE(cust_industry_level1, '未知'), '-', COALESCE(cust_industry_level2, '未知')) ELSE NULL END)) AS conversion_industries,
    CONCAT_WS(',', COLLECT_SET(CASE WHEN event_type NOT IN ('repeatedImp','skip','playStart','playPause','webclose','intentSuccess','appOpen','webopen') AND total_task_cnvr_target_cnvr_cnt > 0 THEN promote_app_name ELSE NULL END)) AS conversion_targets
FROM pps.ads_pps_user_base_indicator_dm
WHERE pt_d >= '20260301' AND pt_d <= '20260310'
  AND did IN (SELECT usid FROM adhoctemp.tmp_l00527489_20260317_game_payment_sample_pool)
GROUP BY did, pt_d;

-- Step 4.3: 合并历史和近期事件
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260317_all_events;
CREATE TABLE adhoctemp.tmp_l00527489_20260317_all_events (
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
SELECT * FROM adhoctemp.tmp_l00527489_20260317_historical_events
UNION ALL
SELECT * FROM adhoctemp.tmp_l00527489_20260317_recent_events;

-- Step 4.4: 构建事件序列字符串
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260317_event_sequences;
CREATE TABLE adhoctemp.tmp_l00527489_20260317_event_sequences (
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
FROM adhoctemp.tmp_l00527489_20260317_all_events
WHERE impression_cnt > 0 OR click_cnt > 0 OR conversion_cnt > 0;

-- Step 4.5: 按用户聚合，构建时间倒序序列
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260317_game_payment_ad_events;
CREATE TABLE adhoctemp.tmp_l00527489_20260317_game_payment_ad_events (
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
CREATE TABLE adhoctemp.tmp_l00527489_20260317_game_payment_final_wide_table (
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
