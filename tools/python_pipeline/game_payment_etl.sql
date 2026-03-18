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
        CONCAT('性别:', CASE
            WHEN gender_new_dev = 'g_m' THEN '男性'
            WHEN gender_new_dev = 'g_f' THEN '女性'
            ELSE 'unknown'
        END),
        CONCAT('年龄:', CASE
            WHEN forecast_age_dev = '1' THEN '18岁以内(少年)'
            WHEN forecast_age_dev = '2' THEN '18~23岁(青年)'
            WHEN forecast_age_dev = '3' THEN '24~34岁(青年)'
            WHEN forecast_age_dev = '4' THEN '35~44岁(中年)'
            WHEN forecast_age_dev = '5' THEN '45~54岁(中年)'
            WHEN forecast_age_dev = '6' THEN '55岁及以上(老年)'
            ELSE 'unknown'
        END),
        CONCAT('学历:', CASE
            WHEN education_dev = '1' THEN '大学及以上'
            WHEN education_dev = '0' THEN '高中及以下'
            ELSE 'unknown'
        END),

        -- 设备属性
        CONCAT('设备传播命:', COALESCE(CAST(product_new_dev AS STRING), '0'), '元'),
        CONCAT('设备品牌:', COALESCE(CAST(brand_new_dev AS STRING), 'unknown')),
        CONCAT('设备系列:', COALESCE(CAST(series_new_dev AS STRING), 'unknown')),
        CONCAT('激活天数:', COALESCE(CAST(active_duration_dev AS STRING), '0'), '天'),
        CONCAT('月在线天数:', COALESCE(CAST(push_online_days_30d_dev AS STRING), '0'), '天'),

        -- 经济属性
        CONCAT('有房:', CASE
            WHEN owner_house_flag_dev = '1' THEN '是'
            ELSE '否'
        END),
        CONCAT('有车:', CASE
            WHEN owner_cars_user_dev = '1' THEN '是'
            ELSE '否'
        END),
        CONCAT('消费频率:', CASE
            WHEN consume_frequency_dev = 'p1' THEN '极高'
            WHEN consume_frequency_dev = 'p2' THEN '高'
            WHEN consume_frequency_dev = 'p3' THEN '较高'
            WHEN consume_frequency_dev = 'p4' THEN '中'
            WHEN consume_frequency_dev = 'p5' THEN '低'
            ELSE 'unknown'
        END),
        CONCAT('信用卡使用:', CASE
            WHEN consume_credit_card_level_dev = 'p1' THEN '极高'
            WHEN consume_credit_card_level_dev = 'p2' THEN '高'
            WHEN consume_credit_card_level_dev = 'p3' THEN '较高'
            WHEN consume_credit_card_level_dev = 'p4' THEN '中'
            WHEN consume_credit_card_level_dev = 'p5' THEN '低'
            ELSE 'unknown'
        END),

        -- 游戏付费（30天）
        CONCAT('游戏付费30天现金付费金额:', COALESCE(CAST(sum_cashpay_amt_30d AS STRING), '0'), '元'),
        CONCAT('游戏付费30天现金付费次数:', COALESCE(CAST(cashpay_cnt_30d AS STRING), '0'), '次'),
        CONCAT('游戏付费30天优惠券付费金额:', COALESCE(CAST(sum_couponpay_amt_30d AS STRING), '0'), '元'),
        CONCAT('游戏付费30天优惠券付费次数:', COALESCE(CAST(couponpay_cnt_30d AS STRING), '0'), '次'),

        -- 游戏付费（60天）
        CONCAT('游戏付费60天现金付费金额:', COALESCE(CAST(sum_cashpay_amt_60d AS STRING), '0'), '元'),
        CONCAT('游戏付费60天现金付费次数:', COALESCE(CAST(cashpay_cnt_60d AS STRING), '0'), '次'),
        CONCAT('游戏付费60天优惠券付费金额:', COALESCE(CAST(sum_couponpay_amt_60d AS STRING), '0'), '元'),
        CONCAT('游戏付费60天优惠券付费次数:', COALESCE(CAST(couponpay_cnt_60d AS STRING), '0'), '次'),

        -- 游戏行为
        CONCAT('7天游戏搜索TOP10:', COALESCE(game_search_tfidf_7d_list, 'none')),
        CONCAT('30天游戏搜索TOP10:', COALESCE(game_search_tfidf_30d_list, 'none')),
        CONCAT('端侧浏览应用包名:', COALESCE(ha_view_packages, 'none')),
        CONCAT('搜索关键词:', COALESCE(search_keywords_dev, 'none')),

        -- 游戏分类付费
        CONCAT('30天游戏分类付费:', COALESCE(game_category_pay_30days, 'none')),
        CONCAT('90天游戏分类付费:', COALESCE(game_category_pay_90days, 'none')),
 
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
    event_type STRING COMMENT '事件类型：appUsage/appInstall/appUninstall',
    app_name STRING COMMENT '应用名称',
    usage_duration BIGINT COMMENT '使用时长（秒，仅appUsage有值）',
    row_num BIGINT COMMENT '排序序号'
) COMMENT 'APP事件明细表（合并使用和安装卸载数据）';

-- 插入使用行为数据（最近7天每天TOP30，7天之前TOP100）
INSERT INTO adhoctemp.tmp_l00527489_20260317_app_events
SELECT
    usid,
    event_date,
    event_type,
    app_name,
    usage_duration,
    row_num
FROM (
    -- 最近7天（3/4-3/10）：每天TOP30
    SELECT
        bind.usid,
        app.pt_d AS event_date,
        'appUsage' AS event_type,
        COALESCE(app_info.promote_app_name, app.package_name) AS app_name,
        CAST(COALESCE(app.total_time, 0) / 1000 AS BIGINT) AS usage_duration,
        ROW_NUMBER() OVER (PARTITION BY bind.usid, app.pt_d ORDER BY CAST(COALESCE(app.total_time, 0) AS BIGINT) DESC) AS row_num
    FROM pps.dwd_pps_appdata_appusage_dm app
    INNER JOIN (
        SELECT dsid, usid
        FROM bicoredata.dwd_pty_combine_device_up_bind_ds
        WHERE pt_d = '20260304'
    ) bind ON app.adid = bind.dsid
    LEFT JOIN (
        SELECT promote_app_pkg, promote_app_name
        FROM pps.dim_pps_metric_promoted_app_info_hs
        WHERE pt_h = '2026031023'
    ) app_info ON app.package_name = app_info.promote_app_pkg
    WHERE app.pt_d >= '20260304' AND app.pt_d <= '20260310'
      AND bind.usid IN (SELECT usid FROM adhoctemp.tmp_l00527489_20260317_game_payment_sample_pool)
      AND COALESCE(app_info.promote_app_name, app.package_name) NOT IN ('日历','联系人','设置','相机','滚动截屏','华为桌面','信息','电话','System Share','图库','文件','时钟','计算器')
) t1
WHERE row_num <= 30

UNION ALL

SELECT
    usid,
    event_date,
    event_type,
    app_name,
    usage_duration,
    row_num
FROM (
    -- 7天之前（2/9-3/3）：总共TOP100
    SELECT
        bind.usid,
        app.pt_d AS event_date,
        'appUsage' AS event_type,
        COALESCE(app_info.promote_app_name, app.package_name) AS app_name,
        CAST(COALESCE(app.total_time, 0) / 1000 AS BIGINT) AS usage_duration,
        ROW_NUMBER() OVER (PARTITION BY bind.usid ORDER BY CAST(COALESCE(app.total_time, 0) AS BIGINT) DESC) AS row_num
    FROM pps.dwd_pps_appdata_appusage_dm app
    INNER JOIN (
        SELECT dsid, usid
        FROM bicoredata.dwd_pty_combine_device_up_bind_ds
        WHERE pt_d = '20260304'
    ) bind ON app.adid = bind.dsid
    LEFT JOIN (
        SELECT promote_app_pkg, promote_app_name
        FROM pps.dim_pps_metric_promoted_app_info_hs
        WHERE pt_h = '2026031023'
    ) app_info ON app.package_name = app_info.promote_app_pkg
    WHERE app.pt_d >= '20260209' AND app.pt_d < '20260304'
      AND bind.usid IN (SELECT usid FROM adhoctemp.tmp_l00527489_20260317_game_payment_sample_pool)
      AND COALESCE(app_info.promote_app_name, app.package_name) NOT IN ('日历','联系人','设置','相机','滚动截屏','华为桌面','信息','电话','System Share','图库','文件','时钟','计算器')
) t2
WHERE row_num <= 100;

-- 插入安装行为数据（最近1000次）
INSERT INTO adhoctemp.tmp_l00527489_20260317_app_events
SELECT
    usid,
    event_date,
    event_type,
    app_name,
    0 AS usage_duration,
    row_num
FROM (
    SELECT
        bind.usid,
        iu.pt_d AS event_date,
        'appInstall' AS event_type,
        COALESCE(app_info.promote_app_name, iu.package_name) AS app_name,
        ROW_NUMBER() OVER (PARTITION BY bind.usid ORDER BY iu.pt_d DESC, iu.report_timestamp DESC) AS row_num
    FROM pps.dwd_pps_appdata_install_uninstall_update_dm iu
    INNER JOIN (
        SELECT dsid, usid
        FROM bicoredata.dwd_pty_combine_device_up_bind_ds
        WHERE pt_d = '20260304'
    ) bind ON iu.adid = bind.dsid
    LEFT JOIN (
        SELECT promote_app_pkg, promote_app_name
        FROM pps.dim_pps_metric_promoted_app_info_hs
        WHERE pt_h = '2026031023'
    ) app_info ON iu.package_name = app_info.promote_app_pkg
    WHERE iu.pt_d >= '20260209' AND iu.pt_d <= '20260310'
      AND iu.event_type = 'appInstall'
      AND bind.usid IN (SELECT usid FROM adhoctemp.tmp_l00527489_20260317_game_payment_sample_pool)
      AND COALESCE(app_info.promote_app_name, iu.package_name) NOT IN ('日历','联系人','设置','相机','滚动截屏','华为桌面','信息','电话','System Share','图库','文件','时钟','计算器')
) t
WHERE row_num <= 100;

-- 插入卸载行为数据（最近100次）
INSERT INTO adhoctemp.tmp_l00527489_20260317_app_events
SELECT
    usid,
    event_date,
    event_type,
    app_name,
    0 AS usage_duration,
    row_num
FROM (
    SELECT
        bind.usid,
        iu.pt_d AS event_date,
        'appUninstall' AS event_type,
        COALESCE(app_info.promote_app_name, iu.package_name) AS app_name,
        ROW_NUMBER() OVER (PARTITION BY bind.usid ORDER BY iu.pt_d DESC, iu.report_timestamp DESC) AS row_num
    FROM pps.dwd_pps_appdata_install_uninstall_update_dm iu
    INNER JOIN (
        SELECT dsid, usid
        FROM bicoredata.dwd_pty_combine_device_up_bind_ds
        WHERE pt_d = '20260304'
    ) bind ON iu.adid = bind.dsid
    LEFT JOIN (
        SELECT promote_app_pkg, promote_app_name
        FROM pps.dim_pps_metric_promoted_app_info_hs
        WHERE pt_h = '2026031023'
    ) app_info ON iu.package_name = app_info.promote_app_pkg
    WHERE iu.pt_d >= '20260209' AND iu.pt_d <= '20260310'
      AND iu.event_type = 'appUninstall'
      AND bind.usid IN (SELECT usid FROM adhoctemp.tmp_l00527489_20260317_game_payment_sample_pool)
      AND COALESCE(app_info.promote_app_name, iu.package_name) NOT IN ('日历','联系人','设置','相机','滚动截屏','华为桌面','信息','电话','System Share','图库','文件','时钟','计算器')
) t
WHERE row_num <= 100;

-- Step 3.2: 构建 APP 行为序列（CSV表格格式）
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260317_game_payment_app_behavior;
CREATE TABLE IF NOT EXISTS adhoctemp.tmp_l00527489_20260317_game_payment_app_behavior (
    usid STRING COMMENT '用户标识',
    app_behavior_seq STRING COMMENT 'APP行为序列（CSV表格格式）'
) COMMENT 'APP行为序列表';

INSERT INTO adhoctemp.tmp_l00527489_20260317_game_payment_app_behavior
SELECT
    usid,
    CONCAT(
        '日期,行为类型,应用名称,使用时长(秒)\n',
        CONCAT_WS('\n',
            SORT_ARRAY(
                COLLECT_LIST(
                    CONCAT(
                        event_date, ',',
                        CASE
                            WHEN event_type = 'appUsage' THEN '使用'
                            WHEN event_type = 'appInstall' THEN '安装'
                            WHEN event_type = 'appUninstall' THEN '卸载'
                            ELSE event_type
                        END, ',',
                        app_name, ',',
                        CAST(usage_duration AS STRING)
                    )
                ),
                FALSE
            )
        )
    ) AS app_behavior_seq
FROM adhoctemp.tmp_l00527489_20260317_app_events
GROUP BY usid;


-- ============================================================================
-- 阶段 4：广告事件数据表（特征期：2月9日-3月10日，避免标签泄露）
-- ============================================================================

-- Step 4.1: 收集广告事件明细（曝光、点击、转化各保留最近100条）
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260317_ad_event_details;
CREATE TABLE IF NOT EXISTS adhoctemp.tmp_l00527489_20260317_ad_event_details (
    usid STRING COMMENT '用户标识',
    event_date STRING COMMENT '事件日期',
    event_type STRING COMMENT '事件类型：impression/click/conversion',
    industry_level1 STRING COMMENT '一级行业',
    industry_level2 STRING COMMENT '二级行业',
    position_name STRING COMMENT '版位名称',
    promote_app_name STRING COMMENT '推广应用名称',
    event_count BIGINT COMMENT '事件次数',
    row_num BIGINT COMMENT '排序序号'
) COMMENT '广告事件明细表';

-- 插入曝光事件（最近100条）
INSERT INTO adhoctemp.tmp_l00527489_20260317_ad_event_details
SELECT
    usid,
    event_date,
    event_type,
    industry_level1,
    industry_level2,
    position_name,
    promote_app_name,
    event_count,
    row_num
FROM (
    SELECT
        bind.usid,
        ind.pt_d AS event_date,
        'impression' AS event_type,
        COALESCE(ind.cust_industry_level1, '未知') AS industry_level1,
        COALESCE(ind.cust_industry_level2, '未知') AS industry_level2,
        COALESCE(ind.position_name, '未知版位') AS position_name,
        COALESCE(ind.promote_app_name, '未知应用') AS promote_app_name,
        ind.received_total_imp AS event_count,
        ROW_NUMBER() OVER (PARTITION BY bind.usid ORDER BY ind.pt_d DESC, ind.received_total_imp DESC) AS row_num
    FROM pps.ads_pps_user_base_indicator_dm ind
    INNER JOIN (
        SELECT dsid, usid
        FROM bicoredata.dwd_pty_combine_device_up_bind_ds
        WHERE pt_d = '20260304'
    ) bind ON ind.did = bind.dsid
    WHERE ind.pt_d >= '20260209' AND ind.pt_d <= '20260310'
      AND bind.usid IN (SELECT usid FROM adhoctemp.tmp_l00527489_20260317_game_payment_sample_pool)
      AND ind.received_total_imp > 0
) t
WHERE row_num <= 100;

-- 插入点击事件（最近100条）
INSERT INTO adhoctemp.tmp_l00527489_20260317_ad_event_details
SELECT
    usid,
    event_date,
    event_type,
    industry_level1,
    industry_level2,
    position_name,
    promote_app_name,
    event_count,
    row_num
FROM (
    SELECT
        bind.usid,
        ind.pt_d AS event_date,
        'click' AS event_type,
        COALESCE(ind.cust_industry_level1, '未知') AS industry_level1,
        COALESCE(ind.cust_industry_level2, '未知') AS industry_level2,
        COALESCE(ind.position_name, '未知版位') AS position_name,
        COALESCE(ind.promote_app_name, '未知应用') AS promote_app_name,
        ind.received_total_click AS event_count,
        ROW_NUMBER() OVER (PARTITION BY bind.usid ORDER BY ind.pt_d DESC, ind.received_total_click DESC) AS row_num
    FROM pps.ads_pps_user_base_indicator_dm ind
    INNER JOIN (
        SELECT dsid, usid
        FROM bicoredata.dwd_pty_combine_device_up_bind_ds
        WHERE pt_d = '20260304'
    ) bind ON ind.did = bind.dsid
    WHERE ind.pt_d >= '20260209' AND ind.pt_d <= '20260310'
      AND bind.usid IN (SELECT usid FROM adhoctemp.tmp_l00527489_20260317_game_payment_sample_pool)
      AND ind.received_total_click > 0
) t
WHERE row_num <= 100;

-- 插入转化事件（最近100条）
INSERT INTO adhoctemp.tmp_l00527489_20260317_ad_event_details
SELECT
    usid,
    event_date,
    event_type,
    industry_level1,
    industry_level2,
    position_name,
    promote_app_name,
    event_count,
    row_num
FROM (
    SELECT
        bind.usid,
        ind.pt_d AS event_date,
        'conversion' AS event_type,
        COALESCE(ind.cust_industry_level1, '未知') AS industry_level1,
        COALESCE(ind.cust_industry_level2, '未知') AS industry_level2,
        COALESCE(ind.position_name, '未知版位') AS position_name,
        COALESCE(ind.promote_app_name, '未知应用') AS promote_app_name,
        ind.total_task_cnvr_target_cnvr_cnt AS event_count,
        ROW_NUMBER() OVER (PARTITION BY bind.usid ORDER BY ind.pt_d DESC, ind.total_task_cnvr_target_cnvr_cnt DESC) AS row_num
    FROM pps.ads_pps_user_base_indicator_dm ind
    INNER JOIN (
        SELECT dsid, usid
        FROM bicoredata.dwd_pty_combine_device_up_bind_ds
        WHERE pt_d = '20260304'
    ) bind ON ind.did = bind.dsid
    WHERE ind.pt_d >= '20260209' AND ind.pt_d <= '20260310'
      AND bind.usid IN (SELECT usid FROM adhoctemp.tmp_l00527489_20260317_game_payment_sample_pool)
      AND ind.event_type NOT IN ('repeatedImp','skip','playStart','playPause','webclose','intentSuccess','appOpen','webopen')
      AND ind.total_task_cnvr_target_cnvr_cnt > 0
) t
WHERE row_num <= 100;

-- Step 4.2: 计算异常用户标记（基于全量数据统计）
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260317_abnormal_users;
CREATE TABLE IF NOT EXISTS adhoctemp.tmp_l00527489_20260317_abnormal_users (
    usid STRING COMMENT '用户标识',
    total_impression_cnt BIGINT COMMENT '总曝光次数',
    total_click_cnt BIGINT COMMENT '总点击次数',
    total_conversion_cnt BIGINT COMMENT '总转化次数',
    abnormal_user_flag STRING COMMENT '异常用户标记'
) COMMENT '异常用户标记表';

INSERT INTO adhoctemp.tmp_l00527489_20260317_abnormal_users
SELECT
    bind.usid,
    SUM(COALESCE(ind.received_total_imp, 0)) AS total_impression_cnt,
    SUM(COALESCE(ind.received_total_click, 0)) AS total_click_cnt,
    SUM(CASE WHEN ind.event_type NOT IN ('repeatedImp','skip','playStart','playPause','webclose','intentSuccess','appOpen','webopen')
        THEN COALESCE(ind.total_task_cnvr_target_cnvr_cnt, 0) ELSE 0 END) AS total_conversion_cnt,
    CASE
        WHEN SUM(COALESCE(ind.received_total_imp, 0)) > 10000 THEN '异常（曝光过多）'
        WHEN SUM(COALESCE(ind.received_total_click, 0)) > 1000 THEN '异常（点击过多）'
        WHEN SUM(CASE WHEN ind.event_type NOT IN ('repeatedImp','skip','playStart','playPause','webclose','intentSuccess','appOpen','webopen')
                 THEN COALESCE(ind.total_task_cnvr_target_cnvr_cnt, 0) ELSE 0 END) > 500 THEN '异常（转化过多）'
        ELSE '正常'
    END AS abnormal_user_flag
FROM pps.ads_pps_user_base_indicator_dm ind
INNER JOIN (
    SELECT dsid, usid
    FROM bicoredata.dwd_pty_combine_device_up_bind_ds
    WHERE pt_d = '20260304'
) bind ON ind.did = bind.dsid
WHERE ind.pt_d >= '20260209' AND ind.pt_d <= '20260310'
  AND bind.usid IN (SELECT usid FROM adhoctemp.tmp_l00527489_20260317_game_payment_sample_pool)
GROUP BY bind.usid;

-- Step 4.3: 构建广告事件序列（CSV表格格式）
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260317_game_payment_ad_events;
CREATE TABLE IF NOT EXISTS adhoctemp.tmp_l00527489_20260317_game_payment_ad_events (
    usid STRING COMMENT '用户标识',
    ad_event_seq STRING COMMENT '广告事件序列（CSV表格格式）'
) COMMENT '广告事件序列表';

INSERT INTO adhoctemp.tmp_l00527489_20260317_game_payment_ad_events
SELECT
    usid,
    CONCAT(
        '日期,事件类型,一级行业,二级行业,版位,推广应用,次数\n',
        CONCAT_WS('\n',
            SORT_ARRAY(
                COLLECT_LIST(
                    CONCAT(
                        event_date, ',',
                        CASE
                            WHEN event_type = 'impression' THEN '曝光'
                            WHEN event_type = 'click' THEN '点击'
                            WHEN event_type = 'conversion' THEN '转化'
                            ELSE event_type
                        END, ',',
                        industry_level1, ',',
                        industry_level2, ',',
                        position_name, ',',
                        promote_app_name, ',',
                        CAST(event_count AS STRING)
                    )
                ),
                FALSE
            )
        )
    ) AS ad_event_seq
FROM adhoctemp.tmp_l00527489_20260317_ad_event_details
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
    abnormal_user_flag STRING COMMENT '异常用户标记',
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
    COALESCE(ab.abnormal_user_flag, '正常') AS abnormal_user_flag,
    FROM_UNIXTIME(UNIX_TIMESTAMP()) AS create_time
FROM adhoctemp.tmp_l00527489_20260317_game_payment_sample_pool s
LEFT JOIN adhoctemp.tmp_l00527489_20260317_game_payment_user_profile p ON s.usid = p.usid
LEFT JOIN adhoctemp.tmp_l00527489_20260317_game_payment_app_behavior a ON s.usid = a.usid
LEFT JOIN adhoctemp.tmp_l00527489_20260317_game_payment_ad_events e ON s.usid = e.usid
LEFT JOIN adhoctemp.tmp_l00527489_20260317_abnormal_users ab ON s.usid = ab.usid;


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

-- 5. 异常用户统计
SELECT
    abnormal_user_flag,
    COUNT(*) AS user_cnt,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) AS pct
FROM adhoctemp.tmp_l00527489_20260317_game_payment_final_wide_table
GROUP BY abnormal_user_flag;

-- 6. 样本数据预览（前10条）
SELECT
    usid,
    sample_label,
    total_payment_amt_7d,
    total_payment_cnt_7d,
    abnormal_user_flag,
    SUBSTR(user_profile_features, 1, 100) AS profile_preview,
    SUBSTR(app_behavior_seq, 1, 100) AS app_behavior_preview,
    SUBSTR(ad_event_seq, 1, 100) AS ad_event_preview
FROM adhoctemp.tmp_l00527489_20260317_game_payment_final_wide_table
LIMIT 10;
