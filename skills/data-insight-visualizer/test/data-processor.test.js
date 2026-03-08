const test = require('node:test');
const assert = require('node:assert/strict');
const { processMetrics } = require('../lib/data-processor');

test('processMetrics calculates yoy deterministically', () => {
  const result = processMetrics({
    operation: 'yoy',
    metricKey: 'cost',
    dimensionKey: 'date',
    data: [
      { date: '2025-01-01', cost: 100 },
      { date: '2026-01-01', cost: 120 },
    ],
  });

  assert.equal(result.data[1].previousValue, 100);
  assert.equal(result.data[1].change, 20);
  assert.equal(result.data[1].changeRate, 0.2);
});

test('processMetrics calculates mom deterministically', () => {
  const result = processMetrics({
    operation: 'mom',
    metricKey: 'cost',
    dimensionKey: 'date',
    data: [
      { date: '2026-01-15', cost: 80 },
      { date: '2026-02-15', cost: 100 },
    ],
  });

  assert.equal(result.data[1].previousValue, 80);
  assert.equal(result.data[1].changeRate, 0.25);
});

test('processMetrics calculates ratio deterministically', () => {
  const result = processMetrics({
    operation: 'ratio',
    metricKey: 'cost',
    data: [
      { channel: 'A', cost: 40 },
      { channel: 'B', cost: 60 },
    ],
  });

  assert.equal(result.data[0].total, 100);
  assert.equal(result.data[0].ratio, 0.4);
  assert.equal(result.data[1].percentage, 60);
});

test('processMetrics calculates tgi deterministically', () => {
  const result = processMetrics({
    operation: 'tgi',
    targetMetricKey: 'targetConversions',
    targetBaseKey: 'targetUsers',
    overallMetricKey: 'overallConversions',
    overallBaseKey: 'overallUsers',
    data: [
      {
        segment: '年轻用户',
        targetConversions: 30,
        targetUsers: 100,
        overallConversions: 20,
        overallUsers: 100,
      },
    ],
  });

  assert.equal(result.data[0].targetRate, 0.3);
  assert.equal(result.data[0].overallRate, 0.2);
  assert.equal(result.data[0].tgi, 150);
});

test('processMetrics validates input', () => {
  assert.throws(() => processMetrics({ data: [] }), /operation is required/);
});
