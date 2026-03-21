-- ============================================================================
-- 金融小额借贷行业 贷款意图预测 ETL SQL 方案（无 WITH 语法版本）
-- ============================================================================
-- 目标：构建正负样本特征宽表，用于大模型预测贷款意图（授信/动支/完件）
-- 正样本：3月11日-3月17日有完件转化的用户
-- 负样本：金融画像宽表大盘随机10000用户（排除正样本）
-- 输出：一个用户一行，包含画像特征、APP行为序列、电商搜索/浏览序列、广告事件序列
-- 时间切分：特征数据取3月10日之前，避免与标签期（3月11-17日）重叠
-- ID映射：did=adid，通过 dwd_pty_combine_device_up_bind_ds 映射到 usid
-- ============================================================================

-- ============================================================================
-- 所有建表语句（按执行顺序排列）
-- ============================================================================

-- 表1: 正样本表
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260317_finance_loan_positive_samples;
CREATE TABLE IF NOT EXISTS adhoctemp.tmp_l00527489_20260317_finance_loan_positive_samples (
    usid STRING COMMENT '用户标识',
    sample_label STRING COMMENT '样本标签',
    first_conversion_type STRING COMMENT '首次转化类型（授信/动支/完件）',
    conversion_value_7d DOUBLE COMMENT '7天动支金额（标签期：3月11-17日）',
    conversion_cnt_7d BIGINT COMMENT '7天转化次数（标签期：3月11-17日）'
) COMMENT '正样本：标签期借贷转化用户（最多10000个）';

-- 表2: 负样本表
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260317_finance_loan_negative_samples;
CREATE TABLE IF NOT EXISTS adhoctemp.tmp_l00527489_20260317_finance_loan_negative_samples (
    usid STRING COMMENT '用户标识',
    sample_label STRING COMMENT '样本标签',
    first_conversion_type STRING COMMENT '首次转化类型（负样本为空）',
    conversion_value_7d DOUBLE COMMENT '7天动支金额（负样本为0）',
    conversion_cnt_7d BIGINT COMMENT '7天转化次数（负样本为0）'
) COMMENT '负样本：大盘随机用户（最多10000个）';

-- 表3: 样本池表（依赖表1、表2）
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260317_finance_loan_sample_pool;
CREATE TABLE IF NOT EXISTS adhoctemp.tmp_l00527489_20260317_finance_loan_sample_pool (
    usid STRING COMMENT '用户标识',
    sample_label STRING COMMENT '样本标签：positive/negative',
    first_conversion_type STRING COMMENT '首次转化类型',
    conversion_value_7d DOUBLE COMMENT '7天动支金额',
    conversion_cnt_7d BIGINT COMMENT '7天转化次数'
) COMMENT '样本池：正负样本合并';

-- 表4: 用户画像特征表（依赖表3）
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260317_finance_loan_user_profile;
CREATE TABLE IF NOT EXISTS adhoctemp.tmp_l00527489_20260317_finance_loan_user_profile (
    usid STRING COMMENT '用户标识',
    user_profile_features STRING COMMENT '用户画像特征（key:value;key:value格式）'
) COMMENT '用户画像特征表';

-- 表5: APP事件明细表（依赖表3）
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260317_finance_loan_app_events;
CREATE TABLE IF NOT EXISTS adhoctemp.tmp_l00527489_20260317_finance_loan_app_events (
    usid STRING COMMENT '用户标识',
    event_date STRING COMMENT '事件日期',
    event_type STRING COMMENT '事件类型：appUsage/appInstall/appUninstall',
    app_name STRING COMMENT '应用名称',
    usage_duration BIGINT COMMENT '使用时长（秒，仅appUsage有值）',
    row_num BIGINT COMMENT '排序序号'
) COMMENT 'APP事件明细表（合并使用和安装卸载数据）';

-- 表6: APP行为序列表（依赖表5）
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260317_finance_loan_app_behavior;
CREATE TABLE IF NOT EXISTS adhoctemp.tmp_l00527489_20260317_finance_loan_app_behavior (
    usid STRING COMMENT '用户标识',
    app_behavior_seq STRING COMMENT 'APP行为序列（CSV表格格式）'
) COMMENT 'APP行为序列表';

-- 表9: 汽车/旅游行为明细表（依赖表3）
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260317_finance_loan_travel_car_events;
CREATE TABLE IF NOT EXISTS adhoctemp.tmp_l00527489_20260317_finance_loan_travel_car_events (
    usid STRING COMMENT '用户标识',
    event_date STRING COMMENT '事件日期',
    behavior_type STRING COMMENT '行为描述（industry+behavior_type，来自dataid_mapping）',
    app_name STRING COMMENT '应用名称（来自appid_mapping，500_11_xxxx用ext_value1）',
    field1 STRING COMMENT '核心字段1（含义随data_id变化，见注释）',
    field2 STRING COMMENT '核心字段2（含义随data_id变化，见注释）',
    field3 STRING COMMENT '核心字段3（含义随data_id变化，见注释）',
    field4 STRING COMMENT '核心字段4（含义随data_id变化，见注释）',
    data_id STRING COMMENT '原始data_id，便于下游区分字段含义',
    row_num BIGINT COMMENT '排序序号'
) COMMENT '汽车/旅游行为明细表（字段含义按data_id区分）';

-- 表10: 汽车/旅游/本地生活行为序列表（依赖表9）
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260317_finance_loan_travel_car_behavior;
CREATE TABLE IF NOT EXISTS adhoctemp.tmp_l00527489_20260317_finance_loan_travel_car_behavior (
    usid STRING COMMENT '用户标识',
    travel_car_behavior_seq STRING COMMENT '汽车/旅游/本地生活行为序列（CSV表格格式）'
) COMMENT '汽车/旅游/本地生活行为序列表';

-- 表10a: 金融行业行为明细表（依赖表3）
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260317_finance_loan_finance_behavior_events;
CREATE TABLE IF NOT EXISTS adhoctemp.tmp_l00527489_20260317_finance_loan_finance_behavior_events (
    usid STRING COMMENT '用户标识',
    event_date STRING COMMENT '事件日期',
    behavior_type STRING COMMENT '行为描述（industry+behavior_type，来自dataid_mapping）',
    app_name STRING COMMENT '应用名称（来自appid_mapping）',
    ext_value2 STRING COMMENT '扩展字段2',
    ext_value3 STRING COMMENT '扩展字段3',
    ext_value4 STRING COMMENT '扩展字段4',
    ext_value5 STRING COMMENT '扩展字段5',
    data_id STRING COMMENT '原始data_id',
    row_num BIGINT COMMENT '排序序号'
) COMMENT '金融行业行为明细表';

-- 表10b: 金融行业行为序列表（依赖表10a）
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260317_finance_loan_finance_behavior_seq;
CREATE TABLE IF NOT EXISTS adhoctemp.tmp_l00527489_20260317_finance_loan_finance_behavior_seq (
    usid STRING COMMENT '用户标识',
    finance_behavior_seq STRING COMMENT '金融行业行为序列（CSV表格格式）'
) COMMENT '金融行业行为序列表';

-- 表10e: 电商行业行为明细表（依赖表3）
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260317_finance_loan_ecom_industry_events;
CREATE TABLE IF NOT EXISTS adhoctemp.tmp_l00527489_20260317_finance_loan_ecom_industry_events (
    usid STRING COMMENT '用户标识',
    event_date STRING COMMENT '事件日期',
    behavior_type STRING COMMENT '行为描述（industry+behavior_type，来自dataid_mapping）',
    app_name STRING COMMENT '应用名称（来自appid_mapping，500_20_0009_02用ext_value2，500_10_0013_7用ext_value8）',
    category_l3_code STRING COMMENT '商品目录L3 code',
    category_l3_name STRING COMMENT '商品目录L3名称（来自tmp_l00527489_20260317_tag_level3）',
    goods_id STRING COMMENT '商品ID（500_20_0009_02用ext_value8，500_20_0005_7/500_10_0013_7用ext_value7）',
    data_id STRING COMMENT '原始data_id',
    row_num BIGINT COMMENT '排序序号'
) COMMENT '电商行业行为明细表';

-- 表10f: 电商行业行为序列表（依赖表10e）
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260317_finance_loan_ecom_industry_seq;
CREATE TABLE IF NOT EXISTS adhoctemp.tmp_l00527489_20260317_finance_loan_ecom_industry_seq (
    usid STRING COMMENT '用户标识',
    ecom_industry_behavior_seq STRING COMMENT '电商行业行为序列（CSV表格格式）'
) COMMENT '电商行业行为序列表';

-- 表11: 广告事件明细表（依赖表3）
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260317_finance_loan_ad_event_details;
CREATE TABLE IF NOT EXISTS adhoctemp.tmp_l00527489_20260317_finance_loan_ad_event_details (
    usid STRING COMMENT '用户标识',
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
) COMMENT '广告事件明细表';

-- 表12: 异常用户标记表（依赖表3）
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260317_finance_loan_abnormal_users;
CREATE TABLE IF NOT EXISTS adhoctemp.tmp_l00527489_20260317_finance_loan_abnormal_users (
    usid STRING COMMENT '用户标识',
    total_impression_cnt BIGINT COMMENT '总曝光次数',
    total_click_cnt BIGINT COMMENT '总点击次数',
    total_conversion_cnt BIGINT COMMENT '总转化次数',
    abnormal_user_flag STRING COMMENT '异常用户标记'
) COMMENT '异常用户标记表';

-- 表13: 广告事件序列表（依赖表11）
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260317_finance_loan_ad_events;
CREATE TABLE IF NOT EXISTS adhoctemp.tmp_l00527489_20260317_finance_loan_ad_events (
    usid STRING COMMENT '用户标识',
    ad_event_seq STRING COMMENT '广告事件序列（CSV表格格式）'
) COMMENT '广告事件序列表';

-- 表14: 最终宽表（依赖表3、表4、表6、表10、表10a、表10e、表13、表12）
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260317_finance_loan_final_wide_table;
CREATE TABLE IF NOT EXISTS adhoctemp.tmp_l00527489_20260317_finance_loan_final_wide_table (
    usid STRING COMMENT '用户标识',
    sample_label STRING COMMENT '样本标签：positive/negative',
    first_conversion_type STRING COMMENT '首次转化类型（授信/动支/完件）',
    conversion_value_7d DOUBLE COMMENT '7天动支金额（标签期：3月11-17日）',
    conversion_cnt_7d BIGINT COMMENT '7天转化次数（标签期：3月11-17日）',
    user_profile_features STRING COMMENT '用户画像特征（特征期：3月10日快照）',
    app_behavior_seq STRING COMMENT 'APP行为序列（特征期：2月9日-3月10日，30天）',
    travel_car_behavior_seq STRING COMMENT '汽车/旅游/本地生活行为序列（特征期：2月9日-3月10日）',
    finance_behavior_seq STRING COMMENT '金融行业行为序列（来源：dwd_pps_financial_behavior_appdata_hm，特征期：2月9日-3月10日）',
    ecom_industry_behavior_seq STRING COMMENT '电商行业行为序列（来源：dwd_pps_ecommerce_behavior_appdata_hm，特征期：2月9日-3月10日）',
    ad_event_seq STRING COMMENT '广告事件序列（特征期：2月9日-3月10日，30天）',
    abnormal_user_flag STRING COMMENT '异常用户标记',
    create_time STRING COMMENT '创建时间'
) COMMENT '最终特征宽表（特征期与标签期严格分离）';


-- ============================================================================
-- 阶段 1：样本池构建（分步骤创建临时表）
-- ============================================================================

-- Step 1.1: 正样本 = 3月11-17日有完件转化的用户（直接采样，最多10000个）
-- 转化节点：event_type = 'loanCompletion'
-- 推广标的白名单：360借条、好分期、桔多多等20个小额借贷产品
INSERT INTO adhoctemp.tmp_l00527489_20260317_finance_loan_positive_samples
SELECT
    usid,
    'positive' AS sample_label,
    first_conversion_type,
    conversion_value_7d,
    conversion_cnt_7d
FROM (
    SELECT
        bind.usid,
        '完件' AS first_conversion_type,
        0 AS conversion_value_7d,
        COUNT(1) AS conversion_cnt_7d
    FROM pps.dwd_pps_finance_all_channel_conversion_event_dm evt
    INNER JOIN (
        SELECT dsid, usid
        FROM bicoredata.dwd_pty_combine_device_up_bind_ds
        WHERE pt_d = '20260304'
    ) bind ON evt.adid = bind.dsid
    WHERE evt.pt_d >= '20260311' AND evt.pt_d <= '20260317'
      AND evt.event_type = 'loanCompletion'
      AND evt.promotion_target IN ('360借条', '好分期', '桔多多', '洋钱罐借款', '榕树贷款', '度小满金融', '极融借款', '还呗', '小辉付', '拍拍贷借款', '安逸花', '宜享花', '小赢卡贷', '你我贷借款', '众安贷', '融360', '建信消费金融', '度小满', '奇富借条', '中原消费金融')
      AND bind.usid IS NOT NULL
    GROUP BY bind.usid
) t
DISTRIBUTE BY RAND()
SORT BY RAND()
LIMIT 10000;

-- Step 1.2: 负样本 = 金融画像宽表大盘用户（排除正样本，直接采样，最多10000个）
INSERT INTO adhoctemp.tmp_l00527489_20260317_finance_loan_negative_samples
SELECT
    usid,
    'negative' AS sample_label,
    '' AS first_conversion_type,
    0 AS conversion_value_7d,
    0 AS conversion_cnt_7d
FROM pps.ads_model_feature_finance_microloans_0206_all_latest_1
WHERE pt_d = '20260310'
  AND usid NOT IN (SELECT usid FROM adhoctemp.tmp_l00527489_20260317_finance_loan_positive_samples)
DISTRIBUTE BY RAND()
SORT BY RAND()
LIMIT 10000;

-- Step 1.3: 合并正负样本
INSERT INTO adhoctemp.tmp_l00527489_20260317_finance_loan_sample_pool
SELECT usid, sample_label, first_conversion_type, conversion_value_7d, conversion_cnt_7d
FROM adhoctemp.tmp_l00527489_20260317_finance_loan_positive_samples
UNION ALL
SELECT usid, sample_label, first_conversion_type, conversion_value_7d, conversion_cnt_7d
FROM adhoctemp.tmp_l00527489_20260317_finance_loan_negative_samples;


-- ============================================================================
-- 阶段 2：用户画像特征表（使用3月10日快照，避免标签泄露）
-- ============================================================================

INSERT INTO adhoctemp.tmp_l00527489_20260317_finance_loan_user_profile
SELECT usid, user_profile_features
FROM (
    SELECT
        usid,
        CONCAT_WS(';',
            -- ===== 基础人口属性 =====
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
            CONCAT('婚姻状态:', COALESCE(marriage_status_dev, 'unknown')),
            CONCAT('育儿状态:', COALESCE(parenting_status_dev, 'unknown')),

            -- ===== 地域属性 =====
            CONCAT('省份:', COALESCE(province_new_dev, 'unknown')),
            CONCAT('城市:', COALESCE(city_new_dev, 'unknown')),
            CONCAT('城市等级:', COALESCE(city_new_grade_dev, 'unknown')),
            CONCAT('常驻城市:', COALESCE(pps_visit_city_year_dev, 'unknown')),

            -- ===== 设备属性 =====
            CONCAT('设备品牌:', COALESCE(brand_new_dev, 'unknown')),
            CONCAT('设备型号:', COALESCE(product_new_dev, 'unknown')),
            CONCAT('设备系列:', COALESCE(series_new_dev, 'unknown')),
            CONCAT('设备价格:', COALESCE(price_new_dev, 'unknown')),
            CONCAT('激活时长:', COALESCE(dev_first_time_duration_dev, '0')),
            CONCAT('月在线天数:', COALESCE(push_online_days_30d_dev, '0'), '天'),

            -- ===== 资产属性 =====
            CONCAT('有房:', CASE
                WHEN owner_house_flag_dev = '1' THEN '是'
                ELSE '否'
            END),
            CONCAT('有车:', CASE
                WHEN owner_cars_user_dev = '1' THEN '是'
                ELSE '否'
            END),
            CONCAT('小区等级:', COALESCE(level_of_community_dev, 'unknown')),
            CONCAT('小区均价:', COALESCE(price_of_community_dev, 'unknown')),

            -- ===== 消费能力 =====
            CONCAT('消费能力:', COALESCE(consume_ability_dev, 'unknown')),
            CONCAT('消费频率:', CASE
                WHEN consume_frequency_dev = 'p1' THEN '极高'
                WHEN consume_frequency_dev = 'p2' THEN '高'
                WHEN consume_frequency_dev = 'p3' THEN '较高'
                WHEN consume_frequency_dev = 'p4' THEN '中'
                WHEN consume_frequency_dev = 'p5' THEN '低'
                ELSE 'unknown'
            END),
            CONCAT('30天消费金额:', COALESCE(CAST(consume_amount_30d AS STRING), '0')),
            CONCAT('30天消费频次:', COALESCE(CAST(consume_frequency_30d AS STRING), '0')),

            -- ===== 金融资质 =====
            CONCAT('社保卡持有:', CASE
                WHEN social_security_card_owner = '1' THEN '有社保卡'
                ELSE '无社保卡'
            END),
            CONCAT('实名认证:', CASE
                WHEN up_realname_verify_dev = '1' THEN '已实名'
                ELSE '未实名'
            END),

            -- ===== 社会属性 =====
            CONCAT('高净值人群:', COALESCE(socialattr_fact_high_class_dev, 'unknown')),
            CONCAT('职业三级分类:', COALESCE(career_third_level_type_dev, 'unknown'))
        ) AS user_profile_features,
        ROW_NUMBER() OVER (PARTITION BY usid ORDER BY usid) AS rn
    FROM pps.ads_model_feature_finance_microloans_0206_all_latest_1
    WHERE pt_d = '20260310'
      AND usid IN (SELECT usid FROM adhoctemp.tmp_l00527489_20260317_finance_loan_sample_pool)
) t
WHERE rn = 1;


-- ============================================================================
-- 阶段 3：APP 行为数据表（特征期：2月9日-3月10日，30天）
-- ============================================================================

-- Step 3.1: 提取 APP 事件明细（合并使用行为和安装卸载行为）

-- 插入使用行为数据（最近7天每天TOP30）
INSERT INTO adhoctemp.tmp_l00527489_20260317_finance_loan_app_events
SELECT
    usid,
    event_date,
    event_type,
    app_name,
    usage_duration,
    row_num
FROM (
    SELECT
        usid,
        event_date,
        event_type,
        app_name,
        usage_duration,
        ROW_NUMBER() OVER (PARTITION BY usid, event_date ORDER BY usage_duration DESC) AS row_num
    FROM (
        SELECT
            bind.usid,
            app.pt_d AS event_date,
            'appUsage' AS event_type,
            COALESCE(app_info.promote_app_name, app.package_name) AS app_name,
            SUM(CAST(COALESCE(app.total_time, 0) / 1000 AS BIGINT)) AS usage_duration
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
          AND bind.usid IN (SELECT usid FROM adhoctemp.tmp_l00527489_20260317_finance_loan_sample_pool)
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
        GROUP BY bind.usid, app.pt_d, COALESCE(app_info.promote_app_name, app.package_name)
        HAVING SUM(CAST(COALESCE(app.total_time, 0) / 1000 AS BIGINT)) > 5
    ) agg
) t
WHERE row_num <= 30;

-- 插入使用行为数据（7天之前总共TOP100）
INSERT INTO adhoctemp.tmp_l00527489_20260317_finance_loan_app_events
SELECT
    usid,
    event_date,
    event_type,
    app_name,
    usage_duration,
    row_num
FROM (
    SELECT
        usid,
        event_date,
        event_type,
        app_name,
        usage_duration,
        ROW_NUMBER() OVER (PARTITION BY usid ORDER BY usage_duration DESC) AS row_num
    FROM (
        SELECT
            bind.usid,
            app.pt_d AS event_date,
            'appUsage' AS event_type,
            COALESCE(app_info.promote_app_name, app.package_name) AS app_name,
            SUM(CAST(COALESCE(app.total_time, 0) / 1000 AS BIGINT)) AS usage_duration
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
          AND bind.usid IN (SELECT usid FROM adhoctemp.tmp_l00527489_20260317_finance_loan_sample_pool)
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
        GROUP BY bind.usid, app.pt_d, COALESCE(app_info.promote_app_name, app.package_name)
        HAVING SUM(CAST(COALESCE(app.total_time, 0) / 1000 AS BIGINT)) > 5
    ) agg
) t
WHERE row_num <= 100;

-- 插入安装行为数据（最近1000次）
INSERT INTO adhoctemp.tmp_l00527489_20260317_finance_loan_app_events
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
      AND bind.usid IN (SELECT usid FROM adhoctemp.tmp_l00527489_20260317_finance_loan_sample_pool)
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

-- 插入卸载行为数据（最近100次）
INSERT INTO adhoctemp.tmp_l00527489_20260317_finance_loan_app_events
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
      AND bind.usid IN (SELECT usid FROM adhoctemp.tmp_l00527489_20260317_finance_loan_sample_pool)
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

-- Step 3.2: 构建 APP 行为序列（CSV表格格式）
INSERT INTO adhoctemp.tmp_l00527489_20260317_finance_loan_app_behavior
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
FROM adhoctemp.tmp_l00527489_20260317_finance_loan_app_events
GROUP BY usid;


-- ============================================================================
-- 阶段 3（续）：汽车/旅游/本地生活行为数据（特征期：2月9日-3月10日）
-- ============================================================================

-- Step 3.5: 提取汽车/旅游行为明细
-- 来源：pps.dwd_pps_travel_car_behavior_appdata_hm
-- 保留5个 data_id，字段含义如下：
--
-- 500_13_0001_07: 文旅12306高铁短信
--   field1=车次（G+ext_value2，ext_value2为空则过滤）, field2=日期(ext_value3)
--   无 app_name
--
-- 500_13_0001_03: 文旅OTA短信行程识别
--   field1=通知类型(ext_value3: reserved/refund/ticket等)
--   field2=酒店名称+地址(ext_value4), field3=行程信息(ext_value6), field4=时间(ext_value7)
--   无 app_name
--
-- 500_11_0009_1: 汽车浏览/搜索
--   app_name=ext_value1
--   field1=行为标识(ext_value2: 100_5000浏览/100_5001搜索)
--   field2=页面ID(ext_value3), field3=品牌(ext_value4)--   field4=型号(ext_value5)，次数在ext_value6（拼入field4）
--
-- 500_11_0008_1: 汽车APP点击
--   app_name=ext_value1
--   field1=行为标识(ext_value2: 100_5000浏览/100_5001搜索)
--   field2=页面ID(ext_value3), field3=品牌(ext_value4), field4=型号(ext_value5)
--
-- 400_11_0009_1: 试驾信息
--   field1=试驾发送方(ext_value1), 无 app_name

INSERT INTO adhoctemp.tmp_l00527489_20260317_finance_loan_travel_car_events
SELECT
    usid,
    event_date,
    behavior_type,
    app_name,
    field1,
    field2,
    field3,
    field4,
    data_id,
    row_num
FROM (
    SELECT
        bind.usid,
        SUBSTR(tcb.pt_h, 1, 8) AS event_date,
        COALESCE(CONCAT(dm.industry, dm.behavior_type), tcb.data_id) AS behavior_type,
        -- app_name：500_11_xxxx 用 ext_value1，文旅短信/试驾无 app
        CASE
            WHEN tcb.data_id IN ('500_11_0009_1', '500_11_0008_1')
                THEN COALESCE(am.app_name, CONCAT('应用ID:', tcb.ext_value1))
            ELSE ''
        END AS app_name,
        -- field1：各 data_id 核心字段1
        CASE
            WHEN tcb.data_id = '500_13_0001_07'
                THEN CONCAT('G', tcb.ext_value2)                              -- 高铁车次，补G前缀
            WHEN tcb.data_id = '500_13_0001_03'
                THEN tcb.ext_value3                                            -- 通知类型
            WHEN tcb.data_id IN ('500_11_0009_1', '500_11_0008_1')
                THEN CASE tcb.ext_value2
                         WHEN '100_5000' THEN '浏览'
                         WHEN '100_5001' THEN '搜索'
                         ELSE tcb.ext_value2
                     END                                                       -- 行为标识
            WHEN tcb.data_id = '400_11_0009_1'
                THEN tcb.ext_value1                                            -- 试驾发送方
            ELSE NULL
        END AS field1,
        -- field2：各 data_id 核心字段2
        CASE
            WHEN tcb.data_id = '500_13_0001_07'
                THEN tcb.ext_value3                                            -- 日期
            WHEN tcb.data_id = '500_13_0001_03'
                THEN tcb.ext_value4                                            -- 酒店名称+地址
            WHEN tcb.data_id IN ('500_11_0009_1', '500_11_0008_1')
                THEN tcb.ext_value3                                            -- 页面ID
            ELSE NULL
        END AS field2,
        -- field3：各 data_id 核心字段3
        CASE
            WHEN tcb.data_id = '500_13_0001_03'
                THEN tcb.ext_value6                                            -- 行程信息
            WHEN tcb.data_id IN ('500_11_0009_1', '500_11_0008_1')
                THEN tcb.ext_value4                                            -- 品牌名称
            ELSE NULL
        END AS field3,
        -- field4：各 data_id 核心字段4
        CASE
            WHEN tcb.data_id = '500_13_0001_03'
                THEN tcb.ext_value7                                            -- 时间
            WHEN tcb.data_id = '500_11_0009_1'
                THEN CONCAT(COALESCE(tcb.ext_value5,''), '|次数:', COALESCE(tcb.ext_value6,''))  -- 型号+次数
            WHEN tcb.data_id = '500_11_0008_1'
                THEN tcb.ext_value5                                            -- 型号
            ELSE NULL
        END AS field4,
        tcb.data_id,
        ROW_NUMBER() OVER (PARTITION BY bind.usid ORDER BY tcb.pt_h DESC) AS row_num
    FROM pps.dwd_pps_travel_car_behavior_appdata_hm tcb
    INNER JOIN (
        SELECT dsid, usid
        FROM bicoredata.dwd_pty_combine_device_up_bind_ds
        WHERE pt_d = '20260304'
    ) bind ON tcb.adid = bind.dsid
    LEFT JOIN adhoctemp.tmp_l00527489_20260317_dataid_mapping dm
        ON tcb.data_id = dm.data_id
    -- app_name 映射（仅 500_11_xxxx）
    LEFT JOIN adhoctemp.tmp_l00527489_20260317_appid_mapping am
        ON tcb.data_id IN ('500_11_0009_1', '500_11_0008_1')
        AND tcb.ext_value1 = am.app_id
    WHERE tcb.data_id IN ('500_13_0001_07', '500_13_0001_03', '500_11_0009_1', '500_11_0008_1', '400_11_0009_1')
      AND tcb.pt_h >= '2026020900' AND tcb.pt_h <= '2026031023'
      AND bind.usid IN (SELECT usid FROM adhoctemp.tmp_l00527489_20260317_finance_loan_sample_pool)
      -- 500_13_0001_07 车次为空则过滤
      AND NOT (tcb.data_id = '500_13_0001_07' AND (tcb.ext_value2 IS NULL OR tcb.ext_value2 = ''))
) t
WHERE row_num <= 200;

-- Step 3.6: 构建汽车/旅游行为序列（CSV表格格式）
-- 字段含义说明（按 data_id 区分）：
--   500_13_0001_07: 行为类型,,车次(G+车次号),日期,,
--   500_13_0001_03: 行为类型,,通知类型,酒店名+地址,行程信息,时间
--   500_11_0009_1:  行为类型,应用,浏览/搜索,页面名称,品牌,型号|次数
--   500_11_0008_1:  行为类型,应用,浏览/搜索,页面名称,品牌,型号
--   400_11_0009_1:  行为类型,,试驾发送方,,,
INSERT INTO adhoctemp.tmp_l00527489_20260317_finance_loan_travel_car_behavior
SELECT
    usid,
    CONCAT(
        '日期,行为类型,应用,字段1,字段2,字段3,字段4,data_id\n',
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
    ) AS travel_car_behavior_seq
FROM adhoctemp.tmp_l00527489_20260317_finance_loan_travel_car_events
GROUP BY usid;


-- ============================================================================
-- 阶段 3（续）：金融专属行为数据（特征期：2月9日-3月10日）
-- ============================================================================

-- Step 3.7: 提取金融行业行为明细
-- 来源：pps.dwd_pps_financial_behavior_appdata_hm
-- 保留4个有效 data_id：
--   500_12_0020_1: 带宽营销，ext_value1=应用ID
--   400_12_1001_3: 金融券商广告主短信，ext_value1 无值，ext_value2=券商名字
--   400_12_0017_1: 金融借贷授信/动支/完件/营销短信，ext_value1=应用信息，ext_value2=营销短信类型
--   400_12_0016_1: 金融保险投保短信，ext_value1=应用信息，ext_value2=营销短信类型
-- app_name：400_12_1001_3 用 ext_value2 关联 appid_mapping，其余用 ext_value1

INSERT INTO adhoctemp.tmp_l00527489_20260317_finance_loan_finance_behavior_events
SELECT
    usid,
    event_date,
    behavior_type,
    app_name,
    ext_value2,
    ext_value3,
    ext_value4,
    ext_value5,
    data_id,
    row_num
FROM (
    SELECT
        bind.usid,
        SUBSTR(fb.pt_h, 1, 8) AS event_date,
        COALESCE(
            CONCAT(dm.industry, dm.behavior_type),
            fb.data_id
        ) AS behavior_type,
        -- 400_12_1001_3 的应用名在 ext_value2，其余在 ext_value1
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
        ROW_NUMBER() OVER (PARTITION BY bind.usid ORDER BY fb.pt_h DESC) AS row_num
    FROM pps.dwd_pps_financial_behavior_appdata_hm fb
    INNER JOIN (
        SELECT dsid, usid
        FROM bicoredata.dwd_pty_combine_device_up_bind_ds
        WHERE pt_d = '20260304'
    ) bind ON fb.adid = bind.dsid
    LEFT JOIN adhoctemp.tmp_l00527489_20260317_dataid_mapping dm
        ON fb.data_id = dm.data_id
    LEFT JOIN adhoctemp.tmp_l00527489_20260317_appid_mapping am
        ON CASE
            WHEN fb.data_id = '400_12_1001_3' THEN fb.ext_value2
            ELSE fb.ext_value1
        END = am.app_id
    WHERE fb.data_id IN ('500_12_0020_1', '400_12_1001_3', '400_12_0017_1', '400_12_0016_1')
      AND fb.pt_h >= '2026020900' AND fb.pt_h <= '2026031023'
      AND bind.usid IN (SELECT usid FROM adhoctemp.tmp_l00527489_20260317_finance_loan_sample_pool)
) t
WHERE row_num <= 200;

-- Step 3.8: 构建金融行业行为序列（CSV表格格式）
-- CSV列：日期,行为类型,应用,短信类型/券商名(ext_value2),扩展字段3,扩展字段4,扩展字段5,data_id
INSERT INTO adhoctemp.tmp_l00527489_20260317_finance_loan_finance_behavior_seq
SELECT
    usid,
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
    ) AS finance_behavior_seq
FROM adhoctemp.tmp_l00527489_20260317_finance_loan_finance_behavior_events
GROUP BY usid;


-- ============================================================================
-- 阶段 3（续）：电商行业行为数据（特征期：2月9日-3月10日）
-- ============================================================================

-- Step 3.11: 提取电商行业行为明细
-- 来源：pps.dwd_pps_ecommerce_behavior_appdata_hm
-- 保留3个 data_id：
--   500_20_0009_02: 购买事件，app_id=ext_value2，L1=ext_value3，L2=ext_value4，L3=ext_value5，L4=ext_value6，商品ID=ext_value8
--   500_20_0005_7:  详情页浏览，无app_id，L1=ext_value2，L2=ext_value3，L3=ext_value4，L4=ext_value5，商品ID=ext_value7
--   500_10_0013_7:  电商行为，app_id=ext_value8，L1=ext_value2，L2=ext_value3，L3=ext_value4，L4=ext_value5，商品ID=ext_value7
-- L3 标签名称通过 tmp_l00527489_20260317_tag_level3（tag_code=L3 code, tag_name=L3名称）关联
-- app_name 通过 appid_mapping 关联

INSERT INTO adhoctemp.tmp_l00527489_20260317_finance_loan_ecom_industry_events
SELECT
    usid,
    event_date,
    behavior_type,
    app_name,
    category_l3_code,
    category_l3_name,
    goods_id,
    data_id,
    row_num
FROM (
    SELECT
        bind.usid,
        SUBSTR(eb.pt_h, 1, 8) AS event_date,
        COALESCE(
            CONCAT(dm.industry, dm.behavior_type),
            eb.data_id
        ) AS behavior_type,
        -- app_id 位置：500_20_0009_02 用 ext_value2，500_10_0013_7 用 ext_value8，500_20_0005_7 无
        COALESCE(
            am.app_name,
            CASE
                WHEN eb.data_id = '500_20_0009_02' THEN CONCAT('应用ID:', eb.ext_value2)
                WHEN eb.data_id = '500_10_0013_7'  THEN CONCAT('应用ID:', eb.ext_value8)
                ELSE ''
            END
        ) AS app_name,
        -- L3 code 位置：500_20_0009_02 用 ext_value5，其余用 ext_value4
        CASE
            WHEN eb.data_id = '500_20_0009_02' THEN eb.ext_value5
            ELSE eb.ext_value4
        END AS category_l3_code,
        -- L3 名称通过 tmp_l00527489_20260317_tag_level3 映射
        tl3.tag_name AS category_l3_name,
        -- 商品ID：500_20_0009_02 用 ext_value8，其余用 ext_value7
        CASE
            WHEN eb.data_id = '500_20_0009_02' THEN eb.ext_value8
            ELSE eb.ext_value7
        END AS goods_id,
        eb.data_id,
        ROW_NUMBER() OVER (PARTITION BY bind.usid ORDER BY eb.pt_h DESC) AS row_num
    FROM pps.dwd_pps_ecommerce_behavior_appdata_hm eb
    INNER JOIN (
        SELECT dsid, usid
        FROM bicoredata.dwd_pty_combine_device_up_bind_ds
        WHERE pt_d = '20260304'
    ) bind ON eb.adid = bind.dsid
    LEFT JOIN adhoctemp.tmp_l00527489_20260317_dataid_mapping dm
        ON eb.data_id = dm.data_id
    -- app_name 映射：按 data_id 选取对应 app_id 字段
    LEFT JOIN adhoctemp.tmp_l00527489_20260317_appid_mapping am
        ON CASE
            WHEN eb.data_id = '500_20_0009_02' THEN eb.ext_value2
            WHEN eb.data_id = '500_10_0013_7'  THEN eb.ext_value8
            ELSE NULL
        END = am.app_id
    -- L3 标签名称映射
    LEFT JOIN adhoctemp.tmp_l00527489_20260317_tag_level3 tl3
        ON CASE
            WHEN eb.data_id = '500_20_0009_02' THEN eb.ext_value5
            ELSE eb.ext_value4
        END = tl3.tag_code
    WHERE eb.data_id IN ('500_20_0009_02', '500_20_0005_7', '500_10_0013_7')
      AND eb.pt_h >= '2026020900' AND eb.pt_h <= '2026031023'
      AND bind.usid IN (SELECT usid FROM adhoctemp.tmp_l00527489_20260317_finance_loan_sample_pool)
) t
WHERE row_num <= 200;

-- Step 3.12: 构建电商行业行为序列（CSV表格格式）
INSERT INTO adhoctemp.tmp_l00527489_20260317_finance_loan_ecom_industry_seq
SELECT
    usid,
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
    ) AS ecom_industry_behavior_seq
FROM adhoctemp.tmp_l00527489_20260317_finance_loan_ecom_industry_events
GROUP BY usid;


-- ============================================================================
-- 阶段 4：广告事件数据表（特征期：2月9日-3月10日，避免标签泄露）
-- ============================================================================

-- Step 4.1: 收集广告事件明细（曝光、点击、转化各保留最近100条）

-- 插入曝光事件（最近100条，不含创意信息）
-- 行业过滤：保留金融相关行业（cust_industry_level1 包含金融/银行/保险等）
INSERT INTO adhoctemp.tmp_l00527489_20260317_finance_loan_ad_event_details
SELECT
    usid,
    event_date,
    event_type,
    industry_level1,
    industry_level2,
    position_name,
    promote_app_name,
    NULL AS creative_title,
    NULL AS creative_desc,
    NULL AS creative_label,
    event_count,
    row_num
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
    WHERE ind.pt_d >= '20260209' AND ind.pt_d <= '20260310'
      AND ind.usid IN (SELECT usid FROM adhoctemp.tmp_l00527489_20260317_finance_loan_sample_pool)
      AND ind.received_total_imp > 0
) t
WHERE row_num <= 100;

-- 插入点击事件（最近100条，关联创意信息）
INSERT INTO adhoctemp.tmp_l00527489_20260317_finance_loan_ad_event_details
SELECT
    usid,
    event_date,
    event_type,
    industry_level1,
    industry_level2,
    position_name,
    promote_app_name,
    creative_title,
    creative_desc,
    creative_label,
    event_count,
    row_num
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
        WHERE pt_h = '2026031023'
    ) crt ON ind.creative_id = crt.creative_id
    WHERE ind.pt_d >= '20260209' AND ind.pt_d <= '20260310'
      AND ind.usid IN (SELECT usid FROM adhoctemp.tmp_l00527489_20260317_finance_loan_sample_pool)
      AND ind.received_total_click > 0
) t
WHERE row_num <= 100;

-- 插入转化事件（最近100条，不含创意信息，过滤无效事件类型）
INSERT INTO adhoctemp.tmp_l00527489_20260317_finance_loan_ad_event_details
SELECT
    usid,
    event_date,
    event_type,
    industry_level1,
    industry_level2,
    position_name,
    promote_app_name,
    NULL AS creative_title,
    NULL AS creative_desc,
    NULL AS creative_label,
    event_count,
    row_num
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
    WHERE ind.pt_d >= '20260209' AND ind.pt_d <= '20260310'
      AND ind.usid IN (SELECT usid FROM adhoctemp.tmp_l00527489_20260317_finance_loan_sample_pool)
      AND ind.event_type NOT IN ('repeatedImp','playPause','intentSuccess','playStart','webclose','webopen','webloadfinish','skip','downloadstart','playEnd','installStart','impInLandingPage','playResume','clickLandingpage','repeatedClick','intentFail','appFirstOpen','appOpen','browse','soundClickOn','easterEggEnd','downloadResume')
      AND ind.total_task_cnvr_target_cnvr_cnt > 0
) t
WHERE row_num <= 100;

-- Step 4.2: 计算异常用户标记（基于全量数据统计）
INSERT INTO adhoctemp.tmp_l00527489_20260317_finance_loan_abnormal_users
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
WHERE ind.pt_d >= '20260209' AND ind.pt_d <= '20260310'
  AND ind.usid IN (SELECT usid FROM adhoctemp.tmp_l00527489_20260317_finance_loan_sample_pool)
  AND ind.event_type NOT IN ('repeatedImp','playPause','intentSuccess','playStart','webclose','webopen','webloadfinish','skip','downloadstart','playEnd','installStart','impInLandingPage','playResume','clickLandingpage','repeatedClick','intentFail','appFirstOpen','appOpen','browse','soundClickOn','easterEggEnd','downloadResume')
GROUP BY ind.usid;

-- Step 4.3: 构建广告事件序列（CSV表格格式）
INSERT INTO adhoctemp.tmp_l00527489_20260317_finance_loan_ad_events
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
FROM adhoctemp.tmp_l00527489_20260317_finance_loan_ad_event_details
GROUP BY usid;


-- ============================================================================
-- 阶段 5：最终宽表 JOIN
-- ============================================================================

INSERT INTO adhoctemp.tmp_l00527489_20260317_finance_loan_final_wide_table
SELECT
    s.usid,
    s.sample_label,
    s.first_conversion_type,
    s.conversion_value_7d,
    s.conversion_cnt_7d,
    COALESCE(p.user_profile_features, '') AS user_profile_features,
    COALESCE(a.app_behavior_seq, '') AS app_behavior_seq,
    COALESCE(tc.travel_car_behavior_seq, '') AS travel_car_behavior_seq,
    COALESCE(fb.finance_behavior_seq, '') AS finance_behavior_seq,
    COALESCE(eib.ecom_industry_behavior_seq, '') AS ecom_industry_behavior_seq,
    COALESCE(e.ad_event_seq, '') AS ad_event_seq,
    COALESCE(ab.abnormal_user_flag, '正常') AS abnormal_user_flag,
    FROM_UNIXTIME(UNIX_TIMESTAMP()) AS create_time
FROM adhoctemp.tmp_l00527489_20260317_finance_loan_sample_pool s
LEFT JOIN adhoctemp.tmp_l00527489_20260317_finance_loan_user_profile p ON s.usid = p.usid
LEFT JOIN adhoctemp.tmp_l00527489_20260317_finance_loan_app_behavior a ON s.usid = a.usid
LEFT JOIN adhoctemp.tmp_l00527489_20260317_finance_loan_travel_car_behavior tc ON s.usid = tc.usid
LEFT JOIN adhoctemp.tmp_l00527489_20260317_finance_loan_finance_behavior_seq fb ON s.usid = fb.usid
LEFT JOIN adhoctemp.tmp_l00527489_20260317_finance_loan_ecom_industry_seq eib ON s.usid = eib.usid
LEFT JOIN adhoctemp.tmp_l00527489_20260317_finance_loan_ad_events e ON s.usid = e.usid
LEFT JOIN adhoctemp.tmp_l00527489_20260317_finance_loan_abnormal_users ab ON s.usid = ab.usid;


-- ============================================================================
-- 验证 SQL
-- ============================================================================

-- 1. 样本分布验证（正负样本数、转化率）
SELECT
    sample_label,
    COUNT(*) AS cnt,
    COUNT(CASE WHEN first_conversion_type != '' THEN 1 ELSE NULL END) AS with_conversion_type,
    ROUND(AVG(conversion_value_7d), 2) AS avg_conversion_value,
    ROUND(AVG(conversion_cnt_7d), 2) AS avg_conversion_cnt
FROM adhoctemp.tmp_l00527489_20260317_finance_loan_sample_pool
GROUP BY sample_label;

-- 2. 特征覆盖率验证
SELECT
    COUNT(*) AS total_users,
    COUNT(CASE WHEN user_profile_features != '' THEN 1 ELSE NULL END) AS with_profile,
    COUNT(CASE WHEN app_behavior_seq != '' THEN 1 ELSE NULL END) AS with_app_behavior,
    COUNT(CASE WHEN travel_car_behavior_seq != '' THEN 1 ELSE NULL END) AS with_travel_car_behavior,
    COUNT(CASE WHEN finance_behavior_seq != '' THEN 1 ELSE NULL END) AS with_finance_behavior,
    COUNT(CASE WHEN ecom_industry_behavior_seq != '' THEN 1 ELSE NULL END) AS with_ecom_industry_behavior,
    COUNT(CASE WHEN ad_event_seq != '' THEN 1 ELSE NULL END) AS with_ad_events,
    ROUND(COUNT(CASE WHEN user_profile_features != '' THEN 1 ELSE NULL END) * 100.0 / COUNT(*), 2) AS profile_coverage_pct,
    ROUND(COUNT(CASE WHEN app_behavior_seq != '' THEN 1 ELSE NULL END) * 100.0 / COUNT(*), 2) AS app_behavior_coverage_pct,
    ROUND(COUNT(CASE WHEN travel_car_behavior_seq != '' THEN 1 ELSE NULL END) * 100.0 / COUNT(*), 2) AS travel_car_coverage_pct,
    ROUND(COUNT(CASE WHEN finance_behavior_seq != '' THEN 1 ELSE NULL END) * 100.0 / COUNT(*), 2) AS finance_behavior_coverage_pct,
    ROUND(COUNT(CASE WHEN ecom_industry_behavior_seq != '' THEN 1 ELSE NULL END) * 100.0 / COUNT(*), 2) AS ecom_industry_coverage_pct,
    ROUND(COUNT(CASE WHEN ad_event_seq != '' THEN 1 ELSE NULL END) * 100.0 / COUNT(*), 2) AS ad_event_coverage_pct
FROM adhoctemp.tmp_l00527489_20260317_finance_loan_final_wide_table;

-- 3. 正样本转化类型分布验证（应全为完件）
SELECT
    first_conversion_type,
    COUNT(*) AS cnt,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) AS pct
FROM adhoctemp.tmp_l00527489_20260317_finance_loan_final_wide_table
WHERE sample_label = 'positive'
GROUP BY first_conversion_type;

-- 4. 正负样本不重叠验证（期望结果为0）
SELECT
    '正负样本不重叠验证' AS check_name,
    COUNT(*) AS invalid_cnt
FROM adhoctemp.tmp_l00527489_20260317_finance_loan_final_wide_table
WHERE sample_label = 'negative' AND usid IN (
    SELECT usid FROM adhoctemp.tmp_l00527489_20260317_finance_loan_final_wide_table WHERE sample_label = 'positive'
);

-- 5. 异常用户统计
SELECT
    abnormal_user_flag,
    COUNT(*) AS user_cnt,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) AS pct
FROM adhoctemp.tmp_l00527489_20260317_finance_loan_final_wide_table
GROUP BY abnormal_user_flag;

-- 6. 样本数据预览（前10条）
SELECT
    usid,
    sample_label,
    first_conversion_type,
    conversion_value_7d,
    conversion_cnt_7d,
    abnormal_user_flag,
    SUBSTR(user_profile_features, 1, 100) AS profile_preview,
    SUBSTR(app_behavior_seq, 1, 100) AS app_behavior_preview,
    SUBSTR(ecom_industry_behavior_seq, 1, 100) AS ecom_industry_behavior_preview,
    SUBSTR(ad_event_seq, 1, 100) AS ad_event_preview
FROM adhoctemp.tmp_l00527489_20260317_finance_loan_final_wide_table
LIMIT 10;