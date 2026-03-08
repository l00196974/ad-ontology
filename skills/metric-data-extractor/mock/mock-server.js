const express = require('express');

const app = express();
app.use(express.json());

function enumerateDates(startDate, endDate) {
  const dates = [];
  const cursor = new Date(startDate);
  const end = new Date(endDate);

  while (cursor <= end) {
    dates.push(cursor.toISOString().split('T')[0]);
    cursor.setDate(cursor.getDate() + 1);
  }

  return dates;
}

function dimensionValuesFor(code) {
  const dimensionMap = {
    promotionTarget: ['yuanbao_insurance', 'car_brand_a', 'wenjie_m7', 'wenjie_m9', 'byd_han'],
    channel: ['feed', 'search', 'splash', 'banner', 'interstitial'],
    device: ['android', 'ios', 'harmony'],
    media: ['huawei_browser', 'huawei_video', 'huawei_music', 'huawei_appgallery'],
    mediaPosition: ['feed_position', 'search_position', 'splash_position'],
    industry: ['automotive', 'insurance', 'ecommerce', 'education'],
    conversionGoal: ['download', 'install', 'register', 'lead', 'purchase'],
    bidStrategy: ['cpc', 'cpm', 'cpa', 'ocpc'],
    region: ['beijing', 'shanghai', 'guangdong', 'nationwide'],
    age: ['18-24', '25-34', '35-44', '45+'],
    gender: ['male', 'female', 'unknown'],
    carBrand: ['wenjie', 'byd', 'tesla', 'lixiang'],
    carModel: ['m7', 'm9', 'han', 'tang', 'model_y'],
    contentType: ['auto_news', 'auto_review', 'auto_price'],
    searchIntent: ['brand_search', 'price_search', 'param_search'],
    userScenario: ['commute', 'shopping', 'work', 'entertainment'],
    timeSlot: ['morning', 'noon', 'evening', 'night'],
    weekday: ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'],
  };

  return dimensionMap[code] || [];
}

function baseValue(indicatorKey, index) {
  const seed = {
    // 核心指标
    cost: 450000,
    leads: 320,
    impressions: 900000,
    clicks: 24000,
    conversions: 2600,

    // 计算指标
    ctr: 0.026,
    cvr: 0.11,
    cpc: 18.75,
    cpm: 500,
    cpa: 173.08,
    roi: 2.5,

    // 广告请求相关
    requests: 1200000,
    fills: 950000,
    fillRate: 0.79,

    // APP相关
    downloads: 2800,
    installs: 2400,
    activations: 1800,

    // 其他转化
    registrations: 1500,
    purchases: 450,
    revenue: 125000,

    // 落地页指标
    avgDuration: 45,
    bounceRate: 0.35,

    // 深浅层转化
    deepConversions: 800,
    shallowConversions: 1800,

    // 视频指标
    videoViews: 85000,
    videoCompletions: 42000,
    videoCompletionRate: 0.49,
  };

  const value = seed[indicatorKey] || 100;

  // 比率类指标保持在0-1之间
  if (['ctr', 'cvr', 'fillRate', 'bounceRate', 'videoCompletionRate'].includes(indicatorKey)) {
    const variation = (Math.random() - 0.5) * 0.02; // ±1%的随机波动
    return Number(Math.max(0, Math.min(1, value + variation)).toFixed(4));
  }

  // ROI类指标
  if (indicatorKey === 'roi') {
    const variation = (Math.random() - 0.5) * 0.5;
    return Number((value + variation).toFixed(2));
  }

  // 成本类指标
  if (['cpc', 'cpm', 'cpa'].includes(indicatorKey)) {
    const variation = (Math.random() - 0.5) * value * 0.2; // ±10%波动
    return Number((value + variation).toFixed(2));
  }

  // 时长类指标(秒)
  if (indicatorKey === 'avgDuration') {
    const variation = (Math.random() - 0.5) * 20;
    return Number((value + variation).toFixed(0));
  }

  // 数量类指标添加随机波动
  const variation = (Math.random() - 0.5) * value * 0.3; // ±15%波动
  return Number(Math.max(0, value + variation + index * 137.5).toFixed(2));
}

app.post('/ads-data/openapi/v1/chart/common', (req, res) => {
  const { indicators = [], dimensions = [], dateTimeFilter = [], filterConditions = [] } = req.body || {};
  const startDate = dateTimeFilter[0]?.start || '2026-01-01';
  const endDate = dateTimeFilter[0]?.end || startDate;
  const dates = enumerateDates(startDate, endDate);

  let rows = dates.map((date, index) => {
    const row = { date };
    for (const indicator of indicators) {
      row[indicator.indicatorKey] = baseValue(indicator.indicatorKey, index);
    }
    return row;
  });

  for (const dimension of dimensions || []) {
    if (dimension === 'day') {
      continue;
    }

    const values = dimensionValuesFor(dimension);
    if (values.length === 0) {
      continue;
    }

    rows = rows.flatMap((row, rowIndex) =>
      values.map((value, valueIndex) => {
        const factor = valueIndex + 1;
        const next = { ...row, [dimension]: value };
        for (const indicator of indicators) {
          const current = next[indicator.indicatorKey];
          if (typeof current === 'number') {
            next[indicator.indicatorKey] = Number((current / factor + rowIndex * 17).toFixed(4));
          }
        }
        return next;
      }),
    );
  }

  for (const filter of filterConditions) {
    rows = rows.filter((row) => {
      if (!(filter.source in row)) {
        return true;
      }
      return (filter.targetValue || []).includes(row[filter.source]);
    });
  }

  res.json({
    code: 200,
    data: {
      data: rows,
      total: rows.length,
    },
    message: 'OK',
  });
});

const port = Number(process.env.PORT || 3000);
app.listen(port, () => {
  console.log(`Mock API服务启动: http://localhost:${port}`);
});
