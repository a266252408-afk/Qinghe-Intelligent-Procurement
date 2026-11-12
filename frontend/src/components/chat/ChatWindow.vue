<template>
  <div class="chat-window" ref="scrollEl">
    <div v-if="chatStore.messages.length === 0" class="empty-state">
      <el-icon size="48" color="#c0c4cc"><ChatDotRound /></el-icon>
      <p>发送消息开始对话</p>
      <p class="hint">支持斜杠命令：/比价、/询价、/知识、/历史</p>
    </div>

    <MessageBubble
      v-for="(msg, idx) in chatStore.messages"
      :key="idx"
      :message="msg"
    />

    <!-- 流式加载指示 -->
    <div v-if="chatStore.isStreaming" class="streaming-indicator">
      <span class="dot" /><span class="dot" /><span class="dot" />
    </div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue'
import { useChatStore } from '@/stores/chat'
import MessageBubble from './MessageBubble.vue'

const chatStore = useChatStore()
const scrollEl = ref(null)

// 新消息时自动滚到底部
watch(
  () => chatStore.messages.length,
  () => nextTick(() => {
    if (scrollEl.value) scrollEl.value.scrollTop = scrollEl.value.scrollHeight
  }),
)

// 流式内容更新时也滚底
watch(
  () => chatStore.messages[chatStore.messages.length - 1]?.content,
  () => nextTick(() => {
    if (scrollEl.value) scrollEl.value.scrollTop = scrollEl.value.scrollHeight
  }),
)
</script>

<style scoped>
.chat-window {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.empty-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: #c0c4cc;
  font-size: 14px;
}

.hint {
  font-size: 12px;
  color: #dcdfe6;
}

.streaming-indicator {
  display: flex;
  gap: 4px;
  padding: 4px 12px;
}

.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #c0c4cc;
  animation: bounce 1.2s infinite;
}

.dot:nth-child(2) { animation-delay: 0.2s; }
.dot:nth-child(3) { animation-delay: 0.4s; }

@keyframes bounce {
  0%, 80%, 100% { transform: scale(0.8); opacity: 0.5; }
  40% { transform: scale(1.2); opacity: 1; }
}
</style>
