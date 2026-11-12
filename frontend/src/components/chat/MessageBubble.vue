<template>
  <div class="message-bubble" :class="message.role">
    <!-- 用户消息 -->
    <template v-if="message.role === 'user'">
      <div class="bubble user-bubble">
        <div v-if="message.metadata?.file_name" class="attachment-name">
          <el-icon><Document /></el-icon>
          <span>{{ message.metadata.file_name }}</span>
        </div>
        <div v-if="message.content">{{ message.content }}</div>
      </div>
      <el-avatar :size="28" icon="UserFilled" class="avatar" />
    </template>

    <!-- AI 消息 -->
    <template v-else>
      <el-avatar :size="28" class="avatar bot-avatar">
        <el-icon><Tree /></el-icon>
      </el-avatar>
      <div class="bubble assistant-bubble">
        <!-- markdown-it 渲染，流式时显示光标 -->
        <div
          class="md-content"
          v-html="renderedContent"
        />
        <span v-if="message.streaming" class="cursor">▍</span>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import MarkdownIt from 'markdown-it'

const md = new MarkdownIt({ breaks: true, linkify: true })

const props = defineProps({
  message: { type: Object, required: true },
})

const renderedContent = computed(() => {
  if (props.message.role === 'assistant') {
    return md.render(props.message.content || '')
  }
  return ''
})
</script>

<style scoped>
.message-bubble {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  max-width: 85%;
}

.message-bubble.user {
  flex-direction: row-reverse;
  align-self: flex-end;
  max-width: 70%;
}

.message-bubble.assistant {
  align-self: flex-start;
}

.avatar {
  flex-shrink: 0;
  margin-top: 2px;
}

.bot-avatar {
  background: #409eff;
  color: white;
}

.bubble {
  padding: 10px 14px;
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.6;
  word-break: break-word;
}

.user-bubble {
  background: #409eff;
  color: white;
  border-bottom-right-radius: 4px;
}

.assistant-bubble {
  background: #f5f7fa;
  color: #303133;
  border-bottom-left-radius: 4px;
}

.attachment-name {
  display: flex;
  align-items: center;
  gap: 6px;
  max-width: 260px;
  margin-bottom: 4px;
  font-size: 13px;
  font-weight: 600;
  overflow-wrap: anywhere;
}

.md-content :deep(p) { margin: 0 0 6px; }
.md-content :deep(p:last-child) { margin-bottom: 0; }
.md-content :deep(ul), .md-content :deep(ol) { padding-left: 20px; }
.md-content :deep(code) {
  background: #e4e7ed;
  padding: 1px 4px;
  border-radius: 3px;
  font-size: 13px;
}
.md-content :deep(pre) {
  background: #2b2b2b;
  color: #f8f8f2;
  padding: 10px;
  border-radius: 6px;
  overflow-x: auto;
  font-size: 13px;
}

.cursor {
  animation: blink 1s step-end infinite;
  color: #409eff;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}
</style>
