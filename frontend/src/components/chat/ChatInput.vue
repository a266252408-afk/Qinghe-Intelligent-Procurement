<template>
  <div class="chat-input-area">
    <!-- 斜杠命令提示 -->
    <Transition name="slide-up">
      <div v-if="showSlashMenu" class="slash-menu">
        <div
          v-for="cmd in filteredCommands"
          :key="cmd.value"
          class="slash-item"
          @click="insertCommand(cmd)"
        >
          <span class="cmd-value">{{ cmd.value }}</span>
          <span class="cmd-desc">{{ cmd.desc }}</span>
        </div>
      </div>
    </Transition>

    <!-- 文件预览 -->
    <div v-if="attachedFile" class="file-preview">
      <el-icon><Document /></el-icon>
      <span>{{ attachedFile.name }}</span>
      <el-button text :icon="Close" size="small" @click="attachedFile = null" />
    </div>

    <!-- 输入行 -->
    <div class="input-row">
      <el-radio-group v-model="fileType" size="small" :disabled="inputDisabled">
        <el-radio-button label="list">采购清单</el-radio-button>
        <el-radio-button label="quote">供应商报价</el-radio-button>
      </el-radio-group>
      <!-- 文件上传按钮 -->
      <el-upload
        :show-file-list="false"
        :before-upload="handleFileSelect"
        accept=".xlsx,.xls,.csv,.txt"
      >
        <el-button text :icon="Paperclip" :disabled="inputDisabled" />
      </el-upload>

      <el-input
        ref="inputRef"
        v-model="inputText"
        type="textarea"
        :autosize="{ minRows: 1, maxRows: 6 }"
        placeholder="输入消息，/ 触发命令，Shift+Enter 换行..."
        resize="none"
        :disabled="inputDisabled"
        @keydown.enter.exact.prevent="handleSend"
        @input="checkSlashCommand"
      />

      <el-button
        type="primary"
        :icon="chatStore.isStreaming ? Loading : Promotion"
        :loading="chatStore.isStreaming"
        :disabled="inputDisabled || (!inputText.trim() && !attachedFile)"
        circle
        @click="handleSend"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { Close, Paperclip, Promotion, Loading } from '@element-plus/icons-vue'
import { useChatStore } from '@/stores/chat'
import { uploadChatFile } from '@/api/chat'

const chatStore = useChatStore()
const inputText = ref('')
const attachedFile = ref(null)
const fileType = ref('list')
const showSlashMenu = ref(false)
const inputRef = ref(null)
const inputDisabled = computed(
  () => chatStore.isStreaming || Boolean(chatStore.pendingRouteConfirm),
)

const SLASH_COMMANDS = [
  { value: '/比价', desc: '对已有报价单进行比价分析' },
  { value: '/询价', desc: '生成询价单 Excel' },
  { value: '/知识', desc: '查询行业知识库：规范、养护、验收' },
  { value: '/历史', desc: '查询团队长期材料价格记录' },
  { value: '/总结', desc: '总结本轮对话要点' },
]

const filteredCommands = computed(() => {
  const slashIdx = inputText.value.lastIndexOf('/')
  if (slashIdx === -1) return SLASH_COMMANDS
  const partial = inputText.value.slice(slashIdx)
  return SLASH_COMMANDS.filter((c) => c.value.startsWith(partial))
})

function checkSlashCommand() {
  showSlashMenu.value = inputText.value.includes('/') && !inputText.value.endsWith(' ')
}

function insertCommand(cmd) {
  const slashIdx = inputText.value.lastIndexOf('/')
  inputText.value = inputText.value.slice(0, slashIdx) + cmd.value + ' '
  showSlashMenu.value = false
  inputRef.value?.focus()
}

function handleFileSelect(file) {
  attachedFile.value = file
  return false  // 阻止 el-upload 自动上传
}

async function handleSend() {
  const text = inputText.value.trim()
  if (!text && !attachedFile.value) return
  if (inputDisabled.value) return

  if (!chatStore.currentSessionId) {
    ElMessage.warning('请先在左侧创建一个对话会话')
    return
  }

  inputText.value = ''
  showSlashMenu.value = false

  let fileInfo = null
  try {
    if (attachedFile.value) {
      const stored = await uploadChatFile(attachedFile.value, fileType.value)
      fileInfo = { file_id: stored.path, file_type: fileType.value, file_name: stored.original_name, upload_id: stored.upload_id }
    }
    await chatStore.sendMessage(text, fileInfo)
  } catch (error) {
    ElMessage.error(error.message || '文件处理失败')
  }

  attachedFile.value = null
}
</script>

<style scoped>
.chat-input-area {
  padding: 12px 16px 16px;
  border-top: 1px solid #e4e7ed;
  position: relative;
  flex-shrink: 0;
}

.slash-menu {
  position: absolute;
  bottom: 100%;
  left: 16px;
  right: 16px;
  background: white;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.1);
  overflow: hidden;
  z-index: 100;
}

.slash-item {
  display: flex;
  gap: 12px;
  padding: 8px 16px;
  cursor: pointer;
  transition: background 0.15s;
}

.slash-item:hover {
  background: #f5f7fa;
}

.cmd-value {
  font-weight: 600;
  color: #409eff;
  min-width: 60px;
  font-size: 13px;
}

.cmd-desc {
  color: #909399;
  font-size: 13px;
}

.file-preview {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  background: #f0f7ff;
  border-radius: 6px;
  margin-bottom: 8px;
  font-size: 13px;
  color: #409eff;
}

.input-row {
  display: flex;
  align-items: flex-end;
  gap: 8px;
}

.input-row .el-input {
  flex: 1;
}

.slide-up-enter-active,
.slide-up-leave-active {
  transition: all 0.15s ease;
}

.slide-up-enter-from,
.slide-up-leave-to {
  opacity: 0;
  transform: translateY(6px);
}
</style>
