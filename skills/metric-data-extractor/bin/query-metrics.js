#!/usr/bin/env node
const { parseArgs, printJsonError } = require('../lib/arg-parser');
const { EntityMapper } = require('../lib/entity-mapper');
const { DSLBuilder } = require('../lib/dsl-builder');
const { HuaweiAdsClient } = require('../lib/api-client');
const { SemanticSearch } = require('../lib/semantic-search');

function parseFilters(rawFilters) {
  if (!rawFilters) {
    return {};
  }

  try {
    return JSON.parse(rawFilters);
  } catch (_error) {
    throw new Error('filters 必须是合法 JSON');
  }
}

function parseList(value) {
  if (!value) {
    return [];
  }

  return String(value)
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
}

async function trySemanticFix(errors, originalFilters) {
  const valueErrors = errors.filter((error) => error.field === 'filter_value');
  if (valueErrors.length === 0) {
    return null;
  }

  const fixedFilters = JSON.parse(JSON.stringify(originalFilters || {}));
  const searcher = new SemanticSearch();
  await searcher.initialize();

  for (const error of valueErrors) {
    const candidates = await searcher.search(error.dimension, error.value, 1);
    if (candidates.length === 0 || candidates[0].similarity < 0.5) {
      return null;
    }

    const originalKey = Object.keys(fixedFilters).find((key) => key === error.dimension || key === error.dimension || key === '推广对象' || key === '渠道' || key === '落地页' || key === '设备');
    if (originalKey) {
      fixedFilters[originalKey] = candidates[0].value_code;
    }
  }

  return fixedFilters;
}

async function main() {
  try {
    const args = parseArgs(process.argv.slice(2));

    if (!args.metrics || !args.startDate || !args.endDate) {
      printJsonError('缺少必需参数', {
        usage: 'query-metrics --metrics <list> --start-date <YYYY-MM-DD> --end-date <YYYY-MM-DD> [--dimensions <list>] [--filters <json>] [--mock]',
      });
      process.exit(1);
    }

    const mapper = new EntityMapper();
    const originalFilters = parseFilters(args.filters);
    let mappingResult = mapper.map({
      metrics: parseList(args.metrics),
      dimensions: parseList(args.dimensions),
      filters: originalFilters,
    });

    if (mappingResult.errors.length > 0) {
      const fixedFilters = await trySemanticFix(mappingResult.errors, originalFilters);
      if (fixedFilters) {
        mappingResult = mapper.map({
          metrics: parseList(args.metrics),
          dimensions: parseList(args.dimensions),
          filters: fixedFilters,
        });
      }
    }

    if (mappingResult.errors.length > 0) {
      const firstError = mappingResult.errors[0];
      printJsonError(firstError.message, {
        suggestions: firstError.suggestions || [],
        hint: '请使用建议的字段名重新查询，或使用 search-dimension-values 工具查找相似值',
      });
      process.exit(1);
    }

    const requestBody = new DSLBuilder().build({
      indicators: mappingResult.metrics,
      dimensions: mappingResult.dimensions,
      filters: mappingResult.filters,
      startDate: args.startDate,
      endDate: args.endDate,
    });

    const client = new HuaweiAdsClient({
      baseUrl: args.mock ? 'http://localhost:3000' : 'https://wo-drcn.dbankcloud.cn',
      appId: process.env.HUAWEI_ADS_APP_ID || 'mock-app-id',
      secret: process.env.HUAWEI_ADS_SECRET || 'mock-secret',
    });

    const response = await client.query(requestBody);
    const payload = response.data.data;

    if (Array.isArray(payload.data) && payload.data.length > 1000) {
      payload.data = payload.data.slice(0, 1000);
      payload.truncated = true;
      payload.total_before_truncation = response.data.data.total;
    }

    console.log(JSON.stringify(payload, null, 2));
  } catch (error) {
    printJsonError(error.message);
    process.exit(1);
  }
}

main();
