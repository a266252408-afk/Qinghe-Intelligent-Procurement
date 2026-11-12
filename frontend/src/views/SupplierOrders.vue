<template>
  <div class="page-layout">
    <div class="page-header">
      <div class="header-title">
        <el-button text :icon="ArrowLeft" title="返回上一页" @click="$router.back()" />
        <div><h2>下单管理</h2><p>查看管理员审批通过后的供应商下单记录</p></div>
      </div>
      <el-button text :icon="Refresh" :loading="loading" @click="loadOrders">刷新</el-button>
    </div>

    <el-table :data="supplierOrders" border stripe v-loading="loading" @row-click="openDetail">
      <el-table-column label="项目" prop="project_name" min-width="160" />
      <el-table-column label="采购单" min-width="180">
        <template #default="{ row }"><div>{{ row.purchase_order_name || `采购单 #${row.purchase_order_id}` }}</div><small v-if="row.purchase_order_name" class="order-number">#{{ row.purchase_order_id }}</small></template>
      </el-table-column>
      <el-table-column label="下单项" width="100">
        <template #default="{ row }">{{ row.items.length }} 项</template>
      </el-table-column>
      <el-table-column label="下单时间" width="180">
        <template #default="{ row }">{{ formatDate(row.ordered_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="230" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="primary" @click.stop="download(row, 'xlsx')">下载 Excel</el-button>
          <el-button text :icon="View" title="预览下单明细" @click.stop="openDetail(row)" />
          <el-button v-if="isOwner" text type="danger" :icon="Delete" title="删除下单记录" @click.stop="removeOrder(row)" />
        </template>
      </el-table-column>
    </el-table>
    <el-empty v-if="!loading && supplierOrders.length === 0" description="暂无已审批下单记录" />

    <el-dialog v-model="detailVisible" title="下单明细预览" width="min(1100px, 95vw)" destroy-on-close>
      <template v-if="selectedOrder">
        <div class="detail-summary">
          <span>{{ selectedOrder.project_name }} / {{ selectedOrder.purchase_order_name || `采购单 #${selectedOrder.purchase_order_id}` }}</span>
          <span>下单时间：{{ formatDate(selectedOrder.ordered_at) }}</span>
        </div>
        <el-table :data="selectedOrder.items" border max-height="460">
          <el-table-column prop="species" label="品种" min-width="140" />
          <el-table-column prop="spec" label="规格" min-width="150" />
          <el-table-column prop="quantity" label="数量" width="90" />
          <el-table-column prop="unit" label="单位" width="75" />
          <el-table-column prop="supplier_name" label="供应商" min-width="140" />
          <el-table-column prop="supplier_quote_price" label="供应商报价" width="110" />
          <el-table-column prop="final_price" label="成交价" width="100" />
          <el-table-column prop="total_price" label="总价" width="110" />
          <el-table-column label="下载" width="170" fixed="right">
            <template #default="{ row }">
              <el-button size="small" @click="download(selectedOrder, 'csv', row.item_id)">CSV</el-button>
              <el-button size="small" type="primary" @click="download(selectedOrder, 'xlsx', row.item_id)">Excel</el-button>
            </template>
          </el-table-column>
        </el-table>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft, Delete, Refresh, View } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { ordersApi } from '@/api/orders'

const supplierOrders = ref([])
const selectedOrder = ref(null)
const detailVisible = ref(false)
const loading = ref(false)
const authStore = useAuthStore()
const isOwner = computed(() => authStore.role === 'owner')

onMounted(loadOrders)

async function loadOrders() {
  loading.value = true
  try {
    supplierOrders.value = await ordersApi.supplierOrders()
  } finally {
    loading.value = false
  }
}

function openDetail(row) {
  selectedOrder.value = row
  detailVisible.value = true
}

async function download(row, fileFormat, itemId) {
  try {
    const blob = await ordersApi.supplierOrderDownload(row.supplier_order_id, fileFormat, itemId)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `下单_${row.purchase_order_id}${itemId ? `_明细_${itemId}` : ''}.${fileFormat}`
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
    ElMessage.success('文件下载已开始')
  } catch {
    // 请求拦截器负责展示接口错误。
  }
}

async function removeOrder(row) {
  try {
    await ElMessageBox.confirm(`确认删除下单记录 #${row.supplier_order_id}？收货单也会删除，长期材料历史保留。`, '删除确认', { type: 'warning' })
    await ordersApi.removeSupplierOrder(row.supplier_order_id)
    if (selectedOrder.value?.supplier_order_id === row.supplier_order_id) detailVisible.value = false
    await loadOrders()
    ElMessage.success('下单记录已删除')
  } catch {}
}

function formatDate(value) {
  return value ? new Date(value).toLocaleString('zh-CN') : '-'
}
</script>

<style scoped>
.page-layout > * { flex-shrink: 0; }
.page-layout { padding: 24px; display: flex; flex-direction: column; gap: 16px; height: 100vh; min-height: 0; max-height: 100vh; overflow-y: auto; }
.page-header, .header-title { display: flex; align-items: center; }
.page-header { justify-content: space-between; }.header-title { gap: 8px; }
.header-title h2 { font-size: 20px; color: #303133; }.header-title p { margin-top: 4px; color: #909399; font-size: 13px; }
.order-number { color: #909399; }
.detail-summary { display: flex; justify-content: space-between; gap: 12px; margin-bottom: 16px; color: #606266; font-size: 13px; }
@media (max-width: 700px) { .page-layout { padding: 12px; }.detail-summary { flex-direction: column; } }
</style>
