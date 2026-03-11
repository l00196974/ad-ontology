import { BaseSkill } from './base';
import { exec } from 'child_process';
import { promisify } from 'util';
import path from 'path';

const execAsync = promisify(exec);

export class SearchDimensionValuesSkill extends BaseSkill {
  name = 'search_dimension_values';
  description = '搜索维度值，用于查找推广对象、媒体等维度的可用值。例如搜索"京东"找到相关的推广对象名称';

  input_schema = {
    type: 'object' as const,
    properties: {
      dimension: {
        type: 'string',
        description: '维度代码，如：promotionTarget（推广对象）、mediaName（媒体名称）',
      },
      query: {
        type: 'string',
        description: '搜索关键词，如："京东"、"问界"',
      },
      top_k: {
        type: 'number',
        description: '返回结果数量，默认5',
      },
    },
    required: ['dimension', 'query'],
  };

  async execute(args: Record<string, any>): Promise<any> {
    const { dimension, query, top_k = 5 } = args;

    const skillPath = path.resolve(__dirname, '../../../../skills/metric-data-extractor');
    const command = `cd "${skillPath}" && node bin/search-dimension-values.js --dimension "${dimension}" --query "${query}" --top-k ${top_k}`;

    console.log('Executing command:', command);

    try {
      const { stdout, stderr } = await execAsync(command, {
        maxBuffer: 10 * 1024 * 1024,
      });

      if (stderr) {
        console.error('Search dimension values stderr:', stderr);
      }

      return JSON.parse(stdout);
    } catch (error: any) {
      console.error('Search dimension values error:', error);
      return {
        error: error.message,
        stderr: error.stderr,
      };
    }
  }
}
