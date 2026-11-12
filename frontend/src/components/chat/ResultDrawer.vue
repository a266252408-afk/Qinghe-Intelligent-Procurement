<template>
  <el-drawer :model-value="modelValue" title="分析结果" direction="rtl" size="620px" @update:model-value="$emit('update:modelValue', $event)">
    <div v-if="result" class="drawer-content">
      <template v-if="result.type === 'compare'"><el-alert type="success" show-icon :closable="false">{{ result.data?.suggestion || '比价分析完成' }}</el-alert><CompareChart :data="result.data" /></template>
      <template v-else-if="result.type === 'list'">
        <el-alert v-if="result.data?.needs_review" type="warning" show-icon :closable="false" title="部分项目存在不确定内容，请人工核查后再确认" style="margin-bottom:12px" />
        <div class="section-heading"><span>采购清单（可修改）</span><el-button text type="primary" :icon="Plus" size="small" @click="addRow">添加一行</el-button></div>
        <el-table :data="editableItems" size="small" border>
          <el-table-column label="品种" min-width="120"><template #default="{ row }"><el-input v-model="row.species" size="small" /></template></el-table-column>
          <el-table-column label="规格" min-width="150"><template #default="{ row }"><el-input v-model="row.spec" size="small" /></template></el-table-column>
          <el-table-column label="数量" width="100"><template #default="{ row }"><el-input-number v-model="row.quantity" :min="0.01" size="small" controls-position="right" /></template></el-table-column>
          <el-table-column label="单位" width="75"><template #default="{ row }"><el-input v-model="row.unit" size="small" /></template></el-table-column>
          <el-table-column label="单价" width="105"><template #default="{ row }"><el-input-number v-model="row.unit_price" :min="0" :precision="2" size="small" controls-position="right" /></template></el-table-column>
          <el-table-column label="操作" width="52" fixed="right"><template #default="{ $index }"><el-button text type="danger" :icon="Delete" size="small" title="删除此行" @click="removeRow($index)" /></template></el-table-column>
        </el-table>
        <el-divider />
        <div class="section-heading"><span>确认添加到采购单</span></div>
        <el-alert v-if="currentProjectId === null" type="info" :closable="false" title="当前对话未关联项目，请先从左侧项目中选择对话。" />
        <el-select v-else v-model="selectedOrderId" placeholder="选择当前项目下的草稿采购单" style="width:100%" :loading="ordersLoading" no-data-text="当前项目暂无草稿采购单，请先创建采购单">
          <el-option v-for="order in draftOrders" :key="order.order_id" :label="orderLabel(order)" :value="order.order_id" />
        </el-select>
        <div v-if="currentProjectId !== null && draftOrders.length === 0" class="order-hint"><span>没有可添加的草稿采购单</span><el-button text type="primary" @click="goOrders">去采购单页创建</el-button></div>
        <el-button type="primary" :icon="Check" :loading="saving" :disabled="!selectedOrderId || editableItems.length === 0" class="confirm-button" @click="confirmList">确认并添加到采购单</el-button>
      </template>
      <template v-else-if="result.type === 'quote'">
        <el-alert type="info" :closable="false" style="margin-bottom:12px">报价文件已解析，请修改确认后保存到报价管理。</el-alert>
        <div class="file-info"><span>文件：{{ result.data?.file_name }}</span><span>存储路径：{{ result.data?.file_id }}</span></div>
        <div class="section-heading"><span>供应商报价（可修改）</span><el-button text type="primary" @click="quoteSupplierVisible = true">自定义供应商名称</el-button></div>
        <el-input v-if="quoteSupplierVisible" v-model="quoteSupplierName" placeholder="请输入供应商名称" style="margin-bottom:12px" />
        <el-table :data="editableQuoteItems" size="small" border>
          <el-table-column label="品种" min-width="120"><template #default="{ row }"><el-input v-model="row.species" size="small" /></template></el-table-column>
          <el-table-column label="规格" min-width="130"><template #default="{ row }"><el-input v-model="row.spec" size="small" /></template></el-table-column>
          <el-table-column label="数量" width="90"><template #default="{ row }"><el-input-number v-model="row.quantity" :min="0" size="small" /></template></el-table-column>
          <el-table-column label="供应商报价" width="110"><template #default="{ row }"><el-input-number v-model="row.unit_price" :min="0" :precision="2" size="small" /></template></el-table-column>
          <el-table-column label="成交价" width="110"><template #default="{ row }"><el-input-number v-model="row.final_price" :min="0" :precision="2" size="small" /></template></el-table-column>
          <el-table-column label="总价（元）" width="110"><template #default="{ row }"><el-input-number v-model="row.total_price" :min="0" :precision="2" size="small" /></template></el-table-column>
        </el-table>
        <el-divider />
        <div class="section-heading"><span>保存到采购单</span></div>
        <el-select v-model="quoteOrderId" placeholder="选择报价所属采购单" style="width:100%" :loading="ordersLoading">
          <el-option v-for="order in quoteOrders" :key="order.order_id" :label="orderLabel(order)" :value="order.order_id" />
        </el-select>
        <el-date-picker v-model="quoteDate" type="date" value-format="YYYY-MM-DD" placeholder="选择报价日期" style="width:100%;margin-top:12px" />
        <el-button type="primary" :icon="Check" :loading="quoteSaving" :disabled="!quoteOrderId || !quoteSupplierName.trim()" class="confirm-button" @click="confirmQuote">确认保存报价</el-button>
      </template>
      <template v-else-if="result.type === 'knowledge'">
        <el-alert type="info" :closable="false" style="margin-bottom:12px">以下为本次回答的检索依据。</el-alert>
        <div v-if="result.data?.results?.length" class="knowledge-list">
          <div v-for="(item, index) in result.data.results" :key="index" class="knowledge-item">
            <div class="knowledge-head">
              <el-tag size="small">行业知识</el-tag>
              <span class="knowledge-source">{{ item.source_file || '未知来源' }}</span>
              <span class="knowledge-score">相关度 {{ percent(item.score) }}</span>
            </div>
            <p class="knowledge-content">{{ item.content }}</p>
          </div>
        </div>
        <el-empty v-else description="本次回答没有检索到依据" />
      </template>
      <template v-else-if="result.type === 'history'"><el-table :data="result.data ?? []" size="small"><el-table-column label="品种" prop="species" /><el-table-column label="规格" prop="spec" /><el-table-column label="单价" prop="price" width="90" /><el-table-column label="供应商" prop="supplier" /></el-table></template>
      <template v-else><pre class="raw-result">{{ JSON.stringify(result.data, null, 2) }}</pre></template>
    </div>
    <div v-else class="empty-drawer"><el-icon size="48" color="#c0c4cc"><DataLine /></el-icon><p>对话中产生的结构化结果将在此展示</p></div>
  </el-drawer>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Check, Delete, Plus } from '@element-plus/icons-vue'
import { useChatStore } from '@/stores/chat'
import { ordersApi } from '@/api/orders'
import { quotesApi } from '@/api/quotes'
import CompareChart from '@/components/order/CompareChart.vue'

const props = defineProps({ modelValue: Boolean })
const emit = defineEmits(['update:modelValue'])
const router = useRouter()
const chatStore = useChatStore()
const result = computed(() => chatStore.structuredResult)
const editableItems = ref([])
const draftOrders = ref([])
const selectedOrderId = ref(null)
const ordersLoading = ref(false)
const saving = ref(false)
const editableQuoteItems = ref([])
const quoteOrders = ref([])
const quoteOrderId = ref(null)
const quoteSupplierName = ref('')
const quoteSupplierVisible = ref(false)
const quoteDate = ref(today())
const quoteSaving = ref(false)
const currentProjectId = computed(() => chatStore.sessions.find((item) => item.session_id === chatStore.currentSessionId)?.project_id ?? null)

watch(() => [result.value, props.modelValue], async () => {
  if (result.value?.type !== 'list') return
  editableItems.value = JSON.parse(JSON.stringify(result.value.data?.items ?? []))
  selectedOrderId.value = null
  await loadDraftOrders()
}, { immediate: true })

watch(() => [result.value, props.modelValue], async () => {
  if (result.value?.type !== 'quote') return
  editableQuoteItems.value = JSON.parse(JSON.stringify(result.value.data?.items ?? []))
  quoteOrderId.value = null
  quoteSupplierName.value = ''
  quoteDate.value = today()
  quoteSupplierVisible.value = false
  await loadQuoteOrders()
}, { immediate: true })

async function loadDraftOrders() {
  if (currentProjectId.value === null) { draftOrders.value = []; return }
  ordersLoading.value = true
  try { const data = await ordersApi.list({ project_id: currentProjectId.value, status: 'draft' }); draftOrders.value = data.items ?? [] } finally { ordersLoading.value = false }
}
async function loadQuoteOrders() {
  if (currentProjectId.value === null) { quoteOrders.value = []; return }
  ordersLoading.value = true
  try {
    const data = await ordersApi.list({ project_id: currentProjectId.value })
    quoteOrders.value = data.items ?? []
  } finally { ordersLoading.value = false }
}
function orderLabel(order) {
  return `${order.name || `采购单 #${order.order_id}`}${order.remark ? `（${order.remark}）` : ''}`
}
function addRow() { editableItems.value.push({ species: '', spec: '', quantity: 1, unit: '株', unit_price: null, uncertain: true }) }
function removeRow(index) { editableItems.value.splice(index, 1) }
async function confirmList() {
  if (editableItems.value.some((item) => !item.species?.trim() || !item.spec?.trim() || !item.unit?.trim() || item.quantity <= 0)) { ElMessage.warning('请完整填写品种、规格、数量和单位'); return }
  saving.value = true
  try {
    await ordersApi.saveItems(selectedOrderId.value, editableItems.value.map((item) => ({ species: item.species.trim(), spec: item.spec.trim(), quantity: Number(item.quantity), unit: item.unit.trim(), unit_price: item.unit_price === null || item.unit_price === '' ? null : Number(item.unit_price), total_price: item.unit_price ? Number(item.quantity) * Number(item.unit_price) : null })))
    ElMessage.success('清单已添加到采购单')
    chatStore.clearResult()
    emit('update:modelValue', false)
  } finally { saving.value = false }
}
async function confirmQuote() {
  if (!quoteSupplierName.value.trim()) { ElMessage.warning('请填写供应商名称'); quoteSupplierVisible.value = true; return }
  if (editableQuoteItems.value.some((item) => !item.species?.trim() || item.unit_price === null || item.unit_price < 0)) {
    ElMessage.warning('请完整填写每项品种和单价'); return
  }
  quoteSaving.value = true
  try {
    await quotesApi.create({
      order_id: quoteOrderId.value,
      supplier_name: quoteSupplierName.value.trim(),
      file_path: result.value.data.file_id,
      original_name: result.value.data.file_name,
      upload_id: result.value.data.upload_id,
      quote_date: quoteDate.value,
      items: editableQuoteItems.value,
    })
    ElMessage.success('报价已确认并保存到报价管理')
    chatStore.clearResult()
    emit('update:modelValue', false)
  } finally { quoteSaving.value = false }
}
function percent(value) {
  const num = Number(value)
  return Number.isNaN(num) ? '—' : `${(num * 100).toFixed(0)}%`
}
function today() { return new Date().toISOString().slice(0, 10) }
function goOrders() { router.push({ path: '/orders', query: { project_id: String(currentProjectId.value) } }) }
</script>

<style scoped>
.drawer-content { padding: 4px 0; }
.section-heading { display:flex; align-items:center; justify-content:space-between; margin:4px 0 10px; font-weight:600; color:#303133; }
.order-hint { display:flex; align-items:center; justify-content:space-between; margin-top:10px; color:#909399; font-size:13px; }
.confirm-button { width:100%; margin-top:16px; }
.file-info { display:flex; flex-direction:column; gap:4px; margin-bottom:12px; color:#606266; font-size:12px; overflow-wrap:anywhere; }
.knowledge-list { display:flex; flex-direction:column; gap:10px; }
.knowledge-item { border:1px solid #e4e7ed; border-radius:8px; padding:10px 12px; }
.knowledge-head { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
.knowledge-source { color:#303133; font-size:13px; font-weight:600; }
.knowledge-score { margin-left:auto; color:#909399; font-size:12px; }
.knowledge-content { margin:6px 0 0; color:#606266; font-size:13px; line-height:1.6; white-space:pre-wrap; }
.raw-result { font-size:12px; background:#f5f7fa; padding:12px; border-radius:6px; overflow-x:auto; white-space:pre-wrap; word-break:break-all; }
.empty-drawer { display:flex; flex-direction:column; align-items:center; gap:12px; padding:60px 20px; color:#c0c4cc; font-size:14px; text-align:center; }
</style>
