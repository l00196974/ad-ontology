import { BaseSkill } from './base';
import { readFileSync } from 'fs';
import path from 'path';
import { parse } from 'csv-parse/sync';

export class ListDimensionsSkill extends BaseSkill {
  name = 'list_dimensions';
  description = '列出所有可用的维度。当用户询问有哪些维度可以分组或筛选时使用此技能';

  input_schema = {
    type: 'object' as const,
    properties: {},
    required: [],
  };

  async execute(args: Record<string, any>): Promise<any> {
    try {
      const dimensionsPath = path.resolve(
        __dirname,
        '../../../../skills/metric-data-extractor/config/dimensions.csv',
      );
      const content = readFileSync(dimensionsPath, 'utf-8');
      const records = parse(content, {
        columns: true,
        skip_empty_lines: true,
      });

      return {
        total: records.length,
        dimensions: records.map((r: any) => ({
          code: r.dimension_code,
          name: r.dimension_name,
          description: r.dimension_desc,
        })),
      };
    } catch (error: any) {
      console.error('List dimensions error:', error);
      return {
        error: error.message,
      };
    }
  }
}
