class DSLBuilder {
  build({ indicators, dimensions, filters, startDate, endDate }) {
    const timingDimension = Array.isArray(dimensions) && dimensions.includes('day') ? 'day' : null;

    return {
      pageSize: null,
      pageNum: null,
      top: null,
      timingDimension,
      filterConditions: Object.values(filters || {}).map((filterConfig) => ({
        oper: filterConfig.oper,
        source: filterConfig.source,
        targetValue: filterConfig.targetValue,
      })),
      dateTimeFilter: [
        {
          start: startDate,
          end: endDate,
        },
      ],
      orderBy: null,
      indicators: (indicators || []).map((indicatorKey) => ({ indicatorKey })),
      dimensions: Array.isArray(dimensions) && dimensions.length > 0 ? dimensions : null,
      calcFlag: null,
    };
  }
}

module.exports = {
  DSLBuilder,
};
