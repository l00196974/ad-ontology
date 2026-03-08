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
  switch (code) {
    case 'promotionTarget':
      return ['yuanbao_insurance', 'car_brand_a'];
    case 'channel':
      return ['feed', 'search', 'splash'];
    case 'device':
      return ['android', 'ios'];
    default:
      return [];
  }
}

function baseValue(indicatorKey, index) {
  const seed = {
    cost: 450000,
    leads: 320,
    impressions: 900000,
    clicks: 24000,
    ctr: 0.026,
    cvr: 0.11,
    conversions: 2600,
  };

  const value = seed[indicatorKey] || 100;
  if (indicatorKey === 'ctr' || indicatorKey === 'cvr') {
    return Number((value + index * 0.002).toFixed(4));
  }

  return Number((value + index * 1375.23).toFixed(2));
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
