<template>
  <el-container class="home-layout">
    <!-- 左侧边栏 -->
    <el-aside width="260px">
      <AppSidebar />
    </el-aside>

    <!-- 主内容区 -->
    <el-main class="main-area">
      <div class="chat-header">
        <span class="chat-title">
          {{ chatStore.currentSessionId ? '对话' : '选择或新建对话开始' }}
        </span>
        <div class="header-actions">
          <el-button
            v-if="structuredResult"
            type="primary"
            text
            :icon="View"
            @click="drawerVisible = true"
          >
            查看结果
          </el-button>
        </div>
      </div>

      <!-- 聊天窗口 -->
      <ChatWindow />

      <!-- 输入框 -->
      <ChatInput />
    </el-main>

    <!-- 结果抽屉 -->
    <ResultDrawer v-model="drawerVisible" />

    <!-- 低置信度路由人工确认 -->
    <RouteConfirmDialog />
  </el-container>
</template>

<script setup>
import { ref, watch } from 'vue'
import { View } from '@element-plus/icons-vue'
import { useChatStore } from '@/stores/chat'
import AppSidebar from '@/components/AppSidebar.vue'
import ChatWindow from '@/components/chat/ChatWindow.vue'
import ChatInput from '@/components/chat/ChatInput.vue'
import ResultDrawer from '@/components/chat/ResultDrawer.vue'
import RouteConfirmDialog from '@/components/chat/RouteConfirmDialog.vue'

const chatStore = useChatStore()
const drawerVisible = ref(false)
const structuredResult = ref(null)

// 有新结构化结果时自动打开抽屉
watch(() => chatStore.structuredResult, (val) => {
  structuredResult.value = val
  if (val) drawerVisible.value = true
})
</script>

<style scoped>
.home-layout {
  height: 100vh;
  overflow: hidden;
}

.main-area {
  display: flex;
  flex-direction: column;
  padding: 0;
  overflow: hidden;
  background: #fff;
}

.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 20px;
  border-bottom: 1px solid #e4e7ed;
  flex-shrink: 0;
}

.chat-title {
  font-size: 15px;
  font-weight: 500;
  color: #303133;
}
</style>
