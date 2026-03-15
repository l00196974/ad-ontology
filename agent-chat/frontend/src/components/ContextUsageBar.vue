<template>
  <div class="ctx-bar" v-if="usage">
    <!-- 主进度条行 -->
    <div class="ctx-bar-row">
      <div class="ctx-label">CTX</div>
      <div class="ctx-track" @mouseenter="showBreakdown = true" @mouseleave="showBreakdown = false">
        <div
          class="ctx-fill"
          :class="tierClass"
          :style="{ width: Math.min(percentage, 100) + '%' }"
        ></div>
        <!-- Breakdown tooltip -->
        <div v-if="showBreakdown" class="ctx-tooltip">
          <div class="tooltip-row">
            <span class="tooltip-label">系统提示</span>
            <span class="tooltip-val">{{ usage.breakdown.systemPrompt.toLocaleString() }} tk</span>
          </div>
          <div class="tooltip-row">
            <span class="tooltip-label">对话历史</span>
            <span class="tooltip-val">{{ usage.breakdown.conversation.toLocaleString() }} tk</span>
          </div>
          <div class="tooltip-row">
            <span class="tooltip-label">工具结果</span>
            <span class="tooltip-val">{{ usage.breakdown.toolResults.toLocaleString() }} tk</span>
          </div>
          <div class="tooltip-row">
            <span class="tooltip-label">技能文档</span>
            <span class="tooltip-val">{{ usage.breakdown.skillDocs.toLocaleString() }} tk</span>
          </div>
          <div class="tooltip-sep"></div>
          <div class="tooltip-row tooltip-total">
            <span class="tooltip-label">合计</span>
            <span class="tooltip-val">{{ usage.used.toLocaleString() }} / {{ usage.total.toLocaleString() }}</span>
          </div>
        </div>
      </div>
      <div class="ctx-pct" :class="tierClass">{{ percentage.toFixed(1) }}%</div>
      <button
        v-if="showCompactBtn"
        class="ctx-compact-btn"
        :class="{ 'is-loading': compacting }"
        :disabled="compacting"
        @click="$emit('compact')"
        title="压缩上下文"
      >
        <span v-if="!compacting">⚡ COMPACT</span>
        <span v-else class="compact-loading">压缩中...</span>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';

interface ContextUsage {
  used: number;
  total: number;
  percentage: number;
  breakdown: {
    systemPrompt: number;
    conversation: number;
    toolResults: number;
    skillDocs: number;
  };
}

const props = defineProps<{
  usage: ContextUsage | null;
  compacting?: boolean;
}>();

defineEmits<{
  (e: 'compact'): void;
}>();

const showBreakdown = ref(false);

const percentage = computed(() => {
  if (!props.usage) return 0;
  return Math.round(props.usage.percentage * 1000) / 10;
});

const tierClass = computed(() => {
  const pct = percentage.value;
  if (pct >= 95) return 'tier-critical';
  if (pct >= 80) return 'tier-high';
  if (pct >= 60) return 'tier-medium';
  return 'tier-low';
});

const showCompactBtn = computed(() => percentage.value > 40);
</script>

<style scoped>
.ctx-bar {
  padding: 4px 0 2px;
}

.ctx-bar-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.ctx-label {
  font-family: var(--font-display);
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.12em;
  color: var(--text-tertiary);
  flex-shrink: 0;
  width: 24px;
}

.ctx-track {
  flex: 1;
  height: 6px;
  background: rgba(255, 255, 255, 0.06);
  border-radius: 3px;
  overflow: visible;
  position: relative;
  cursor: default;
}

.ctx-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.4s ease, background-color 0.3s ease;
}

.ctx-fill.tier-low {
  background: var(--accent-green, #00ff88);
  box-shadow: 0 0 6px rgba(0, 255, 136, 0.4);
}

.ctx-fill.tier-medium {
  background: var(--accent-yellow, #ffd700);
  box-shadow: 0 0 6px rgba(255, 215, 0, 0.4);
}

.ctx-fill.tier-high {
  background: #ff8c42;
  box-shadow: 0 0 6px rgba(255, 140, 66, 0.5);
  animation: pulseHighCtx 1.5s ease-in-out infinite;
}

.ctx-fill.tier-critical {
  background: var(--accent-magenta, #ff006e);
  box-shadow: 0 0 8px rgba(255, 0, 110, 0.6);
  animation: pulseCritical 0.8s ease-in-out infinite;
}

@keyframes pulseHighCtx {
  0%, 100% { box-shadow: 0 0 6px rgba(255, 140, 66, 0.5); }
  50% { box-shadow: 0 0 12px rgba(255, 140, 66, 0.8); }
}

@keyframes pulseCritical {
  0%, 100% { box-shadow: 0 0 8px rgba(255, 0, 110, 0.6); }
  50% { box-shadow: 0 0 16px rgba(255, 0, 110, 0.9); }
}

.ctx-pct {
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 600;
  flex-shrink: 0;
  width: 40px;
  text-align: right;
}

.ctx-pct.tier-low { color: var(--accent-green, #00ff88); }
.ctx-pct.tier-medium { color: var(--accent-yellow, #ffd700); }
.ctx-pct.tier-high { color: #ff8c42; }
.ctx-pct.tier-critical { color: var(--accent-magenta, #ff006e); }

/* Compact button */
.ctx-compact-btn {
  flex-shrink: 0;
  padding: 2px 8px;
  border: 1px solid var(--border-glow-cyan);
  border-radius: 10px;
  background: rgba(0, 217, 255, 0.06);
  color: var(--accent-cyan, #00d9ff);
  font-family: var(--font-display);
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.08em;
  cursor: pointer;
  transition: all 0.2s ease;
  white-space: nowrap;
}

.ctx-compact-btn:hover:not(:disabled) {
  background: rgba(0, 217, 255, 0.14);
  box-shadow: 0 0 8px rgba(0, 217, 255, 0.3);
}

.ctx-compact-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.compact-loading {
  font-family: var(--font-mono);
  animation: blinkText 1s ease-in-out infinite;
}

@keyframes blinkText {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

/* Tooltip */
.ctx-tooltip {
  position: absolute;
  bottom: calc(100% + 10px);
  left: 50%;
  transform: translateX(-50%);
  background: var(--bg-deep, #0a1128);
  border: 1px solid var(--border-medium);
  border-radius: 8px;
  padding: 10px 12px;
  z-index: 1000;
  white-space: nowrap;
  min-width: 200px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.5);
}

.tooltip-row {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 4px;
}

.tooltip-row:last-child { margin-bottom: 0; }

.tooltip-label {
  font-size: 11px;
  color: var(--text-secondary);
}

.tooltip-val {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-primary);
}

.tooltip-sep {
  height: 1px;
  background: var(--border-subtle);
  margin: 6px 0;
}

.tooltip-total .tooltip-label,
.tooltip-total .tooltip-val {
  font-weight: 600;
  color: var(--accent-cyan, #00d9ff);
}
</style>
