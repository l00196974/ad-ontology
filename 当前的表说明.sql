-- 这个表是线索表，属于正样本数据，取 '20260223' 分区下，leads_create_time 在2026-02-23的用户随机取1000个 status='cleaned' 这个表是个全量表每天都是全量的留资数据，会不断的刷状态
CREATE EXTERNAL TABLE IF NOT EXISTS bicoredata.dwd_evt_hicar_leads_postback_tf_dm (
  `did` string COMMENT '华为设备编号',
  `leads_create_time` string COMMENT '原始线索创建时间',
  `source` string COMMENT '来源渠道',
  `intention_brand` string COMMENT '意向品牌',
  `intention_model` string COMMENT '意向车型',
  `follow_up_time` string COMMENT '线索首触时间',
  `status` string COMMENT '原始线索状态',
) COMMENT '事件域智选车线索回传表' PARTITIONED BY (`pt_d` string COMMENT '天分区 yyyyMMdd')


--这个是用户的行为表，里面存的是APP使用行为，只有APP使用行为，用event_type区分时间类型
CREATE EXTERNAL TABLE IF NOT EXISTS pps.dwd_pps_appdata_appusage_dm (
  `event_type` string COMMENT '事件类型',
  `package_name` string COMMENT 'APP包名',
  `first_timestamp` string COMMENT '采集时间段内第一次使用时间戳',
  `last_timestamp` string COMMENT '采集时间段内最后使用时间戳',
  `first_time_used` string COMMENT '端侧可以采集的尽可能早的应用开始使用时间戳',
  `last_time_used` string COMMENT '应用最后一次使用时间戳，时间不一定在采集时间段内',
  `total_time` string COMMENT '采集时间段内使用总时长',
  `src_pkg` string COMMENT 'thirdAppInstall: 拉起系统安装器的应用包名；appOpen: 跳转前用户点击操作的APP包名；marketInstall：应用市场包名',
  `oaid_hmac_sha256` string COMMENT 'OAID的hmacsha256',
  `app_name` string COMMENT '应用名称',
  `adid` string COMMENT 'adid',
) COMMENT '用户APP使用情况明细数据天表【探索分析使用，禁止引用】'



CREATE EXTERNAL TABLE IF NOT EXISTS biads.ads_persona_supply_persona_did_default_user_economicattr_ear_a_dm (
  `did` string COMMENT '主键编号',

  `economicattr_fact_owner_house_u` string COMMENT '有房人士',
  `economicattr_fact_consume_ability_u` string COMMENT '消费能力',
  `car_interest_owned_price_u` string COMMENT '汽车已有-价格',
) COMMENT '画像服务供给表-did-用户属性-经济属性' PARTITIONED BY (
  `pt_d` string COMMENT '天分区')
 

CREATE EXTERNAL TABLE IF NOT EXISTS biads.ads_persona_supply_persona_did_default_user_naturalattr_ear_a_dm (
  `did` string COMMENT '主键编号',
 
  `gender_new_dev` string COMMENT '性别',
  `forecast_age_dev` string COMMENT '年龄',
) COMMENT '用户属性-自然属性' PARTITIONED BY (
  `pt_d` string COMMENT '天分区',
  `shard` string COMMENT '二级分区'
)

                            CREATE EXTERNAL TABLE IF NOT EXISTS biads.ads_persona_supply_persona_did_default_scenario_trip_tim_a_dm (

  `trip_fact_public_transport_commute_u` string COMMENT '公共交通通勤',
  `trip_fact_selfdrive_commute_u` string COMMENT '自驾通勤',
) COMMENT '画像服务供给表-did-场景人群-出行场景' PARTITIONED BY (
  `pt_d` string COMMENT '天分区',
  `shard` string COMMENT '二级分区'
)


 CREATE EXTERNAL TABLE IF NOT EXISTS pps.dwd_pps_imp_cdr_all_v1_dm (
  
  `adid` string COMMENT 'ADID',
) COMMENT '曝光话单明细数据天表(加bloom)【探索分析使用，禁止引用】' PARTITIONED BY (`pt_d` string COMMENT '分区粒度字段，系统自动创建')