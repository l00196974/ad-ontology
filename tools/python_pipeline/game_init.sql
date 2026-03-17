


--这个是用户的行为表，里面存的是APP使用行为，只有APP使用行为，用event_type区分时间类型，UNBASE64(app_name)需要解码
CREATE EXTERNAL TABLE IF NOT EXISTS pps.dwd_pps_appdata_appusage_dm (
  `event_type` string COMMENT '事件类型',
  `package_name` string COMMENT 'APP包名',
  `first_timestamp` string COMMENT '采集时间段内第一次使用时间戳',
  `total_time` string COMMENT '采集时间段内使用总时长',
  `app_name` string COMMENT '应用名称',
  `adid` string COMMENT 'adid',
) COMMENT '用户APP使用情况明细数据天表【探索分析使用，禁止引用】' PARTITIONED BY (`pt_d` string COMMENT '天分区')

--这个是用户的行为表，里面存的是APP使用行为，只有APP使用行为，用event_type区分时间类型，UNBASE64(app_name)需要解码
CREATE EXTERNAL TABLE IF NOT EXISTS pps.dwd_pps_appdata_appusage_dm (
  `event_type` string COMMENT '事件类型',
  `package_name` string COMMENT 'APP包名',
  `report_timestamp` string COMMENT '安装卸载上报事件，存储的是毫秒值',
  `adid` string COMMENT 'adid',
) COMMENT '用户APP安装卸载数据天表【探索分析使用，禁止引用】' PARTITIONED BY (`pt_d` string COMMENT '天分区')


--用来获取应用名称和应用分类的，通过 promote_app_pkg 宝马关联
 CREATE EXTERNAL TABLE IF NOT EXISTS pps.dim_pps_metric_promoted_app_info_hs (
  `alliance_app_id` string COMMENT '开发者联盟AppId',
  `promote_app_pkg` string COMMENT '推广应用包名',
  `promote_app_name` string COMMENT '推广应用名称',
  `download_url` string COMMENT '应用下载地址',
  `apk_size` string COMMENT 'APK包大小（应用市场大小）',
  `category_level3` string COMMENT '应用三级分类'
) COMMENT '推广应用信息全量表' PARTITIONED BY (`pt_h` string COMMENT '分区粒度字段，系统自动创建')


 -- 用户特征信息，用来补充用户画像信息，可以从里面选取相关的字段
CREATE EXTERNAL TABLE IF NOT EXISTS biads.ads_usidpersona_inf_game_payment_intention_new_dm (
  `usid` string COMMENT 'usid',
  `sum_cashpay_amt_30d` double COMMENT '30天现金付费总额',
  `max_cashpay_amt_30d` double COMMENT '30天现金付费最大额',
  `cashpay_cnt_30d` bigint COMMENT '30天现金付费次数',
  `avg_cashpay_amt_30d` double COMMENT '30天现金付费平均额',
  `max_cashpay_days_30d` bigint COMMENT '30天现金付费最大额距今天数',
  `sum_couponpay_amt_30d` double COMMENT '30天优惠券付费总额',
  `max_couponpay_amt_30d` double COMMENT '30天优惠券付费最大额',
  `couponpay_cnt_30d` bigint COMMENT '30天优惠券付费次数',
  `avg_couponpay_amt_30d` double COMMENT '30天优惠券付费平均额',
  `max_couponpay_days_30d` bigint COMMENT '30天优惠券付费最大额距今天数',
  `sum_cashpay_amt_60d` double COMMENT '60天现金付费总额',
  `max_cashpay_amt_60d` double COMMENT '60天现金付费最大额',
  `cashpay_cnt_60d` bigint COMMENT '60天现金付费次数',
  `avg_cashpay_amt_60d` double COMMENT '60天现金付费平均额',
  `max_cashpay_days_60d` bigint COMMENT '60天现金付费最大额距今天数',
  `sum_couponpay_amt_60d` double COMMENT '60天优惠券付费总额',
  `max_couponpay_amt_60d` double COMMENT '60天优惠券付费最大额',
  `couponpay_cnt_60d` bigint COMMENT '60天优惠券付费次数',
  `avg_couponpay_amt_60d` double COMMENT '60天优惠券付费平均额',
  `max_couponpay_days_60d` bigint COMMENT '60天优惠券付费最大额距今天数',
  `gender_new_dev` string COMMENT '性别',
  `forecast_age_dev` string COMMENT '年龄',
  `price_new_dev` string COMMENT '设备价格',
  `brand_new_dev` string COMMENT '品牌',
  `color_v2_dev` string COMMENT '机身颜色',
  `active_duration_dev` string COMMENT '激活天数',
  `series_new_dev` string COMMENT '系列名称',
  `product_new_dev` string COMMENT '传播名',
  `push_online_days_30d_dev` string COMMENT '手机月在线天数',
  `last_mon_used_mobile_data_size_dev` string COMMENT '上月使用移动流量',
  `education_dev` string COMMENT '学历',
  `owner_house_flag_dev` string COMMENT '有房人士',
  `owner_cars_user_dev` string COMMENT '有车人士',
  `consume_frequency_dev` string COMMENT '消费频率',
  `consume_credit_card_level_dev` string COMMENT '信用卡使用',
  `care_offc_acct_up` string COMMENT '已关注通知号',
  `game_search_tfidf_1d_list` string COMMENT '1天内游戏搜索按次数tfidf排名列表TOP10',
  `game_search_tfidf_3d_list` string COMMENT '3天内游戏搜索按次数tfidf排名列表TOP10',
  `game_search_tfidf_7d_list` string COMMENT '7天内游戏搜索按次数tfidf排名列表TOP10',
  `game_search_tfidf_15d_list` string COMMENT '15天内游戏搜索按次数tfidf排名列表TOP10',
  `game_search_tfidf_30d_list` string COMMENT '30天内游戏搜索按次数tfidf排名列表TOP10',
  `search_keywords_dev` string COMMENT '搜索关键词特征，多个关键词用分隔符分隔',
  `content_keywords_dev` string COMMENT '内容关键词特征，多个关键词用分隔符分隔',
  `ha_view_packages` string COMMENT '端侧浏览的应用包名，多个包名用分隔符分隔',
  `ha_search_keywords` string COMMENT '端侧搜索的关键词，多个关键词用分隔符分隔',
  `gc_query_keywords` string COMMENT '游戏中心搜索的关键词，多个关键词用分隔符分隔',
  `game_category_pay_30days` string COMMENT '游戏分类付费数据30天，多个类目用分隔符分隔',
  `game_category_pay_90days` string COMMENT '游戏分类付费数据90天，多个类目用分隔符分隔',
  `game_category_pay_180days` string COMMENT '游戏分类付费数据180天，多个类目用分隔符分隔',
  `game_interest_thirdclass_user_lifetime_u` string COMMENT '游戏用户生命周期_三级分类，多个类目用分隔符分隔',
  `game_interest_secondclass_user_lifetime_u` string COMMENT '游戏用户生命周期_二级分类，多个类目用分隔符分隔',
  `game_interest_user_lifetime_u` string COMMENT '游戏用户生命周期',
  `game_fact_rmb_user_u` string COMMENT '游戏用户大R等级',
  `game_fact_sedclass_rmb_user_u` string COMMENT '游戏用户大R等级_二级分类，多个类目用分隔符分隔',
  `game_fact_thirdclass_rmb_user_u` string COMMENT '游戏用户大R等级_三级分类，多个类目用分隔符分隔',
) COMMENT '游戏意向标签新预测集' PARTITIONED BY (`pt_d` string COMMENT '天分区')

-- 取点击，转化，曝光事件 ，你可以参考这个取数逻辑
SELECT
    did,
    CONCAT_WS(' -> ', SORT_ARRAY(COLLECT_LIST(event_detail),false)) AS ad_action_seq
FROM (
         -- ==========================================
         -- 1. 远期汇总: 特定转化事件 (< 20260215)
         -- ==========================================
         SELECT
             a.did,
             -- 明确补充了 [02/01-02/14 历史汇总]
             CONCAT('[2026-02-14][02/01-02/14 历史汇总]【', b.event_type, '】累计发生:', CAST(SUM(b.event_cnt) AS STRING),
                    ' 行业:', COALESCE(b.cust_industry_level1, '未知'), '-', COALESCE(b.cust_industry_level2, '未知'),
                    ' 版位:', COALESCE(b.position_name, '未知'),
                    ' 标的:', COALESCE(b.promote_app_name, '未知')
             ) AS event_detail
         FROM adhoctemp.tmp_l00527489_20260305_ads_llm_auto_intent_sample_pool_ctr a
                  JOIN pps.ads_pps_user_base_indicator_dm b ON a.did = b.did
         WHERE a.pt_d = '20260305'
           AND b.pt_d >= '20260201' AND b.pt_d < '20260215'
           AND b.event_cnt > 0
           AND b.event_type NOT IN ('repeatedImp','skip','playStart','playPause','webclose','intentSuccess','appOpen','webopen')
           AND b.total_task_cnvr_target_cnvr_cnt > 0
         GROUP BY a.did, b.event_type, b.cust_industry_level1, b.cust_industry_level2, b.position_name, b.promote_app_name

         UNION ALL

         -- ==========================================
         -- 2. 远期汇总: 汽车行业曝光 (< 20260215)
         -- ==========================================
         SELECT
             a.did,
             CONCAT('[2026-02-14][02/01-02/14 历史汇总]【曝光】累计次数:', CAST(SUM(b.received_total_imp) AS STRING),
                    ' 行业:', COALESCE(b.cust_industry_level1, '未知'), '-', COALESCE(b.cust_industry_level2, '未知'),
                    ' 版位:', COALESCE(b.position_name, '未知'),
                    ' 标的:', COALESCE(b.promote_app_name, '未知')
             ) AS event_detail
         FROM adhoctemp.tmp_l00527489_20260305_ads_llm_auto_intent_sample_pool_ctr a
                  JOIN pps.ads_pps_user_base_indicator_dm b ON a.did = b.did
         WHERE a.pt_d = '20260305'
           AND b.pt_d >= '20260201' AND b.pt_d < '20260215'
           AND b.received_total_imp > 0
         GROUP BY a.did, b.cust_industry_level1, b.cust_industry_level2, b.position_name, b.promote_app_name

         UNION ALL

         -- ==========================================
         -- 3. 远期汇总: 全行业点击 (< 20260215)
         -- ==========================================
         SELECT
             a.did,
             CONCAT('[2026-02-14][02/01-02/14 历史汇总]【点击】累计次数:', CAST(SUM(b.received_total_click) AS STRING),
                    ' 行业:', COALESCE(b.cust_industry_level1, '未知'), '-', COALESCE(b.cust_industry_level2, '未知'),
                    ' 版位:', COALESCE(b.position_name, '未知'),
                    ' 标的:', COALESCE(b.promote_app_name, '未知')
             ) AS event_detail
         FROM adhoctemp.tmp_l00527489_20260305_ads_llm_auto_intent_sample_pool_ctr a
                  JOIN pps.ads_pps_user_base_indicator_dm b ON a.did = b.did
         WHERE a.pt_d = '20260305'
           AND b.pt_d >= '20260201' AND b.pt_d < '20260215'
           AND b.received_total_click > 0
         GROUP BY a.did, b.cust_industry_level1, b.cust_industry_level2, b.position_name, b.promote_app_name

         UNION ALL

         -- ==========================================
         -- 4. 近期明细: 特定转化事件 (>= 20260215)
         -- ==========================================
         SELECT
             a.did,
             CONCAT('[', b.event_day, '][广告]【', b.event_type, '】事件发生次数:', CAST(SUM(b.event_cnt) AS STRING),
                    ' 行业:', COALESCE(b.cust_industry_level1, '未知'), '-', COALESCE(b.cust_industry_level2, '未知'),
                    ' 版位:', COALESCE(b.position_name, '未知'),
                    ' 标的:', COALESCE(b.promote_app_name, '未知')
             ) AS event_detail
         FROM adhoctemp.tmp_l00527489_20260305_ads_llm_auto_intent_sample_pool_ctr a
                  JOIN pps.ads_pps_user_base_indicator_dm b ON a.did = b.did
         WHERE a.pt_d = '20260305'
           AND b.pt_d >= '20260215' AND b.pt_d <= '20260301'
           AND b.event_cnt > 0
           AND b.event_type NOT IN ('repeatedImp','skip','playStart','playPause','webclose','intentSuccess','appOpen','webopen')
           AND b.total_task_cnvr_target_cnvr_cnt > 0
         GROUP BY a.did, b.event_day, b.event_type, b.cust_industry_level1, b.cust_industry_level2, b.position_name, b.promote_app_name

         UNION ALL

         -- ==========================================
         -- 5. 近期明细: 汽车行业曝光 (>= 20260215)
         -- ==========================================
         SELECT
             a.did,
             CONCAT('[', b.event_day, '][广告]【曝光】曝光次数:', CAST(SUM(b.received_total_imp) AS STRING),
                    ' 行业:', COALESCE(b.cust_industry_level1, '未知'), '-', COALESCE(b.cust_industry_level2, '未知'),
                    ' 版位:', COALESCE(b.position_name, '未知'),
                    ' 标的:', COALESCE(b.promote_app_name, '未知')
             ) AS event_detail
         FROM adhoctemp.tmp_l00527489_20260305_ads_llm_auto_intent_sample_pool_ctr a
                  JOIN pps.ads_pps_user_base_indicator_dm b ON a.did = b.did
         WHERE a.pt_d = '20260305'
           AND b.pt_d >= '20260215' AND b.pt_d <= '20260301'
           AND b.received_total_imp > 0
         GROUP BY a.did, b.event_day, b.cust_industry_level1, b.cust_industry_level2, b.position_name, b.promote_app_name

         UNION ALL

         -- ==========================================
         -- 6. 近期明细: 全行业点击 (>= 20260215)
         -- ==========================================
         SELECT
             a.did,
             CONCAT('[', b.event_day, '][广告]【点击】点击次数:', CAST(SUM(b.received_total_click) AS STRING),
                    ' 行业:', COALESCE(b.cust_industry_level1, '未知'), '-', COALESCE(b.cust_industry_level2, '未知'),
                    ' 版位:', COALESCE(b.position_name, '未知'),
                    ' 标的:', COALESCE(b.promote_app_name, '未知')
             ) AS event_detail
         FROM adhoctemp.tmp_l00527489_20260305_ads_llm_auto_intent_sample_pool_ctr a
                  JOIN pps.ads_pps_user_base_indicator_dm b ON a.did = b.did
         WHERE a.pt_d = '20260305'
           AND b.pt_d >= '20260215' AND b.pt_d <= '20260301'
           AND b.received_total_click > 0
         GROUP BY a.did, b.event_day, b.cust_industry_level1, b.cust_industry_level2, b.position_name, b.promote_app_name

     ) combined_ad_actions
GROUP BY did



--参考这个做usid映射
    SELECT
        bind.usid,
        SUM(COALESCE(ind.total_task_cnvr_target_cnvr_cnt, 0)) AS total_payment_amt_7d,
        SIZE(COLLECT_SET(ind.pt_d)) AS total_payment_cnt_7d
    FROM pps.ads_pps_user_base_indicator_dm ind
    INNER JOIN bicoredata.dwd_pty_combine_device_up_bind_ds bind
        ON ind.did = bind.dsid
        AND bind.pt_d = '20260304'

        这个表里面