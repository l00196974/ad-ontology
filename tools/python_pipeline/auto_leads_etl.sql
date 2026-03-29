-- ============================================================================
-- 汽车行业 线索意图预测 ETL SQL 方案（无 WITH 语法版本）
-- ============================================================================
-- 目标：构建正负样本特征宽表，用于大模型预测汽车购车意图（线索提交转化）
-- 正样本：3月20日及以后有线索转化（hicar_leads_postback，status=cleaned）的用户
-- 负样本（两部分）：
--   negative_click  : 特征期内有汽车行业广告点击、但无线索转化的用户（最多10000，强负样本）
--   negative_random : 大盘随机用户，排除正样本和汽车点击负样本（最多10000，弱负样本）
-- 输出：一个用户一行，包含画像特征（账号级）、APP行为序列（按设备分段）、
--        汽车/旅游行为序列、金融/电商行业行为序列（按设备分段）、广告事件序列
-- 时间切分：特征数据取3月20日及之前，标签数据取3月20日及之后
-- ID映射：did=adid，通过 dwd_pty_combine_year_active_device_current_up_bind_ds 映射到 most_used_usid
-- 设备区分：行为数据按设备(dsid)分段，格式为"=== 设备{dsid} ===" 分隔，主键保持 usid
-- ============================================================================

-- ============================================================================
-- 所有建表语句（按执行顺序排列）
-- ============================================================================

-- 表1: 正样本表
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260329_auto_leads_positive_samples;
CREATE TABLE IF NOT EXISTS adhoctemp.tmp_l00527489_20260329_auto_leads_positive_samples (
    did STRING COMMENT '设备标识',
    usid STRING COMMENT '用户标识（通过did映射）',
    sample_label STRING COMMENT '样本标签',
    leads_cnt BIGINT COMMENT '线索提交次数（标签期：3月20日及以后）'
) COMMENT '正样本：标签期汽车线索转化用户（最多10000个）';

-- 表2a: 负样本-汽车点击用户表
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260329_auto_leads_negative_click;
CREATE TABLE IF NOT EXISTS adhoctemp.tmp_l00527489_20260329_auto_leads_negative_click (
    did STRING COMMENT '设备标识',
    usid STRING COMMENT '用户标识（通过did映射）',
    sample_label STRING COMMENT '样本标签：negative_click',
    leads_cnt BIGINT COMMENT '线索提交次数（负样本为0）'
) COMMENT '负样本（汽车点击）：特征期内有汽车广告点击、但无线索转化的用户（最多10000个）';

-- 表2b: 负样本-大盘随机用户表
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260329_auto_leads_negative_random;
CREATE TABLE IF NOT EXISTS adhoctemp.tmp_l00527489_20260329_auto_leads_negative_random (
    did STRING COMMENT '设备标识',
    usid STRING COMMENT '用户标识（通过did映射）',
    sample_label STRING COMMENT '样本标签：negative_random',
    leads_cnt BIGINT COMMENT '线索提交次数（负样本为0）'
) COMMENT '负样本（大盘随机）：排除正样本和汽车点击负样本的大盘随机用户（最多10000个）';

-- 表3: 样本池表（依赖表1、表2a、表2b）
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260329_auto_leads_sample_pool;
CREATE TABLE IF NOT EXISTS adhoctemp.tmp_l00527489_20260329_auto_leads_sample_pool (
    did STRING COMMENT '设备标识',
    usid STRING COMMENT '用户标识',
    sample_label STRING COMMENT '样本标签：positive/negative_click/negative_random',
    leads_cnt BIGINT COMMENT '线索提交次数'
) COMMENT '样本池：正负样本合并（正样本+汽车点击负样本+大盘随机负样本）';

-- 表4: 用户画像特征表（依赖表3）
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260329_auto_leads_user_profile;
CREATE TABLE IF NOT EXISTS adhoctemp.tmp_l00527489_20260329_auto_leads_user_profile (
    usid STRING COMMENT '用户标识',
    user_profile_features STRING COMMENT '用户画像特征（key:value;key:value格式）'
) COMMENT '用户画像特征表';

-- 表5: APP事件明细表（依赖表3）
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260329_auto_leads_app_events;
CREATE TABLE IF NOT EXISTS adhoctemp.tmp_l00527489_20260329_auto_leads_app_events (
    usid STRING COMMENT '用户标识',
    did STRING COMMENT '设备标识(dsid)',
    event_date STRING COMMENT '事件日期',
    event_type STRING COMMENT '事件类型：appUsage/appInstall/appUninstall',
    app_name STRING COMMENT '应用名称',
    usage_duration BIGINT COMMENT '使用时长（秒，仅appUsage有值）',
    row_num BIGINT COMMENT '排序序号'
) COMMENT 'APP事件明细表（合并使用和安装卸载数据，含设备标识）';

-- 表6: APP行为序列表（依赖表5）
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260329_auto_leads_app_behavior;
CREATE TABLE IF NOT EXISTS adhoctemp.tmp_l00527489_20260329_auto_leads_app_behavior (
    usid STRING COMMENT '用户标识',
    app_behavior_seq STRING COMMENT 'APP行为序列（CSV表格格式）'
) COMMENT 'APP行为序列表';

-- 表9: 汽车/旅游行为明细表（依赖表3）
-- 重点：汽车行业中 500_11_0009_1(汽车浏览/搜索) 和 500_11_0008_1(汽车APP点击) 是核心信号
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260329_auto_leads_travel_car_events;
CREATE TABLE IF NOT EXISTS adhoctemp.tmp_l00527489_20260329_auto_leads_travel_car_events (
    usid STRING COMMENT '用户标识',
    did STRING COMMENT '设备标识(dsid)',
    event_date STRING COMMENT '事件日期',
    behavior_type STRING COMMENT '行为描述（industry+behavior_type，来自dataid_mapping）',
    app_name STRING COMMENT '应用名称（来自appid_mapping，500_11_xxxx用ext_value1）',
    field1 STRING COMMENT '核心字段1（含义随data_id变化，见注释）',
    field2 STRING COMMENT '核心字段2（含义随data_id变化，见注释）',
    field3 STRING COMMENT '核心字段3（含义随data_id变化，见注释）',
    field4 STRING COMMENT '核心字段4（含义随data_id变化，见注释）',
    data_id STRING COMMENT '原始data_id，便于下游区分字段含义',
    row_num BIGINT COMMENT '排序序号'
) COMMENT '汽车/旅游行为明细表（字段含义按data_id区分，含设备标识）';

-- 表10: 汽车/旅游/本地生活行为序列表（依赖表9）
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260329_auto_leads_travel_car_behavior;
CREATE TABLE IF NOT EXISTS adhoctemp.tmp_l00527489_20260329_auto_leads_travel_car_behavior (
    usid STRING COMMENT '用户标识',
    travel_car_behavior_seq STRING COMMENT '汽车/旅游/本地生活行为序列（CSV表格格式）'
) COMMENT '汽车/旅游/本地生活行为序列表';

-- 表10a: 金融行业行为明细表（依赖表3）
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260329_auto_leads_finance_behavior_events;
CREATE TABLE IF NOT EXISTS adhoctemp.tmp_l00527489_20260329_auto_leads_finance_behavior_events (
    usid STRING COMMENT '用户标识',
    did STRING COMMENT '设备标识(dsid)',
    event_date STRING COMMENT '事件日期',
    behavior_type STRING COMMENT '行为描述（industry+behavior_type，来自dataid_mapping）',
    app_name STRING COMMENT '应用名称（来自appid_mapping）',
    ext_value2 STRING COMMENT '扩展字段2',
    ext_value3 STRING COMMENT '扩展字段3',
    ext_value4 STRING COMMENT '扩展字段4',
    ext_value5 STRING COMMENT '扩展字段5',
    data_id STRING COMMENT '原始data_id',
    row_num BIGINT COMMENT '排序序号'
) COMMENT '金融行业行为明细表（含设备标识，辅助特征：汽车贷款/保险意图）';

-- 表10b: 金融行业行为序列表（依赖表10a）
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260329_auto_leads_finance_behavior_seq;
CREATE TABLE IF NOT EXISTS adhoctemp.tmp_l00527489_20260329_auto_leads_finance_behavior_seq (
    usid STRING COMMENT '用户标识',
    finance_behavior_seq STRING COMMENT '金融行业行为序列（CSV表格格式）'
) COMMENT '金融行业行为序列表';

-- 表10e: 电商行业行为明细表（依赖表3）
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260329_auto_leads_ecom_industry_events;
CREATE TABLE IF NOT EXISTS adhoctemp.tmp_l00527489_20260329_auto_leads_ecom_industry_events (
    usid STRING COMMENT '用户标识',
    did STRING COMMENT '设备标识(dsid)',
    event_date STRING COMMENT '事件日期',
    behavior_type STRING COMMENT '行为描述（industry+behavior_type，来自dataid_mapping）',
    app_name STRING COMMENT '应用名称（来自appid_mapping）',
    category_l3_code STRING COMMENT '商品目录L3 code',
    category_l3_name STRING COMMENT '商品目录L3名称',
    goods_id STRING COMMENT '商品ID',
    data_id STRING COMMENT '原始data_id',
    row_num BIGINT COMMENT '排序序号'
) COMMENT '电商行业行为明细表（含设备标识）';

-- 表10f: 电商行业行为序列表（依赖表10e）
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260329_auto_leads_ecom_industry_seq;
CREATE TABLE IF NOT EXISTS adhoctemp.tmp_l00527489_20260329_auto_leads_ecom_industry_seq (
    usid STRING COMMENT '用户标识',
    ecom_industry_behavior_seq STRING COMMENT '电商行业行为序列（CSV表格格式）'
) COMMENT '电商行业行为序列表';

-- 表11: 广告事件明细表（依赖表3）
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260329_auto_leads_ad_event_details;
CREATE TABLE IF NOT EXISTS adhoctemp.tmp_l00527489_20260329_auto_leads_ad_event_details (
    usid STRING COMMENT '用户标识',
    did STRING COMMENT '设备标识(dsid)',
    event_date STRING COMMENT '事件日期',
    event_type STRING COMMENT '事件类型：impression/click/conversion',
    industry_level1 STRING COMMENT '一级行业',
    industry_level2 STRING COMMENT '二级行业',
    position_name STRING COMMENT '版位名称',
    promote_app_name STRING COMMENT '推广应用名称',
    creative_title STRING COMMENT '创意标题',
    creative_desc STRING COMMENT '创意描述',
    creative_label STRING COMMENT '创意标签',
    event_count BIGINT COMMENT '事件次数',
    row_num BIGINT COMMENT '排序序号'
) COMMENT '广告事件明细表（含设备标识）';

-- 表12: 异常用户标记表（依赖表3）
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260329_auto_leads_abnormal_users;
CREATE TABLE IF NOT EXISTS adhoctemp.tmp_l00527489_20260329_auto_leads_abnormal_users (
    usid STRING COMMENT '用户标识',
    total_impression_cnt BIGINT COMMENT '总曝光次数',
    total_click_cnt BIGINT COMMENT '总点击次数',
    total_conversion_cnt BIGINT COMMENT '总转化次数',
    abnormal_user_flag STRING COMMENT '异常用户标记'
) COMMENT '异常用户标记表';

-- 表13: 广告事件序列表（依赖表11）
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260329_auto_leads_ad_events;
CREATE TABLE IF NOT EXISTS adhoctemp.tmp_l00527489_20260329_auto_leads_ad_events (
    usid STRING COMMENT '用户标识',
    ad_event_seq STRING COMMENT '广告事件序列（CSV表格格式）'
) COMMENT '广告事件序列表';

-- 表14: 最终宽表（依赖表3、表4、表6、表10、表10b、表10f、表13、表12）
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260329_auto_leads_final_wide_table;
CREATE TABLE IF NOT EXISTS adhoctemp.tmp_l00527489_20260329_auto_leads_final_wide_table (
    usid STRING COMMENT '用户标识',
    sample_label STRING COMMENT '样本标签：positive/negative',
    leads_cnt BIGINT COMMENT '线索提交次数（标签期：3月20日及以后）',
    user_profile_features STRING COMMENT '用户画像特征（特征期：3月20日快照）',
    app_behavior_seq STRING COMMENT 'APP行为序列（特征期：2月19日-3月20日，30天）',
    travel_car_behavior_seq STRING COMMENT '汽车/旅游行为序列（特征期：2月19日-3月20日，重点汽车浏览/搜索/试驾）',
    finance_behavior_seq STRING COMMENT '金融行业行为序列（特征期：2月19日-3月20日，辅助特征）',
    ecom_industry_behavior_seq STRING COMMENT '电商行业行为序列（特征期：2月19日-3月20日）',
    ad_event_seq STRING COMMENT '广告事件序列（特征期：2月19日-3月20日）',
    abnormal_user_flag STRING COMMENT '异常用户标记',
    create_time STRING COMMENT '创建时间'
) COMMENT '最终特征宽表（特征期：3月20日及之前；标签期：3月20日及之后）';


-- ============================================================================
-- 阶段 1：样本池构建
-- ============================================================================

-- Step 1.1: 正样本 = 3月20日及之后有线索提交（status=cleaned）的用户，最多10000个
-- 正样本来源：bicoredata.dwd_evt_hicar_leads_postback_tf_dm
-- 条件：leads_create_time >= '2026-03-20'，pt_d >= '20260320'，status = 'cleaned'
-- ID映射：did → most_used_usid（设备-账号绑定表），过滤无法映射的 did（most_used_usid IS NULL）
-- 去重：同一 usid 对应多个 did 时合并计数，以 usid 为主键
INSERT INTO adhoctemp.tmp_l00527489_20260329_auto_leads_positive_samples
SELECT
    did,
    usid,
    'positive' AS sample_label,
    leads_cnt
FROM (
    SELECT
        -- 取该 usid 下任意一个 did（用于代表设备，后续行为取全部设备数据）
        MIN(leads.did) AS did,
        bind.most_used_usid AS usid,
        COUNT(1) AS leads_cnt
    FROM bicoredata.dwd_evt_hicar_leads_postback_tf_dm leads
    INNER JOIN (
        -- 强制映射：只保留能映射到 usid 的 did，过滤孤立设备
        SELECT dsid, most_used_usid
        FROM bicoredata.dwd_pty_combine_year_active_device_current_up_bind_ds
        WHERE pt_d = '20260320'
          AND most_used_usid IS NOT NULL
    ) bind ON leads.did = bind.dsid
    WHERE leads.pt_d >= '20260320'
      AND substr(leads.leads_create_time, 1, 10) >= '2026-03-20'
      AND leads.status = 'cleaned'
    GROUP BY bind.most_used_usid  -- 以 usid 为主键去重，同一账号多设备合并
) t
DISTRIBUTE BY RAND()
SORT BY RAND()
LIMIT 10000;

-- Step 1.2a: 负样本（汽车点击）= 特征期内有汽车行业广告点击、但无线索转化的用户，最多10000个
-- 来源：ads_pps_user_base_indicator_dm，过滤一级行业='汽车'且有点击的账号
-- 排除正样本 usid，以 usid 为主键去重
INSERT INTO adhoctemp.tmp_l00527489_20260329_auto_leads_negative_click
SELECT
    did,
    usid,
    'negative_click' AS sample_label,
    0 AS leads_cnt
FROM (
    SELECT
        MIN(bind.dsid) AS did,
        ind.usid
    FROM pps.ads_pps_user_base_indicator_dm ind
    INNER JOIN (
        SELECT dsid, most_used_usid
        FROM bicoredata.dwd_pty_combine_year_active_device_current_up_bind_ds
        WHERE pt_d = '20260320'
          AND most_used_usid IS NOT NULL
    ) bind ON ind.usid = bind.most_used_usid
    WHERE ind.pt_d >= '20260219' AND ind.pt_d <= '20260320'
      AND ind.cust_industry_level1 = '汽车'
      AND ind.received_total_click > 0
      AND ind.usid IS NOT NULL
      AND ind.usid NOT IN (SELECT usid FROM adhoctemp.tmp_l00527489_20260329_auto_leads_positive_samples)
    GROUP BY ind.usid  -- 以 usid 去重
) t
DISTRIBUTE BY RAND()
SORT BY RAND()
LIMIT 10000;

-- Step 1.2b: 负样本（大盘随机）= 大盘用户，排除正样本和汽车点击负样本，随机抽10000个
-- 排除逻辑均按 usid 比对，确保无账号级重叠
INSERT INTO adhoctemp.tmp_l00527489_20260329_auto_leads_negative_random
SELECT
    did,
    usid,
    'negative_random' AS sample_label,
    0 AS leads_cnt
FROM (
    SELECT
        MIN(bind.dsid) AS did,
        bind.most_used_usid AS usid
    FROM bicoredata.dwd_pty_combine_year_active_device_current_up_bind_ds bind
    WHERE bind.pt_d = '20260320'
      AND bind.most_used_usid IS NOT NULL
      AND bind.most_used_usid NOT IN (SELECT usid FROM adhoctemp.tmp_l00527489_20260329_auto_leads_positive_samples)
      AND bind.most_used_usid NOT IN (SELECT usid FROM adhoctemp.tmp_l00527489_20260329_auto_leads_negative_click)
    GROUP BY bind.most_used_usid  -- 以 usid 去重
) t
DISTRIBUTE BY RAND()
SORT BY RAND()
LIMIT 10000;

-- Step 1.3: 合并正负样本（三部分）
INSERT INTO adhoctemp.tmp_l00527489_20260329_auto_leads_sample_pool
SELECT did, usid, sample_label, leads_cnt
FROM adhoctemp.tmp_l00527489_20260329_auto_leads_positive_samples
UNION ALL
SELECT did, usid, sample_label, leads_cnt
FROM adhoctemp.tmp_l00527489_20260329_auto_leads_negative_click
UNION ALL
SELECT did, usid, sample_label, leads_cnt
FROM adhoctemp.tmp_l00527489_20260329_auto_leads_negative_random;


-- ============================================================================
-- 阶段 2：用户画像特征表（使用3月20日快照）
-- ============================================================================

INSERT INTO adhoctemp.tmp_l00527489_20260329_auto_leads_user_profile
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
        CONCAT('设备型号:', COALESCE(CAST(product_new_dev AS STRING), 'unknown')),
        CONCAT('设备品牌:', COALESCE(CAST(brand_new_dev AS STRING), 'unknown')),
        CONCAT('设备系列:', COALESCE(CAST(series_new_dev AS STRING), 'unknown')),
        CONCAT('激活天数:', COALESCE(CAST(active_duration_dev AS STRING), '0'), '天'),
        CONCAT('月在线天数:', COALESCE(CAST(push_online_days_30d_dev AS STRING), '0'), '天'),

        -- 经济属性（购车意图重要信号）
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

        -- 行为偏好
        CONCAT('7天游戏搜索TOP10:', COALESCE(game_search_tfidf_7d_list, 'none')),
        CONCAT('30天游戏搜索TOP10:', COALESCE(game_search_tfidf_30d_list, 'none')),
        CONCAT('端侧浏览应用包名:', COALESCE(ha_view_packages, 'none')),
        CONCAT('搜索关键词:', COALESCE(search_keywords_dev, 'none')),
        CONCAT('30天游戏分类付费:', COALESCE(game_category_pay_30days, 'none')),
        CONCAT('90天游戏分类付费:', COALESCE(game_category_pay_90days, 'none')),
        CONCAT('内容关键词:', COALESCE(content_keywords_dev, 'none'))
    ) AS user_profile_features
FROM biads.ads_usidpersona_inf_game_payment_intention_new_dm
WHERE pt_d = '20260320'
  AND usid IN (SELECT usid FROM adhoctemp.tmp_l00527489_20260329_auto_leads_sample_pool);


-- ============================================================================
-- 阶段 3：APP 行为数据表（特征期：2月19日-3月20日，30天）
-- ============================================================================

-- Step 3.1: 提取 APP 使用行为（最近7天每天TOP30）
INSERT INTO adhoctemp.tmp_l00527489_20260329_auto_leads_app_events
SELECT
    usid, did, event_date, event_type, app_name, usage_duration, row_num
FROM (
    SELECT
        usid, did, event_date, event_type, app_name, usage_duration,
        ROW_NUMBER() OVER (PARTITION BY usid, did, event_date ORDER BY usage_duration DESC) AS row_num
    FROM (
        SELECT
            bind.most_used_usid AS usid,
            bind.dsid AS did,
            app.pt_d AS event_date,
            'appUsage' AS event_type,
            COALESCE(app_info.promote_app_name, app.package_name) AS app_name,
            SUM(CAST(COALESCE(app.total_time, 0) / 1000 AS BIGINT)) AS usage_duration
        FROM pps.dwd_pps_appdata_appusage_dm app
        INNER JOIN (
            SELECT dsid, most_used_usid
            FROM bicoredata.dwd_pty_combine_year_active_device_current_up_bind_ds
            WHERE pt_d = '20260320'
        ) bind ON app.adid = bind.dsid
        LEFT JOIN (
            SELECT promote_app_pkg, promote_app_name
            FROM pps.dim_pps_metric_promoted_app_info_hs
            WHERE pt_h = '2026032023'
        ) app_info ON app.package_name = app_info.promote_app_pkg
        WHERE app.pt_d >= '20260314' AND app.pt_d <= '20260320'
          AND bind.most_used_usid IN (SELECT usid FROM adhoctemp.tmp_l00527489_20260329_auto_leads_sample_pool)
          AND app.package_name NOT IN (
              'com.huawei.android.launcher','com.android.mms','com.huawei.contacts',
              'com.huawei.android.internal.app','com.android.permissioncontroller','com.android.incallui',
              'com.hihonor.deskclock','com.hihonor.notepad','com.hihonor.mms','com.huawei.camera',
              'com.huawei.photos','com.huawei.himovie.local','com.android.systemui','com.android.settings',
              'com.huawei.HwMultiScreenShot','com.hihonor.android.launcher','com.hihonor.android.internal.app',
              'com.android.server.telecom','com.android.phone','com.android.packageinstaller',
              'com.android.gallery3d','com.android.deskclock',
              'com.huawei.systemmanager','com.huawei.android.hwouc','com.huawei.filemanager',
              'com.huawei.trustspace','com.huawei.android.instantshare','com.huawei.security.privacycenter',
              'com.huawei.hwid','com.huawei.calendar','com.huawei.deskclock','com.huawei.calculator',
              'com.huawei.hitouch','com.huawei.hmos.himovie.fa'
          )
          AND COALESCE(app_info.promote_app_name, app.package_name) NOT IN ('日历','联系人','设置','相机','滚动截屏','华为桌面','信息','电话','System Share','图库','文件','时钟','计算器','杂志锁屏')
        GROUP BY bind.most_used_usid, bind.dsid, app.pt_d, COALESCE(app_info.promote_app_name, app.package_name)
        HAVING SUM(CAST(COALESCE(app.total_time, 0) / 1000 AS BIGINT)) > 5
    ) agg
) t
WHERE row_num <= 30;

-- 7天之前总共TOP100（汇总）
INSERT INTO adhoctemp.tmp_l00527489_20260329_auto_leads_app_events
SELECT
    usid, did, event_date, event_type, app_name, usage_duration, row_num
FROM (
    SELECT
        usid, did, event_date, event_type, app_name, usage_duration,
        ROW_NUMBER() OVER (PARTITION BY usid, did ORDER BY usage_duration DESC) AS row_num
    FROM (
        SELECT
            bind.most_used_usid AS usid,
            bind.dsid AS did,
            app.pt_d AS event_date,
            'appUsage' AS event_type,
            COALESCE(app_info.promote_app_name, app.package_name) AS app_name,
            SUM(CAST(COALESCE(app.total_time, 0) / 1000 AS BIGINT)) AS usage_duration
        FROM pps.dwd_pps_appdata_appusage_dm app
        INNER JOIN (
            SELECT dsid, most_used_usid
            FROM bicoredata.dwd_pty_combine_year_active_device_current_up_bind_ds
            WHERE pt_d = '20260320'
        ) bind ON app.adid = bind.dsid
        LEFT JOIN (
            SELECT promote_app_pkg, promote_app_name
            FROM pps.dim_pps_metric_promoted_app_info_hs
            WHERE pt_h = '2026032023'
        ) app_info ON app.package_name = app_info.promote_app_pkg
        WHERE app.pt_d >= '20260219' AND app.pt_d < '20260314'
          AND bind.most_used_usid IN (SELECT usid FROM adhoctemp.tmp_l00527489_20260329_auto_leads_sample_pool)
          AND app.package_name NOT IN (
              'com.huawei.android.launcher','com.android.mms','com.huawei.contacts',
              'com.huawei.android.internal.app','com.android.permissioncontroller','com.android.incallui',
              'com.hihonor.deskclock','com.hihonor.notepad','com.hihonor.mms','com.huawei.camera',
              'com.huawei.photos','com.huawei.himovie.local','com.android.systemui','com.android.settings',
              'com.huawei.HwMultiScreenShot','com.hihonor.android.launcher','com.hihonor.android.internal.app',
              'com.android.server.telecom','com.android.phone','com.android.packageinstaller',
              'com.android.gallery3d','com.android.deskclock',
              'com.huawei.systemmanager','com.huawei.android.hwouc','com.huawei.filemanager',
              'com.huawei.trustspace','com.huawei.android.instantshare','com.huawei.security.privacycenter',
              'com.huawei.hwid','com.huawei.calendar','com.huawei.deskclock','com.huawei.calculator',
              'com.huawei.hitouch','com.huawei.hmos.himovie.fa'
          )
          AND COALESCE(app_info.promote_app_name, app.package_name) NOT IN ('日历','联系人','设置','相机','滚动截屏','华为桌面','信息','电话','System Share','图库','文件','时钟','计算器','杂志锁屏')
        GROUP BY bind.most_used_usid, bind.dsid, app.pt_d, COALESCE(app_info.promote_app_name, app.package_name)
        HAVING SUM(CAST(COALESCE(app.total_time, 0) / 1000 AS BIGINT)) > 5
    ) agg
) t
WHERE row_num <= 100;

-- 安装行为（最近1000次）
INSERT INTO adhoctemp.tmp_l00527489_20260329_auto_leads_app_events
SELECT
    usid, did, event_date, event_type, app_name, 0 AS usage_duration, row_num
FROM (
    SELECT
        bind.most_used_usid AS usid,
        bind.dsid AS did,
        iu.pt_d AS event_date,
        'appInstall' AS event_type,
        COALESCE(app_info.promote_app_name, iu.package_name) AS app_name,
        ROW_NUMBER() OVER (PARTITION BY bind.most_used_usid, bind.dsid ORDER BY iu.pt_d DESC, iu.report_timestamp DESC) AS row_num
    FROM pps.dwd_pps_appdata_install_uninstall_update_dm iu
    INNER JOIN (
        SELECT dsid, most_used_usid
        FROM bicoredata.dwd_pty_combine_year_active_device_current_up_bind_ds
        WHERE pt_d = '20260320'
    ) bind ON iu.adid = bind.dsid
    LEFT JOIN (
        SELECT promote_app_pkg, promote_app_name
        FROM pps.dim_pps_metric_promoted_app_info_hs
        WHERE pt_h = '2026032023'
    ) app_info ON iu.package_name = app_info.promote_app_pkg
    WHERE iu.pt_d >= '20260219' AND iu.pt_d <= '20260320'
      AND iu.event_type = 'appInstall'
      AND bind.most_used_usid IN (SELECT usid FROM adhoctemp.tmp_l00527489_20260329_auto_leads_sample_pool)
      AND iu.package_name NOT IN (
          'com.huawei.android.launcher','com.android.mms','com.huawei.contacts',
          'com.huawei.android.internal.app','com.android.permissioncontroller','com.android.incallui',
          'com.hihonor.deskclock','com.hihonor.notepad','com.hihonor.mms','com.huawei.camera',
          'com.huawei.photos','com.huawei.himovie.local','com.android.systemui','com.android.settings',
          'com.huawei.HwMultiScreenShot','com.hihonor.android.launcher','com.hihonor.android.internal.app',
          'com.android.server.telecom','com.android.phone','com.android.packageinstaller',
          'com.android.gallery3d','com.android.deskclock',
          'com.huawei.systemmanager','com.huawei.android.hwouc','com.huawei.filemanager',
          'com.huawei.trustspace','com.huawei.android.instantshare','com.huawei.security.privacycenter',
          'com.huawei.hwid','com.huawei.calendar','com.huawei.deskclock','com.huawei.calculator',
          'com.huawei.hitouch','com.huawei.hmos.himovie.fa'
      )
      AND COALESCE(app_info.promote_app_name, iu.package_name) NOT IN ('日历','联系人','设置','相机','滚动截屏','华为桌面','信息','电话','System Share','图库','文件','时钟','计算器','杂志锁屏')
) t
WHERE row_num <= 1000;

-- 卸载行为（最近100次）
INSERT INTO adhoctemp.tmp_l00527489_20260329_auto_leads_app_events
SELECT
    usid, did, event_date, event_type, app_name, 0 AS usage_duration, row_num
FROM (
    SELECT
        bind.most_used_usid AS usid,
        bind.dsid AS did,
        iu.pt_d AS event_date,
        'appUninstall' AS event_type,
        COALESCE(app_info.promote_app_name, iu.package_name) AS app_name,
        ROW_NUMBER() OVER (PARTITION BY bind.most_used_usid, bind.dsid ORDER BY iu.pt_d DESC, iu.report_timestamp DESC) AS row_num
    FROM pps.dwd_pps_appdata_install_uninstall_update_dm iu
    INNER JOIN (
        SELECT dsid, most_used_usid
        FROM bicoredata.dwd_pty_combine_year_active_device_current_up_bind_ds
        WHERE pt_d = '20260320'
    ) bind ON iu.adid = bind.dsid
    LEFT JOIN (
        SELECT promote_app_pkg, promote_app_name
        FROM pps.dim_pps_metric_promoted_app_info_hs
        WHERE pt_h = '2026032023'
    ) app_info ON iu.package_name = app_info.promote_app_pkg
    WHERE iu.pt_d >= '20260219' AND iu.pt_d <= '20260320'
      AND iu.event_type = 'appUninstall'
      AND bind.most_used_usid IN (SELECT usid FROM adhoctemp.tmp_l00527489_20260329_auto_leads_sample_pool)
      AND iu.package_name NOT IN (
          'com.huawei.android.launcher','com.android.mms','com.huawei.contacts',
          'com.huawei.android.internal.app','com.android.permissioncontroller','com.android.incallui',
          'com.hihonor.deskclock','com.hihonor.notepad','com.hihonor.mms','com.huawei.camera',
          'com.huawei.photos','com.huawei.himovie.local','com.android.systemui','com.android.settings',
          'com.huawei.HwMultiScreenShot','com.hihonor.android.launcher','com.hihonor.android.internal.app',
          'com.android.server.telecom','com.android.phone','com.android.packageinstaller',
          'com.android.gallery3d','com.android.deskclock',
          'com.huawei.systemmanager','com.huawei.android.hwouc','com.huawei.filemanager',
          'com.huawei.trustspace','com.huawei.android.instantshare','com.huawei.security.privacycenter',
          'com.huawei.hwid','com.huawei.calendar','com.huawei.deskclock','com.huawei.calculator',
          'com.huawei.hitouch','com.huawei.hmos.himovie.fa'
      )
      AND COALESCE(app_info.promote_app_name, iu.package_name) NOT IN ('日历','联系人','设置','相机','滚动截屏','华为桌面','信息','电话','System Share','图库','文件','时钟','计算器','杂志锁屏')
) t
WHERE row_num <= 100;

-- Step 3.2: 构建 APP 行为序列（按设备分段，多设备时加 "=== 设备{did} ===" 分隔）
INSERT INTO adhoctemp.tmp_l00527489_20260329_auto_leads_app_behavior
SELECT
    usid,
    CASE
        WHEN SIZE(COLLECT_SET(did)) = 1
        THEN MIN(device_seq)
        ELSE CONCAT_WS('\n',
            SORT_ARRAY(COLLECT_LIST(
                CONCAT('=== 设备', did, ' ===\n', device_seq)
            ), TRUE)
        )
    END AS app_behavior_seq
FROM (
    SELECT
        usid,
        did,
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
        ) AS device_seq
    FROM adhoctemp.tmp_l00527489_20260329_auto_leads_app_events
    GROUP BY usid, did
) t
GROUP BY usid;


-- ============================================================================
-- 阶段 3（续）：汽车/旅游行为数据（特征期：2月19日-3月20日）
-- ============================================================================
-- 来源：pps.dwd_pps_travel_car_behavior_appdata_hm
-- 对汽车行业重点保留以下5个 data_id（汽车信号最强）：
--
-- 500_11_0009_1: 汽车浏览/搜索 ★★★ 最强购车意图信号
--   app_name=ext_value1，field1=行为标识(浏览/搜索)，field2=页面ID，field3=品牌，field4=型号|次数
--
-- 500_11_0008_1: 汽车APP点击 ★★★ 强购车意图信号
--   app_name=ext_value1，field1=行为标识(浏览/搜索)，field2=页面ID，field3=品牌，field4=型号
--
-- 400_11_0009_1: 试驾短信 ★★★ 极强购车意图信号
--   field1=试驾发送方(ext_value1)，无app_name
--
-- 500_13_0001_07: 文旅12306高铁短信（出行偏好参考）
--   field1=车次(G+ext_value2)，field2=日期(ext_value3)，无app_name
--
-- 500_13_0001_03: 文旅OTA短信行程识别（消费力参考）
--   field1=通知类型(ext_value3)，field2=酒店名称+地址(ext_value4)，field3=行程信息(ext_value6)，field4=时间(ext_value7)，无app_name

INSERT INTO adhoctemp.tmp_l00527489_20260329_auto_leads_travel_car_events
SELECT
    usid, did, event_date, behavior_type, app_name,
    field1, field2, field3, field4, data_id, row_num
FROM (
    SELECT
        bind.most_used_usid AS usid,
        bind.dsid AS did,
        SUBSTR(tcb.pt_h, 1, 8) AS event_date,
        COALESCE(CONCAT(dm.industry, dm.behavior_type), tcb.data_id) AS behavior_type,
        -- app_name：500_11_xxxx 用 ext_value1，文旅短信/试驾无 app
        CASE
            WHEN tcb.data_id IN ('500_11_0009_1', '500_11_0008_1')
                THEN COALESCE(am.app_name, CONCAT('应用ID:', tcb.ext_value1))
            ELSE ''
        END AS app_name,
        -- field1
        CASE
            WHEN tcb.data_id = '500_13_0001_07'
                THEN CONCAT('G', tcb.ext_value2)
            WHEN tcb.data_id = '500_13_0001_03'
                THEN tcb.ext_value3
            WHEN tcb.data_id IN ('500_11_0009_1', '500_11_0008_1')
                THEN CASE tcb.ext_value2
                         WHEN '100_5000' THEN '浏览'
                         WHEN '100_5001' THEN '搜索'
                         ELSE tcb.ext_value2
                     END
            WHEN tcb.data_id = '400_11_0009_1'
                THEN tcb.ext_value1
            ELSE NULL
        END AS field1,
        -- field2
        CASE
            WHEN tcb.data_id = '500_13_0001_07'
                THEN tcb.ext_value3
            WHEN tcb.data_id = '500_13_0001_03'
                THEN tcb.ext_value4
            WHEN tcb.data_id IN ('500_11_0009_1', '500_11_0008_1')
                THEN tcb.ext_value3
            ELSE NULL
        END AS field2,
        -- field3
        CASE
            WHEN tcb.data_id = '500_13_0001_03'
                THEN tcb.ext_value6
            WHEN tcb.data_id IN ('500_11_0009_1', '500_11_0008_1')
                THEN tcb.ext_value4
            ELSE NULL
        END AS field3,
        -- field4
        CASE
            WHEN tcb.data_id = '500_13_0001_03'
                THEN tcb.ext_value7
            WHEN tcb.data_id = '500_11_0009_1'
                THEN CONCAT(COALESCE(tcb.ext_value5,''), '|次数:', COALESCE(tcb.ext_value6,''))
            WHEN tcb.data_id = '500_11_0008_1'
                THEN tcb.ext_value5
            ELSE NULL
        END AS field4,
        tcb.data_id,
        ROW_NUMBER() OVER (PARTITION BY bind.most_used_usid, bind.dsid ORDER BY tcb.pt_h DESC) AS row_num
    FROM pps.dwd_pps_travel_car_behavior_appdata_hm tcb
    INNER JOIN (
        SELECT dsid, most_used_usid
        FROM bicoredata.dwd_pty_combine_year_active_device_current_up_bind_ds
        WHERE pt_d = '20260320'
    ) bind ON tcb.adid = bind.dsid
    LEFT JOIN adhoctemp.tmp_l00527489_20260324_dataid_mapping dm
        ON tcb.data_id = dm.data_id
    LEFT JOIN adhoctemp.tmp_l00527489_20260324_appid_mapping am
        ON tcb.data_id IN ('500_11_0009_1', '500_11_0008_1')
        AND tcb.ext_value1 = am.app_id
    WHERE tcb.data_id IN ('500_13_0001_07', '500_13_0001_03', '500_11_0009_1', '500_11_0008_1', '400_11_0009_1')
      AND tcb.pt_h >= '2026021900' AND tcb.pt_h <= '2026032023'
      AND bind.most_used_usid IN (SELECT usid FROM adhoctemp.tmp_l00527489_20260329_auto_leads_sample_pool)
      AND NOT (tcb.data_id = '500_13_0001_07' AND (tcb.ext_value2 IS NULL OR tcb.ext_value2 = ''))
) t
WHERE row_num <= 200;

-- Step 3.6: 构建汽车/旅游行为序列（汽车行业核心特征列）
-- CSV列：日期,行为类型,应用,字段1,字段2,字段3,字段4,data_id
INSERT INTO adhoctemp.tmp_l00527489_20260329_auto_leads_travel_car_behavior
SELECT
    usid,
    CASE
        WHEN SIZE(COLLECT_SET(did)) = 1
        THEN MIN(device_seq)
        ELSE CONCAT_WS('\n',
            SORT_ARRAY(COLLECT_LIST(
                CONCAT('=== 设备', did, ' ===\n', device_seq)
            ), TRUE)
        )
    END AS travel_car_behavior_seq
FROM (
    SELECT
        usid,
        did,
        CONCAT(
            '日期,行为类型,应用,字段1(行为/车次/通知类型/试驾方),字段2(页面ID/日期/酒店),字段3(品牌/行程),字段4(型号+次数/时间),data_id\n',
            CONCAT_WS('\n',
                SORT_ARRAY(
                    COLLECT_LIST(
                        CONCAT(
                            event_date, ',',
                            behavior_type, ',',
                            COALESCE(app_name, ''), ',',
                            COALESCE(field1, ''), ',',
                            COALESCE(field2, ''), ',',
                            COALESCE(field3, ''), ',',
                            COALESCE(field4, ''), ',',
                            data_id
                        )
                    ),
                    FALSE
                )
            )
        ) AS device_seq
    FROM adhoctemp.tmp_l00527489_20260329_auto_leads_travel_car_events
    GROUP BY usid, did
) t
GROUP BY usid;


-- ============================================================================
-- 阶段 3（续）：金融行业行为数据（特征期：2月19日-3月20日）
-- 对汽车行业：金融信号体现用户车贷/保险意图，作为辅助特征
-- ============================================================================

INSERT INTO adhoctemp.tmp_l00527489_20260329_auto_leads_finance_behavior_events
SELECT
    usid, did, event_date, behavior_type, app_name,
    ext_value2, ext_value3, ext_value4, ext_value5, data_id, row_num
FROM (
    SELECT
        bind.most_used_usid AS usid,
        bind.dsid AS did,
        SUBSTR(fb.pt_h, 1, 8) AS event_date,
        COALESCE(CONCAT(dm.industry, dm.behavior_type), fb.data_id) AS behavior_type,
        COALESCE(
            am.app_name,
            CASE
                WHEN fb.data_id = '400_12_1001_3' THEN fb.ext_value2
                ELSE fb.ext_value1
            END
        ) AS app_name,
        fb.ext_value2,
        fb.ext_value3,
        fb.ext_value4,
        fb.ext_value5,
        fb.data_id,
        ROW_NUMBER() OVER (PARTITION BY bind.most_used_usid, bind.dsid ORDER BY fb.pt_h DESC) AS row_num
    FROM pps.dwd_pps_financial_behavior_appdata_hm fb
    INNER JOIN (
        SELECT dsid, most_used_usid
        FROM bicoredata.dwd_pty_combine_year_active_device_current_up_bind_ds
        WHERE pt_d = '20260320'
    ) bind ON fb.adid = bind.dsid
    LEFT JOIN adhoctemp.tmp_l00527489_20260324_dataid_mapping dm
        ON fb.data_id = dm.data_id
    LEFT JOIN adhoctemp.tmp_l00527489_20260324_appid_mapping am
        ON CASE
            WHEN fb.data_id = '400_12_1001_3' THEN fb.ext_value2
            ELSE fb.ext_value1
        END = am.app_id
    WHERE fb.data_id IN ('500_12_0020_1', '400_12_1001_3', '400_12_0017_1', '400_12_0016_1')
      AND fb.pt_h >= '2026021900' AND fb.pt_h <= '2026032023'
      AND bind.most_used_usid IN (SELECT usid FROM adhoctemp.tmp_l00527489_20260329_auto_leads_sample_pool)
) t
WHERE row_num <= 200;

INSERT INTO adhoctemp.tmp_l00527489_20260329_auto_leads_finance_behavior_seq
SELECT
    usid,
    CASE
        WHEN SIZE(COLLECT_SET(did)) = 1
        THEN MIN(device_seq)
        ELSE CONCAT_WS('\n',
            SORT_ARRAY(COLLECT_LIST(
                CONCAT('=== 设备', did, ' ===\n', device_seq)
            ), TRUE)
        )
    END AS finance_behavior_seq
FROM (
    SELECT
        usid,
        did,
        CONCAT(
            '日期,行为类型,应用,短信类型_券商名,扩展字段3,扩展字段4,扩展字段5,data_id\n',
            CONCAT_WS('\n',
                SORT_ARRAY(
                    COLLECT_LIST(
                        CONCAT(
                            event_date, ',',
                            behavior_type, ',',
                            app_name, ',',
                            COALESCE(ext_value2, ''), ',',
                            COALESCE(ext_value3, ''), ',',
                            COALESCE(ext_value4, ''), ',',
                            COALESCE(ext_value5, ''), ',',
                            COALESCE(data_id, '')
                        )
                    ),
                    FALSE
                )
            )
        ) AS device_seq
    FROM adhoctemp.tmp_l00527489_20260329_auto_leads_finance_behavior_events
    GROUP BY usid, did
) t
GROUP BY usid;


-- ============================================================================
-- 阶段 3（续）：电商行业行为数据（特征期：2月19日-3月20日）
-- ============================================================================

INSERT INTO adhoctemp.tmp_l00527489_20260329_auto_leads_ecom_industry_events
SELECT
    usid, did, event_date, behavior_type, app_name,
    category_l3_code, category_l3_name, goods_id, data_id, row_num
FROM (
    SELECT
        bind.most_used_usid AS usid,
        bind.dsid AS did,
        SUBSTR(eb.pt_h, 1, 8) AS event_date,
        COALESCE(CONCAT(dm.industry, dm.behavior_type), eb.data_id) AS behavior_type,
        COALESCE(
            am.app_name,
            CASE
                WHEN eb.data_id = '500_20_0009_02' THEN CONCAT('应用ID:', eb.ext_value2)
                WHEN eb.data_id = '500_10_0013_7'  THEN CONCAT('应用ID:', eb.ext_value8)
                ELSE ''
            END
        ) AS app_name,
        CASE
            WHEN eb.data_id = '500_20_0009_02' THEN eb.ext_value5
            ELSE eb.ext_value4
        END AS category_l3_code,
        tl3.tag_name AS category_l3_name,
        CASE
            WHEN eb.data_id = '500_20_0009_02' THEN eb.ext_value8
            ELSE eb.ext_value7
        END AS goods_id,
        eb.data_id,
        ROW_NUMBER() OVER (PARTITION BY bind.most_used_usid, bind.dsid ORDER BY eb.pt_h DESC) AS row_num
    FROM pps.dwd_pps_ecommerce_behavior_appdata_hm eb
    INNER JOIN (
        SELECT dsid, most_used_usid
        FROM bicoredata.dwd_pty_combine_year_active_device_current_up_bind_ds
        WHERE pt_d = '20260320'
    ) bind ON eb.adid = bind.dsid
    LEFT JOIN adhoctemp.tmp_l00527489_20260324_dataid_mapping dm
        ON eb.data_id = dm.data_id
    LEFT JOIN adhoctemp.tmp_l00527489_20260324_appid_mapping am
        ON CASE
            WHEN eb.data_id = '500_20_0009_02' THEN eb.ext_value2
            WHEN eb.data_id = '500_10_0013_7'  THEN eb.ext_value8
            ELSE NULL
        END = am.app_id
    LEFT JOIN adhoctemp.tmp_l00527489_20260324_tag_level3 tl3
        ON CASE
            WHEN eb.data_id = '500_20_0009_02' THEN eb.ext_value5
            ELSE eb.ext_value4
        END = tl3.tag_code
    WHERE eb.data_id IN ('500_20_0009_02', '500_20_0005_7', '500_10_0013_7')
      AND eb.pt_h >= '2026021900' AND eb.pt_h <= '2026032023'
      AND bind.most_used_usid IN (SELECT usid FROM adhoctemp.tmp_l00527489_20260329_auto_leads_sample_pool)
) t
WHERE row_num <= 200;

INSERT INTO adhoctemp.tmp_l00527489_20260329_auto_leads_ecom_industry_seq
SELECT
    usid,
    CASE
        WHEN SIZE(COLLECT_SET(did)) = 1
        THEN MIN(device_seq)
        ELSE CONCAT_WS('\n',
            SORT_ARRAY(COLLECT_LIST(
                CONCAT('=== 设备', did, ' ===\n', device_seq)
            ), TRUE)
        )
    END AS ecom_industry_behavior_seq
FROM (
    SELECT
        usid,
        did,
        CONCAT(
            '日期,行为类型,应用,商品目录L3,商品ID,data_id\n',
            CONCAT_WS('\n',
                SORT_ARRAY(
                    COLLECT_LIST(
                        CONCAT(
                            event_date, ',',
                            behavior_type, ',',
                            COALESCE(app_name, ''), ',',
                            COALESCE(category_l3_name, category_l3_code, ''), ',',
                            COALESCE(goods_id, ''), ',',
                            COALESCE(data_id, '')
                        )
                    ),
                    FALSE
                )
            )
        ) AS device_seq
    FROM adhoctemp.tmp_l00527489_20260329_auto_leads_ecom_industry_events
    GROUP BY usid, did
) t
GROUP BY usid;


-- ============================================================================
-- 阶段 4：广告事件数据表（特征期：2月19日-3月20日）
-- ============================================================================

-- 曝光事件（最近100条）
INSERT INTO adhoctemp.tmp_l00527489_20260329_auto_leads_ad_event_details
SELECT
    usid, NULL AS did, event_date, event_type,
    industry_level1, industry_level2, position_name, promote_app_name,
    NULL AS creative_title, NULL AS creative_desc, NULL AS creative_label,
    event_count, row_num
FROM (
    SELECT
        ind.usid,
        ind.pt_d AS event_date,
        'impression' AS event_type,
        COALESCE(ind.cust_industry_level1, '未知') AS industry_level1,
        COALESCE(ind.cust_industry_level2, '未知') AS industry_level2,
        COALESCE(ind.position_name, '未知版位') AS position_name,
        COALESCE(ind.promote_app_name, '未知应用') AS promote_app_name,
        ind.received_total_imp AS event_count,
        ROW_NUMBER() OVER (PARTITION BY ind.usid ORDER BY ind.pt_d DESC, ind.received_total_imp DESC) AS row_num
    FROM pps.ads_pps_user_base_indicator_dm ind
    WHERE ind.pt_d >= '20260219' AND ind.pt_d <= '20260320'
      AND ind.usid IN (SELECT usid FROM adhoctemp.tmp_l00527489_20260329_auto_leads_sample_pool)
      AND ind.received_total_imp > 0
) t
WHERE row_num <= 100;

-- 点击事件（最近100条，关联创意信息）
INSERT INTO adhoctemp.tmp_l00527489_20260329_auto_leads_ad_event_details
SELECT
    usid, NULL AS did, event_date, event_type,
    industry_level1, industry_level2, position_name, promote_app_name,
    creative_title, creative_desc, creative_label,
    event_count, row_num
FROM (
    SELECT
        ind.usid,
        ind.pt_d AS event_date,
        'click' AS event_type,
        COALESCE(ind.cust_industry_level1, '未知') AS industry_level1,
        COALESCE(ind.cust_industry_level2, '未知') AS industry_level2,
        COALESCE(ind.position_name, '未知版位') AS position_name,
        COALESCE(ind.promote_app_name, '未知应用') AS promote_app_name,
        COALESCE(crt.title_text, '') AS creative_title,
        COALESCE(crt.description_text, '') AS creative_desc,
        COALESCE(crt.label, '') AS creative_label,
        ind.received_total_click AS event_count,
        ROW_NUMBER() OVER (PARTITION BY ind.usid ORDER BY ind.pt_d DESC, ind.received_total_click DESC) AS row_num
    FROM pps.ads_pps_user_base_indicator_dm ind
    LEFT JOIN (
        SELECT creative_id, title_text, description_text, label
        FROM pps.dwd_pps_t_creative_hs
        WHERE pt_h = '2026032023'
    ) crt ON ind.creative_id = crt.creative_id
    WHERE ind.pt_d >= '20260219' AND ind.pt_d <= '20260320'
      AND ind.usid IN (SELECT usid FROM adhoctemp.tmp_l00527489_20260329_auto_leads_sample_pool)
      AND ind.received_total_click > 0
) t
WHERE row_num <= 100;

-- 转化事件（最近100条）
INSERT INTO adhoctemp.tmp_l00527489_20260329_auto_leads_ad_event_details
SELECT
    usid, NULL AS did, event_date, event_type,
    industry_level1, industry_level2, position_name, promote_app_name,
    NULL AS creative_title, NULL AS creative_desc, NULL AS creative_label,
    event_count, row_num
FROM (
    SELECT
        ind.usid,
        ind.pt_d AS event_date,
        'conversion' AS event_type,
        COALESCE(ind.cust_industry_level1, '未知') AS industry_level1,
        COALESCE(ind.cust_industry_level2, '未知') AS industry_level2,
        COALESCE(ind.position_name, '未知版位') AS position_name,
        COALESCE(ind.promote_app_name, '未知应用') AS promote_app_name,
        ind.total_task_cnvr_target_cnvr_cnt AS event_count,
        ROW_NUMBER() OVER (PARTITION BY ind.usid ORDER BY ind.pt_d DESC, ind.total_task_cnvr_target_cnvr_cnt DESC) AS row_num
    FROM pps.ads_pps_user_base_indicator_dm ind
    WHERE ind.pt_d >= '20260219' AND ind.pt_d <= '20260320'
      AND ind.usid IN (SELECT usid FROM adhoctemp.tmp_l00527489_20260329_auto_leads_sample_pool)
      AND ind.event_type NOT IN ('repeatedImp','playPause','intentSuccess','playStart','webclose','webopen','webloadfinish','skip','downloadstart','playEnd','installStart','impInLandingPage','playResume','clickLandingpage','repeatedClick','intentFail','appFirstOpen','appOpen','browse','soundClickOn','easterEggEnd','downloadResume')
      AND ind.total_task_cnvr_target_cnvr_cnt > 0
) t
WHERE row_num <= 100;

-- Step 4.2: 异常用户标记
INSERT INTO adhoctemp.tmp_l00527489_20260329_auto_leads_abnormal_users
SELECT
    ind.usid,
    SUM(COALESCE(ind.received_total_imp, 0)) AS total_impression_cnt,
    SUM(COALESCE(ind.received_total_click, 0)) AS total_click_cnt,
    SUM(COALESCE(ind.total_task_cnvr_target_cnvr_cnt, 0)) AS total_conversion_cnt,
    CASE
        WHEN SUM(COALESCE(ind.received_total_imp, 0)) > 10000 THEN '异常（曝光过多）'
        WHEN SUM(COALESCE(ind.received_total_click, 0)) > 1000 THEN '异常（点击过多）'
        WHEN SUM(COALESCE(ind.total_task_cnvr_target_cnvr_cnt, 0)) > 500 THEN '异常（转化过多）'
        ELSE '正常'
    END AS abnormal_user_flag
FROM pps.ads_pps_user_base_indicator_dm ind
WHERE ind.pt_d >= '20260219' AND ind.pt_d <= '20260320'
  AND ind.usid IN (SELECT usid FROM adhoctemp.tmp_l00527489_20260329_auto_leads_sample_pool)
  AND ind.event_type NOT IN ('repeatedImp','playPause','intentSuccess','playStart','webclose','webopen','webloadfinish','skip','downloadstart','playEnd','installStart','impInLandingPage','playResume','clickLandingpage','repeatedClick','intentFail','appFirstOpen','appOpen','browse','soundClickOn','easterEggEnd','downloadResume')
GROUP BY ind.usid;

-- Step 4.3: 构建广告事件序列
INSERT INTO adhoctemp.tmp_l00527489_20260329_auto_leads_ad_events
SELECT
    usid,
    CONCAT(
        '日期,事件类型,一级行业,二级行业,版位,推广应用,创意标题,创意描述,创意标签,次数\n',
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
                        COALESCE(creative_title, ''), ',',
                        COALESCE(creative_desc, ''), ',',
                        COALESCE(creative_label, ''), ',',
                        CAST(event_count AS STRING)
                    )
                ),
                FALSE
            )
        )
    ) AS ad_event_seq
FROM adhoctemp.tmp_l00527489_20260329_auto_leads_ad_event_details
GROUP BY usid;


-- ============================================================================
-- 阶段 5：最终宽表 JOIN
-- ============================================================================

INSERT INTO adhoctemp.tmp_l00527489_20260329_auto_leads_final_wide_table
SELECT
    s.usid,
    s.sample_label,
    s.leads_cnt,
    CONCAT(
        '【账号', s.usid, '，共', COALESCE(CAST(dl.device_cnt AS STRING), '1'), '个设备(',
        COALESCE(dl.did_list, s.usid), ')】\n',
        COALESCE(p.user_profile_features, '')
    ) AS user_profile_features,
    COALESCE(a.app_behavior_seq, '') AS app_behavior_seq,
    COALESCE(tc.travel_car_behavior_seq, '') AS travel_car_behavior_seq,
    COALESCE(fb.finance_behavior_seq, '') AS finance_behavior_seq,
    COALESCE(eib.ecom_industry_behavior_seq, '') AS ecom_industry_behavior_seq,
    COALESCE(e.ad_event_seq, '') AS ad_event_seq,
    COALESCE(ab.abnormal_user_flag, '正常') AS abnormal_user_flag,
    FROM_UNIXTIME(UNIX_TIMESTAMP()) AS create_time
FROM adhoctemp.tmp_l00527489_20260329_auto_leads_sample_pool s
LEFT JOIN adhoctemp.tmp_l00527489_20260329_auto_leads_user_profile p ON s.usid = p.usid
LEFT JOIN adhoctemp.tmp_l00527489_20260329_auto_leads_app_behavior a ON s.usid = a.usid
LEFT JOIN adhoctemp.tmp_l00527489_20260329_auto_leads_travel_car_behavior tc ON s.usid = tc.usid
LEFT JOIN adhoctemp.tmp_l00527489_20260329_auto_leads_finance_behavior_seq fb ON s.usid = fb.usid
LEFT JOIN adhoctemp.tmp_l00527489_20260329_auto_leads_ecom_industry_seq eib ON s.usid = eib.usid
LEFT JOIN adhoctemp.tmp_l00527489_20260329_auto_leads_ad_events e ON s.usid = e.usid
LEFT JOIN adhoctemp.tmp_l00527489_20260329_auto_leads_abnormal_users ab ON s.usid = ab.usid
LEFT JOIN (
    SELECT
        most_used_usid AS usid,
        COUNT(dsid) AS device_cnt,
        CONCAT_WS(',', COLLECT_SET(dsid)) AS did_list
    FROM bicoredata.dwd_pty_combine_year_active_device_current_up_bind_ds
    WHERE pt_d = '20260320'
      AND most_used_usid IN (SELECT usid FROM adhoctemp.tmp_l00527489_20260329_auto_leads_sample_pool)
    GROUP BY most_used_usid
) dl ON s.usid = dl.usid;


-- ============================================================================
-- 验证 SQL
-- ============================================================================

-- 1. 样本分布验证
SELECT
    sample_label,
    COUNT(*) AS cnt,
    SUM(leads_cnt) AS total_leads,
    ROUND(AVG(leads_cnt), 2) AS avg_leads_cnt
FROM adhoctemp.tmp_l00527489_20260329_auto_leads_sample_pool
GROUP BY sample_label;

-- 2. 特征覆盖率验证
SELECT
    COUNT(*) AS total_users,
    COUNT(CASE WHEN user_profile_features != '' THEN 1 ELSE NULL END) AS with_profile,
    COUNT(CASE WHEN app_behavior_seq != '' THEN 1 ELSE NULL END) AS with_app_behavior,
    COUNT(CASE WHEN travel_car_behavior_seq != '' THEN 1 ELSE NULL END) AS with_travel_car_behavior,
    COUNT(CASE WHEN finance_behavior_seq != '' THEN 1 ELSE NULL END) AS with_finance_behavior,
    COUNT(CASE WHEN ecom_industry_behavior_seq != '' THEN 1 ELSE NULL END) AS with_ecom_behavior,
    COUNT(CASE WHEN ad_event_seq != '' THEN 1 ELSE NULL END) AS with_ad_events,
    ROUND(COUNT(CASE WHEN travel_car_behavior_seq != '' THEN 1 ELSE NULL END) * 100.0 / COUNT(*), 2) AS car_behavior_coverage_pct,
    ROUND(COUNT(CASE WHEN ad_event_seq != '' THEN 1 ELSE NULL END) * 100.0 / COUNT(*), 2) AS ad_event_coverage_pct
FROM adhoctemp.tmp_l00527489_20260329_auto_leads_final_wide_table;

-- 3. 三类样本不重叠验证（期望结果均为0）
SELECT
    '正样本与汽车点击负样本不重叠' AS check_name,
    COUNT(*) AS invalid_cnt
FROM adhoctemp.tmp_l00527489_20260329_auto_leads_final_wide_table
WHERE sample_label = 'negative_click' AND usid IN (
    SELECT usid FROM adhoctemp.tmp_l00527489_20260329_auto_leads_final_wide_table WHERE sample_label = 'positive'
)
UNION ALL
SELECT
    '正样本与大盘随机负样本不重叠' AS check_name,
    COUNT(*) AS invalid_cnt
FROM adhoctemp.tmp_l00527489_20260329_auto_leads_final_wide_table
WHERE sample_label = 'negative_random' AND usid IN (
    SELECT usid FROM adhoctemp.tmp_l00527489_20260329_auto_leads_final_wide_table WHERE sample_label = 'positive'
)
UNION ALL
SELECT
    '两类负样本之间不重叠' AS check_name,
    COUNT(*) AS invalid_cnt
FROM adhoctemp.tmp_l00527489_20260329_auto_leads_final_wide_table
WHERE sample_label = 'negative_random' AND usid IN (
    SELECT usid FROM adhoctemp.tmp_l00527489_20260329_auto_leads_final_wide_table WHERE sample_label = 'negative_click'
);

-- 4. 汽车行为信号覆盖（正样本有汽车行为的比例，越高越好）
SELECT
    sample_label,
    COUNT(*) AS total_cnt,
    COUNT(CASE WHEN travel_car_behavior_seq != '' THEN 1 ELSE NULL END) AS with_car_behavior,
    ROUND(COUNT(CASE WHEN travel_car_behavior_seq != '' THEN 1 ELSE NULL END) * 100.0 / COUNT(*), 2) AS car_behavior_pct
FROM adhoctemp.tmp_l00527489_20260329_auto_leads_final_wide_table
GROUP BY sample_label;

-- 5. 异常用户统计
SELECT
    abnormal_user_flag,
    COUNT(*) AS user_cnt,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) AS pct
FROM adhoctemp.tmp_l00527489_20260329_auto_leads_final_wide_table
GROUP BY abnormal_user_flag;

-- 6. 样本数据预览（前10条）
SELECT
    usid,
    sample_label,
    leads_cnt,
    abnormal_user_flag,
    SUBSTR(user_profile_features, 1, 100) AS profile_preview,
    SUBSTR(travel_car_behavior_seq, 1, 200) AS car_behavior_preview,
    SUBSTR(ad_event_seq, 1, 100) AS ad_event_preview
FROM adhoctemp.tmp_l00527489_20260329_auto_leads_final_wide_table
LIMIT 10;
