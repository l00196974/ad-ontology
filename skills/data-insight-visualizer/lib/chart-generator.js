// 检测输入格式类型
function detectInputFormat(payload) {
  if (payload.dataset) {
    return 'echarts-dataset';
  }
  if (payload.data && payload.data.source) {
    return 'simplified';
  }
  if (payload.series && payload.dimensionKey) {
    return 'legacy';
  }
  throw new Error('Invalid input format. Expected: ECharts dataset, simplified format, or legacy format.');
}

// 格式1: 完整 ECharts option（推荐）
function generateFromEChartsDataset(payload) {
  // 如果已经是完整的 ECharts option，只需补充默认配置
  const defaultConfig = {
    tooltip: { trigger: 'axis' },
    legend: {},
  };

  // 如果没有 tooltip，添加默认的
  if (!payload.tooltip) {
    // 根据图表类型设置 tooltip
    const firstSeries = payload.series && payload.series[0];
    if (firstSeries && firstSeries.type === 'pie') {
      defaultConfig.tooltip.trigger = 'item';
    }
  }

  return {
    ...defaultConfig,
    ...payload
  };
}

// 格式2: 简化格式
function generateFromSimplifiedFormat(payload) {
  const { chartType = 'line', title, data } = payload;

  if (!data || !data.source) {
    throw new Error('data.source is required in simplified format');
  }

  const option = {
    tooltip: { trigger: chartType === 'pie' ? 'item' : 'axis' },
    legend: {},
    dataset: data,
  };

  if (title) {
    option.title = { text: title };
  }

  // 根据图表类型设置坐标轴和系列
  if (chartType === 'line' || chartType === 'bar') {
    option.xAxis = { type: 'category' };
    option.yAxis = { type: 'value' };
    option.series = [{ type: chartType }];
  } else if (chartType === 'pie') {
    option.series = [{ type: 'pie' }];
  } else if (chartType === 'scatter') {
    option.xAxis = { type: 'value' };
    option.yAxis = { type: 'value' };
    option.series = [{ type: 'scatter' }];
  } else {
    throw new Error(`Unsupported chartType: ${chartType}`);
  }

  return option;
}

// 格式3: 旧格式（向后兼容）
function generateFromLegacyFormat(payload) {
  const { chartType, dimensionKey, title = '' } = payload;
  const series = normalizeSeriesInput(payload);
  const baseData = series[0]?.data;

  if (!Array.isArray(baseData)) {
    throw new Error('series data must be an array');
  }

  const option = {
    title: { text: title },
    tooltip: { trigger: chartType === 'pie' ? 'item' : 'axis' },
    legend: { data: series.map((item) => item.name || item.metricKey) },
  };

  if (chartType === 'line' || chartType === 'bar') {
    option.xAxis = { type: 'category', data: extractCategories(baseData, dimensionKey) };
    option.yAxis = { type: 'value' };
    option.series = buildCartesianSeries(chartType, series, dimensionKey);
  } else if (chartType === 'pie') {
    option.series = buildPieSeries(series, dimensionKey);
  } else if (chartType === 'scatter') {
    option.xAxis = { type: 'category', data: extractCategories(baseData, dimensionKey) };
    option.yAxis = { type: 'value' };
    option.series = buildScatterSeries(series, dimensionKey, payload.valueKey);
  } else {
    throw new Error(`unsupported chartType: ${chartType}`);
  }

  return option;
}

// 旧格式的辅助函数（保持向后兼容）
function normalizeSeriesInput(payload) {
  if (Array.isArray(payload.series)) {
    return payload.series;
  }

  if (Array.isArray(payload.data) && payload.metricKey) {
    return [
      {
        name: payload.seriesName || payload.metricKey,
        metricKey: payload.metricKey,
        data: payload.data,
      },
    ];
  }

  throw new Error('series is required');
}

function extractCategories(data, dimensionKey) {
  return data.map((row) => row[dimensionKey]);
}

function buildCartesianSeries(chartType, series, dimensionKey) {
  return series.map((item) => ({
    name: item.name || item.metricKey,
    type: chartType,
    data: item.data.map((row) => row[item.metricKey]),
  }));
}

function buildPieSeries(series, dimensionKey) {
  const first = series[0];
  return [{
    name: first.name || first.metricKey,
    type: 'pie',
    data: first.data.map((row) => ({
      name: row[dimensionKey],
      value: row[first.metricKey],
    })),
  }];
}

function buildScatterSeries(series, dimensionKey, valueKey) {
  return series.map((item) => ({
    name: item.name || item.metricKey,
    type: 'scatter',
    data: item.data.map((row) => [row[dimensionKey], row[valueKey || item.metricKey]]),
  }));
}

// 主函数：根据输入格式选择处理方式
function generateChartOption(payload) {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    throw new Error('payload must be an object');
  }

  const format = detectInputFormat(payload);

  switch (format) {
    case 'echarts-dataset':
      return generateFromEChartsDataset(payload);
    case 'simplified':
      return generateFromSimplifiedFormat(payload);
    case 'legacy':
      return generateFromLegacyFormat(payload);
    default:
      throw new Error(`Unknown format: ${format}`);
  }
}

module.exports = {
  generateChartOption,
};
