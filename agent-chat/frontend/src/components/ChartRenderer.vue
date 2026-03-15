<template>
  <div class="chart-renderer">
    <!-- 图表控制栏 -->
    <div class="chart-controls" v-if="chartData">
      <el-button-group>
        <el-button
          :type="viewMode === 'chart' ? 'primary' : 'default'"
          @click="viewMode = 'chart'"
          :icon="TrendCharts"
        >
          图表视图
        </el-button>
        <el-button
          :type="viewMode === 'json' ? 'primary' : 'default'"
          @click="viewMode = 'json'"
          :icon="Document"
        >
          JSON配置
        </el-button>
      </el-button-group>

      <!-- 图表类型切换 -->
      <div class="chart-type-selector" v-if="viewMode === 'chart'">
        <span class="selector-label">图表类型：</span>
        <el-button-group>
          <el-button
            :type="currentChartType === 'line' ? 'primary' : 'default'"
            @click="updateChartType('line')"
            size="small"
          >
            📈 折线图
          </el-button>
          <el-button
            :type="currentChartType === 'bar' ? 'primary' : 'default'"
            @click="updateChartType('bar')"
            size="small"
          >
            📊 柱状图
          </el-button>
          <el-button
            :type="currentChartType === 'pie' ? 'primary' : 'default'"
            @click="updateChartType('pie')"
            size="small"
          >
            🥧 饼图
          </el-button>
          <el-button
            :type="currentChartType === 'scatter' ? 'primary' : 'default'"
            @click="updateChartType('scatter')"
            size="small"
          >
            ⚫ 散点图
          </el-button>
        </el-button-group>
      </div>

      <!-- 格式化配置按钮 -->
      <el-button
        v-if="viewMode === 'chart' && Object.keys(formatConfigs).length > 0"
        :icon="Setting"
        size="small"
        @click="showFormatPanel = !showFormatPanel"
      >
        数值格式
      </el-button>
    </div>

    <!-- 格式化配置面板 -->
    <div v-if="showFormatPanel && viewMode === 'chart'" class="format-panel glass">
      <div v-for="(config, dim) in formatConfigs" :key="dim" class="format-item">
        <span class="format-label">{{ dim }}：</span>
        <el-select v-model="config.unit" size="small" style="width: 110px; margin-right: 8px">
          <el-option label="自动" value="auto" />
          <el-option label="原始" value="none" />
          <el-option label="百分比(%)" value="percent" />
          <el-option label="千(K)" value="thousand" />
          <el-option label="万" value="tenThousand" />
          <el-option label="百万(M)" value="million" />
        </el-select>
        <span class="format-label">小数位：</span>
        <el-input-number
          v-model="config.decimals"
          :min="0"
          :max="4"
          size="small"
          style="width: 100px"
        />
      </div>
    </div>

    <!-- 图表渲染区域 -->
    <div v-if="chartData && viewMode === 'chart'" class="chart-container">
      <v-chart
        :option="chartOption"
        :style="{ height: '400px', width: '100%' }"
        autoresize
      />
    </div>

    <!-- JSON 配置显示 -->
    <div v-if="chartData && viewMode === 'json'" class="json-container">
      <el-input
        v-model="jsonString"
        type="textarea"
        :rows="15"
        readonly
        class="json-textarea"
      />
      <div class="json-actions">
        <el-button @click="copyToClipboard" size="small" type="primary">
          复制配置
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart, BarChart as BarChartType, PieChart, ScatterChart } from 'echarts/charts'
import {
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent,
  DatasetComponent
} from 'echarts/components'
import VChart from 'vue-echarts'
import { TrendCharts, Document, Setting } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

// 注册 ECharts 组件
use([
  CanvasRenderer,
  LineChart,
  BarChartType,
  PieChart,
  ScatterChart,
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent,
  DatasetComponent
])

interface Props {
  chartData?: any
}

interface FormatConfig {
  unit: 'auto' | 'none' | 'thousand' | 'tenThousand' | 'million' | 'percent'
  decimals: number
  actualUnit?: FormatConfig['unit']  // 记录 auto 模式下实际使用的单位
}

const props = defineProps<Props>()

const viewMode = ref<'chart' | 'json'>('chart')
const currentChartType = ref('line')
const showFormatPanel = ref(false)

// 数值格式化配置（按维度/指标名存储）
const formatConfigs = ref<Record<string, FormatConfig>>({})

// 自动检测合适的单位
function autoDetectUnit(values: number[]): FormatConfig['unit'] {
  const maxVal = Math.max(...values.filter(v => typeof v === 'number' && !isNaN(v)))
  const minVal = Math.min(...values.filter(v => typeof v === 'number' && !isNaN(v)))

  // 如果所有值都在 0-1 之间，可能是百分比
  if (maxVal <= 1 && minVal >= 0) return 'percent'

  if (maxVal >= 1000000) return 'million'
  if (maxVal >= 10000) return 'tenThousand'
  if (maxVal >= 1000) return 'thousand'
  return 'none'
}

// 格式化数值
function formatValue(value: any, config: FormatConfig): string {
  if (typeof value !== 'number' || isNaN(value)) return String(value)

  let divisor = 1
  let suffix = ''

  if (config.unit === 'auto') {
    // 自动选择单位
    if (value <= 1 && value >= 0) {
      // 百分比
      return (value * 100).toFixed(config.decimals) + '%'
    } else if (value >= 1000000) {
      divisor = 1000000
      suffix = 'M'
    } else if (value >= 10000) {
      divisor = 10000
      suffix = '万'
    } else if (value >= 1000) {
      divisor = 1000
      suffix = 'K'
    }
  } else if (config.unit === 'percent') {
    return (value * 100).toFixed(config.decimals) + '%'
  } else if (config.unit === 'million') {
    divisor = 1000000
    suffix = 'M'
  } else if (config.unit === 'tenThousand') {
    divisor = 10000
    suffix = '万'
  } else if (config.unit === 'thousand') {
    divisor = 1000
    suffix = 'K'
  }

  const formatted = (value / divisor).toFixed(config.decimals)
  return formatted + suffix
}

// 获取 dataset 中的所有数值维度
function getNumericDimensions(dataset: any): string[] {
  if (!dataset || !dataset.source || dataset.source.length < 2) return []

  const dimensions = dataset.dimensions || dataset.source[0]
  const firstDataRow = dataset.source[1]

  return dimensions.filter((_dim: string, idx: number) => {
    const val = firstDataRow[idx]
    return typeof val === 'number' && !isNaN(val)
  })
}

// 初始化格式化配置
function initFormatConfigs(dataset: any) {
  const numericDims = getNumericDimensions(dataset)

  numericDims.forEach(dim => {
    if (!formatConfigs.value[dim]) {
      // 提取该维度的所有数值
      const values = dataset.source.slice(1).map((row: any[]) => {
        const idx = dataset.dimensions ? dataset.dimensions.indexOf(dim) : dataset.source[0].indexOf(dim)
        return row[idx]
      }).filter((v: any) => typeof v === 'number')

      const detectedUnit = autoDetectUnit(values)
      formatConfigs.value[dim] = {
        unit: 'auto',
        actualUnit: detectedUnit,  // 记录实际检测到的单位
        decimals: detectedUnit === 'none' ? 0 : (detectedUnit === 'percent' ? 2 : 2)
      }
    }
  })
}

// 计算属性：格式化的 JSON 字符串
const jsonString = computed(() => {
  if (!props.chartData) return ''
  return JSON.stringify(props.chartData, null, 2)
})

// 计算属性：ECharts 配置
const chartOption = computed(() => {
  if (!props.chartData) return {}

  let option = { ...props.chartData }

  // 如果有 dataset，初始化格式化配置
  if (option.dataset) {
    initFormatConfigs(option.dataset)
  }

  // 递归处理函数字符串
  const processFunctions = (obj: any): any => {
    if (typeof obj === 'string' && obj.trim().startsWith('function')) {
      try {
        // 使用eval解析函数字符串
        return eval(`(${obj})`)
      } catch (e) {
        console.warn('Failed to parse function:', obj, e)
        return obj
      }
    } else if (Array.isArray(obj)) {
      return obj.map(processFunctions)
    } else if (obj && typeof obj === 'object') {
      const result: any = {}
      for (const [key, value] of Object.entries(obj)) {
        result[key] = processFunctions(value)
      }
      return result
    }
    return obj
  }

  // 处理所有可能包含函数的配置
  option = processFunctions(option)

  // 应用数值格式化到 dataset
  if (option.dataset && option.dataset.source) {
    const dimensions = option.dataset.dimensions || option.dataset.source[0]
    const formattedSource = option.dataset.source.map((row: any[], rowIdx: number) => {
      if (rowIdx === 0) return row // 保持表头不变
      return row.map((val: any, colIdx: number) => {
        const dim = dimensions[colIdx]
        const config = formatConfigs.value[dim]
        if (config && typeof val === 'number') {
          if (config.unit === 'percent') {
            // 百分比：乘以100后保留小数
            return parseFloat((val * 100).toFixed(config.decimals))
          } else {
            // 其他单位：除以除数后保留小数
            return parseFloat((val / getDivisor(config.unit)).toFixed(config.decimals))
          }
        }
        return val
      })
    })
    option.dataset.source = formattedSource
  }

  // 如果有 dataset 但没有 series，根据 dimensions 自动生成 series
  if (option.dataset && !option.series) {
    const dims: string[] = option.dataset.dimensions || []
    // 第一列作为 x 轴（category），其余列各生成一个 series
    const seriesDims = dims.slice(1)
    option.series = seriesDims.map((dim: string) => ({
      type: currentChartType.value,
      name: dim,
      encode: { x: dims[0], y: dim },
    }))
  }

  // 更新 series 的图表类型（无论是否有 dataset）
  if (option.series) {
    option.series = option.series.map((series: any) => ({
      ...series,
      type: currentChartType.value
    }))
  }

  // 确保有基本配置
  if (!option.tooltip) {
    option.tooltip = { trigger: 'axis' }
  }
  if (!option.legend) {
    option.legend = {}
  }

  // 自定义 tooltip 格式化器
  if (option.dataset) {
    option.tooltip.formatter = (params: any) => {
      if (!Array.isArray(params)) params = [params]
      let result = `${params[0].axisValue}<br/>`
      params.forEach((param: any) => {
        const dim = param.seriesName
        const config = formatConfigs.value[dim]
        if (config) {
          const suffix = getUnitSuffix(config.unit, config.actualUnit)
          result += `${param.marker} ${param.seriesName}: ${param.value[param.encode.y[0]]}${suffix}<br/>`
        } else {
          result += `${param.marker} ${param.seriesName}: ${param.value[param.encode.y[0]]}<br/>`
        }
      })
      return result
    }
  }

  // Y轴格式化
  if (option.yAxis && option.dataset) {
    const numericDims = getNumericDimensions(option.dataset)
    if (numericDims.length > 0) {
      const firstDim = numericDims[0]
      const config = formatConfigs.value[firstDim]
      if (config) {
        const suffix = getUnitSuffix(config.unit, config.actualUnit)
        option.yAxis.axisLabel = {
          formatter: (value: number) => value + suffix
        }
        // 添加 Y轴名称显示单位
        if (suffix && !option.yAxis.name) {
          option.yAxis.name = firstDim + ' (' + suffix + ')'
        }
      }
    }
  }

  // 饼图特殊处理
  if (currentChartType.value === 'pie') {
    option.tooltip.trigger = 'item'
    // 如果是 dataset 格式，需要特殊处理饼图
    if (option.dataset && option.dataset.source) {
      const source = option.dataset.source
      if (source.length > 1) {
        const data = source.slice(1)

        option.series = [{
          type: 'pie',
          data: data.map((row: any[]) => ({
            name: row[0],
            value: row[1]
          }))
        }]
        // 饼图不需要 xAxis 和 yAxis
        delete option.xAxis
        delete option.yAxis
        delete option.dataset
      }
    }
  } else {
    // 非饼图确保有坐标轴
    if (!option.xAxis) {
      option.xAxis = { type: 'category' }
    }
    if (!option.yAxis) {
      option.yAxis = { type: 'value' }
    }
  }

  return option
})

// 辅助函数：获取单位除数
function getDivisor(unit: FormatConfig['unit']): number {
  switch (unit) {
    case 'million': return 1000000
    case 'tenThousand': return 10000
    case 'thousand': return 1000
    default: return 1
  }
}

// 辅助函数：获取单位后缀（考虑 auto 模式）
function getUnitSuffix(unit: FormatConfig['unit'], autoUnit?: FormatConfig['unit']): string {
  // 如果是 auto 模式，使用实际检测到的单位
  const actualUnit = unit === 'auto' ? autoUnit : unit

  switch (actualUnit) {
    case 'million': return 'M'
    case 'tenThousand': return '万'
    case 'thousand': return 'K'
    case 'percent': return '%'
    default: return ''
  }
}

// 监听 chartData 变化，自动检测图表类型
watch(() => props.chartData, (newData) => {
  if (newData && newData.series && newData.series[0]) {
    currentChartType.value = newData.series[0].type || 'line'
  } else {
    // 如果没有 series（dataset 模式），保持当前类型或默认 line
    // 不重置，避免覆盖用户手动切换的类型
  }
}, { immediate: true, flush: 'sync' })

// 监听格式配置变化，更新 actualUnit
watch(formatConfigs, (configs) => {
  Object.keys(configs).forEach(dim => {
    const config = configs[dim]
    // 当用户手动选择单位时，更新 actualUnit
    if (config.unit !== 'auto') {
      config.actualUnit = config.unit
    }
  })
}, { deep: true })

// 更新图表类型
const updateChartType = (type: string) => {
  currentChartType.value = type
}

// 复制到剪贴板
const copyToClipboard = async () => {
  try {
    await navigator.clipboard.writeText(jsonString.value)
    ElMessage.success('配置已复制到剪贴板')
  } catch (err) {
    ElMessage.error('复制失败')
  }
}
</script>

<style scoped>
.chart-renderer {
  border: 1px solid var(--border-subtle, #e4e7ed);
  border-radius: var(--radius-lg, 12px);
  overflow: hidden;
  margin: 8px 0;
  background: var(--bg-surface, #0d1b2a);
}

.chart-controls {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 16px;
  background: var(--bg-elevated, #1b263b);
  border-bottom: 1px solid var(--border-subtle, #e4e7ed);
  gap: 12px;
  flex-wrap: wrap;
}

.format-panel {
  padding: 12px 16px;
  background: var(--bg-elevated, #1b263b);
  border-bottom: 1px solid var(--border-subtle, #e4e7ed);
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.format-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.format-label {
  font-size: 12px;
  color: var(--text-secondary, #8b95a5);
  font-weight: 500;
  white-space: nowrap;
}

.chart-type-selector {
  display: flex;
  align-items: center;
  gap: 8px;
}

.selector-label {
  font-size: 12px;
  color: var(--text-secondary, #8b95a5);
  font-weight: 500;
  white-space: nowrap;
}

.chart-container {
  padding: 16px;
  background: var(--bg-surface, #0d1b2a);
}

.json-container {
  padding: 16px;
  background: var(--bg-deep, #0a1128);
}

.json-textarea {
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  font-size: 12px;
}

.json-actions {
  margin-top: 12px;
  text-align: right;
}

:deep(.el-textarea__inner) {
  font-family: var(--font-mono, 'Monaco', 'Menlo', monospace);
  font-size: 12px;
  line-height: 1.4;
  background: var(--bg-void, #050a12);
  color: var(--accent-green, #06ffa5);
  border-color: var(--border-subtle, #1e2a3a);
}

:deep(.el-button) {
  font-family: var(--font-display, monospace);
  letter-spacing: 0.04em;
}

:deep(.el-select .el-input__wrapper) {
  background: var(--bg-elevated, #1b263b);
  border-color: var(--border-medium, #2a3b5a);
}

:deep(.el-select .el-input__inner) {
  color: var(--text-primary, #e8f1f5);
  font-size: 12px;
}
</style>