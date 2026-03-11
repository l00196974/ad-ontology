const fs = require('fs');
const path = require('path');

// 读取官方数据
const metricsJson = JSON.parse(fs.readFileSync('/tmp/metrics_fixed.json', 'utf8'));
const dimensionsJson = JSON.parse(fs.readFileSync('/tmp/dimensions_fixed.json', 'utf8'));

// 指标分类映射
const metricCategories = {
  // 基础指标 - 点击相关
  'click': ['基础指标', '点击相关'],
  'receivedExposure': ['基础指标', '曝光相关'],

  // 竞价指标
  'recallSumCount': ['竞价指标', '召回相关'],
  'recallSumWinRate': ['竞价指标', '召回相关'],
  'roughRowParticipation': ['竞价指标', '粗排相关'],
  'roughRowWinRate': ['竞价指标', '粗排相关'],
  'impreciseRankWinRate': ['竞价指标', '粗排相关'],
  'preciseRowParticipation': ['竞价指标', '精排相关'],
  'preciseRowWinRate': ['竞价指标', '精排相关'],
  'preciseRankWinRate': ['竞价指标', '精排相关'],

  // 填充指标
  'stockCount': ['填充指标', '库存相关'],
  'stockNumber': ['填充指标', '库存相关'],
  'adsRequestCount': ['填充指标', '请求相关'],
  'adRequestNumber': ['填充指标', '请求相关'],
  'adReturnCount': ['填充指标', '返回相关'],
  'adReturnNumber': ['填充指标', '返回相关'],
  'mediaReceiveCount': ['填充指标', '返回相关'],
  'adFillRateCount': ['填充指标', '填充率相关'],
  'adFillRateNumber': ['填充指标', '填充率相关'],
  'adImpRateCount': ['填充指标', '展示率相关'],
  'adImpRateNumber': ['填充指标', '展示率相关'],

  // 转化指标
  'pbiConvertRate': ['转化指标', '转化率'],
  'adGroupShallowConversionNumber': ['转化指标', '浅层转化'],
  'adGroupDeepConversionNumber': ['转化指标', '深层转化'],
  'deepCvr': ['转化指标', '深层转化'],
  'deepCtcvr': ['转化指标', '深层转化'],

  // 成本指标
  'realityConversionCost': ['成本指标', '转化成本'],
  'deepExceptConversionCost': ['成本指标', '转化成本'],
  'shallowCostOffset': ['成本指标', '成本抵进'],
  'deepCostOffset': ['成本指标', '成本抵进'],
  'actualSpent': ['成本指标', '流水相关'],
  'clickActualSpent': ['成本指标', '流水相关'],
  'corpValue': ['成本指标', '价值相关'],
  'totalOcpxAdvTargetCnvrPrice': ['成本指标', '转化价格'],

  // 价格指标
  'realEcpm': ['价格指标', 'ECPM相关'],
  'dspRealEcpm': ['价格指标', 'ECPM相关'],
  'clickFirstPrice': ['价格指标', '一二价相关'],
  'clickSecondPrice': ['价格指标', '一二价相关'],
  'firstSecondPriceGap': ['价格指标', '一二价相关'],
  'clickFirstSecondPriceGap': ['价格指标', '一二价相关'],
  'revenueGap': ['价格指标', '价格GAP'],

  // 算法指标
  'pctrBias': ['算法指标', 'Bias相关'],
  'pcvrBias': ['算法指标', 'Bias相关'],
  'finalPCVRBias': ['算法指标', 'Bias相关'],
  'resPcvrBias': ['算法指标', 'Bias相关'],
  'resPcvr': ['算法指标', '预估值相关'],

  // 出价指标
  'pacer1': ['出价指标', '出价因子'],
  'costRatio': ['出价指标', '调价因子'],
  'costRatioCnt': ['出价指标', '调价因子'],
  'feeDeductionRatio': ['出价指标', '扣费因子'],

  // 流量指标
  'activeUV': ['流量指标', 'UV相关'],
  'dspReqUV': ['流量指标', 'UV相关'],
  'dspReqPV': ['流量指标', 'PV相关'],
  'dspReturnCount': ['流量指标', 'DSP相关'],

  // 其他指标
  'rtaBidRate': ['其他指标', 'RTA相关'],
};

// 指标别名映射
const metricAliases = {
  'click': '点击,点击数,点击量,clicks',
  'receivedExposure': '曝光,曝光量,曝光次数,实收曝光,exposure',
  'pbiConvertRate': '转化率,CVR,转化',
  'realEcpm': 'ecpm,ECPM,真实ECPM',
  'activeUV': 'UV,用户数,活跃用户',
  'pacer1': '出价因子,pacer,pacer1',
  'costRatio': '调价因子,cost_ratio',
  'feeDeductionRatio': '扣费因子,扣费',
  'pctrBias': 'pctr_bias,点击率bias',
  'pcvrBias': 'pcvr_bias,转化率bias',
};

// 指标支持的维度（通用维度）
const commonDimensions = 'reqDay,reqHour,hour,promotionTarget,mediaName,positionName,priceType,adGroupName,adGroupStatus,corpName,mediaType,slotForm';

// 生成指标描述
function generateMetricDesc(metric) {
  const indicatorName = metric.indicatorName || metric.uxName;
  const code = metric.name;

  // 基于指标类型生成描述
  if (code.includes('Rate') || code.includes('rate')) {
    return `${indicatorName}，表示相关事件的比率`;
  } else if (code.includes('Count') || code.includes('Number')) {
    return `${indicatorName}，统计相关事件的数量`;
  } else if (code.includes('Cost') || code.includes('Spent')) {
    return `${indicatorName}，反映广告投放的成本`;
  } else if (code.includes('Price') || code.includes('ecpm')) {
    return `${indicatorName}，反映广告的价格水平`;
  } else if (code.includes('Bias')) {
    return `${indicatorName}，算法预估偏差指标`;
  } else if (code.includes('Conversion')) {
    return `${indicatorName}，衡量转化效果`;
  } else {
    return indicatorName;
  }
}

// 生成增强的 metrics.csv
function generateMetricsCsv() {
  const header = 'metric_code,metric_name,metric_desc,category_level1,category_level2,supported_dimensions,metric_aliases,indicator_id,decimal_places';
  const rows = [header];

  metricsJson.forEach(metric => {
    const code = metric.name;
    const name = metric.uxName;
    const desc = generateMetricDesc(metric);
    const category = metricCategories[code] || ['其他指标', '未分类'];
    const dimensions = commonDimensions;
    const aliases = metricAliases[code] || name;
    const indicatorId = metric.indicatorId || '';
    const decimalPlaces = metric.decimalPlaces || 8;

    // CSV转义：包含逗号的字段用双引号包裹
    const row = `${code},${name},"${desc}",${category[0]},${category[1]},"${dimensions}","${aliases}",${indicatorId},${decimalPlaces}`;
    rows.push(row);
  });

  return rows.join('\n');
}

// 维度类型和枚举值映射
const dimensionTypes = {
  'priceType': { type: 'enum', values: 'CPC,CPM,CPA,oCPC,oCPM' },
  'adGroupStatus': { type: 'enum', values: '运行中,已暂停,已结束,待审核' },
  'mediaType': { type: 'semi-enum', values: '视频,资讯,音乐,阅读,游戏,浏览器,应用市场,等' },
  'slotForm': { type: 'semi-enum', values: '信息流,横幅,插屏,开屏,激励视频,等' },
  'promotionType': { type: 'enum', values: 'PDB,PD,RTB' },
  'algModeTag': { type: 'semi-enum', values: 'oCPC,oCPM,智能出价,等' },
  'shallowEffectType': { type: 'semi-enum', values: '下载,注册,表单提交,咨询,激活,等' },
  'deepEffectType': { type: 'semi-enum', values: '付费,次留,购买,激活,关键行为,等' },
  'gameMonetizeType': { type: 'semi-enum', values: '重度游戏,中度游戏,轻度游戏,超休闲游戏,等' },
  'mediaName': { type: 'semi-enum', values: '华为浏览器,华为视频,华为音乐,华为阅读,华为应用市场,等' },
  'positionName': { type: 'semi-enum', values: '信息流版位,搜索版位,开屏版位,详情页版位,等' },
  'reqDay': { type: 'date', values: '2026-03-01,2026-03-08(格式:YYYY-MM-DD)' },
  'reqHour': { type: 'time', values: '00,08,12,18,23(格式:HH,00-23)' },
  'hour': { type: 'time', values: '00,08,12,18,23(格式:HH,00-23)' },
  'dspId': { type: 'id', values: 'dsp_001,dsp_002(格式:dsp_xxx)' },
  'corpId': { type: 'id', values: 'corp_001,corp_002(格式:corp_xxx)' },
  'adGroupId': { type: 'id', values: 'adgroup_001,adgroup_002(格式:adgroup_xxx)' },
  'campaignId': { type: 'id', values: 'campaign_001,campaign_002(格式:campaign_xxx)' },
  'positionId': { type: 'id', values: 'position_001,position_002(格式:position_xxx)' },
  'slotId': { type: 'id', values: 'slot_001,slot_002(格式:slot_xxx)' },
  'promoteAppPkg': { type: 'package', values: 'com.huawei.aito,com.example.app(格式:包名)' },
  'packageName': { type: 'package', values: 'com.huawei.browser,com.huawei.himovie(格式:包名)' },
  'promotionTarget': { type: 'string', values: '问界M7,元保保险,某电商APP(示例)' },
  'adGroupName': { type: 'string', values: '问界M7推广任务01,元保车险推广任务01(示例)' },
  'corpName': { type: 'string', values: '问界汽车广告主,元保保险广告主(示例)' },
  'promoteAppName': { type: 'string', values: '问界汽车,元保保险(示例)' },
  'slotName': { type: 'string', values: '首页信息流,搜索结果页(示例)' },
  'dspName': { type: 'string', values: 'DSP_A,DSP_B(示例)' },
  'sspName': { type: 'string', values: 'SSP_A,SSP_B(示例)' },
  'mediaAppName': { type: 'string', values: '华为浏览器,华为视频(示例)' },
  'appSecondClassName': { type: 'string', values: 'AG二级分类示例' },
  'operatingIndustryLevel1NotConsistent': { type: 'semi-enum', values: '汽车,保险,电商,教育,游戏,金融,等' },
  'operatingIndustryLevel2NotConsistent': { type: 'semi-enum', values: '新能源汽车,传统汽车,车险,寿险,等' },
  'appFirstIndustryClass': { type: 'semi-enum', values: '视频,资讯,音乐,阅读,游戏,等' },
  'appSecondIndustryClass': { type: 'semi-enum', values: '短视频,长视频,新闻资讯,小说阅读,等' },
  'mediaAppSecondClass': { type: 'semi-enum', values: '短视频,长视频,新闻资讯,小说阅读,等' },
};

// 维度别名映射
const dimensionAliases = {
  'promotionTarget': '推广标的,推广对象,广告主,标的',
  'priceType': '计费方式,计费类型,出价方式',
  'adGroupName': '任务名称,任务,task_name',
  'adGroupStatus': '任务状态,状态',
  'mediaName': '媒体名称,媒体,media',
  'positionName': '版位名称,版位,position',
  'slotName': '广告位名称,广告位,slot',
  'reqDay': '请求时间,请求日期,日期,天',
  'reqHour': '请求小时,小时',
  'hour': '小时,时间',
  'corpName': '广告主名称,广告主',
  'promoteAppName': '推广应用名称,应用名称',
  'promoteAppPkg': '推广应用包名,应用包名',
  'packageName': '包名,应用包名',
  'mediaType': '媒体分类,媒体类型',
  'slotForm': '广告位展示形式,展示形式,广告形式',
  'shallowEffectType': '浅层转化目标,浅层目标',
  'deepEffectType': '深层转化目标,深层目标',
  'algModeTag': '算法模型,模型',
  'gameMonetizeType': '游戏行业分类,游戏分类',
  'promotionType': '采买模式,采买方式',
};

// 生成维度描述
function generateDimensionDesc(dimension) {
  const code = dimension.name;
  const name = dimension.uxName || dimension.dimensionName;

  const typeInfo = dimensionTypes[code];
  if (!typeInfo) {
    return `${name}，用于数据筛选和分组`;
  }

  const { type, values } = typeInfo;

  if (type === 'enum') {
    return `${name}，枚举类维度，可选值：${values}`;
  } else if (type === 'semi-enum') {
    return `${name}，半枚举类维度，常见值包括：${values}`;
  } else if (type === 'date') {
    return `${name}，日期类维度，格式：YYYY-MM-DD`;
  } else if (type === 'time') {
    return `${name}，时间类维度，格式：HH (00-23)`;
  } else if (type === 'id') {
    return `${name}，标识符类维度`;
  } else if (type === 'package') {
    return `${name}，应用包名类维度`;
  } else {
    return `${name}，自由文本类维度`;
  }
}

// 生成增强的 dimensions.csv
function generateDimensionsCsv() {
  const header = 'dimension_code,dimension_name,dimension_en_name,dimension_desc,dimension_aliases,value_examples,dimension_type';
  const rows = [header];

  dimensionsJson.forEach(dimension => {
    const code = dimension.name;
    const name = dimension.dimensionName || dimension.uxName;
    const enName = dimension.dimensionEnName;
    const desc = generateDimensionDesc(dimension);
    const aliases = dimensionAliases[code] || name;
    const typeInfo = dimensionTypes[code] || { type: 'string', values: '(待补充示例)' };
    const examples = typeInfo.values;
    const type = typeInfo.type;

    // CSV转义
    const row = `${code},${name},${enName},"${desc}","${aliases}","${examples}",${type}`;
    rows.push(row);
  });

  return rows.join('\n');
}

// 生成文件
const metricsCsv = generateMetricsCsv();
const dimensionsCsv = generateDimensionsCsv();

fs.writeFileSync('/home/linxiankun/huawei-ad-ontology/skills/metric-data-extractor/config/metrics.csv', metricsCsv, 'utf8');
fs.writeFileSync('/home/linxiankun/huawei-ad-ontology/skills/metric-data-extractor/config/dimensions.csv', dimensionsCsv, 'utf8');

console.log('✓ 生成 metrics.csv 完成');
console.log('✓ 生成 dimensions.csv 完成');
