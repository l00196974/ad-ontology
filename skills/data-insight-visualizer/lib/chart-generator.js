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

function validatePayload(payload) {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    throw new Error('payload must be an object');
  }
  if (!payload.chartType) {
    throw new Error('chartType is required');
  }
  if (!payload.dimensionKey) {
    throw new Error('dimensionKey is required');
  }
}

function generateChartOption(payload) {
  validatePayload(payload);

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
    return option;
  }

  if (chartType === 'pie') {
    option.series = buildPieSeries(series, dimensionKey);
    return option;
  }

  if (chartType === 'scatter') {
    option.xAxis = { type: 'category', data: extractCategories(baseData, dimensionKey) };
    option.yAxis = { type: 'value' };
    option.series = buildScatterSeries(series, dimensionKey, payload.valueKey);
    return option;
  }

  throw new Error(`unsupported chartType: ${chartType}`);
}

module.exports = {
  generateChartOption,
};
