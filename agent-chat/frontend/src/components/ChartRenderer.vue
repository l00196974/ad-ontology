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
        <el-select v-model="currentChartType" @change="updateChartType" size="small">
          <el-option label="折线图" value="line" />
          <el-option label="柱状图" value="bar" />
          <el-option label="饼图" value="pie" />
          <el-option label="散点图" value="scatter" />
        </el-select>
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
import { TrendCharts, Document } from '@element-plus/icons-vue'
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

const props = defineProps<Props>()

const viewMode = ref<'chart' | 'json'>('chart')
const currentChartType = ref('line')

// 计算属性：格式化的 JSON 字符串
const jsonString = computed(() => {
  if (!props.chartData) return ''
  return JSON.stringify(props.chartData, null, 2)
})

// 计算属性：ECharts 配置
const chartOption = computed(() => {
  if (!props.chartData) return {}

  let option = { ...props.chartData }

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

  // 如果有 dataset，更新 series 的图表类型
  if (option.dataset && option.series) {
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

// 监听 chartData 变化，自动检测图表类型
watch(() => props.chartData, (newData) => {
  if (newData && newData.series && newData.series[0]) {
    currentChartType.value = newData.series[0].type || 'line'
  }
}, { immediate: true })

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
}

.chart-type-selector {
  display: flex;
  align-items: center;
  gap: 8px;
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