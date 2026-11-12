<template>
  <div class="page-layout">
    <div class="page-header">
      <div class="header-title">
        <el-button text :icon="ArrowLeft" title="返回上一页" @click="$router.back()" />
        <div><h2>收货管理</h2><p>填写货到时间并确认材料收货</p></div>
      </div>
      <el-button text :icon="Refresh" :loading="loading" @click="loadReceipts">刷新</el-button>
    </div>

    <el-table :data="receipts" border stripe v-loading="loading" @row-click="openDetail">
      <el-table-column label="项目" prop="project_name" min-width="170" />
      <el-table-column label="下单记录" width="110"><template #default="{ row }">#{{ row.supplier_order_id }}</template></el-table-column>
      <el-table-column label="收货项" width="100"><template #default="{ row }">{{ row.items.length }} 项</template></el-table-column>
      <el-table-column label="状态" width="100"><template #default="{ row }"><el-tag :type="statusType(row.status)">{{ statusLabel(row.status) }}</el-tag></template></el-table-column>
      <el-table-column label="确认时间" width="180"><template #default="{ row }">{{ formatDate(row.confirmed_at) }}</template></el-table-column>
      <el-table-column label="操作" width="220" fixed="right"><template #default="{ row }"><el-button size="small" type="primary" @click.stop="openDetail(row)">查看并确认</el-button><el-button v-if="isOwner" text type="danger" :icon="Delete" title="删除收货单" @click.stop="removeReceipt(row)" /></template></el-table-column>
    </el-table>
    <el-empty v-if="!loading && receipts.length === 0" description="暂无待收货记录" />

    <el-dialog v-model="detailVisible" title="收货单明细" width="min(1100px, 95vw)" destroy-on-close>
      <template v-if="selectedReceipt">
        <div class="detail-summary"><span>{{ selectedReceipt.project_name }} / 下单记录 #{{ selectedReceipt.supplier_order_id }}</span><span>已确认 {{ receivedCount }}/{{ selectedReceipt.items.length }} 项</span></div>
        <el-table :data="selectedReceipt.items" border max-height="460">
          <el-table-column prop="species" label="品种" min-width="140" />
          <el-table-column prop="spec" label="规格" min-width="150" />
          <el-table-column prop="quantity" label="数量" width="90" />
          <el-table-column prop="unit" label="单位" width="75" />
          <el-table-column prop="supplier_name" label="供应商" min-width="140" />
          <el-table-column prop="final_price" label="成交价" width="100" />
          <el-table-column label="货到时间" width="190">
            <template #default="{ row }">
              <el-date-picker v-model="row.arrived_at" type="datetime" value-format="YYYY-MM-DDTHH:mm:ss" placeholder="选择时间" size="small" />
            </template>
          </el-table-column>
          <el-table-column label="确认" width="90"><template #default="{ row }"><el-checkbox v-model="row.is_received" :disabled="row.is_received" /></template></el-table-column>
        </el-table>
      </template>
      <template #footer>
        <el-button @click="detailVisible = false">关闭</el-button>
        <el-button :loading="saving" @click="fillArrivalTimes">一键填写货到时间</el-button>
        <el-button :loading="saving" @click="saveDetail">保存修改</el-button>
        <el-button type="primary" :loading="saving" @click="confirmAll">一键确认收货</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft, Delete, Refresh } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { receiptsApi } from '@/api/receipts'

const receipts = ref([])
const selectedReceipt = ref(null)
const detailVisible = ref(false)
const loading = ref(false)
const saving = ref(false)
const authStore = useAuthStore()
const isOwner = computed(() => authStore.role === 'owner')
const receivedCount = computed(() => selectedReceipt.value?.items.filter((item) => item.is_received).length ?? 0)

const statusLabel = (status) => ({ pending: '待收货', partial: '部分收货', received: '已收货' }[status] || status)
const statusType = (status) => ({ pending: 'warning', partial: 'primary', received: 'success' }[status] || 'info')

onMounted(loadReceipts)

async function loadReceipts() {
  loading.value = true
  try { receipts.value = await receiptsApi.list() } finally { loading.value = false }
}

function openDetail(row) {
  selectedReceipt.value = JSON.parse(JSON.stringify(row))
  detailVisible.value = true
}

// 当前本地时间，格式与货到时间选择器一致（YYYY-MM-DDTHH:mm:ss）
function nowLocal() {
  const pad = (n) => String(n).padStart(2, '0')
  const d = new Date()
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

async function fillArrivalTimes() {
  if (!selectedReceipt.value) return
  const pending = selectedReceipt.value.items.filter((item) => !item.arrived_at)
  if (pending.length === 0) {
    ElMessage.info('所有材料均已填写货到时间')
    return
  }
  pending.forEach((item) => { item.arrived_at = nowLocal() })
  ElMessage.success(`已为 ${pending.length} 项材料填写当前时间，点击“保存修改”或“一键确认收货”生效`)
}

async function saveDetail() {
  if (!selectedReceipt.value) return
  saving.value = true
  try {
    selectedReceipt.value = await receiptsApi.update(selectedReceipt.value.receipt_id, { items: selectedReceipt.value.items })
    await loadReceipts()
    ElMessage.success('收货信息已保存')
  } finally { saving.value = false }
}

async function confirmAll() {
  if (!selectedReceipt.value) return
  saving.value = true
  try {
    // 手动填写的时间只存在前端，确认前必须先整体保存；
    // 未填写的自动补当前时间，一步完成收货
    const filled = selectedReceipt.value.items.filter((item) => !item.arrived_at)
    if (filled.length > 0) {
      filled.forEach((item) => { item.arrived_at = nowLocal() })
    }
    selectedReceipt.value = await receiptsApi.update(selectedReceipt.value.receipt_id, { items: selectedReceipt.value.items })
    selectedReceipt.value = await receiptsApi.confirm(selectedReceipt.value.receipt_id)
    await loadReceipts()
    ElMessage.success(filled.length > 0 ? `已自动填写 ${filled.length} 项货到时间并确认全部收货` : '已确认全部收货')
  } finally { saving.value = false }
}

async function removeReceipt(row) {
  try {
    await ElMessageBox.confirm(`确认删除收货单 #${row.receipt_id}？下单记录和长期材料历史会保留。`, '删除确认', { type: 'warning' })
    await receiptsApi.remove(row.receipt_id)
    if (selectedReceipt.value?.receipt_id === row.receipt_id) detailVisible.value = false
    await loadReceipts()
    ElMessage.success('收货单已删除')
  } catch {}
}

function formatDate(value) { return value ? new Date(value).toLocaleString('zh-CN') : '-' }
</script>

<style scoped>
.page-layout > * { flex-shrink: 0; }
.page-layout { padding: 24px; display: flex; flex-direction: column; gap: 16px; height: 100vh; min-height: 0; max-height: 100vh; overflow-y: auto; }
.page-header, .header-title { display: flex; align-items: center; }.page-header { justify-content: space-between; }.header-title { gap: 8px; }
.header-title h2 { font-size: 20px; color: #303133; }.header-title p { margin-top: 4px; color: #909399; font-size: 13px; }.detail-summary { display: flex; justify-content: space-between; margin-bottom: 16px; color: #606266; font-size: 13px; }
@media (max-width: 700px) { .page-layout { padding: 12px; }.detail-summary { flex-direction: column; gap: 6px; } }
</style>
