const test = require('node:test');
const assert = require('node:assert/strict');
const { generateChartOption } = require('../lib/chart-generator');

const baseSeries = [{
  name: '消耗',
  metricKey: 'cost',
  data: [
    { date: '2026-01-01', channel: 'A', cost: 100, value: 100 },
    { date: '2026-01-02', channel: 'B', cost: 200, value: 200 },
  ],
}];

test('generateChartOption renders line option', () => {
  const option = generateChartOption({
    chartType: 'line',
    title: '趋势',
    dimensionKey: 'date',
    series: baseSeries,
  });

  assert.equal(option.xAxis.type, 'category');
  assert.deepEqual(option.series[0].data, [100, 200]);
});

test('generateChartOption renders bar option', () => {
  const option = generateChartOption({
    chartType: 'bar',
    dimensionKey: 'channel',
    series: baseSeries,
  });

  assert.equal(option.series[0].type, 'bar');
  assert.deepEqual(option.xAxis.data, ['A', 'B']);
});

test('generateChartOption renders pie option', () => {
  const option = generateChartOption({
    chartType: 'pie',
    dimensionKey: 'channel',
    series: baseSeries,
  });

  assert.equal(option.series[0].type, 'pie');
  assert.deepEqual(option.series[0].data[0], { name: 'A', value: 100 });
});

test('generateChartOption renders scatter option', () => {
  const option = generateChartOption({
    chartType: 'scatter',
    dimensionKey: 'date',
    series: baseSeries,
  });

  assert.equal(option.series[0].type, 'scatter');
  assert.deepEqual(option.series[0].data[1], ['2026-01-02', 200]);
});

test('generateChartOption throws on unsupported chart type', () => {
  assert.throws(() => generateChartOption({ chartType: 'radar', dimensionKey: 'date', series: baseSeries }), /unsupported chartType/);
});
