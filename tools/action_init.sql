CREATE EXTERNAL TABLE IF NOT EXISTS pps.dwd_pps_behaviour_sequence_appdata_hm (
  `adid` string COMMENT 'adid',
  `data_ver` string COMMENT '数据版本',
  `name` string COMMENT '数据name',
  `original_time` string COMMENT '数据原始时间',
  `process_time` string COMMENT '数据加工时间',
  `report_time` string COMMENT '数据上报时间', 
  `ext_value1` string COMMENT 'value扩展字段',
  `ext_value2` string COMMENT 'value扩展字段',
  `ext_value3` string COMMENT 'value扩展字段',
  `ext_value4` string COMMENT 'value扩展字段',
  `ext_value5` string COMMENT 'value扩展字段',
  `ext_value6` string COMMENT 'value扩展字段',
  `ext_value7` string COMMENT 'value扩展字段',
  `ext_value8` string COMMENT 'value扩展字段',
  `ext_value9` string COMMENT 'value扩展字段', 
) COMMENT '行为序列数据' PARTITIONED BY (
  `pt_h` string COMMENT '小时分区',
  `data_id` string COMMENT '数据id'
) 

-- 行为表的数据逻辑，同的data_id存放的字段是不一样的，需要参考下述内容  内容切分后的序号对应ext_value的下标

-- 行业	数据类型(短信、搜索词、页面内容、push)	数据采集内容（应用具体页面）	数据加工内容	data_id	数据加工结果示例(O层表value字段)
-- 电商	搜索词	"京东搜索词
-- 淘宝搜索词
-- 盒马搜索词
-- 山姆搜索词
-- 叮咚买菜搜索词
-- 朴朴超市搜索词
-- 京东到家搜索词"	应用、商品分类、品牌、价格、SPU属性	500_20_0006_14	"统计周期：14天
-- 内容：2025-06-13 14:35:14:02_0201_020110_020110001(分类ID):253(品牌ID):6(包名):1(搜索次数)|||..."
-- 				500_20_0006_7	"统计周期：7天
-- 内容：2025-06-13 14:35:14^02^0201^020110^020110001(分类ID)^253(品牌ID)^6(包名)^1(搜索次数)^(HEX编码后的spu属性)"
-- 	页面内容	"京东详情页浏览
-- 淘宝详情页浏览"	应用、商品分类、品牌、价格、SPU属性	500_20_0005_14	"统计周期：14天
-- 内容：2025-06-10 02:15:04:02_0203_020306_020306001(分类ID):0000(品牌ID):6(包名):300400(价格分档):0(是否搜索):1(浏览次数)|||..."
-- 				500_20_0005_7	"统计周期：7天
-- 内容：2025-06-10 02:15:04^02^0203^020306^020306001(分类ID)^0000(品牌ID)^6(包名)^300400(价格分档)^0(是否搜索)^1(浏览次数)^(HEX编码后的spu属性)"
-- 	页面内容	"京东详情页收藏/购买/加购点击行为
-- 淘宝详情页收藏/购买/加购点击行为"	应用、商品分类、品牌、价格、SPU属性	500_20_0008_14	"统计周期：14天
-- 内容：5（应用编码）__02_0209_020901_020901004（分类ID）__200_5002_1000500_5（行为ID）__6(操作次数)|||...|||..."
-- 				500_20_0008_7	"统计周期：14天
-- 内容：2025-06-10 02:15:04^5(应用编码)^02^0209^020901^020901004(分类ID)^200_5002_1000500_5(行为ID)^6(操作次数)^(HEX编码后的spu属性)"
-- 				500_10_0006_14	"统计周期：14天
-- 内容：5(应用编码)^02^0209^020901^020901004(分类ID)^200_5002_1000500_5(行为ID)^6(操作次数)|||..."
-- 	页面内容	"京东直播详情页浏览
-- 淘宝直播详情页浏览"	应用、商品分类、品牌、价格、SPU属性	500_10_0011_7	"统计周期：7天
-- 内容：2025-06-10 02:15:04^02^0207^020718^020718002^02020005492000999(分类ID)^0000(品牌ID)^6(包名)^300400(价格分档)^0(是否搜索)^1(浏览次数)^(HEX编码后的spu属性)"
-- 	页面内容	"京东商品购买事件
-- 淘宝商品购买事件"	应用、商品分类、品牌、价格、SPU属性、购买时间	500_20_0009_02	支付时间^应用编码^分类ID^品牌ID^支付金额分档^HEX编码后的spu属性
-- 	页面内容	京东、淘宝提交订单页	应用、商品分类、品牌、价格、SPU属性	500_10_0013_7	"统计周期：7天
-- 2025-09-25 07:03:52^02^0203^020306^020306007^^02020036219000^9^0010^9^7B226272616E64223A22E5AE89E8B88F222C227072696365223A352E322C226272616E644964223A223032303230303336323139303030227D"
-- 	页面内容	"京东商品购买事件(关联提交订单)
-- 淘宝商品购买事件(关联提交订单)"	应用、商品分类、品牌、价格、SPU属性、购买时间	500_10_0008_2	"统计周期：2天
-- 2025-09-25 16:00:22^9^02^0207^020707^020707001^^02020072346000^0010^7B226272616E64223A22E88892E58FAFE4B990222C227072696365223A352E322C226272616E644964223A223032303230303732333436303030227D"
-- 	PUSH	京东、淘宝PUSH消息（内容理解）	应用、商品分类、品牌、SPU属性	400_10_0001_1	"统计周期：7天
-- 内容：时间(年月日按天分类统计最小时间)^应用id^一级分类ID_二级分类ID_三级分类ID_四级分类ID_五级分类ID^品牌ID^属性hex编码^pushCategory^次数^action(0曝光、1点击、2清除、3清除所有)
-- 内容样例：2025-10-02^9^02_0205_020505_020505011_^^7B226272616E64223A22E998BFE78E9BE5B0BC222C227075736843617465676F7279223A22E59586E59381E5A48DE68EA8222C226272616E644964223A22227D^商品复推^2^1"

CREATE TABLE IF NOT EXISTS adhoctemp.tmp_l00527489_20260317_dataid_mapping (
                                                                               industry STRING COMMENT '行业',
                                                                               data_id STRING COMMENT '数据ID',
                                                                               data_type STRING COMMENT '数据类型',
                                                                               collect_content STRING COMMENT '数据采集内容',
                                                                               process_content STRING COMMENT '数据加工内容',
                                                                               description STRING COMMENT '映射说明',
                                                                               behavior_type STRING COMMENT '行为类型：搜索/浏览/点击/支付/订单/PUSH/短信/行为序列/打开APP'
) COMMENT 'data_id 标准映射字典表'


DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260317_appid_mapping;
CREATE TABLE IF NOT EXISTS adhoctemp.tmp_l00527489_20260317_appid_mapping (
                                                                              app_name STRING COMMENT '应用名称',
                                                                              package_name STRING COMMENT '包名',
                                                                              app_id STRING COMMENT '应用ID'
) COMMENT 'APPID-包名-应用名称标准映射字典表'
    STORED AS ORC
    TBLPROPERTIES ('orc.compress'='SNAPPY');



DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260317_brand_mapping;
CREATE TABLE IF NOT EXISTS adhoctemp.tmp_l00527489_20260317_brand_mapping (
                                                                              brand_name_cn    STRING COMMENT '品牌中文名',
                                                                              brand_name_en    STRING COMMENT '品牌英文名',
                                                                              brand_category   STRING COMMENT '品牌分类',
                                                                              brand_id         STRING COMMENT '品牌编号ID'
) COMMENT '高端品牌-分类-品牌ID标准映射字典表'
    STORED AS ORC
    TBLPROPERTIES ('orc.compress'='SNAPPY');


DROP TABLE IF EXISTS adhoctemp.tmp_l00527489_20260317_pageid_mapping;
CREATE TABLE IF NOT EXISTS adhoctemp.tmp_l00527489_20260317_pageid_mapping
(
    app_name    STRING COMMENT '应用名称',
    page_desc   STRING COMMENT '页面/行为说明',
    page_id     STRING COMMENT '页面ID'
)
    COMMENT '页面pageid-应用-页面说明标准映射表'
    STORED AS ORC
    TBLPROPERTIES ('orc.compress'='SNAPPY');



-- 金融用户特征宽表
CREATE EXTERNAL TABLE IF NOT EXISTS pps.ads_model_feature_finance_microloans_0206_all_latest_1 ( 
  `brand_new_dev` string COMMENT '',
  `career_third_level_type_dev` string COMMENT '',
  `care_offc_acct_up` string COMMENT '',
  `car_price_interest_exist_dev` string COMMENT '',
  `cashpay_cnt_30d` string COMMENT '',
  `cashpay_cnt_60d` string COMMENT '',
  `category_score` string COMMENT '',
  `city_new_dev` string COMMENT '',
  `city_new_grade_dev` string COMMENT '', 
  `color_v2_dev` string COMMENT '',
  `consume_ability_dev` string COMMENT '', 
  `consume_amount_30d` string COMMENT '', 
   
  `consume_frequency_30d` string COMMENT '', 
  `consume_frequency_dev` string COMMENT '',
  
  `cp_new_dev` string COMMENT '', 
  `customer_group_dev` string COMMENT '',
  `dev_first_time_duration_dev` string COMMENT '',
  
   
  `education_dev` string COMMENT '',
   
  `forecast_age_dev` string COMMENT '',
  `frequency_level_auid` string COMMENT '',
  `game_category_pay_180days` string COMMENT '',
  `game_category_pay_30days` string COMMENT '',
  `game_category_pay_90days` string COMMENT '',
  `gender_new_dev` string COMMENT '',
  `general_ecom_pay_cnt_30d_adid` string COMMENT '',
  `high_tag_discrete_num_list` string COMMENT '',
  
  `level_of_community_dev` string COMMENT '',
  `liteapp_pay_30d_top20` string COMMENT '',
  `loancompletion_flag` string COMMENT '',
  
  `low_tag_discrete_num_list` string COMMENT '',
  `marriage_status_dev` string COMMENT '',
  
   
  
  `monetary_level_auid` string COMMENT '',
   
  `non_care_offc_acct_up` string COMMENT '',
  `online_pay_30d_top20` string COMMENT '',
  
  `owner_cars_user_dev` string COMMENT '',
  `owner_house_flag_dev` string COMMENT '',
  `parenting_status_dev` string COMMENT '',
  `pettyloan_eligibility_value_adid` string COMMENT '',
  
  `pps_visit_city_year_dev` string COMMENT '',
  `price_new_dev` string COMMENT '',
  `price_of_community_dev` string COMMENT '',
  `product_new_dev` string COMMENT '',
  `province_new_dev` string COMMENT '',
  `push_online_days_30d_dev` string COMMENT '',
  `recent_level_auid` string COMMENT '',
  
  `series_new_dev` string COMMENT '',
  `socialattr_fact_high_class_dev` string COMMENT '',
  `social_security_card_owner` string COMMENT '',
  `sum_cashpay_amt_30d` string COMMENT '',
  `sum_cashpay_amt_60d` string COMMENT '',
  `sum_couponpay_amt_30d` string COMMENT '',
  `sum_couponpay_amt_60d` string COMMENT '',
  
  `taobao_pay_cnt_30d_adid` string COMMENT '', 
  `trips_one_year_cnt` string COMMENT '',
  `uninstalled_app_category1_30d` string COMMENT '',
  `uninstalled_app_category1_3d` string COMMENT '',
  `uninstalled_app_category1_7d` string COMMENT '',
  `up_realname_verify_dev` string COMMENT '',
  
   
  `use_news_app_lastfornow_hours_30d` string COMMENT '', 
 
  `did` string COMMENT '标签字段',
  `aid` string COMMENT '标签字段',
  `usid` string COMMENT '标签字段',
  `auid` string COMMENT '标签字段'
) COMMENT '111' PARTITIONED BY (`pt_d` string COMMENT '分区字段')


overdue_records_small_loan_list_90d	overdue_records_small_loan_list_90d	近2个月小贷贷款逾期列表
withdraw_frequency_90d	withdraw_frequency_90d	近3个月取现总频度


-- 正样本表， 取3月10-3月20日，有过 event_type= 完件
-- promotion_target：'360借条', '好分期', '桔多多', '洋钱罐借款', '榕树贷款', '度小满金融', '极融借款', '还呗', '小辉付', '拍拍贷借款', '安逸花', '宜享花', '小赢卡贷', '你我贷借款', '众安贷', '融360', '建信消费金融', '度小满', '奇富借条', '中原消费金融'
CREATE TABLE IF NOT EXISTS pps.dwd_pps_finance_all_channel_conversion_event_dm (
  `adid` string COMMENT '广告生成的设备id',
  `event_type` string COMMENT '转化类型：表单提交、完件、授信、动支',
  `event_time` string COMMENT '转化时间字符串，格式为yyyy-MM-dd HH:mm:ss',
  `conversion_value` string COMMENT '广告主一方回传的conversion_extend中的value字段',
  `advertiser_id` string COMMENT '广告主id，对应于其它服务的corp_id',
  `advertiser_name` string COMMENT '广告主名称，对应于其它服务的corp_name',
  `industry_id` string COMMENT '广告主行业id，2101：金融保险；2125: 金融贷超及助贷服务；2102:金融综合线上平台；2121: 金融小额贷款',
  `industry_type` string COMMENT '行业类型，loan: 借贷、insurance:保险',
  `promotion_target` string COMMENT '推广标的，如：360借条、宜享花、还呗、招联金融、拍拍贷等',
  `user_id_type` string COMMENT '用户id类型，user_id_type为20时，用户使用user_id标识，此时user_id为oaid md5值，或电话号码md5值；user_id_type不为20时，用户使用oaid标识，oaid为AES加密后的值',
  `aid` string COMMENT '设备oaid，值为AES加密后的值，user_id_type为20时来源于mapping表的aid，user_id_type不为20时来源于dwd_pps_alt_attribution_cdr_hm表的oaid1',
  `user_id` string COMMENT '设备id标识，user_id_type为20时，用户使用user_id标识，此时user_id为oaid md5值，或电话号码md5值',
  `conversion_params` string COMMENT '转化一方回传时携带的转化附加参数',
  `channel` string COMMENT '数据来源：SMS、ADS、AG、PAGEOPEN、WALLET、API_ATTR(API归因场景，对应数据为other表)、API_ALL（全渠道一方回传）',
  `callback` string COMMENT '广告主一方回传的conversion_extend中的value字段',
  `platform` string COMMENT '来源平台，当前仅在channel为API_ALL且推广标的为360借条时有值，标识是在鲸鸿动能信息流(hwpps)还是华为AG(hwag)曝光后产生的转化',
  `app_pkg` string COMMENT '媒体应用包名，来源于dwd_pps_alt_attribution_cdr_hm表的capp_package_name，广告主不一定回传，值可能为空',
  `promoted_app_pkg_name` string COMMENT '推广应用包名',
  `api_call_source_type` string COMMENT 'API接口调用类型，SRN、API_ORG、MAPI，来源于dwd_pps_alt_attribution_cdr_hm表的source，仅在channel为API_ALL时有值',
  `api_call_channel` string COMMENT 'API调用渠道，来源于dwd_pps_alt_attribution_cdr_hm表的channel，仅在channel为API_ALL时有值',
  `logid` string COMMENT '广告id，来源于other表的logid，仅在channel为API_ATTR时有值',
  `order_id` string COMMENT '计划id，来源于other表的order_id，仅在channel为API_ATTR时有值',
  `task_id` string COMMENT '任务id，来源于other表的task_id，仅在channel为API_ATTR时有值',
  `contend_id` string COMMENT '创意id，来源于other表的contend_id，仅在channel为API_ATTR时有值',
  `normalized_promotion_target` string COMMENT '归一化后的推广标的，默认和promotion_target值一样，如果遇到360借条这种有多个推广标的需要归一的则会在离线任务中进行归一',
  `delay_days` string COMMENT '延迟天数(数据入库日期与事件发生日期间隔天数)'
) COMMENT '金融行业全渠道转化样本表' PARTITIONED BY (`pt_d` string COMMENT '天分区')




金融  CREATE EXTERNAL TABLE IF NOT EXISTS pps.dwd_pps_financial_behavior_appdata_hm (
  `adid` string COMMENT 'adid',
  `data_ver` string COMMENT '数据版本',
  `name` string COMMENT '数据name',
  `original_time` string COMMENT '数据原始时间', 
  `ext_value1` string COMMENT 'value扩展字段',
  `ext_value2` string COMMENT 'value扩展字段',
  `ext_value3` string COMMENT 'value扩展字段',
  `ext_value4` string COMMENT 'value扩展字段',
  `ext_value5` string COMMENT 'value扩展字段',
  `ext_value6` string COMMENT 'value扩展字段',
  `ext_value7` string COMMENT 'value扩展字段',
  `ext_value8` string COMMENT 'value扩展字段',
  `ext_value9` string COMMENT 'value扩展字段',
  `ext_value10` string COMMENT 'value扩展字段',
  `ext_value11` string COMMENT 'value扩展字段',
  `ext_value12` string COMMENT 'value扩展字段',
  `ext_value13` string COMMENT 'value扩展字段', 
) COMMENT '金融行业行为数据' PARTITIONED BY (
  `pt_h` string COMMENT '小时分区',
  `data_id` string COMMENT '数据id'
)

-- 金融	PUSH	大智慧、同花顺、同花顺高级版、赢家财富通、广发证券、中信证券、指南针股票、国泰海通君弘、招商证券、银河证券、国泰君安期货、东证期货、平安金管家、涨乐财富通、泰康泰生活、国信金太阳、东方财富、平安证券	push消息频次	400_12_0025_1	内容样例：100_1002_1200900_389^51
-- 	短信（规则）	借条、洋钱罐、度小满、拍拍贷、好分期、桔多多授信	广告主	400_12_1001_1	"统计周期：上次任务执行时间到本次任务执行时间
-- 内容：短信标签
-- "
-- 		借条动支		400_12_0006	
-- 		蚂蚁保投保		400_12_0002_1	
-- 		蚂蚁保续保		400_12_0007_1	
-- 		元保投保		400_12_0005	
-- 		借条授信金额		400_12_0004	奇富借条__L1
-- 		蚂蚁保体验版到期提醒		400_12_0012	蚂蚁保^门诊险(体验版)
-- 		借贷行业营销		500_12_0020_1	奇富借条^贷款-营销
-- 		借贷行业授信、动支、完件、营销		400_12_0017_1	"奇富借条^贷款-申请-审批通过
-- 奇富借条^贷款-申请-提款成功
-- 奇富借条^贷款-申请-申请贷款
-- 奇富借条^贷款-营销"
-- 		保险行业投保		400_12_0016_1	"蚂蚁保^保险-营销^门诊险
-- 蚂蚁保^保险-投保^门诊险
-- 蚂蚁保^保险-续保保险-续保提醒^门诊险
-- 蚂蚁保^保险-续保失败^门诊险
-- 蚂蚁保^保险-退保^门诊险
-- 蚂蚁保^保险-咨询预约^门诊险
-- 蚂蚁保^保险-理赔^门诊险"
-- 		券商分广告主	广告主	400_12_1001_3	NULL^招商证券^NULL
-- 	搜索词	"抖音搜索词
-- 今日头条搜索词
-- 小红书搜索词
-- 抖音极速版搜索词
-- 今日头条极速版搜索词
-- 快手搜索词
-- 快手极速版搜索词
-- "	L1-L4人货一体化标签	500_12_0021_1	"统计周期：前一天
-- 内容：2025-06-10 10^06^0604^^^1
-- 包名^一级分类^二级分类^三级分类^四级分类^次数
-- "
-- 	页面内容	奇富借条、360借条	广告主、类型	400_12_0009	奇富借条_授信


CREATE EXTERNAL TABLE IF NOT EXISTS pps.dwd_pps_travel_car_behavior_appdata_hm (
  `adid` string COMMENT 'adid',
  `data_ver` string COMMENT '数据版本',
  `name` string COMMENT '数据name',
  `original_time` string COMMENT '数据原始时间', 
  `ext_value1` string COMMENT 'value扩展字段',
  `ext_value2` string COMMENT 'value扩展字段',
  `ext_value3` string COMMENT 'value扩展字段',
  `ext_value4` string COMMENT 'value扩展字段',
  `ext_value5` string COMMENT 'value扩展字段',
  `ext_value6` string COMMENT 'value扩展字段',
  `ext_value7` string COMMENT 'value扩展字段',
  `ext_value8` string COMMENT 'value扩展字段',
  `ext_value9` string COMMENT 'value扩展字段',
  `ext_value10` string COMMENT 'value扩展字段',
  `ext_value11` string COMMENT 'value扩展字段',
  `ext_value12` string COMMENT 'value扩展字段',
  `ext_value13` string COMMENT 'value扩展字段', 
) COMMENT '汽车，文旅，本地生活行业行为数据' PARTITIONED BY (
  `pt_h` string COMMENT '小时分区',
  `data_id` string COMMENT '数据id'
)

-- 汽车	搜索词、页面内容	"抖音搜索词
-- 今日头条搜索词
-- 小红书搜索词
-- 懂车帝搜索词、车辆详情页、车型对比页、车贷计算页
-- 汽车之家搜索词、车辆详情页、车型对比页、直播页面、车贷计算页
-- 易车搜索词、车辆详情页、车型对比页、直播页面、车贷计算页
-- "	搜索词和页面内容识别为汽车品牌、型号	500_11_0006_1	"统计周期：一天
-- 2(包名)^100_5000(数据类型)^AITO(品牌)^问界M5(型号)^5(次数)"
-- 	搜索词、页面内容	"抖音搜索词
-- 今日头条搜索词
-- 小红书搜索词
-- 懂车帝搜索词、车辆详情页、车型对比页、车贷计算页
-- 汽车之家搜索词、车辆详情页、车型对比页、直播页面、车贷计算页
-- 易车搜索词、车辆详情页、车型对比页、直播页面、车贷计算页
-- "	搜索词和页面内容识别为汽车品牌、型号	500_11_0006_2	"统计周期：一天
-- 2(包名)^100_5000(数据类型)^200_5000_1100000_97(页面ID)^AITO(品牌)^问界M5(型号)^5(次数)"
-- 	搜索词	"懂车帝搜索词
-- 汽车之家搜索词
-- 易车搜索词"	搜索词识别为汽车车型（轿车/SUV等）、动力（电车/油车等）、价格	500_11_0007_1	"统计周期：一天
-- 97(包名)^小型SUV(车型)^电车(动力)^20(价格)"
-- 	页面内容	"懂车帝查落地价、联系销售、查找门店、上门试驾、车型对比
-- 汽车之家查落地价、联系销售、车型对比
-- 易车查落地价、联系销售、车型对比"	汽车行为关联车辆详情识别的品牌、型号	500_11_0008_1	"统计周期：一天
-- 97(包名)^100_5002(数据类型)^200_5002_1100200_97(行为ID)^大众(品牌)^速腾(型号)"
-- 	搜索词	"抖音搜索词
-- 今日头条搜索词
-- 小红书搜索词
-- 懂车帝搜索词
-- 汽车之家搜索词
-- 易车搜索词"	汽车搜索词按照规则加工数据	400_11_0004_1	"统计周期：一天
-- 97(包名)^问界(车型)^(汽车属性)^(汽车问询)^(购车行为)^(汽车使用)"
-- 	短信	鸿蒙智行短信	鸿蒙智行短信留资、到店、预约试驾数据	400_11_0005_1	"统计周期：一天
-- 鸿蒙智行(短信签名)^1(留资)^1(到店)^问界M7(预约试驾)^1(试驾报告)^1(试驾评价)"
-- 	页面内容	"鸿蒙智行App试驾、订购行为
-- AITO App试驾、订购行为"	采集试驾、订购行为数据，识别出品牌、型号	400_11_0006_1	"统计周期：一天
-- 521(应用)^100_5002(行为)^200_5002_1100400_521(事件ID)^AITO(品牌)^问界M9(型号)"
-- 	页面内容	"驾考宝典查学车价行为
-- 驾校一点通查学车价行为"	采集查学车价行为数据	400_11_0007_1	"统计周期：一天
-- 247(应用)^100_5002(行为)^200_5002_1100700_247(事件ID)"
-- 	页面内容	"抖音私信页面中聊天商户名称
-- 快手私信页面中聊天商户名称
-- 懂车帝私信页面中聊天商户名称
-- 汽车之家私信页面中聊天商户名称
-- 易车私信页面中聊天商户名称
-- 百度搜索词
-- 百度极速版搜索词
-- 悟空浏览器搜索词"	采集聊天对象名称通过内容理解识别汽车品牌	500_11_0009_1	"统计周期：一天
-- 97(应用)^100_5000(行为)^200_5000_1100000_97(事件ID)^AITO(品牌)^问界M7(型号)^4(次数)"
-- 	页面内容	"懂车帝搜索词
-- 汽车之家搜索词
-- 易车搜索词
-- 抖音搜索词
-- 今日头条搜索词
-- 小红书搜索词
-- 快手搜索词
-- B站搜索词"	搜索词经过内容理解加工为汽车卖点	500_11_0010_1	"统计周期：一天
-- 97(应用)^100_5000(行为)^200_5000_1100000_97(事件ID)^AITO(品牌)^问界M7(型号)^其他(卖点分类)^其他(卖点)^1(次数)"
-- 	短信	短信	将短信内容通过内容理解识别出行为和汽车品牌车型	400_11_0008_1	"统计周期：一天
-- 200_1001_1_1(事件ID)^鸿蒙智行(短信签名)^预约试驾(短信行为)^AITO(品牌)^问界M9(型号)"
-- 	短信	短信	将试乘/试驾短信通过规则提取出品牌	400_11_0009_1	"统计周期：一天
-- 鸿蒙智行（短信签名）"
-- 	页面内容	抖音直播	提取直播间名称加工为汽车品牌	500_11_0011_1	"统计周期：一天
-- 2^200_5101_2300101_2^南京宁宝宝马^2"



-- 文旅	搜索词	"抖音搜索词
-- 今日头条搜索词
-- 小红书搜索词"	L1-L4人货一体化标签	500_13_0001_05	包名^一级分类^二级分类^三级分类^四级分类
-- 	页面内容	携程的酒店民宿机票预支付页面	机票酒店到达的城市国家出行时间	400_13_2001_02	"ext_value1:采集事件eventID(机票200_5001_1300100_60，酒店200_5001_1300101_60，民宿/客栈200_5001_1300102_60)
-- 200_5001^1300100^60^2025-08-26 12:25^中国^上海市^意大利^罗马"
-- 		携程酒店已支付订单页	识别酒店入住时间，酒店名称，价格	500_13_0001_04	"60^200_5001_1300603_60^8月14日^全季酒店(长春国际会展中心店)^¥2008
-- "
-- 	短信	携程，同程，去哪儿，飞猪，美团的短信模板采集	识别日期，支付行为，酒店名称，景区名称，出发地目的地，时间	500_13_0001_03	日期^预定/退款^酒店名称^景区名称^出发地-目的地^未来几天
-- 	短信	12306的高铁预定短信	识别日期 车次 和站点	500_13_0001_07	178^G17^11月25日^车站
-- 	搜索词	"抖音搜索词
-- 今日头条搜索词
-- 小红书搜索词"	L1-L4人货一体化标签	500_13_0001_08 	包名^一级分类^二级分类^三级分类^四级分类
-- 	搜索词词包	综媒垂媒	搜索词映射id和次数	500_13_0001_09	appid^搜索词映射id^搜索次数统计
					
-- 本地生活	PUSH	美团、淘宝闪购PUSH消息（规则）	应用使用次数	500_14_0001_2	"统计周期：7天
-- 内容：时间(年月日按天分类统计最小时间)^应用id^下单次数
-- 内容样例：2025-09-09^12^1"
-- 	搜索词	美团、美团外卖、大众点评、京东秒送搜索词	应用和商品分类	500_14_0001_1	"统计周期：7天
-- 内容：2025-06-13 (年月日按天分类统计最小时间)^12(应用id)^01_0101_010113_010113001(分类ID)^00001(品牌ID)^SPU属性hex编码^1(搜索次数)"
-- 	支付	美团全渠道支付	支付渠道	NA（公共事件）


CREATE EXTERNAL TABLE IF NOT EXISTS pps.dwd_pps_game_behavior_appdata_hm (
  `adid` string COMMENT 'adid',
  `data_ver` string COMMENT '数据版本',
  `name` string COMMENT '数据name',
  `original_time` string COMMENT '数据原始时间', 
  `ext_value1` string COMMENT 'value扩展字段',
  `ext_value2` string COMMENT 'value扩展字段',
  `ext_value3` string COMMENT 'value扩展字段',
  `ext_value4` string COMMENT 'value扩展字段',
  `ext_value5` string COMMENT 'value扩展字段',
  `ext_value6` string COMMENT 'value扩展字段',
  `ext_value7` string COMMENT 'value扩展字段',
  `ext_value8` string COMMENT 'value扩展字段',
  `ext_value9` string COMMENT 'value扩展字段',
  `ext_value10` string COMMENT 'value扩展字段',
  `ext_value11` string COMMENT 'value扩展字段',
  `ext_value12` string COMMENT 'value扩展字段',
  `ext_value13` string COMMENT 'value扩展字段', 
) COMMENT '游戏' PARTITIONED BY (
  `pt_h` string COMMENT '小时分区',
  `data_id` string COMMENT '数据id'
)

-- 游戏	搜索词	"哔哩哔哩搜索词
-- TapTap搜索词
-- 好游快爆搜索词"	游戏名称	500_16_0001_1	375^1460
-- 		"抖音搜索词
-- 小红书搜索词
-- 今日头条搜索词"	游戏名称	500_16_0001_2	375^1460
-- 	页面内容	"哔哩哔哩页面内容
-- TapTap页面内容
-- 好游快爆页面内容
-- 应用宝页面内容"	游戏名称	500_16_0002_1	32^unfollowed^unDownloaded^1460


CREATE EXTERNAL TABLE IF NOT EXISTS pps.dwd_pps_behaviour_sequence_appdata_hm  (
  `adid` string COMMENT 'adid',
  `data_ver` string COMMENT '数据版本',
  `name` string COMMENT '数据name',
  `original_time` string COMMENT '数据原始时间', 
  `ext_value1` string COMMENT 'value扩展字段',
  `ext_value2` string COMMENT 'value扩展字段',
  `ext_value3` string COMMENT 'value扩展字段',
  `ext_value4` string COMMENT 'value扩展字段',
  `ext_value5` string COMMENT 'value扩展字段',
  `ext_value6` string COMMENT 'value扩展字段',
  `ext_value7` string COMMENT 'value扩展字段',
  `ext_value8` string COMMENT 'value扩展字段',
  `ext_value9` string COMMENT 'value扩展字段',
  `ext_value10` string COMMENT 'value扩展字段',
  `ext_value11` string COMMENT 'value扩展字段',
  `ext_value12` string COMMENT 'value扩展字段',
  `ext_value13` string COMMENT 'value扩展字段', 
) COMMENT '行为序列' PARTITIONED BY (
  `pt_h` string COMMENT '小时分区',
  `data_id` string COMMENT '数据id'
)

-- 行为序列	页面内容	京东、淘宝、拼多多、小红书、头条、美团、大众点评等应用搜索词和浏览数据	行为（搜索、浏览）、应用、页面、商品分类、品牌、价格区间	210_20_0001_2	"内容：行为id^应用Id^页面Id^L1~L4分类^品牌id^预留字段^price区间
-- 内容样例：100_5000^9^200_5000_1000000_9^02_0208_020805_020805002^NULL^NULL^0010"
-- 	点击	京东、淘宝商品详情页收藏、加购、购买行为	行为（点击）、应用、页面	210_20_0001_3	"内容：行为id^应用Id^页面Id^L1~L4分类^NULL^预留字段^NULL
-- 内容样例：100_5002^9^200_5002_1000300^NULL^NULL^NULL^NULL"
-- 	支付	微信、支付宝、QQ钱包支付行为	行为（支付）、应用、页面、价格区间	210_20_0001_4	"内容：行为id^应用Id^页面Id^NULL^NULL^预留字段^价格区间
-- 内容样例：100_5001^1^200_5001_2500602_1^NULL^NULL^NULL^1020"
-- 	"appOpen
-- pageOpen"	"京东、淘宝、抖音appOpen
-- 美团预支付、美团外卖预支付、抖音预支付页面"	行为（支付）、应用、页面	210_20_0001_5	"内容：行为id^应用Id^页面Id^NULL^NULL^NULL^NULL
-- 内容样例：100_2002^7^200_2002_2000001_4^NULL^NULL^NULL^NULL"
-- 	搜索词、页面内容	"懂车帝搜索词、车辆详情页、车型对比页、车贷计算页
-- 汽车之家搜索词、车辆详情页、车型对比页、直播页面、车贷计算页
-- 易车搜索词、车辆详情页、车型对比页、直播页面、车贷计算页"	搜索词和页面内容识别为汽车品牌、型号	210_20_0001_6	"根据三车搜索和浏览数据加工汽车行为数据，格式为
-- 100_5000(数据类型)^97(包名)^200_5000_1100000_97(行为ID)^NULL(占位)^AITO(品牌)^问界M7(型号)^NULL(占位)"
-- 	提交订单（规则）	美团、美团外卖、大众点评提交订单	行为（提交订单）、应用、页面、价格区间、订单分类	210_20_0001_7	"内容：行为id^应用Id^页面Id^NULL^NULL^NULL^价格区间^订单分类（1外卖、2团购、3闪购，仅美团应用有订单分类）
-- 内容样例：
-- 100_5001^12^200_5001_1400107_12^NULL^NULL^NULL^3040^1"
-- 	提交订单（内容理解）	美团、美团外卖、大众点评提交订单	行为（提交订单）、应用、页面、品类、价格区间	210_20_0001_8	"内容：行为id^应用Id^页面Id^品类^NULL^NULL^价格区间
-- 内容样例：
-- 100_5001^12^200_5001_1400107_12^01_0101_010104_010104001^NULL^NULL^3040"