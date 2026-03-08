function toNumber(value) {
  const num = Number(value);
  return Number.isFinite(num) ? num : 0;
}

function round(value, digits = 6) {
  return Number(value.toFixed(digits));
}

function shiftDateByYears(dateString, years) {
  const date = new Date(`${dateString}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) {
    return null;
  }
  date.setUTCFullYear(date.getUTCFullYear() + years);
  return date.toISOString().slice(0, 10);
}

function shiftDateByMonths(dateString, months) {
  const date = new Date(`${dateString}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) {
    return null;
  }
  const day = date.getUTCDate();
  date.setUTCDate(1);
  date.setUTCMonth(date.getUTCMonth() + months);
  const maxDay = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth() + 1, 0)).getUTCDate();
  date.setUTCDate(Math.min(day, maxDay));
  return date.toISOString().slice(0, 10);
}

function buildIndex(data, dimensionKey) {
  const map = new Map();
  for (const row of data) {
    map.set(String(row[dimensionKey]), row);
  }
  return map;
}

function calculateChange(currentValue, previousValue) {
  const change = round(currentValue - previousValue);
  const changeRate = previousValue === 0 ? null : round(change / previousValue);
  return { change, changeRate };
}

function calculateYoy({ data, metricKey, dimensionKey = 'date' }) {
  const index = buildIndex(data, dimensionKey);
  return data.map((row) => {
    const currentValue = toNumber(row[metricKey]);
    const comparisonKey = shiftDateByYears(String(row[dimensionKey]), -1);
    const previousRow = comparisonKey ? index.get(comparisonKey) : undefined;
    const previousValue = previousRow ? toNumber(previousRow[metricKey]) : null;
    const delta = previousValue === null
      ? { change: null, changeRate: null }
      : calculateChange(currentValue, previousValue);

    return {
      ...row,
      currentValue,
      previousValue,
      comparisonKey,
      change: delta.change,
      changeRate: delta.changeRate,
    };
  });
}

function calculateMom({ data, metricKey, dimensionKey = 'date' }) {
  const index = buildIndex(data, dimensionKey);
  return data.map((row) => {
    const currentValue = toNumber(row[metricKey]);
    const comparisonKey = shiftDateByMonths(String(row[dimensionKey]), -1);
    const previousRow = comparisonKey ? index.get(comparisonKey) : undefined;
    const previousValue = previousRow ? toNumber(previousRow[metricKey]) : null;
    const delta = previousValue === null
      ? { change: null, changeRate: null }
      : calculateChange(currentValue, previousValue);

    return {
      ...row,
      currentValue,
      previousValue,
      comparisonKey,
      change: delta.change,
      changeRate: delta.changeRate,
    };
  });
}

function calculateRatio({ data, metricKey }) {
  const total = round(data.reduce((sum, row) => sum + toNumber(row[metricKey]), 0));
  return data.map((row) => {
    const currentValue = toNumber(row[metricKey]);
    const ratio = total === 0 ? 0 : round(currentValue / total);
    return {
      ...row,
      currentValue,
      total,
      ratio,
      percentage: round(ratio * 100, 2),
    };
  });
}

function calculateTgi({
  data,
  targetMetricKey,
  targetBaseKey,
  overallMetricKey,
  overallBaseKey,
}) {
  return data.map((row) => {
    const targetMetric = toNumber(row[targetMetricKey]);
    const targetBase = toNumber(row[targetBaseKey]);
    const overallMetric = toNumber(row[overallMetricKey]);
    const overallBase = toNumber(row[overallBaseKey]);

    const targetRate = targetBase === 0 ? null : round(targetMetric / targetBase);
    const overallRate = overallBase === 0 ? null : round(overallMetric / overallBase);
    const tgi = targetRate === null || overallRate === null || overallRate === 0
      ? null
      : round((targetRate / overallRate) * 100, 2);

    return {
      ...row,
      targetRate,
      overallRate,
      tgi,
    };
  });
}

function validatePayload(payload) {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    throw new Error('payload must be an object');
  }
  if (!Array.isArray(payload.data)) {
    throw new Error('data must be an array');
  }
  if (!payload.operation) {
    throw new Error('operation is required');
  }
}

function processMetrics(payload) {
  validatePayload(payload);

  const { operation, data } = payload;

  switch (operation) {
    case 'yoy':
      if (!payload.metricKey) {
        throw new Error('metricKey is required for yoy');
      }
      return { operation, data: calculateYoy(payload) };
    case 'mom':
      if (!payload.metricKey) {
        throw new Error('metricKey is required for mom');
      }
      return { operation, data: calculateMom(payload) };
    case 'ratio':
      if (!payload.metricKey) {
        throw new Error('metricKey is required for ratio');
      }
      return { operation, data: calculateRatio(payload) };
    case 'tgi':
      for (const key of ['targetMetricKey', 'targetBaseKey', 'overallMetricKey', 'overallBaseKey']) {
        if (!payload[key]) {
          throw new Error(`${key} is required for tgi`);
        }
      }
      return { operation, data: calculateTgi(payload) };
    default:
      throw new Error(`unsupported operation: ${operation}`);
  }
}

module.exports = {
  processMetrics,
  calculateYoy,
  calculateMom,
  calculateRatio,
  calculateTgi,
};
