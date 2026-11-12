<template>
  <div class="page-layout">
    <div class="page-header">
      <div class="header-title">
        <el-button text :icon="ArrowLeft" title="返回上一页" @click="$router.back()" />
        <div><h2>长期材料记忆</h2><p>供应商报价历史</p></div>
      </div>
      <div class="header-actions">
        <el-button :icon="Upload" @click="$router.push('/quotes')">去报价管理上传</el-button>
        <el-button :icon="Refresh" @click="loadRecords">刷新</el-button>
      </div>
    </div>

    <el-card>
      <el-form :inline="true" class="filter-form" @submit.prevent="handleSearch">
        <el-form-item label="项目">
          <el-select v-model="filters.project_id" clearable placeholder="全部项目" style="width:160px" @change="handleSearch">
            <el-option v-for="project in projects" :key="project.project_id" :label="project.name" :value="project.project_id" />
          </el-select>
        </el-form-item>
        <el-form-item label="供应商"><el-input v-model="filters.supplier_name" clearable placeholder="供应商名称" @keyup.enter="handleSearch" /></el-form-item>
        <el-form-item label="材料"><el-input v-model="filters.material_name" clearable placeholder="材料名称" @keyup.enter="handleSearch" /></el-form-item>
        <el-form-item label="报价日期">
          <el-date-picker v-model="dateRange" type="daterange" value-format="YYYY-MM-DD" range-separator="至" start-placeholder="开始日期" end-placeholder="结束日期" clearable />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :icon="Search" :loading="loading" @click="handleSearch">查询</el-button>
          <el-button :icon="RefreshLeft" :disabled="!hasFilter" @click="resetFilters">恢复全部</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card class="table-card">
      <template #header><div class="card-title"><span>材料历史明细</span><el-tag size="small">{{ records.length }} 条</el-tag></div></template>
      <el-table v-loading="loading" :data="records" border stripe height="calc(100vh - 300px)">
        <el-table-column prop="project_name" label="项目" min-width="120" show-overflow-tooltip>
          <template #default="{ row }">{{ row.project_name || '-' }}</template>
        </el-table-column>
        <el-table-column prop="supplier_name" label="供应商" min-width="140" fixed />
        <el-table-column prop="material_name" label="材料名称" min-width="140" />
        <el-table-column prop="spec" label="规格" min-width="140" />
        <el-table-column prop="quantity" label="数量" width="90" />
        <el-table-column prop="unit" label="单位" width="75" />
        <el-table-column prop="quote_price" label="供应商报价" width="110" />
        <el-table-column prop="total_price" label="报价总价" width="110" />
        <el-table-column prop="final_price" label="成交价" width="100"><template #default="{ row }">{{ row.final_price ?? '未成交' }}</template></el-table-column>
        <el-table-column prop="quote_date" label="报价日期" width="120" />
        <el-table-column prop="ordered_at" label="下单时间" width="160"><template #default="{ row }">{{ formatDate(row.ordered_at) }}</template></el-table-column>
        <el-table-column prop="arrived_at" label="货到时间" width="160"><template #default="{ row }">{{ formatDate(row.arrived_at) }}</template></el-table-column>
        <el-table-column prop="receipt_status" label="收货状态" width="100" />
        <el-table-column prop="valid_until" label="有效期至" width="120" />
        <el-table-column prop="delivery_days" label="交货天数" width="100" />
        <el-table-column prop="payment_terms" label="付款条件" min-width="120" show-overflow-tooltip />
        <el-table-column label="上传人" width="110"><template #default="{ row }">{{ row.uploaded_by_name || row.uploaded_by || '-' }}</template></el-table-column>
        <el-table-column label="确认人" width="110"><template #default="{ row }">{{ row.confirmed_by_name || row.confirmed_by || '-' }}</template></el-table-column>
        <el-table-column prop="source_file" label="来源文件" min-width="220" show-overflow-tooltip />
      </el-table>
      <el-empty v-if="!loading && records.length === 0" description="暂无长期材料记录" />
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ArrowLeft, Refresh, RefreshLeft, Search, Upload } from '@element-plus/icons-vue'
import { knowledgeApi } from '@/api/knowledge'
import { projectsApi } from '@/api/projects'

const records = ref([])
const projects = ref([])
const loading = ref(false)
const dateRange = ref([])
const filters = reactive({ project_id: null, supplier_name: '', material_name: '' })
const hasFilter = computed(() =>
  Boolean(filters.project_id || filters.supplier_name || filters.material_name || dateRange.value?.length))

onMounted(async () => {
  const data = await projectsApi.list()
  projects.value = data.items ?? data
  await loadRecords()
})

async function loadRecords() {
  loading.value = true
  try { records.value = await knowledgeApi.history(buildParams()) } finally { loading.value = false }
}

function buildParams() {
  const params = {}
  if (filters.project_id) params.project_id = filters.project_id
  if (filters.supplier_name.trim()) params.supplier_name = filters.supplier_name.trim()
  if (filters.material_name.trim()) params.material_name = filters.material_name.trim()
  if (dateRange.value?.[0]) params.date_from = dateRange.value[0]
  if (dateRange.value?.[1]) params.date_to = dateRange.value[1]
  return params
}

function handleSearch() { loadRecords() }

function resetFilters() {
  filters.project_id = null
  filters.supplier_name = ''
  filters.material_name = ''
  dateRange.value = []
  loadRecords()
}

function formatDate(value) { return value ? new Date(value).toLocaleString('zh-CN') : '-' }
</script>

<style scoped>
.page-layout > * { flex-shrink: 0; }
.page-layout { padding: 24px; display: flex; flex-direction: column; gap: 16px; height: 100vh; min-height: 0; max-height: 100vh; overflow-y: auto; }
.page-header, .header-title, .header-actions, .card-title { display: flex; align-items: center; }
.page-header, .card-title { justify-content: space-between; }
.header-title { gap: 8px; }.header-actions { gap: 8px; }
.header-title h2 { font-size: 20px; color: #303133; }.header-title p { margin-top: 4px; color: #909399; font-size: 13px; }
.filter-form { margin-bottom: -18px; }.table-card { min-height: 300px; }
@media (max-width: 900px) { .page-layout { padding: 12px; }.page-header { align-items: flex-start; gap: 12px; flex-direction: column; }.filter-form { margin-bottom: 0; }.header-actions { width: 100%; }.header-actions .el-button { flex: 1; } }
</style>
