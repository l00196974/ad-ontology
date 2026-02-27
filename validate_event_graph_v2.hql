-- =====================================================
-- 汽车行业广告投放事理图谱验证脚本 V2
-- 基于实际表结构
-- 目标:验证问界M7投放的事理图谱有效性
-- 日期:2026-02-27
-- =====================================================

-- =====================================================
-- Step 1: 生成样本表
-- 正样本:20260223问界M7留资用户1000人
-- 负样本:有曝光的随机100000用户
-- =====================================================

-- 1.1 创建样本用户表
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260227_ods_sample_users;
CREATE TABLE adhoctemp.tmp_l00527489_20260227_ods_sample_users (
    did STRING COMMENT '设备ID(did和adid通用)',
    sample_type STRING COMMENT '样本类型:positive=正样本(留资)/negative=负样本(曝光)',
    sample_date STRING COMMENT '采样日期'
)
COMMENT '样本用户表:包含正负样本'
PARTITIONED BY (sample_type STRING);

-- 1.2 插入正样本:问界M7留资用户(20260223的1000人,status='cleaned')
INSERT OVERWRITE TABLE adhoctemp.tmp_l00527489_20260227_ods_sample_users PARTITION(sample_type='positive')
SELECT
    did,
    'positive' as sample_type,
    '20260223' as sample_date
FROM bicoredata.dwd_evt_hicar_leads_postback_tf_dm
WHERE pt_d = '20260223'
  AND DATE(leads_create_time) = '2026-02-23'
  AND status = 'cleaned'
  AND intention_model = '问界M7'
ORDER BY RAND()
LIMIT 1000;

-- 1.3 插入负样本:有曝光的随机100000用户
INSERT OVERWRITE TABLE adhoctemp.tmp_l00527489_20260227_ods_sample_users PARTITION(sample_type='negative')
SELECT
    adid as did,
    'negative' as sample_type,
    '20260223' as sample_date
FROM (
    SELECT DISTINCT adid
    FROM pps.dwd_pps_imp_cdr_all_v1_dm
    WHERE pt_d = '20260223'
      AND adid IS NOT NULL
    ORDER BY RAND()
    LIMIT 100000
) t;

-- =====================================================
-- Step 2: 生成样本画像表
-- 关联画像标签表,将枚举值转换为文本
-- =====================================================

-- 2.1 创建画像标签映射表(配置表)
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260227_dim_profile_label_mapping;
CREATE TABLE adhoctemp.tmp_l00527489_20260227_dim_profile_label_mapping (
    field_name STRING COMMENT '字段名',
    code_value STRING COMMENT '枚举值',
    label_text STRING COMMENT '文本标签',
    description STRING COMMENT '说明'
)
COMMENT '画像标签映射表:枚举值转文本';

-- 2.2 插入映射配置(根据实际画像表的枚举值)
INSERT INTO adhoctemp.tmp_l00527489_20260227_dim_profile_label_mapping VALUES
-- 性别
('gender', '1', '男', '男性'),
('gender', '2', '女', '女性'),
('gender', '0', '未知', '未知'),
-- 年龄
('age', '1', '18-24岁', '青年'),
('age', '2', '25-30岁', '青年'),
('age', '3', '31-35岁', '中年'),
('age', '4', '36-40岁', '中年'),
('age', '5', '41-50岁', '中年'),
('age', '6', '50岁以上', '老年'),
-- 消费能力
('consumption', '1', '低消费', '低消费能力'),
('consumption', '2', '中低消费', '中低消费能力'),
('consumption', '3', '中等消费', '中等消费能力'),
('consumption', '4', '中高消费', '中高消费能力'),
('consumption', '5', '高消费', '高消费能力'),
-- 有房人士
('has_house', '1', '有房', '有房产'),
('has_house', '0', '无房', '无房产'),
-- 汽车已有价格
('car_price', '1', '0-10万', '低价车'),
('car_price', '2', '10-20万', '中低价车'),
('car_price', '3', '20-30万', '中价车'),
('car_price', '4', '30-50万', '中高价车'),
('car_price', '5', '50万以上', '高价车'),
('car_price', '0', '无车', '无车'),
-- 公共交通通勤
('public_commute', '1', '是', '使用公共交通通勤'),
('public_commute', '0', '否', '不使用公共交通通勤'),
-- 自驾通勤
('selfdrive_commute', '1', '是', '自驾通勤'),
('selfdrive_commute', '0', '否', '不自驾通勤');

-- 2.3 创建样本画像表(文本化)
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260227_ods_sample_user_profile;
CREATE TABLE adhoctemp.tmp_l00527489_20260227_ods_sample_user_profile (
    did STRING,
    sample_type STRING,

    -- 文本化画像
    gender_label STRING COMMENT '性别',
    age_label STRING COMMENT '年龄',
    consumption_label STRING COMMENT '消费能力',
    has_house_label STRING COMMENT '是否有房',
    car_price_label STRING COMMENT '汽车已有价格',
    public_commute_label STRING COMMENT '公共交通通勤',
    selfdrive_commute_label STRING COMMENT '自驾通勤'
)
COMMENT '样本用户画像表:文本化标签';

-- 2.4 生成样本画像(JOIN实际画像表)
INSERT OVERWRITE TABLE adhoctemp.tmp_l00527489_20260227_ods_sample_user_profile
SELECT
    s.did,
    s.sample_type,
    gender_map.label_text as gender_label,
    age_map.label_text as age_label,
    consumption_map.label_text as consumption_label,
    house_map.label_text as has_house_label,
    car_price_map.label_text as car_price_label,
    public_map.label_text as public_commute_label,
    selfdrive_map.label_text as selfdrive_commute_label
FROM adhoctemp.tmp_l00527489_20260227_ods_sample_users s
-- 关联自然属性表(性别、年龄)
LEFT JOIN (
    SELECT did, gender_new_dev, forecast_age_dev
    FROM biads.ads_persona_supply_persona_did_default_user_naturalattr_ear_a_dm
    WHERE pt_d = '20260223'
) natural_attr ON s.did = natural_attr.did
-- 关联经济属性表(消费能力、有房、车价)
LEFT JOIN (
    SELECT did, economicattr_fact_owner_house_u, economicattr_fact_consume_ability_u, car_interest_owned_price_u
    FROM biads.ads_persona_supply_persona_did_default_user_economicattr_ear_a_dm
    WHERE pt_d = '20260223'
) economic_attr ON s.did = economic_attr.did
-- 关联出行场景表(通勤方式)
LEFT JOIN (
    SELECT did, trip_fact_public_transport_commute_u, trip_fact_selfdrive_commute_u
    FROM biads.ads_persona_supply_persona_did_default_scenario_trip_tim_a_dm
    WHERE pt_d = '20260223'
) trip_attr ON s.did = trip_attr.did
-- 映射枚举值到文本
LEFT JOIN adhoctemp.tmp_l00527489_20260227_dim_profile_label_mapping gender_map
    ON gender_map.field_name = 'gender' AND gender_map.code_value = natural_attr.gender_new_dev
LEFT JOIN adhoctemp.tmp_l00527489_20260227_dim_profile_label_mapping age_map
    ON age_map.field_name = 'age' AND age_map.code_value = natural_attr.forecast_age_dev
LEFT JOIN adhoctemp.tmp_l00527489_20260227_dim_profile_label_mapping consumption_map
    ON consumption_map.field_name = 'consumption' AND consumption_map.code_value = economic_attr.economicattr_fact_consume_ability_u
LEFT JOIN adhoctemp.tmp_l00527489_20260227_dim_profile_label_mapping house_map
    ON house_map.field_name = 'has_house' AND house_map.code_value = economic_attr.economicattr_fact_owner_house_u
LEFT JOIN adhoctemp.tmp_l00527489_20260227_dim_profile_label_mapping car_price_map
    ON car_price_map.field_name = 'car_price' AND car_price_map.code_value = economic_attr.car_interest_owned_price_u
LEFT JOIN adhoctemp.tmp_l00527489_20260227_dim_profile_label_mapping public_map
    ON public_map.field_name = 'public_commute' AND public_map.code_value = trip_attr.trip_fact_public_transport_commute_u
LEFT JOIN adhoctemp.tmp_l00527489_20260227_dim_profile_label_mapping selfdrive_map
    ON selfdrive_map.field_name = 'selfdrive_commute' AND selfdrive_map.code_value = trip_attr.trip_fact_selfdrive_commute_u;

-- =====================================================
-- Step 3: 生成样本事件序列表
-- 提取样本用户的原始行为序列(APP使用行为)
-- =====================================================

-- 3.1 创建样本事件序列表
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260227_ods_sample_event_sequence;
CREATE TABLE adhoctemp.tmp_l00527489_20260227_ods_sample_event_sequence (
    did STRING COMMENT '设备ID',
    event_type STRING COMMENT '事件类型',
    event_time TIMESTAMP COMMENT '事件时间',
    package_name STRING COMMENT 'APP包名',
    app_name STRING COMMENT 'APP名称',
    total_time BIGINT COMMENT '使用时长(秒)'
)
COMMENT '样本用户原始事件序列表'
PARTITIONED BY (pt_d STRING);

-- 3.2 提取APP使用行为(30天窗口: 20260124-20260223)
INSERT OVERWRITE TABLE adhoctemp.tmp_l00527489_20260227_ods_sample_event_sequence PARTITION(pt_d='20260223')
SELECT
    app.adid as did,
    app.event_type,
    FROM_UNIXTIME(CAST(app.first_timestamp AS BIGINT)/1000) as event_time,
    app.package_name,
    app.app_name,
    CAST(app.total_time AS BIGINT) as total_time
FROM pps.dwd_pps_appdata_appusage_dm app
JOIN adhoctemp.tmp_l00527489_20260227_ods_sample_users s ON app.adid = s.did
WHERE app.pt_d BETWEEN '20260124' AND '20260223'
  AND app.adid IS NOT NULL
ORDER BY app.adid, event_time;

-- =====================================================
-- Step 4: 生成样本事理事件序列表
-- 根据事理图谱规则映射原始行为到事理事件
-- =====================================================

-- 4.1 创建APP分类映射表(配置)
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260227_dim_app_category_mapping;
CREATE TABLE adhoctemp.tmp_l00527489_20260227_dim_app_category_mapping (
    package_name STRING COMMENT 'APP包名',
    app_category STRING COMMENT 'APP分类',
    category_desc STRING COMMENT '分类说明'
)
COMMENT 'APP分类映射表';

-- 4.2 插入APP分类配置(根据实际业务定义)
INSERT INTO adhoctemp.tmp_l00527489_20260227_dim_app_category_mapping VALUES
-- 汽车资讯类
('com.autohome.app', 'auto_info', '汽车之家'),
('com.yiche.app', 'auto_info', '易车'),
('com.dongchedi.app', 'auto_info', '懂车帝'),
('com.pcauto.app', 'auto_info', '太平洋汽车'),
-- 车贷计算器类
('com.carloan.calculator', 'loan_calc', '车贷计算器'),
('com.loan.car', 'loan_calc', '汽车贷款计算器'),
-- 育儿类
('com.babytree.app', 'parenting', '宝宝树'),
('com.qinbaobao.app', 'parenting', '亲宝宝'),
('com.mmbang.app', 'parenting', '妈妈帮');

-- 4.3 创建事理事件定义表(配置)
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260227_dim_event_mapping;
CREATE TABLE adhoctemp.tmp_l00527489_20260227_dim_event_mapping (
    event_id STRING COMMENT '事理事件ID',
    event_name STRING COMMENT '事理事件名称',
    event_source STRING COMMENT '数据来源:app_usage',
    app_category STRING COMMENT 'APP分类',
    threshold INT COMMENT '触发阈值(次数)',
    duration_threshold INT COMMENT '时长阈值(秒)',
    time_window INT COMMENT '时间窗口(天)',
    description STRING COMMENT '说明'
)
COMMENT '事理事件定义表';

-- 4.4 插入事理事件定义
INSERT INTO adhoctemp.tmp_l00527489_20260227_dim_event_mapping VALUES
-- 兴趣事件(基于APP使用)
('E101', '开始关注汽车', 'app_usage', 'auto_info', 1, 0, 30, '首次使用汽车资讯APP'),
('E102', '频繁浏览汽车', 'app_usage', 'auto_info', 5, 0, 30, '30天内使用汽车APP>=5次'),
('E103', '深度浏览汽车', 'app_usage', 'auto_info', 1, 600, 30, '单次使用汽车APP>=10分钟'),
-- APP使用事件
('E301', '安装汽车资讯APP', 'app_usage', 'auto_info', 1, 0, 30, '安装汽车资讯APP'),
('E302', '安装购车APP', 'app_usage', 'auto_info', 1, 0, 30, '安装购车平台APP'),
('E303', '使用车贷计算器', 'app_usage', 'loan_calc', 1, 0, 30, '使用车贷计算器'),
('E306', '安装育儿APP', 'app_usage', 'parenting', 1, 0, 90, '安装育儿APP');

-- 4.5 创建样本事理事件表
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260227_dwd_sample_event_abstract;
CREATE TABLE adhoctemp.tmp_l00527489_20260227_dwd_sample_event_abstract (
    did STRING,
    event_id STRING COMMENT '事理事件ID',
    event_name STRING COMMENT '事理事件名称',
    event_triggered INT COMMENT '是否触发:0否/1是',
    event_first_time TIMESTAMP COMMENT '首次触发时间',
    event_count INT COMMENT '触发次数',
    total_duration BIGINT COMMENT '总时长(秒)'
)
COMMENT '样本用户事理事件表'
PARTITIONED BY (pt_d STRING);

-- 4.6 映射生成事理事件
INSERT OVERWRITE TABLE adhoctemp.tmp_l00527489_20260227_dwd_sample_event_abstract PARTITION(pt_d='20260223')
SELECT
    s.did,
    m.event_id,
    m.event_name,
    CASE
        WHEN COALESCE(t.event_count, 0) >= m.threshold
         AND COALESCE(t.total_duration, 0) >= m.duration_threshold
        THEN 1
        ELSE 0
    END as event_triggered,
    t.event_first_time,
    COALESCE(t.event_count, 0) as event_count,
    COALESCE(t.total_duration, 0) as total_duration
FROM adhoctemp.tmp_l00527489_20260227_ods_sample_users s
CROSS JOIN adhoctemp.tmp_l00527489_20260227_dim_event_mapping m
LEFT JOIN (
    -- 统计每个用户每个事件的触发次数和时长
    SELECT
        e.did,
        m.event_id,
        MIN(e.event_time) as event_first_time,
        COUNT(*) as event_count,
        SUM(e.total_time) as total_duration
    FROM adhoctemp.tmp_l00527489_20260227_ods_sample_event_sequence e
    JOIN adhoctemp.tmp_l00527489_20260227_dim_app_category_mapping app_cat
        ON e.package_name = app_cat.package_name
    JOIN adhoctemp.tmp_l00527489_20260227_dim_event_mapping m
        ON app_cat.app_category = m.app_category
        AND e.pt_d = '20260223'
    GROUP BY e.did, m.event_id
) t ON s.did = t.did AND m.event_id = t.event_id;

-- =====================================================
-- Step 5: 按事理图谱链路计算浓度
-- 计算正负样本中触发事理链路的用户浓度
-- =====================================================

-- 5.1 创建链路定义表
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260227_dim_path_definition;
CREATE TABLE adhoctemp.tmp_l00527489_20260227_dim_path_definition (
    path_id STRING COMMENT '链路ID',
    path_name STRING COMMENT '链路名称',
    event_sequence STRING COMMENT '事件序列(逗号分隔)',
    match_mode STRING COMMENT '匹配模式:all=全部触发/any=任一触发',
    description STRING COMMENT '说明'
)
COMMENT '事理链路定义表';

-- 5.2 插入链路定义(基于APP使用行为的简化链路)
INSERT INTO adhoctemp.tmp_l00527489_20260227_dim_path_definition VALUES
('PATH_001', '汽车兴趣型', 'E102,E303', 'all', '频繁浏览汽车+使用车贷计算器'),
('PATH_002', '育儿购车型', 'E306,E101', 'all', '安装育儿APP+开始关注汽车'),
('PATH_003', '深度关注型', 'E103,E303', 'all', '深度浏览汽车+使用车贷计算器'),
('PATH_004', '简化购车型', 'E102', 'all', '频繁浏览汽车');

-- 5.3 创建链路统计结果表
DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260227_ads_path_concentration_result;
CREATE TABLE adhoctemp.tmp_l00527489_20260227_ads_path_concentration_result (
    path_id STRING COMMENT '链路ID',
    path_name STRING COMMENT '链路名称',
    event_sequence STRING COMMENT '事件序列',

    -- 正样本统计
    positive_total INT COMMENT '正样本总数',
    positive_hit INT COMMENT '正样本命中数',
    positive_concentration FLOAT COMMENT '正样本浓度(%)',

    -- 负样本统计
    negative_total INT COMMENT '负样本总数',
    negative_hit INT COMMENT '负样本命中数',
    negative_concentration FLOAT COMMENT '负样本浓度(%)',

    -- 浓度对比
    concentration_lift FLOAT COMMENT '浓度提升比=正浓度/负浓度',
    is_significant STRING COMMENT '是否显著:优质(>2.0)/有效(>1.5)/待优化(>1.2)/无效(<1.2)'
)
COMMENT '链路浓度统计结果表';

-- 5.4 计算所有链路的浓度
INSERT OVERWRITE TABLE adhoctemp.tmp_l00527489_20260227_ads_path_concentration_result
SELECT
    pd.path_id,
    pd.path_name,
    pd.event_sequence,

    -- 正样本统计
    ps.total as positive_total,
    ps.hit as positive_hit,
    ROUND(ps.hit * 100.0 / NULLIF(ps.total, 0), 2) as positive_concentration,

    -- 负样本统计
    ns.total as negative_total,
    ns.hit as negative_hit,
    ROUND(ns.hit * 100.0 / NULLIF(ns.total, 0), 2) as negative_concentration,

    -- 浓度提升比
    ROUND((ps.hit * 1.0 / NULLIF(ps.total, 0)) / NULLIF((ns.hit * 1.0 / NULLIF(ns.total, 0)), 0), 2) as concentration_lift,

    -- 显著性判断
    CASE
        WHEN (ps.hit * 1.0 / NULLIF(ps.total, 0)) / NULLIF((ns.hit * 1.0 / NULLIF(ns.total, 0)), 0) >= 2.0 THEN '优质'
        WHEN (ps.hit * 1.0 / NULLIF(ps.total, 0)) / NULLIF((ns.hit * 1.0 / NULLIF(ns.total, 0)), 0) >= 1.5 THEN '有效'
        WHEN (ps.hit * 1.0 / NULLIF(ps.total, 0)) / NULLIF((ns.hit * 1.0 / NULLIF(ns.total, 0)), 0) >= 1.2 THEN '待优化'
        ELSE '无效'
    END as is_significant
FROM adhoctemp.tmp_l00527489_20260227_dim_path_definition pd
LEFT JOIN (
    -- 正样本统计
    SELECT
        pd.path_id,
        COUNT(DISTINCT s.did) as total,
        COUNT(DISTINCT CASE
            WHEN hit_event_cnt = required_event_cnt THEN s.did
        END) as hit
    FROM adhoctemp.tmp_l00527489_20260227_dim_path_definition pd
    CROSS JOIN adhoctemp.tmp_l00527489_20260227_ods_sample_users s
    LEFT JOIN (
        -- 计算每个用户触发了链路中的多少个事件
        SELECT
            e.did,
            pd.path_id,
            SIZE(SPLIT(pd.event_sequence, ',')) as required_event_cnt,
            COUNT(DISTINCT e.event_id) as hit_event_cnt
        FROM adhoctemp.tmp_l00527489_20260227_dwd_sample_event_abstract e
        JOIN adhoctemp.tmp_l00527489_20260227_dim_path_definition pd
            ON FIND_IN_SET(e.event_id, pd.event_sequence) > 0
            AND e.event_triggered = 1
            AND e.pt_d = '20260223'
        GROUP BY e.did, pd.path_id, pd.event_sequence
    ) hit_stats ON s.did = hit_stats.did AND pd.path_id = hit_stats.path_id
    WHERE s.sample_type = 'positive'
    GROUP BY pd.path_id
) ps ON pd.path_id = ps.path_id
LEFT JOIN (
    -- 负样本统计
    SELECT
        pd.path_id,
        COUNT(DISTINCT s.did) as total,
        COUNT(DISTINCT CASE
            WHEN hit_event_cnt = required_event_cnt THEN s.did
        END) as hit
    FROM adhoctemp.tmp_l00527489_20260227_dim_path_definition pd
    CROSS JOIN adhoctemp.tmp_l00527489_20260227_ods_sample_users s
    LEFT JOIN (
        -- 计算每个用户触发了链路中的多少个事件
        SELECT
            e.did,
            pd.path_id,
            SIZE(SPLIT(pd.event_sequence, ',')) as required_event_cnt,
            COUNT(DISTINCT e.event_id) as hit_event_cnt
        FROM adhoctemp.tmp_l00527489_20260227_dwd_sample_event_abstract e
        JOIN adhoctemp.tmp_l00527489_20260227_dim_path_definition pd
            ON FIND_IN_SET(e.event_id, pd.event_sequence) > 0
            AND e.event_triggered = 1
            AND e.pt_d = '20260223'
        GROUP BY e.did, pd.path_id, pd.event_sequence
    ) hit_stats ON s.did = hit_stats.did AND pd.path_id = hit_stats.path_id
    WHERE s.sample_type = 'negative'
    GROUP BY pd.path_id
) ns ON pd.path_id = ns.path_id;

-- =====================================================
-- 查询验证结果
-- =====================================================

-- 查看链路浓度统计结果
SELECT
    path_id,
    path_name,
    event_sequence,
    positive_total,
    positive_hit,
    positive_concentration,
    negative_total,
    negative_hit,
    negative_concentration,
    concentration_lift,
    is_significant
FROM adhoctemp.tmp_l00527489_20260227_ads_path_concentration_result
ORDER BY concentration_lift DESC;

-- 查看样本画像分布对比
SELECT
    sample_type,
    age_label,
    consumption_label,
    has_house_label,
    car_price_label,
    COUNT(*) as user_count
FROM adhoctemp.tmp_l00527489_20260227_ods_sample_user_profile
GROUP BY sample_type, age_label, consumption_label, has_house_label, car_price_label
ORDER BY sample_type, user_count DESC
LIMIT 20;

-- 查看事理事件触发率对比
SELECT
    e.event_id,
    e.event_name,
    s.sample_type,
    COUNT(DISTINCT e.did) as total_users,
    SUM(e.event_triggered) as triggered_users,
    ROUND(SUM(e.event_triggered) * 100.0 / COUNT(DISTINCT e.did), 2) as trigger_rate
FROM adhoctemp.tmp_l00527489_20260227_dwd_sample_event_abstract e
JOIN adhoctemp.tmp_l00527489_20260227_ods_sample_users s ON e.did = s.did
WHERE e.pt_d = '20260223'
GROUP BY e.event_id, e.event_name, s.sample_type
ORDER BY e.event_id, s.sample_type;
