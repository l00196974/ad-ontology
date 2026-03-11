import { BaseSkill } from './base';
import { exec } from 'child_process';
import { promisify } from 'util';
import path from 'path';

const execAsync = promisify(exec);

export class MetricExtractorSkill extends BaseSkill {
  name = 'query_metrics';
  description = '查询华为广告指标数据，支持点击量、转化率、消耗等56个指标，可按时间、推广对象、计费方式等维度筛选';

  input_schema = {
    type: 'object' as const,
    properties: {
      metrics: {
        type: 'array',
        items: { type: 'string' },
        description: '要查询的指标列表，如：["点击量", "转化率", "实收点击流水"]',
      },
      start_date: {
        type: 'string',
        description: '开始日期，格式：YYYY-MM-DD',
      },
      end_date: {
        type: 'string',
        description: '结束日期，格式：YYYY-MM-DD',
      },
      dimensions: {
        type: 'array',
        items: { type: 'string' },
        description: '维度列表，如：["请求时间", "计费方式"]',
      },
      filters: {
        type: 'object',
        description: '过滤条件，如：{"推广对象": "问界M7"}',
      },
      format: {
        type: 'string',
        enum: ['default', 'echarts_dataset'],
        description: '输出格式：default（默认格式）或 echarts_dataset（ECharts数据集格式）',
      },
    },
    required: ['metrics', 'start_date', 'end_date'],
  };

  async execute(args: Record<string, any>): Promise<any> {
    const { metrics, start_date, end_date, dimensions = [], filters = {}, format = 'default' } = args;

    const skillPath = path.resolve(__dirname, '../../../../skills/metric-data-extractor');
    const metricsStr = Array.isArray(metrics) ? metrics.join(',') : metrics;
    const dimensionsStr = Array.isArray(dimensions) && dimensions.length > 0 ? dimensions.join(',') : '';
    const filtersStr = JSON.stringify(filters);

    // 构建命令，只在有dimensions时才添加--dimensions参数
    let command = `cd "${skillPath}" && node bin/query-metrics.js --metrics "${metricsStr}" --start-date "${start_date}" --end-date "${end_date}"`;

    if (dimensionsStr) {
      command += ` --dimensions "${dimensionsStr}"`;
    }

    command += ` --filters '${filtersStr}' --mock`;

    // 如果需要 ECharts Dataset 格式，添加格式参数
    if (format === 'echarts_dataset') {
      command += ` --format echarts_dataset`;
    }

    console.log('Executing command:', command);

    try {
      const { stdout, stderr } = await execAsync(command, {
        maxBuffer: 10 * 1024 * 1024, // 10MB
      });

      if (stderr) {
        console.error('Metric extractor stderr:', stderr);
      }

      const result = JSON.parse(stdout);

      // 如果请求 ECharts Dataset 格式但工具不支持，则在这里转换
      if (format === 'echarts_dataset' && !result.dataset) {
        return this.convertToEChartsDataset(result, dimensions, metrics);
      }

      return result;
    } catch (error: any) {
      console.error('Metric extractor error:', error);
      return {
        error: error.message,
        stderr: error.stderr,
      };
    }
  }

  // 将默认格式转换为 ECharts Dataset 格式
  private convertToEChartsDataset(data: any, dimensions: string[], metrics: string[]): any {
    if (!data.data || !Array.isArray(data.data)) {
      return data;
    }

    // 构建列名：维度 + 指标
    const columns = [...dimensions, ...metrics];

    // 构建数据源：第一行是列名，后续行是数据
    const source: any[][] = [columns];

    data.data.forEach((row: any) => {
      const dataRow: any[] = [];
      // 添加维度值
      dimensions.forEach(dim => {
        dataRow.push(row[dim] || '');
      });
      // 添加指标值
      metrics.forEach(metric => {
        dataRow.push(row[metric] || 0);
      });
      source.push(dataRow);
    });

    return {
      ...data,
      dataset: {
        source: source
      },
      // 保留原始数据以备需要
      originalData: data.data
    };
  }
}
