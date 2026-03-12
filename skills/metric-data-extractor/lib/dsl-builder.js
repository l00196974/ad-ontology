// 日期计算辅助函数
function addDays(dateStr, days) {
  const date = new Date(dateStr);
  date.setDate(date.getDate() + days);
  return date.toISOString().split('T')[0];
}

class DSLBuilder {
  build({ indicators, dimensions, filters, startDate, endDate, timeMode }) {
    let dateTimeFilter, filterConditions, finalDimensions, timingDimension;

    // 处理现有的过滤条件
    const existingFilters = Object.values(filters || {}).map((filterConfig) => ({
      oper: filterConfig.oper,
      source: filterConfig.source,
      targetValue: filterConfig.targetValue,
    }));

    if (timeMode === 'request') {
      // 广告请求时间口径
      // dateTimeFilter 扩展90天，确保延迟回传的转化数据不丢失
      const extendedEnd = addDays(endDate, 90);
      dateTimeFilter = [{ start: startDate, end: extendedEnd }];

      // 用 filterConditions 限制 reqDay 范围
      filterConditions = [
        {
          oper: 'BETWEEN',
          source: 'reqDay',
          targetValue: [startDate, endDate],
        },
        ...existingFilters,
      ];

      // dimensions 里加 reqDay（如果用户没传）
      const dimensionsArray = Array.isArray(dimensions) ? dimensions : [];
      finalDimensions = dimensionsArray.includes('reqDay') ? dimensionsArray : ['reqDay', ...dimensionsArray];
      timingDimension = null; // 请求时间口径不用 timingDimension

    } else {
      // 事件发生时间口径（event）
      dateTimeFilter = [{ start: startDate, end: endDate }];
      filterConditions = existingFilters;
      finalDimensions = Array.isArray(dimensions) ? dimensions : [];

      // timingDimension: day/week/month，当 dimensions 含 'day' 时设为 'day'
      timingDimension = finalDimensions.includes('day') ? 'day' :
                       finalDimensions.includes('week') ? 'week' :
                       finalDimensions.includes('month') ? 'month' : null;
    }

    return {
      pageSize: null,
      pageNum: null,
      top: null,
      timingDimension,
      filterConditions,
      dateTimeFilter,
      orderBy: null,
      indicators: (indicators || []).map((indicatorKey) => ({ indicatorKey })),
      dimensions: finalDimensions.length > 0 ? finalDimensions : null,
      calcFlag: null,
    };
  }
}

module.exports = {
  DSLBuilder,
};
