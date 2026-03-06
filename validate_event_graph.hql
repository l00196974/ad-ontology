-- =====================================================
-- 汽车行业广告投放事理图谱验证脚本
-- 目标:验证问界M7投放的事理图谱有效性
-- 日期:2026-02-27
-- =====================================================

-- =====================================================
-- Step 1: 生成样本表
-- 正样本:20260223问界M7留资用户1000人
-- 负样本:有曝光的随机100000用户
-- =====================================================

-- 1.1 创建样本用户表
DROP TABLE IF EXISTS ods_sample_users;
CREATE TABLE ods_sample_users (
    user_id STRING COMMENT '用户ID',
    sample_type STRING COMMENT '样本类型:positive=正样本(留资)/negative=负样本(曝光)',
    sample_date STRING COMMENT '采样日期',

    -- 基础画像(原始枚举值)
    age_code INT COMMENT '年龄编码',
    gender_code INT COMMENT '性别编码',
    consumption_code INT COMMENT '消费能力编码',
    marital_status_code INT COMMENT '婚姻状况编码',
    has_child_code INT COMMENT '是否有小孩编码',
    has_car_code INT COMMENT '是否有车编码',
    car_value_code INT COMMENT '现有车辆价值编码',
    education_code INT COMMENT '学历编码',
    has_house_code INT COMMENT '是否有房编码',
    city_level_code INT COMMENT '城市等级编码',
    occupation_code INT COMMENT '职业编码'
)
COMMENT '样本用户表:包含正负样本'
PARTITIONED BY (sample_type STRING);

-- 1.2 插入正样本:问界M7留资用户(20260223的1000人)
INSERT OVERWRITE TABLE ods_sample_users PARTITION(sample_type='positive')
SELECT
    cl.user_id,
    'positive' as sample_type,
    '20260223' as sample_date,
    up.age as age_code,
    up.gender as gender_code,
    up.consumption as consumption_code,
    up.marital_status as marital_status_code,
    up.has_child as has_child_code,
    up.has_car as has_car_code,
    up.car_value as car_value_code,
    up.education as education_code,
    up.has_house as has_house_code,
    up.city_level as city_level_code,
    up.occupation as occupation_code
FROM car_leads cl
JOIN user_profile up ON cl.user_id = up.user_id
WHERE cl.lead_date = '20260223'
  AND cl.car_model = '问界M7'
LIMIT 1000;

-- 1.3 插入负样本:有曝光的随机100000用户
INSERT OVERWRITE TABLE ods_sample_users PARTITION(sample_type='negative')
SELECT
    ae.user_id,
    'negative' as sample_type,
    '20260223' as sample_date,
    up.age as age_code,
    up.gender as gender_code,
    up.consumption as consumption_code,
    up.marital_status as marital_status_code,
    up.has_child as has_child_code,
    up.has_car as has_car_code,
    up.car_value as car_value_code,
    up.education as education_code,
    up.has_house as has_house_code,
    up.city_level as city_level_code,
    up.occupation as occupation_code
FROM (
    SELECT DISTINCT user_id
    FROM ad_exposure_events
    WHERE dt = '20260223'
      AND task_id IN (SELECT task_id FROM ad_tasks WHERE car_model = '问界M7')
    ORDER BY RAND()
    LIMIT 100000
) ae
JOIN user_profile up ON ae.user_id = up.user_id;

-- =====================================================
-- Step 2: 生成样本画像表(枚举值转文本)
-- =====================================================

-- 2.1 创建画像标签映射表(配置表)
DROP TABLE IF EXISTS dim_profile_label_mapping;
CREATE TABLE dim_profile_label_mapping (
    field_name STRING COMMENT '字段名',
    code_value INT COMMENT '枚举值',
    label_text STRING COMMENT '文本标签',
    description STRING COMMENT '说明'
)
COMMENT '画像标签映射表:枚举值转文本';

-- 2.2 插入映射配置
INSERT INTO dim_profile_label_mapping VALUES
-- 年龄
('age', 1, '18-24岁', '青年'),
('age', 2, '25-30岁', '青年'),
('age', 3, '31-35岁', '中年'),
('age', 4, '36-40岁', '中年'),
('age', 5, '41-50岁', '中年'),
('age', 6, '50岁以上', '老年'),
-- 性别
('gender', 1, '男', '男性'),
('gender', 2, '女', '女性'),
('gender', 0, '未知', '未知'),
-- 消费能力
('consumption', 1, '低消费', '低消费能力'),
('consumption', 2, '中低消费', '中低消费能力'),
('consumption', 3, '中等消费', '中等消费能力'),
('consumption', 4, '中高消费', '中高消费能力'),
('consumption', 5, '高消费', '高消费能力'),
-- 婚姻状况
('marital_status', 1, '未婚', '未婚'),
('marital_status', 2, '已婚', '已婚'),
('marital_status', 3, '离异', '离异'),
('marital_status', 4, '丧偶', '丧偶'),
-- 是否有小孩
('has_child', 0, '否', '无小孩'),
('has_child', 1, '是', '有小孩'),
('has_child', 2, '怀孕中', '怀孕中'),
-- 是否有车
('has_car', 0, '否', '无车'),
('has_car', 1, '是', '有车'),
-- 车辆价值
('car_value', 0, '无车', '无车'),
('car_value', 1, '0-10万', '低价车'),
('car_value', 2, '10-20万', '中低价车'),
('car_value', 3, '20-30万', '中价车'),
('car_value', 4, '30-50万', '中高价车'),
('car_value', 5, '50万以上', '高价车'),
-- 学历
('education', 1, '高中及以下', '高中'),
('education', 2, '大专', '大专'),
('education', 3, '本科', '本科'),
('education', 4, '硕士', '硕士'),
('education', 5, '博士', '博士'),
-- 是否有房
('has_house', 0, '否', '无房'),
('has_house', 1, '是', '有房'),
-- 城市等级
('city_level', 1, '一线城市', '一线'),
('city_level', 2, '二线城市', '二线'),
('city_level', 3, '三线城市', '三线'),
('city_level', 4, '四线及以下', '四线'),
-- 职业
('occupation', 1, '企业管理者', '管理层'),
('occupation', 2, '专业技术人员', '技术'),
('occupation', 3, '办公室职员', '职员'),
('occupation', 4, '个体经营者', '个体'),
('occupation', 5, '自由职业者', '自由'),
('occupation', 6, '学生', '学生'),
('occupation', 7, '其他', '其他');

-- 2.3 创建样本画像表(文本化)
DROP TABLE IF EXISTS ods_sample_user_profile;
CREATE TABLE ods_sample_user_profile (
    user_id STRING,
    sample_type STRING,
    
    -- 文本化画像
    age_label STRING COMMENT '年龄',
    gender_label STRING COMMENT '性别',
    consumption_label STRING COMMENT '消费能力',
    marital_status_label STRING COMMENT '婚姻状况',
    has_child_label STRING COMMENT '是否有小孩',
    has_car_label STRING COMMENT '是否有车',
    car_value_label STRING COMMENT '车辆价值',
    education_label STRING COMMENT '学历',
    has_house_label STRING COMMENT '是否有房',
    city_level_label STRING COMMENT '城市等级',
    occupation_label STRING COMMENT '职业'
)
COMMENT '样本用户画像表:文本化标签';

-- 2.4 生成样本画像(JOIN映射表转换)
INSERT OVERWRITE TABLE ods_sample_user_profile
SELECT
    s.user_id,
    s.sample_type,
    age_map.label_text as age_label,
    gender_map.label_text as gender_label,
    consumption_map.label_text as consumption_label,
    marital_map.label_text as marital_status_label,
    child_map.label_text as has_child_label,
    car_map.label_text as has_car_label,
    car_value_map.label_text as car_value_label,
    edu_map.label_text as education_label,
    house_map.label_text as has_house_label,
    city_map.label_text as city_level_label,
    occ_map.label_text as occupation_label
FROM ods_sample_users s
LEFT JOIN dim_profile_label_mapping age_map
    ON age_map.field_name = 'age' AND age_map.code_value = s.age_code
LEFT JOIN dim_profile_label_mapping gender_map
    ON gender_map.field_name = 'gender' AND gender_map.code_value = s.gender_code
LEFT JOIN dim_profile_label_mapping consumption_map
    ON consumption_map.field_name = 'consumption' AND consumption_map.code_value = s.consumption_code
LEFT JOIN dim_profile_label_mapping marital_map
    ON marital_map.field_name = 'marital_status' AND marital_map.code_value = s.marital_status_code
LEFT JOIN dim_profile_label_mapping child_map
    ON child_map.field_name = 'has_child' AND child_map.code_value = s.has_child_code
LEFT JOIN dim_profile_label_mapping car_map
    ON car_map.field_name = 'has_car' AND car_map.code_value = s.has_car_code
LEFT JOIN dim_profile_label_mapping car_value_map
    ON car_value_map.field_name = 'car_value' AND car_value_map.code_value = s.car_value_code
LEFT JOIN dim_profile_label_mapping edu_map
    ON edu_map.field_name = 'education' AND edu_map.code_value = s.education_code
LEFT JOIN dim_profile_label_mapping house_map
    ON house_map.field_name = 'has_house' AND house_map.code_value = s.has_house_code
LEFT JOIN dim_profile_label_mapping city_map
    ON city_map.field_name = 'city_level' AND city_map.code_value = s.city_level_code
LEFT JOIN dim_profile_label_mapping occ_map
    ON occ_map.field_name = 'occupation' AND occ_map.code_value = s.occupation_code;

-- =====================================================
-- Step 3: 生成样本事件序列表
-- 提取样本用户的原始行为序列(APP/浏览/搜索)
-- =====================================================

-- 3.1 创建样本事件序列表
DROP TABLE IF EXISTS ods_sample_event_sequence;
CREATE TABLE ods_sample_event_sequence (
    user_id STRING,
    event_type STRING COMMENT '事件类型:app_usage/browse/search',
    event_time TIMESTAMP COMMENT '事件时间',
    event_detail STRING COMMENT '事件详情JSON'
)
COMMENT '样本用户原始事件序列表'
PARTITIONED BY (dt STRING);

-- 3.2 提取APP使用行为
INSERT INTO TABLE ods_sample_event_sequence PARTITION(dt='20260223')
SELECT
    ae.user_id,
    'app_usage' as event_type,
    ae.start_time as event_time,
    CONCAT_WS('|',
        CONCAT('app_name:', ae.app_name),
        CONCAT('app_category:', ae.app_category),
        CONCAT('duration_sec:', CAST(ae.duration_sec AS STRING))
    ) as event_detail
FROM app_usage_events ae
JOIN ods_sample_users s ON ae.user_id = s.user_id
WHERE ae.dt BETWEEN '20260124' AND '20260223'  -- 30天窗口
ORDER BY ae.user_id, ae.start_time;

-- 3.3 提取浏览行为
INSERT INTO TABLE ods_sample_event_sequence PARTITION(dt='20260223')
SELECT
    be.user_id,
    'browse' as event_type,
    be.browse_time as event_time,
    CONCAT_WS('|',
        CONCAT('content_type:', be.content_type),
        CONCAT('content_tags:', COALESCE(be.content_tags, '')),
        CONCAT('duration_sec:', CAST(be.duration_sec AS STRING)),
        CONCAT('content_category:', COALESCE(be.content_category, ''))
    ) as event_detail
FROM browse_events be
JOIN ods_sample_users s ON be.user_id = s.user_id
WHERE be.dt BETWEEN '20260124' AND '20260223'  -- 30天窗口
ORDER BY be.user_id, be.browse_time;

-- 3.4 提取搜索行为
INSERT INTO TABLE ods_sample_event_sequence PARTITION(dt='20260223')
SELECT
    se.user_id,
    'search' as event_type,
    se.search_time as event_time,
    CONCAT_WS('|',
        CONCAT('keyword:', se.keyword),
        CONCAT('keyword_type:', COALESCE(se.keyword_type, '')),
        CONCAT('keyword_category:', COALESCE(se.keyword_category, ''))
    ) as event_detail
FROM search_events se
JOIN ods_sample_users s ON se.user_id = s.user_id
WHERE se.dt BETWEEN '20260124' AND '20260223'  -- 30天窗口
ORDER BY se.user_id, se.search_time;

-- =====================================================
-- Step 4: 生成样本事理事件序列表
-- 根据事理图谱规则映射原始行为到事理事件
-- =====================================================

-- 4.1 创建事理事件定义表(配置)
DROP TABLE IF EXISTS dim_event_mapping;
CREATE TABLE dim_event_mapping (
    event_id STRING COMMENT '事理事件ID',
    event_name STRING COMMENT '事理事件名称',
    event_source STRING COMMENT '数据来源:app_usage/browse/search',
    match_field STRING COMMENT '匹配字段',
    match_value STRING COMMENT '匹配值',
    threshold INT COMMENT '触发阈值',
    time_window INT COMMENT '时间窗口(天)',
    description STRING COMMENT '说明'
)
COMMENT '事理事件定义表';

-- 4.2 插入事理事件定义
INSERT INTO dim_event_mapping VALUES
-- 兴趣事件
('E101', '开始关注汽车', 'browse', 'content_category', 'auto', 1, 30, '首次浏览汽车内容'),
('E102', '频繁浏览汽车', 'browse', 'content_category', 'auto', 5, 30, '30天内汽车浏览>=5次'),
('E103', '深度浏览汽车', 'browse', 'duration_sec', '600', 1, 30, '单次浏览>=10分钟'),
-- 搜索事件
('E201', '搜索品牌', 'search', 'keyword_type', 'brand', 1, 7, '搜索汽车品牌'),
('E202', '搜索价格', 'search', 'keyword_type', 'price', 1, 7, '搜索价格关键词'),
('E203', '搜索参数', 'search', 'keyword_type', 'param', 1, 7, '搜索参数关键词'),
('E204', '搜索对比', 'search', 'keyword_type', 'compare', 1, 7, '搜索对比关键词'),
('E206', '搜索贷款', 'search', 'keyword_type', 'loan', 1, 7, '搜索贷款关键词'),
('E207', '搜索竞品', 'search', 'keyword_type', 'competitor', 1, 7, '搜索竞品关键词'),
-- APP使用事件
('E301', '安装汽车资讯APP', 'app_usage', 'app_category', 'auto_info', 1, 30, '安装汽车资讯APP'),
('E302', '安装购车APP', 'app_usage', 'app_name', '汽车之家|易车|懂车帝', 1, 30, '安装购车平台APP'),
('E303', '使用车贷计算器', 'app_usage', 'app_category', 'loan_calc', 1, 30, '使用车贷计算器'),
('E306', '安装育儿APP', 'app_usage', 'app_category', 'parenting', 1, 90, '安装育儿APP');

-- 4.3 创建样本事理事件表
DROP TABLE IF EXISTS dwd_sample_event_abstract;
CREATE TABLE dwd_sample_event_abstract (
    user_id STRING,
    event_id STRING COMMENT '事理事件ID',
    event_name STRING COMMENT '事理事件名称',
    event_triggered INT COMMENT '是否触发:0否/1是',
    event_first_time TIMESTAMP COMMENT '首次触发时间',
    event_count INT COMMENT '触发次数'
)
COMMENT '样本用户事理事件表'
PARTITIONED BY (dt STRING);

-- 4.4 映射生成事理事件(通用逻辑)
INSERT OVERWRITE TABLE dwd_sample_event_abstract PARTITION(dt='20260223')
SELECT
    s.user_id,
    m.event_id,
    m.event_name,
    CASE WHEN COALESCE(t.event_count, 0) >= m.threshold THEN 1 ELSE 0 END as event_triggered,
    t.event_first_time,
    COALESCE(t.event_count, 0) as event_count
FROM ods_sample_users s
CROSS JOIN dim_event_mapping m
LEFT JOIN (
    -- 统计每个用户每个事件的触发次数
    SELECT
        e.user_id,
        m.event_id,
        MIN(e.event_time) as event_first_time,
        COUNT(*) as event_count
    FROM ods_sample_event_sequence e
    JOIN dim_event_mapping m
        ON e.event_type = m.event_source
        AND e.dt = '20260223'
        AND (
            -- 匹配规则:根据match_field和match_value进行匹配
            (m.match_field = 'content_category' AND e.event_detail LIKE CONCAT('%content_category:', m.match_value, '%'))
            OR (m.match_field = 'keyword_type' AND e.event_detail LIKE CONCAT('%keyword_type:', m.match_value, '%'))
            OR (m.match_field = 'app_category' AND e.event_detail LIKE CONCAT('%app_category:', m.match_value, '%'))
            OR (m.match_field = 'app_name' AND (
                e.event_detail LIKE '%app_name:汽车之家%'
                OR e.event_detail LIKE '%app_name:易车%'
                OR e.event_detail LIKE '%app_name:懂车帝%'
            ))
            OR (m.match_field = 'duration_sec' AND CAST(REGEXP_EXTRACT(e.event_detail, 'duration_sec:([0-9]+)', 1) AS INT) >= CAST(m.match_value AS INT))
        )
    GROUP BY e.user_id, m.event_id
) t ON s.user_id = t.user_id AND m.event_id = t.event_id;

-- =====================================================
-- Step 5: 按事理图谱链路计算浓度
-- 计算正负样本中触发事理链路的用户浓度
-- =====================================================

-- 5.1 创建链路定义表
DROP TABLE IF EXISTS dim_path_definition;
CREATE TABLE dim_path_definition (
    path_id STRING COMMENT '链路ID',
    path_name STRING COMMENT '链路名称',
    event_sequence STRING COMMENT '事件序列(逗号分隔)',
    match_mode STRING COMMENT '匹配模式:all=全部触发/any=任一触发',
    description STRING COMMENT '说明'
)
COMMENT '事理链路定义表';

-- 5.2 插入链路定义(基于事理图谱文档的5条典型链路)
INSERT INTO dim_path_definition VALUES
('PATH_001', '家庭扩展型', 'E102,E206,E303', 'all', '频繁浏览+搜索贷款+使用车贷计算器'),
('PATH_002', '通勤不便型', 'E101,E201,E202,E203', 'all', '开始关注+搜索品牌+搜索价格+搜索参数'),
('PATH_003', '竞品转化型', 'E102,E207,E204', 'all', '频繁浏览+搜索竞品+搜索对比'),
('PATH_004', '育儿购车型', 'E306,E101,E202', 'all', '安装育儿APP+开始关注汽车+搜索价格'),
('PATH_005', '简化购车型', 'E102,E202', 'all', '频繁浏览+搜索价格');

-- 5.3 创建链路统计结果表
DROP TABLE IF EXISTS ads_path_concentration_result;
CREATE TABLE ads_path_concentration_result (
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

-- 5.4 计算所有链路的浓度(通用SQL)
INSERT OVERWRITE TABLE ads_path_concentration_result
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
FROM dim_path_definition pd
LEFT JOIN (
    -- 正样本统计
    SELECT
        pd.path_id,
        COUNT(DISTINCT s.user_id) as total,
        COUNT(DISTINCT CASE
            WHEN hit_event_cnt = required_event_cnt THEN s.user_id
        END) as hit
    FROM dim_path_definition pd
    CROSS JOIN ods_sample_users s
    LEFT JOIN (
        -- 计算每个用户触发了链路中的多少个事件
        SELECT
            e.user_id,
            pd.path_id,
            SIZE(SPLIT(pd.event_sequence, ',')) as required_event_cnt,
            COUNT(DISTINCT e.event_id) as hit_event_cnt
        FROM dwd_sample_event_abstract e
        JOIN dim_path_definition pd
            ON FIND_IN_SET(e.event_id, pd.event_sequence) > 0
            AND e.event_triggered = 1
            AND e.dt = '20260223'
        GROUP BY e.user_id, pd.path_id, pd.event_sequence
    ) hit_stats ON s.user_id = hit_stats.user_id AND pd.path_id = hit_stats.path_id
    WHERE s.sample_type = 'positive'
    GROUP BY pd.path_id
) ps ON pd.path_id = ps.path_id
LEFT JOIN (
    -- 负样本统计
    SELECT
        pd.path_id,
        COUNT(DISTINCT s.user_id) as total,
        COUNT(DISTINCT CASE
            WHEN hit_event_cnt = required_event_cnt THEN s.user_id
        END) as hit
    FROM dim_path_definition pd
    CROSS JOIN ods_sample_users s
    LEFT JOIN (
        -- 计算每个用户触发了链路中的多少个事件
        SELECT
            e.user_id,
            pd.path_id,
            SIZE(SPLIT(pd.event_sequence, ',')) as required_event_cnt,
            COUNT(DISTINCT e.event_id) as hit_event_cnt
        FROM dwd_sample_event_abstract e
        JOIN dim_path_definition pd
            ON FIND_IN_SET(e.event_id, pd.event_sequence) > 0
            AND e.event_triggered = 1
            AND e.dt = '20260223'
        GROUP BY e.user_id, pd.path_id, pd.event_sequence
    ) hit_stats ON s.user_id = hit_stats.user_id AND pd.path_id = hit_stats.path_id
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
FROM ads_path_concentration_result
ORDER BY concentration_lift DESC;

-- 查看样本画像分布对比
SELECT
    sample_type,
    age_label,
    consumption_label,
    has_child_label,
    has_car_label,
    COUNT(*) as user_count
FROM ods_sample_user_profile
GROUP BY sample_type, age_label, consumption_label, has_child_label, has_car_label
ORDER BY sample_type, user_count DESC
LIMIT 20;

-- 查看事理事件触发率对比
SELECT
    e.event_id,
    e.event_name,
    s.sample_type,
    COUNT(DISTINCT e.user_id) as total_users,
    SUM(e.event_triggered) as triggered_users,
    ROUND(SUM(e.event_triggered) * 100.0 / COUNT(DISTINCT e.user_id), 2) as trigger_rate
FROM dwd_sample_event_abstract e
JOIN ods_sample_users s ON e.user_id = s.user_id
WHERE e.dt = '20260223'
GROUP BY e.event_id, e.event_name, s.sample_type
ORDER BY e.event_id, s.sample_type;

