<template>
  <div class="page-layout">
    <div class="page-header">
      <div class="header-title">
        <el-button text :icon="ArrowLeft" title="返回上一页" @click="$router.back()" />
        <div><h2>报价管理</h2><p>管理已解析确认的供应商报价单</p></div>
      </div>
      <div class="header-actions">
        <el-button text :icon="Refresh" @click="loadQuotes">刷新</el-button>
        <el-upload :auto-upload="false" :show-file-list="false" accept=".xlsx,.csv,.txt" :on-change="handleFileChange">
          <el-button type="primary" :icon="Upload" :loading="uploading">上传报价单</el-button>
        </el-upload>
      </div>
    </div>

    <div class="filter-bar">
      <el-select v-model="filterProject" placeholder="全部项目" clearable style="width:180px" @change="handleProjectFilter">
        <el-option v-for="project in projects" :key="project.project_id" :label="project.name" :value="project.project_id" />
      </el-select>
      <el-select v-model="filterOrder" placeholder="全部采购单" clearable filterable style="width:220px" @change="loadQuotes">
        <el-option v-for="order in filteredOrders" :key="order.order_id" :label="orderLabel(order)" :value="order.order_id" />
      </el-select>
    </div>

    <el-card>
      <template #header><div class="card-title"><span>已确认报价单</span><el-tag size="small">{{ quotes.length }} 份</el-tag></div></template>
      <el-table :data="quotes" border @row-click="selectQuote">
        <el-table-column label="项目" prop="project_name" min-width="150" show-overflow-tooltip />
        <el-table-column label="供应商" prop="supplier_name" min-width="160" />
        <el-table-column label="采购单" width="110"><template #default="{ row }">#{{ row.order_id }}</template></el-table-column>
        <el-table-column label="报价项目" width="110"><template #default="{ row }">{{ row.items.length }} 项</template></el-table-column>
        <el-table-column label="文件名" min-width="180"><template #default="{ row }">{{ originalName(row) }}</template></el-table-column>
        <el-table-column label="存储路径" prop="file_path" min-width="240" show-overflow-tooltip />
        <el-table-column label="确认时间" width="180"><template #default="{ row }">{{ formatDate(row.created_at) }}</template></el-table-column>
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="success" :disabled="quoteCount(row.order_id) < 2" @click.stop="compareQuotes(row.order_id)">对比报价</el-button>
            <el-button
              v-if="isOwner"
              text
              type="danger"
              :icon="Delete"
              size="small"
              title="删除报价"
              @click.stop="removeQuote(row)"
            />
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="quotes.length === 0" description="暂无已确认报价，请上传供应商报价单" />
    </el-card>

    <el-dialog
      class="quote-detail-dialog"
      :model-value="Boolean(selectedQuote)"
      :title="selectedQuote ? `${selectedQuote.supplier_name}报价明细` : '报价明细'"
      width="min(1200px, 95vw)"
      destroy-on-close
      @close="selectedQuote = null"
    >
      <div v-if="selectedQuote" class="detail-scroll-panel">
        <el-table :data="selectedQuote.items" border>
          <el-table-column prop="species" label="品种" min-width="140" />
          <el-table-column prop="spec" label="规格" min-width="160" />
          <el-table-column prop="quantity" label="数量" width="100" />
          <el-table-column prop="unit" label="单位" width="80" />
          <el-table-column prop="unit_price" label="供应商报价" width="120" />
          <el-table-column prop="final_price" label="成交价" width="110" />
          <el-table-column prop="total_price" label="总价（元）" width="120" />
          <el-table-column prop="delivery_days" label="交货天数" width="110" />
          <el-table-column prop="payment_terms" label="付款条件" min-width="160" />
          <el-table-column prop="valid_until" label="报价有效期" width="130" />
        </el-table>
      </div>
    </el-dialog>

    <el-card v-if="compareResult">
      <template #header>多供应商可视化对比</template>
      <el-alert type="success" :closable="false" show-icon>{{ compareResult.ai_suggestion }}</el-alert>
      <div class="comparison-data">
        <CompareChart :data="compareResult" />
      </div>
    </el-card>

    <el-dialog v-model="analysisVisible" title="报价分析结果" width="860px" destroy-on-close>
      <el-alert type="info" :closable="false" style="margin-bottom:16px">请修改报价项目、填写供应商名称，并选择所属采购单后确认保存。</el-alert>
      <div class="file-info"><span>文件名：{{ quoteDraft?.original_name }}</span><span>临时存储路径：{{ quoteDraft?.file_path }}</span></div>
      <div class="supplier-actions">
        <el-button type="primary" plain @click="customSupplierVisible = true">自定义供应商名称</el-button>
        <el-input v-if="customSupplierVisible" v-model="supplierName" placeholder="请输入供应商名称" maxlength="100" show-word-limit />
      </div>
      <el-select v-model="selectedOrderId" placeholder="选择报价所属采购单" filterable style="width:100%;margin-bottom:16px">
        <el-option v-for="order in orders" :key="order.order_id" :label="orderLabel(order)" :value="order.order_id" />
      </el-select>
      <el-date-picker v-model="quoteDate" type="date" value-format="YYYY-MM-DD" placeholder="选择报价日期" style="width:100%;margin-bottom:16px" />
      <el-table :data="editableItems" border>
        <el-table-column label="品种" min-width="150"><template #default="{ row }"><el-input v-model="row.species" /></template></el-table-column>
        <el-table-column label="规格" min-width="130"><template #default="{ row }"><el-input v-model="row.spec" /></template></el-table-column>
        <el-table-column label="数量" width="120"><template #default="{ row }"><el-input-number v-model="row.quantity" :min="0" /></template></el-table-column>
        <el-table-column label="供应商报价" width="140"><template #default="{ row }"><el-input-number v-model="row.unit_price" :min="0" :precision="2" /></template></el-table-column>
        <el-table-column label="成交价" width="140"><template #default="{ row }"><el-input-number v-model="row.final_price" :min="0" :precision="2" /></template></el-table-column>
        <el-table-column label="总价（元）" width="130"><template #default="{ row }"><el-input-number v-model="row.total_price" :min="0" :precision="2" /></template></el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="analysisVisible = false">取消</el-button>
        <el-button type="primary" :loading="confirming" @click="confirmQuote">确认保存报价</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft, Delete, Refresh, Upload } from '@element-plus/icons-vue'
import { ordersApi } from '@/api/orders'
import { projectsApi } from '@/api/projects'
import { quotesApi } from '@/api/quotes'
import { useAuthStore } from '@/stores/auth'
import CompareChart from '@/components/order/CompareChart.vue'

const orders = ref([])
const projects = ref([])
const quotes = ref([])
const selectedQuote = ref(null)
const compareResult = ref(null)
const selectedOrderId = ref(null)
const quoteDraft = ref(null)
const editableItems = ref([])
const supplierName = ref('')
const quoteDate = ref(today())
const customSupplierVisible = ref(false)
const analysisVisible = ref(false)
const uploading = ref(false)
const confirming = ref(false)
const authStore = useAuthStore()
const isOwner = computed(() => authStore.role === 'owner')
const filterProject = ref(null)
const filterOrder = ref(null)
const STATUS_LABELS = { draft: '草稿', pending_approval: '待审批', approved: '已通过', rejected: '已驳回' }
const filteredOrders = computed(() => filterProject.value
  ? orders.value.filter((order) => order.project_id === filterProject.value)
  : orders.value)

onMounted(async () => {
  const projectData = await projectsApi.list()
  projects.value = projectData.items ?? projectData
  await loadOrders()
  await loadQuotes()
})

async function loadOrders() {
  const data = await ordersApi.list({})
  orders.value = data.items ?? []
}

async function loadQuotes() {
  quotes.value = await quotesApi.list({
    project_id: filterProject.value || undefined,
    order_id: filterOrder.value || undefined,
  })
  selectedQuote.value = null
  compareResult.value = null
}

async function handleProjectFilter() {
  if (filterOrder.value && !filteredOrders.value.some((order) => order.order_id === filterOrder.value)) {
    filterOrder.value = null
  }
  await loadQuotes()
}

async function handleFileChange(uploadFile) {
  if (!uploadFile.raw) return
  uploading.value = true
  try {
    quoteDraft.value = await quotesApi.parse(null, uploadFile.raw)
    editableItems.value = JSON.parse(JSON.stringify(quoteDraft.value.items ?? []))
    selectedOrderId.value = null
    supplierName.value = ''
    quoteDate.value = today()
    customSupplierVisible.value = false
    analysisVisible.value = true
  } finally { uploading.value = false }
}

async function confirmQuote() {
  if (!supplierName.value.trim()) { ElMessage.warning('请点击“自定义供应商名称”并填写供应商名称'); customSupplierVisible.value = true; return }
  if (!selectedOrderId.value) { ElMessage.warning('请选择报价所属采购单'); return }
  if (editableItems.value.some((item) => !item.species?.trim() || item.unit_price === null || item.unit_price < 0)) {
    ElMessage.warning('请完整填写每项品种和单价'); return
  }
  confirming.value = true
  try {
    await quotesApi.create({ upload_id: quoteDraft.value.upload_id, order_id: selectedOrderId.value, supplier_name: supplierName.value.trim(), file_path: quoteDraft.value.file_path, original_name: quoteDraft.value.original_name, quote_date: quoteDate.value, items: editableItems.value })
    analysisVisible.value = false
    quoteDraft.value = null
    await loadQuotes()
    ElMessage.success('报价已确认并保存')
  } finally { confirming.value = false }
}

async function compareQuotes(orderId) {
  try { compareResult.value = await ordersApi.compare(orderId, []) } catch {}
}
function selectQuote(quote) { selectedQuote.value = quote }
function quoteCount(orderId) { return quotes.value.filter((quote) => quote.order_id === orderId).length }
async function removeQuote(row) {
  try {
    await ElMessageBox.confirm(`确认删除 ${row.supplier_name || '该供应商'} 的报价记录？长期材料历史会保留。`, '删除确认', { type: 'warning' })
    await quotesApi.remove(row.quote_id)
    if (selectedQuote.value?.quote_id === row.quote_id) selectedQuote.value = null
    await loadQuotes()
    ElMessage.success('报价记录已删除')
  } catch (error) {
    // 取消确认或请求失败均由对话框/请求拦截器处理。
  }
}
function originalName(quote) { return quote.original_name || quote.file_path.split(/[\\/]/).pop() }
function orderLabel(order) { return (order.name || '采购单 #' + order.order_id) + '（' + (STATUS_LABELS[order.status] || order.status) + '）' }
function formatDate(value) { return value ? new Date(value).toLocaleString('zh-CN') : '-' }
function today() { return new Date().toISOString().slice(0, 10) }
</script>

<style scoped>
.page-layout > * { flex-shrink: 0; }
.page-layout { padding:24px 24px 32px; display:flex; flex-direction:column; gap:16px; height:100vh; min-height:0; max-height:100vh; overflow-y:auto; overscroll-behavior:contain; }
.filter-bar { display:flex; gap:12px; }
.page-header, .header-title, .header-actions, .card-title, .supplier-actions { display:flex; align-items:center; }
.page-header, .card-title { justify-content:space-between; }.header-title { gap:8px; }.header-actions { gap:8px; }
.header-title h2 { font-size:20px; color:#303133; }.header-title p { margin-top:4px; color:#909399; font-size:13px; }
.supplier-actions { gap:12px; margin-bottom:16px; }.supplier-actions .el-input { max-width:360px; }
.file-info { display:flex; flex-direction:column; gap:4px; margin-bottom:16px; color:#606266; font-size:12px; overflow-wrap:anywhere; }
.detail-scroll-panel {
  max-height: calc(100vh - 240px);
  min-height: 180px;
  overflow: auto;
  padding-bottom: 16px;
  overscroll-behavior: contain;
}
:deep(.quote-detail-dialog .el-dialog__body) {
  max-height: calc(100vh - 150px);
  overflow: hidden;
  padding-top: 8px;
  padding-bottom: 20px;
}
.comparison-data { margin-top: 16px; }
</style>
