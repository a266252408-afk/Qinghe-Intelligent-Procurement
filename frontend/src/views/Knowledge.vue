<template>
  <div class="page-layout">
    <div class="page-header">
      <div class="header-title"><el-button text :icon="ArrowLeft" title="返回上一页" @click="$router.back()" /><h2>知识库</h2></div>
    </div>

    <el-tabs v-model="activeTab">
      <!-- 搜索 -->
      <el-tab-pane label="检索" name="search">
        <div class="search-area">
          <el-input
            v-model="query"
            placeholder="输入园林工程问题或关键词检索行业知识..."
            size="large"
            :suffix-icon="Search"
            clearable
            @keyup.enter="handleSearch"
          />
          <el-button type="primary" size="large" @click="handleSearch" :loading="searching">搜索</el-button>
        </div>

        <el-card v-if="searched && answer" class="answer-card" shadow="never">
          <div class="answer-header">
            <span class="answer-title">知识库整理回答</span>
            <el-tag size="small" type="success">严格依据检索内容</el-tag>
          </div>
          <div class="answer-content" v-html="answerHtml"></div>
        </el-card>

        <div v-if="results.length > 0" class="evidence-title">检索依据</div>
        <div v-if="results.length > 0" class="result-list">
          <el-card
            v-for="(r, idx) in results"
            :key="idx"
            class="result-card"
            shadow="hover"
          >
            <div class="result-header">
              <el-tag size="small" type="primary">行业知识</el-tag>
              <div class="result-meta">
                <span v-if="r.source_file" class="source-file">{{ r.source_file }}</span>
                <span class="score">相关度 {{ (r.score * 100).toFixed(0) }}%</span>
              </div>
            </div>
            <p class="result-content">{{ r.content }}</p>
          </el-card>
        </div>

        <div v-else-if="searched && !answer && results.length === 0" class="empty-hint">
          未找到相关结果
        </div>
      </el-tab-pane>

      <!-- 上传行业知识 -->
      <el-tab-pane v-if="authStore.role === 'owner'" label="上传行业文档" name="upload">
        <div class="upload-area">
          <el-upload
            drag
            :before-upload="handleUpload"
            :show-file-list="false"
            accept=".txt,.pdf,.xlsx,.md"
          >
            <el-icon size="48" color="#c0c4cc"><Upload /></el-icon>
            <div class="upload-text">
              <p>拖拽文件到此处，或<em>点击上传</em></p>
              <p class="upload-hint">支持 .txt / .pdf / .xlsx / .md，用于行业认知库</p>
            </div>
          </el-upload>

          <div v-if="uploadTasks.length > 0" class="upload-task-list">
            <el-card v-for="task in uploadTasks" :key="task.id" class="upload-task" shadow="never">
              <div class="task-header">
                <span class="task-name">{{ task.name }}</span>
                <el-tag v-if="task.status === 'success'" type="success" size="small">上传成功</el-tag>
                <el-tag v-else-if="task.status === 'error'" type="danger" size="small">上传失败</el-tag>
                <el-tag v-else type="warning" size="small">{{ task.status === 'processing' ? '处理中' : '上传中' }}</el-tag>
              </div>
              <el-progress
                :percentage="task.progress"
                :status="task.status === 'success' ? 'success' : task.status === 'error' ? 'exception' : undefined"
                :indeterminate="task.status === 'processing' || !task.progressKnown"
                :duration="2"
              />
              <div class="task-message" :class="{ 'task-error': task.status === 'error' }">
                {{ task.message }}
              </div>
            </el-card>
          </div>

          <!-- 已上传文档清单：来自知识库持久化记录，刷新后仍在 -->
          <el-card class="doc-list-card" shadow="never" v-loading="docsLoading">
            <template #header>
              <div class="doc-list-header">
                <span>已上传文档</span>
                <el-tag size="small">{{ industryDocs.length }} 份</el-tag>
              </div>
            </template>
            <el-table :data="industryDocs" border size="small">
              <el-table-column type="index" label="序号" width="70" />
              <el-table-column prop="source_file" label="文件名" min-width="280" show-overflow-tooltip />
              <el-table-column prop="chunks" label="知识分块数" width="120" align="center" />
            </el-table>
            <el-empty v-if="!docsLoading && industryDocs.length === 0" description="暂无已上传的行业文档" :image-size="72" />
          </el-card>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { computed, reactive, ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { ArrowLeft, Search, Upload } from '@element-plus/icons-vue'
import MarkdownIt from 'markdown-it'
import { knowledgeApi } from '@/api/knowledge'
import { useAuthStore } from '@/stores/auth'

const activeTab = ref('search')
const query = ref('')
const answer = ref('')
const results = ref([])
const searched = ref(false)
const searching = ref(false)
const uploadTasks = ref([])
const industryDocs = ref([])
const docsLoading = ref(false)
const authStore = useAuthStore()
const markdown = new MarkdownIt({ html: false, breaks: true, linkify: false })
const answerHtml = computed(() => markdown.render(answer.value))

onMounted(() => {
  // 认证信息刷新失败时由请求拦截器统一处理，避免产生未捕获 Promise 异常。
  authStore.refresh().catch(() => {})
  if (authStore.role === 'owner') loadIndustryDocs()
})

async function loadIndustryDocs() {
  docsLoading.value = true
  try { industryDocs.value = await knowledgeApi.listIndustryDocs() } finally { docsLoading.value = false }
}

async function handleSearch() {
  if (!query.value.trim()) return
  searching.value = true
  searched.value = true
  answer.value = ''
  results.value = []
  try {
    const data = await knowledgeApi.search(query.value.trim())
    answer.value = data?.answer || ''
    results.value = Array.isArray(data) ? data : (data?.results ?? [])
  } catch {
    answer.value = ''
    results.value = []
  } finally {
    searching.value = false
  }
}

async function handleUpload(file) {
  // 使用 reactive 保留插入列表后的响应式引用，确保上传回调能实时驱动进度条。
  const task = reactive({
    id: `${Date.now()}-${file.uid || file.name}`,
    name: file.name,
    progress: 0,
    progressKnown: false,
    status: 'uploading',
    message: '正在上传文件...',
  })
  uploadTasks.value.unshift(task)
  const formData = new FormData()
  formData.append('file', file)
  try {
    const data = await knowledgeApi.uploadIndustry(formData, (event) => {
      if (!event.total) return
      task.progressKnown = true
      const percent = Math.round((event.loaded / event.total) * 100)
      task.progress = Math.min(99, percent)
      task.status = percent >= 100 ? 'processing' : 'uploading'
      task.message = percent >= 100 ? '文件已上传，正在解析、清洗并写入向量库...' : `文件上传中（${task.progress}%）...`
    })
    task.progress = 100
    task.status = 'success'
    task.message = `已完成解析并写入知识库，共生成 ${data?.chunks ?? 0} 个知识分块。`
    ElMessage.success(`已上传：${file.name}`)
    await loadIndustryDocs()
  } catch (error) {
    task.status = 'error'
    task.message = getUploadError(error)
  }
  return false
}

function getUploadError(error) {
  return error.response?.data?.msg || error.response?.data?.detail || error.message || '上传失败，请查看后端日志。'
}
</script>

<style scoped>
.page-layout > * {
  flex-shrink: 0;
}

.page-layout {
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  height: 100vh;
  min-height: 0;
  max-height: 100vh;
  overflow-y: auto;
}

.page-header h2 {
  font-size: 20px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 8px;
}

.header-title { display: flex; align-items: center; gap: 4px; }

.search-area {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
}

.result-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.answer-card {
  margin-bottom: 16px;
  border: 1px solid #d9ecff;
  background: #f5faff;
}

.answer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.answer-title,
.evidence-title {
  color: #303133;
  font-weight: 600;
}

.answer-content {
  color: #303133;
  line-height: 1.8;
}

.answer-content :deep(p) { margin: 0 0 8px; }
.answer-content :deep(ul),
.answer-content :deep(ol) { margin: 0 0 8px; padding-left: 22px; }

.evidence-title {
  margin: 4px 0 10px;
  font-size: 14px;
}

.result-card {
  transition: box-shadow 0.2s;
}

.result-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.score {
  font-size: 12px;
  color: #909399;
}

.result-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.source-file {
  max-width: 260px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #606266;
  font-size: 12px;
}

.result-content {
  font-size: 14px;
  color: #606266;
  line-height: 1.6;
}

.upload-area {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.upload-task-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.upload-task { border: 1px solid #ebeef5; }
.task-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.task-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #303133; }
.task-message { margin-top: 6px; color: #909399; font-size: 12px; }
.task-error { color: #f56c6c; }

.doc-list-card { border: 1px solid #ebeef5; }
.doc-list-header { display: flex; align-items: center; justify-content: space-between; font-weight: 600; color: #303133; }

.upload-text p { margin: 4px 0; }
.upload-text em { color: #409eff; }
.upload-hint { font-size: 12px; color: #c0c4cc; }

.empty-hint {
  text-align: center;
  padding: 48px 0;
  color: #c0c4cc;
}
</style>
