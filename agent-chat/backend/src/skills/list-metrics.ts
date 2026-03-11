import { BaseSkill } from './base';
import { readFileSync } from 'fs';
import path from 'path';
import { parse } from 'csv-parse/sync';

export class ListMetricsSkill extends BaseSkill {
  name = 'list_metrics';
  description = '列出所有可用的指标。当用户询问有哪些指标可以查询时使用此技能';

  input_schema = {
    type: 'object' as const,
    properties: {},
    required: [],
  };

  async execute(args: Record<string, any>): Promise<any> {
    try {
      const metricsPath = path.resolve(
        __dirname,
        '../../../../skills/metric-data-extractor/config/metrics.csv',
      );
      const content = readFileSync(metricsPath, 'utf-8');
      const records = parse(content, {
        columns: true,
        skip_empty_lines: true,
      });

      return {
        total: records.length,
        metrics: records.map((r: any) => ({
          code: r.metric_code,
          name: r.metric_name,
          description: r.metric_desc,
        })),
      };
    } catch (error: any) {
      console.error('List metrics error:', error);
      return {
        error: error.message,
      };
    }
  }
}
