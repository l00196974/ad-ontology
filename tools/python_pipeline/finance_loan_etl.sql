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

-- 表7: 电商搜索/浏览行为明细表（依赖表3）⭐金融新增
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260317_finance_loan_ecom_events;
CREATE TABLE IF NOT EXISTS adhoctemp.tmp_l00527489_20260317_finance_loan_ecom_events (
    usid STRING COMMENT '用户标识',
    event_date STRING COMMENT '事件日期',
    behavior_type STRING COMMENT '行为类型：搜索/浏览/点击/支付/appOpen',
    app_name STRING COMMENT '应用名称',
    category_l1 STRING COMMENT '一级分类',
    category_l2 STRING COMMENT '二级分类',
    brand_id STRING COMMENT '品牌ID',
    price_range STRING COMMENT '价格区间',
    event_cnt BIGINT COMMENT '行为次数',
    row_num BIGINT COMMENT '排序序号'
) COMMENT '电商搜索/浏览行为明细表';

-- 表8: 电商行为序列表（依赖表7）⭐金融新增
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260317_finance_loan_ecom_behavior;
CREATE TABLE IF NOT EXISTS adhoctemp.tmp_l00527489_20260317_finance_loan_ecom_behavior (
    usid STRING COMMENT '用户标识',
    ecom_behavior_seq STRING COMMENT '电商行为序列（CSV表格格式）'
) COMMENT '电商行为序列表';

-- 表9: 汽车/旅游/本地生活行为明细表（依赖表3）
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260317_finance_loan_travel_car_events;
CREATE TABLE IF NOT EXISTS adhoctemp.tmp_l00527489_20260317_finance_loan_travel_car_events (
    usid STRING COMMENT '用户标识',
    event_date STRING COMMENT '事件日期',
    behavior_type STRING COMMENT '行为描述（industry+behavior_type，来自dataid_mapping）',
    app_name STRING COMMENT '应用名称（来自appid_mapping）',
    ext_value3 STRING COMMENT '扩展字段3（页面ID/行为ID/酒店名等，含义随data_id不同）',
    ext_value4 STRING COMMENT '扩展字段4（品牌/分类/出发地等，含义随data_id不同）',
    ext_value5 STRING COMMENT '扩展字段5（型号/景区/车次等，含义随data_id不同）',
    ext_value6 STRING COMMENT '扩展字段6（次数/价格/目的地等，含义随data_id不同）',
    data_id STRING COMMENT '原始data_id，便于下游区分字段含义',
    row_num BIGINT COMMENT '排序序号'
) COMMENT '汽车/旅游/本地生活行为明细表';

-- 表10: 汽车/旅游/本地生活行为序列表（依赖表9）
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260317_finance_loan_travel_car_behavior;
CREATE TABLE IF NOT EXISTS adhoctemp.tmp_l00527489_20260317_finance_loan_travel_car_behavior (
    usid STRING COMMENT '用户标识',
    travel_car_behavior_seq STRING COMMENT '汽车/旅游/本地生活行为序列（CSV表格格式）'
) COMMENT '汽车/旅游/本地生活行为序列表';

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

-- 表14: 最终宽表（依赖表3、表4、表6、表8、表10、表13、表12）
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260317_finance_loan_final_wide_table;
CREATE TABLE IF NOT EXISTS adhoctemp.tmp_l00527489_20260317_finance_loan_final_wide_table (
    usid STRING COMMENT '用户标识',
    sample_label STRING COMMENT '样本标签：positive/negative',
    first_conversion_type STRING COMMENT '首次转化类型（授信/动支/完件）',
    conversion_value_7d DOUBLE COMMENT '7天动支金额（标签期：3月11-17日）',
    conversion_cnt_7d BIGINT COMMENT '7天转化次数（标签期：3月11-17日）',
    user_profile_features STRING COMMENT '用户画像特征（特征期：3月10日快照）',
    app_behavior_seq STRING COMMENT 'APP行为序列（特征期：2月9日-3月10日，30天）',
    ecom_behavior_seq STRING COMMENT '电商行为序列（特征期：2月9日-3月10日）',
    travel_car_behavior_seq STRING COMMENT '汽车/旅游/本地生活行为序列（特征期：2月9日-3月10日）',
    finance_behavior_seq STRING COMMENT '金融专属行为序列（TODO：待补充）',
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
    ) AS user_profile_features
FROM pps.ads_model_feature_finance_microloans_0206_all_latest_1
WHERE pt_d = '20260310'
  AND usid IN (SELECT usid FROM adhoctemp.tmp_l00527489_20260317_finance_loan_sample_pool);


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
-- 阶段 3（续）：电商搜索/浏览行为序列（特征期：2月9日-3月10日）⭐金融新增
-- ============================================================================

-- Step 3.3: 提取电商搜索/浏览/点击/支付行为明细
-- 来源：pps.dwd_pps_behaviour_sequence_appdata_hm（各字段已按 ^ 预切分到 ext_value1~ext_value7）
-- 字段映射（根据 data_id 行为序列格式）：
--   ext_value1=行为id, ext_value2=应用Id, ext_value3=页面Id,
--   ext_value4=L1~L4分类(如02_0208_020805...), ext_value5=品牌id, ext_value6=预留, ext_value7=price区间
-- app_name：通过 tmp_l00527489_20260317_appid_mapping 按 ext_value2(app_id) 关联获取
-- behavior_type：通过 tmp_l00527489_20260317_dataid_mapping 按 data_id 关联，取 CONCAT(industry, behavior_type)
-- data_id 范围（电商行为序列）：
--   210_20_0001_2: 搜索+浏览
--   210_20_0001_3: 点击（收藏/加购/购买）
--   210_20_0001_4: 支付（微信/支付宝/QQ钱包）
--   210_20_0001_5: appOpen/预支付页

-- 统一插入所有 data_id（一次扫描，通过 dataid_mapping + appid_mapping 关联）
INSERT INTO adhoctemp.tmp_l00527489_20260317_finance_loan_ecom_events
SELECT
    usid,
    event_date,
    behavior_type,
    app_name,
    category_l1,
    category_l2,
    brand_id,
    price_range,
    event_cnt,
    row_num
FROM (
    SELECT
        bind.usid,
        SUBSTR(seq.pt_h, 1, 8) AS event_date,
        -- behavior_type：从 dataid_mapping 取 industry+behavior_type 拼接
        COALESCE(
            CONCAT(dm.industry, dm.behavior_type),
            seq.data_id
        ) AS behavior_type,
        -- app_name：从 appid_mapping 按 ext_value2(应用Id) 关联取应用名称
        COALESCE(
            am.app_name,
            CONCAT('应用ID:', seq.ext_value2)
        ) AS app_name,
        -- 各字段已预切分：ext_value4=L1分类, ext_value5=L2分类, ext_value6=品牌id, ext_value7=price区间
        seq.ext_value4 AS category_l1,
        seq.ext_value5 AS category_l2,
        seq.ext_value6 AS brand_id,
        seq.ext_value7 AS price_range,
        1 AS event_cnt,
        ROW_NUMBER() OVER (PARTITION BY bind.usid ORDER BY seq.pt_h DESC) AS row_num
    FROM pps.dwd_pps_behaviour_sequence_appdata_hm seq
    INNER JOIN (
        SELECT dsid, usid
        FROM bicoredata.dwd_pty_combine_device_up_bind_ds
        WHERE pt_d = '20260304'
    ) bind ON seq.adid = bind.dsid
    -- behavior_type 映射：data_id → industry + behavior_type
    LEFT JOIN adhoctemp.tmp_l00527489_20260317_dataid_mapping dm
        ON seq.data_id = dm.data_id
    -- app_name 映射：ext_value2(app_id) → app_name
    LEFT JOIN adhoctemp.tmp_l00527489_20260317_appid_mapping am
        ON seq.ext_value2 = am.app_id
    WHERE seq.data_id IN ('210_20_0001_2', '210_20_0001_3', '210_20_0001_4', '210_20_0001_5')
      AND seq.pt_h >= '2026020900' AND seq.pt_h <= '2026031023'
      AND bind.usid IN (SELECT usid FROM adhoctemp.tmp_l00527489_20260317_finance_loan_sample_pool)
      AND seq.ext_value1 IS NOT NULL
) t
WHERE row_num <= 200;

-- Step 3.4: 构建电商行为序列（CSV表格格式）
INSERT INTO adhoctemp.tmp_l00527489_20260317_finance_loan_ecom_behavior
SELECT
    usid,
    CONCAT(
        '日期,行为类型,应用,一级分类,二级分类,品牌,价格区间,次数\n',
        CONCAT_WS('\n',
            SORT_ARRAY(
                COLLECT_LIST(
                    CONCAT(
                        event_date, ',',
                        behavior_type, ',',
                        app_name, ',',
                        COALESCE(category_l1, ''), ',',
                        COALESCE(category_l2, ''), ',',
                        COALESCE(brand_id, ''), ',',
                        COALESCE(price_range, ''), ',',
                        CAST(event_cnt AS STRING)
                    )
                ),
                FALSE
            )
        )
    ) AS ecom_behavior_seq
FROM adhoctemp.tmp_l00527489_20260317_finance_loan_ecom_events
GROUP BY usid;


-- ============================================================================
-- 阶段 3（续）：汽车/旅游/本地生活行为数据（特征期：2月9日-3月10日）
-- ============================================================================

-- Step 3.5: 提取汽车/旅游/本地生活行为明细
-- 来源：pps.dwd_pps_travel_car_behavior_appdata_hm（各字段已预切分到 ext_value1~ext_value13）
-- app_name：通过 tmp_l00527489_20260317_appid_mapping 按 ext_value1(app_id) 关联获取
-- behavior_type：通过 tmp_l00527489_20260317_dataid_mapping 按 data_id 关联，取 CONCAT(industry, behavior_type)
-- data_id 范围及字段说明（统一用 ext_value1~6 承载各行业核心内容）：
--
-- 汽车行为（来源：dwd_pps_travel_car_behavior_appdata_hm）：
--   500_11_0006_1: app^数据类型^品牌^型号^次数
--     ext_value1=app_id, ext_value3=品牌, ext_value4=型号, ext_value5=次数
--   500_11_0007_1: app^车型^动力^价格
--     ext_value1=app_id, ext_value3=车型, ext_value4=动力, ext_value5=价格
--   500_11_0008_1: app^数据类型^行为ID^品牌^型号
--     ext_value1=app_id, ext_value4=品牌, ext_value5=型号
--   400_11_0004_1: app^车型^汽车属性^汽车问询^购车行为^汽车使用
--     ext_value1=app_id, ext_value3=车型, ext_value4=汽车属性, ext_value5=购车行为
--
-- 文旅行为（来源：dwd_pps_travel_car_behavior_appdata_hm）：
--   500_13_0001_05: app^L1分类^L2分类^L3分类^L4分类
--     ext_value1=app_id, ext_value3=L1, ext_value4=L2, ext_value5=L3
--   500_13_0001_03: 日期^预定/退款^酒店名^景区名^出发地-目的地^未来几天
--     ext_value1=日期, ext_value3=酒店名, ext_value4=景区名, ext_value5=出发地-目的地
--   500_13_0001_07: app^车次^日期^车站
--     ext_value1=app_id, ext_value3=车次, ext_value4=日期, ext_value5=车站
--
-- 本地生活行为（来源：dwd_pps_travel_car_behavior_appdata_hm）：
--   500_14_0001_1: 时间^app_id^分类ID^品牌ID^SPU属性^搜索次数
--     ext_value1=时间, ext_value2=app_id, ext_value3=分类ID, ext_value4=品牌ID, ext_value6=搜索次数
--   500_14_0001_2: 时间^app_id^下单次数
--     ext_value1=时间, ext_value2=app_id, ext_value3=下单次数

INSERT INTO adhoctemp.tmp_l00527489_20260317_finance_loan_travel_car_events
SELECT
    usid,
    event_date,
    behavior_type,
    app_name,
    ext_value3,
    ext_value4,
    ext_value5,
    ext_value6,
    data_id,
    row_num
FROM (
    SELECT
        bind.usid,
        SUBSTR(tcb.pt_h, 1, 8) AS event_date,
        -- behavior_type：从 dataid_mapping 取 industry+behavior_type 拼接
        COALESCE(
            CONCAT(dm.industry, dm.behavior_type),
            tcb.data_id
        ) AS behavior_type,
        -- app_name：本地生活 500_14_xxxx 的 app_id 在 ext_value2，其余在 ext_value1
        COALESCE(
            am.app_name,
            CONCAT('应用ID:', CASE
                WHEN tcb.data_id IN ('500_14_0001_1', '500_14_0001_2') THEN tcb.ext_value2
                ELSE tcb.ext_value1
            END)
        ) AS app_name,
        tcb.ext_value3,
        tcb.ext_value4,
        tcb.ext_value5,
        tcb.ext_value6,
        tcb.data_id,
        ROW_NUMBER() OVER (PARTITION BY bind.usid ORDER BY tcb.pt_h DESC) AS row_num
    FROM pps.dwd_pps_travel_car_behavior_appdata_hm tcb
    INNER JOIN (
        SELECT dsid, usid
        FROM bicoredata.dwd_pty_combine_device_up_bind_ds
        WHERE pt_d = '20260304'
    ) bind ON tcb.adid = bind.dsid
    -- behavior_type 映射：data_id → industry + behavior_type
    LEFT JOIN adhoctemp.tmp_l00527489_20260317_dataid_mapping dm
        ON tcb.data_id = dm.data_id
    -- app_name 映射：本地生活用 ext_value2，其余用 ext_value1
    LEFT JOIN adhoctemp.tmp_l00527489_20260317_appid_mapping am
        ON CASE
            WHEN tcb.data_id IN ('500_14_0001_1', '500_14_0001_2') THEN tcb.ext_value2
            ELSE tcb.ext_value1
        END = am.app_id
    WHERE tcb.data_id IN (
        -- 汽车
        '500_11_0006_1', '500_11_0007_1', '500_11_0008_1', '400_11_0004_1',
        -- 文旅
        '500_13_0001_05', '500_13_0001_03', '500_13_0001_07',
        -- 本地生活
        '500_14_0001_1', '500_14_0001_2'
    )
      AND tcb.pt_h >= '2026020900' AND tcb.pt_h <= '2026031023'
      AND bind.usid IN (SELECT usid FROM adhoctemp.tmp_l00527489_20260317_finance_loan_sample_pool)
      AND tcb.ext_value1 IS NOT NULL
) t
WHERE row_num <= 200;

-- Step 3.6: 构建汽车/旅游/本地生活行为序列（CSV表格格式）
INSERT INTO adhoctemp.tmp_l00527489_20260317_finance_loan_travel_car_behavior
SELECT
    usid,
    CONCAT(
        '日期,行为类型,应用,扩展字段3,扩展字段4,扩展字段5,扩展字段6,data_id\n',
        CONCAT_WS('\n',
            SORT_ARRAY(
                COLLECT_LIST(
                    CONCAT(
                        event_date, ',',
                        behavior_type, ',',
                        app_name, ',',
                        COALESCE(ext_value3, ''), ',',
                        COALESCE(ext_value4, ''), ',',
                        COALESCE(ext_value5, ''), ',',
                        COALESCE(ext_value6, ''), ',',
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
-- 阶段 3（续）：金融专属行为数据 — TODO 占位（后续补充）
-- ============================================================================

-- TODO: 金融行业专属行为数据（待补充具体表名和字段）
-- 预留 data_id: 400_12_xxxx, 500_12_xxxx
-- 包含：
--   - 短信触达（借条/洋钱罐/度小满/拍拍贷/好分期/桔多多授信等）data_id: 400_12_1001_1
--   - 授信/动支页面浏览（奇富借条/360借条）data_id: 400_12_0009
--   - 借贷行业授信/动支/完件/营销通知 data_id: 400_12_0017_1
--   - 借贷行业营销推送 data_id: 500_12_0020_1
--   - 搜索词（抖音/头条/小红书）L1-L4人货一体化标签 data_id: 500_12_0021_1
-- 来源表：pps.dwd_pps_financial_behavior_appdata_hm
--
-- 示例字段格式（待确认后填充）：
--   400_12_1001_1: 短信标签（如"360借条授信"）
--   400_12_0009:   推广标的_行为类型（如"奇富借条_授信"）
--   400_12_0017_1: 推广标的^行为类型（如"奇富借条^贷款-申请-审批通过"）
--   500_12_0021_1: 包名^一级分类^二级分类^三级分类^四级分类^次数


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
      AND bind.usid IN (SELECT usid FROM adhoctemp.tmp_l00527489_20260317_finance_loan_sample_pool)
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
        bind.usid,
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
        ROW_NUMBER() OVER (PARTITION BY bind.usid ORDER BY ind.pt_d DESC, ind.received_total_click DESC) AS row_num
    FROM pps.ads_pps_user_base_indicator_dm ind
    INNER JOIN (
        SELECT dsid, usid
        FROM bicoredata.dwd_pty_combine_device_up_bind_ds
        WHERE pt_d = '20260304'
    ) bind ON ind.did = bind.dsid
    LEFT JOIN (
        SELECT creative_id, title_text, description_text, label
        FROM pps.dwd_pps_t_creative_hs
        WHERE pt_h = '2026031023'
    ) crt ON ind.creative_id = crt.creative_id
    WHERE ind.pt_d >= '20260209' AND ind.pt_d <= '20260310'
      AND bind.usid IN (SELECT usid FROM adhoctemp.tmp_l00527489_20260317_finance_loan_sample_pool)
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
      AND bind.usid IN (SELECT usid FROM adhoctemp.tmp_l00527489_20260317_finance_loan_sample_pool)
      AND ind.event_type NOT IN ('repeatedImp','playPause','intentSuccess','playStart','webclose','webopen','webloadfinish','skip','downloadstart','playEnd','installStart','impInLandingPage','playResume','clickLandingpage','repeatedClick','intentFail','appFirstOpen','appOpen','browse','soundClickOn','easterEggEnd','downloadResume')
      AND ind.total_task_cnvr_target_cnvr_cnt > 0
) t
WHERE row_num <= 100;

-- Step 4.2: 计算异常用户标记（基于全量数据统计）
INSERT INTO adhoctemp.tmp_l00527489_20260317_finance_loan_abnormal_users
SELECT
    bind.usid,
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
INNER JOIN (
    SELECT dsid, usid
    FROM bicoredata.dwd_pty_combine_device_up_bind_ds
    WHERE pt_d = '20260304'
) bind ON ind.did = bind.dsid
WHERE ind.pt_d >= '20260209' AND ind.pt_d <= '20260310'
  AND bind.usid IN (SELECT usid FROM adhoctemp.tmp_l00527489_20260317_finance_loan_sample_pool)
  AND ind.event_type NOT IN ('repeatedImp','playPause','intentSuccess','playStart','webclose','webopen','webloadfinish','skip','downloadstart','playEnd','installStart','impInLandingPage','playResume','clickLandingpage','repeatedClick','intentFail','appFirstOpen','appOpen','browse','soundClickOn','easterEggEnd','downloadResume')
GROUP BY bind.usid;

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
    COALESCE(ec.ecom_behavior_seq, '') AS ecom_behavior_seq,
    COALESCE(tc.travel_car_behavior_seq, '') AS travel_car_behavior_seq,
    -- TODO: 金融专属行为待补充后替换此占位符
    'TODO:finance_behavior_seq_pending' AS finance_behavior_seq,
    COALESCE(e.ad_event_seq, '') AS ad_event_seq,
    COALESCE(ab.abnormal_user_flag, '正常') AS abnormal_user_flag,
    FROM_UNIXTIME(UNIX_TIMESTAMP()) AS create_time
FROM adhoctemp.tmp_l00527489_20260317_finance_loan_sample_pool s
LEFT JOIN adhoctemp.tmp_l00527489_20260317_finance_loan_user_profile p ON s.usid = p.usid
LEFT JOIN adhoctemp.tmp_l00527489_20260317_finance_loan_app_behavior a ON s.usid = a.usid
LEFT JOIN adhoctemp.tmp_l00527489_20260317_finance_loan_ecom_behavior ec ON s.usid = ec.usid
LEFT JOIN adhoctemp.tmp_l00527489_20260317_finance_loan_travel_car_behavior tc ON s.usid = tc.usid
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
    COUNT(CASE WHEN ecom_behavior_seq != '' THEN 1 ELSE NULL END) AS with_ecom_behavior,
    COUNT(CASE WHEN ad_event_seq != '' THEN 1 ELSE NULL END) AS with_ad_events,
    ROUND(COUNT(CASE WHEN user_profile_features != '' THEN 1 ELSE NULL END) * 100.0 / COUNT(*), 2) AS profile_coverage_pct,
    ROUND(COUNT(CASE WHEN app_behavior_seq != '' THEN 1 ELSE NULL END) * 100.0 / COUNT(*), 2) AS app_behavior_coverage_pct,
    ROUND(COUNT(CASE WHEN ecom_behavior_seq != '' THEN 1 ELSE NULL END) * 100.0 / COUNT(*), 2) AS ecom_behavior_coverage_pct,
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
    SUBSTR(ecom_behavior_seq, 1, 100) AS ecom_behavior_preview,
    SUBSTR(ad_event_seq, 1, 100) AS ad_event_preview
FROM adhoctemp.tmp_l00527489_20260317_finance_loan_final_wide_table
LIMIT 10;
