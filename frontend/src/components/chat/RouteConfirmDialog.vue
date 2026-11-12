<template>
  <el-dialog
    v-model="visible"
    title="需要确认路由"
    width="720px"
    :close-on-click-modal="false"
    :close-on-press-escape="false"
    append-to-body
    class="route-confirm-dialog"
  >
    <div v-if="pending" class="route-confirm">
      <el-alert
        type="warning"
        :closable="false"
        show-icon
        title="这条消息的意图不够明确，请选择要执行的操作"
      >
        <template #default>
          <div class="summary-line">消息：{{ pending.message }}</div>
          <div class="summary-line">
            {{ sourceLabel }} 判断：{{ topLabel }} · 置信度 {{ percent(pending.confidence) }} ·
            阈值 {{ percent(pending.threshold) }} · Top1-Top2 差距 {{ gapText }}
          </div>
        </template>
      </el-alert>

      <el-radio-group v-model="selected" class="option-list">
        <label
          v-for="(option, index) in pending.options"
          :key="option.intent"
          class="option-card"
          :class="{ 'is-selected': selected === option.intent }"
        >
          <el-radio :label="option.intent" class="option-radio">
            <div class="option-head">
              <span class="option-title">{{ option.label }}</span>
              <el-tag v-if="option.intent === pending.jev_intent" type="primary" size="small">
                {{ isJevSource ? 'JEV 首选' : '模型首选' }}
              </el-tag>
              <el-tag
                :type="option.executable ? 'success' : 'info'"
                size="small"
                effect="plain"
              >
                {{ option.executable ? '可直接执行' : '会转提示/普通对话' }}
              </el-tag>
            </div>
            <div class="option-desc">{{ option.description }}</div>
            <div v-if="option.note" class="option-note">{{ option.note }}</div>
            <div class="probability-row">
              <div class="probability-track">
                <div
                  class="probability-fill"
                  :style="{ width: `${Math.max(0, Math.min(1, option.probability)) * 100}%` }"
                />
              </div>
              <span class="probability-text">{{ percent(option.probability) }}</span>
            </div>
          </el-radio>
        </label>
      </el-radio-group>
    </div>

    <template #footer>
      <el-button :disabled="submitting" @click="handleCancel">
        取消（按普通对话继续）
      </el-button>
      <el-button
        type="primary"
        :disabled="!selected || submitting"
        :loading="submitting"
        @click="handleConfirm"
      >
        按所选执行
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useChatStore } from '@/stores/chat'

const chatStore = useChatStore()
const selected = ref(null)
const submitting = ref(false)
let actionTaken = false

const pending = computed(() => chatStore.pendingRouteConfirm)

const visible = computed({
  get: () => Boolean(pending.value),
  set: (value) => {
    if (!value && pending.value) handleCancel()
  },
})

// 旧待确认 payload 没有 source 字段，按 JEV 展示
const isJevSource = computed(() => (
  !pending.value?.source || pending.value.source === 'jev'
))

const sourceLabel = computed(() => (isJevSource.value ? 'JEV' : '备用模型'))

const topLabel = computed(() => {
  const options = pending.value?.options || []
  return options[0]?.label || '未知'
})

const gapText = computed(() => {
  const options = pending.value?.options || []
  if (options.length < 2) return '—'
  if (!options.some((option) => Number(option.probability) > 0)) return '—'
  return percent(Math.max(0, options[0].probability - options[1].probability))
})

watch(
  () => pending.value?.token,
  (token) => {
    // 新一条待确认消息到达时重置选择状态
    if (token) {
      selected.value = null
      submitting.value = false
      actionTaken = false
    }
  },
  { immediate: true },
)

function percent(value) {
  const num = Number(value)
  if (Number.isNaN(num)) return '—'
  return `${(num * 100).toFixed(1)}%`
}

async function handleConfirm() {
  if (!selected.value || submitting.value) return
  actionTaken = true
  submitting.value = true
  try {
    await chatStore.resolveRouteChoice(selected.value)
  } finally {
    submitting.value = false
  }
}

async function handleCancel() {
  if (actionTaken || !pending.value) return
  actionTaken = true
  await chatStore.resolveRouteChoice('chat', true)
}
</script>

<style scoped>
/* 小屏下限制内容区高度，保证底部操作按钮始终可见（弹窗被 teleport 到 body，需用全局选择器） */
:global(.route-confirm-dialog .el-dialog__body) {
  max-height: calc(100vh - 280px);
  overflow-y: auto;
}

.route-confirm :deep(.el-alert__content) {
  width: 100%;
}

.summary-line {
  margin-top: 4px;
  color: #606266;
  font-size: 13px;
  line-height: 1.6;
}

.option-list {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  flex-wrap: nowrap;
  gap: 12px;
  margin-top: 20px;
  width: 100%;
}

.option-card {
  display: block;
  box-sizing: border-box;
  width: 100%;
  padding: 14px 16px;
  border: 1px solid #e4e7ed;
  border-radius: 10px;
  cursor: pointer;
  transition: border-color 0.15s, background-color 0.15s, box-shadow 0.15s;
}

.option-card:hover {
  border-color: #a0cfff;
  background: #fafcff;
}

.option-card.is-selected {
  border-color: #409eff;
  background: #f2f8ff;
  box-shadow: 0 0 0 1px rgba(64, 158, 255, 0.16);
}

/* Element Plus 的 el-radio 默认固定 height: 32px 且 nowrap，会压塌多行内容 */
.option-radio {
  display: flex;
  align-items: flex-start;
  width: 100%;
  height: auto;
  margin-right: 0;
  white-space: normal;
}

.option-radio :deep(.el-radio__input) {
  margin-top: 3px;
  flex-shrink: 0;
}

.option-radio :deep(.el-radio__label) {
  display: block;
  flex: 1;
  min-width: 0;
  padding-left: 10px;
  font-size: 14px;
  line-height: 1.5;
  white-space: normal;
}

.option-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.option-head :deep(.el-tag) {
  flex-shrink: 0;
}

.option-title {
  color: #303133;
  font-size: 15px;
  font-weight: 600;
  line-height: 22px;
}

.option-desc {
  margin-top: 6px;
  color: #606266;
  font-size: 13px;
  line-height: 1.6;
}

.option-note {
  margin-top: 6px;
  color: #e6a23c;
  font-size: 12px;
  line-height: 1.5;
}

.probability-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 10px;
}

.probability-track {
  flex: 1;
  height: 6px;
  border-radius: 3px;
  background: #ebeef5;
  overflow: hidden;
}

.probability-fill {
  height: 100%;
  border-radius: 3px;
  background: #409eff;
  transition: width 0.3s ease;
}

.probability-text {
  flex: 0 0 52px;
  text-align: right;
  color: #909399;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}
</style>
