<template>
  <div class="page-layout" v-loading="loading">
    <!-- 页面头 -->
    <div class="page-header">
      <el-button text :icon="ArrowLeft" @click="$router.back()">返回</el-button>
      <div class="order-meta">
        <div class="order-title">
          <span class="order-id">{{ order?.name || `采购单 #${order?.order_id}` }}</span>
          <small v-if="order?.name" class="order-number">#{{ order.order_id }}</small>
        </div>
        <el-tag :type="statusType(order?.status)" size="small">
          {{ statusLabel(order?.status) }}
        </el-tag>
      </div>
      <div class="header-actions">
        <el-button v-if="isDraft" type="primary" @click="handleSaveItems">保存</el-button>
        <el-button v-if="isDraft" type="warning" @click="handleSubmit">提交下单申请</el-button>
        <el-dropdown v-if="canGenerateInquiry" @command="handleInquiry">
          <el-button>生成询价单<el-icon class="el-icon--right"><ArrowDown /></el-icon></el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item
                v-for="t in templates"
                :key="t.template_id"
                :command="t.template_id"
              >{{ t.name }}</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </div>

    <el-card v-if="isDraft" class="order-settings">
      <el-form :inline="true">
        <el-form-item label="采购单名称">
          <el-input v-model="orderForm.name" maxlength="120" show-word-limit placeholder="自定义名称" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="orderForm.remark" placeholder="可选" />
        </el-form-item>
        <el-button type="primary" plain @click="handleSaveOrder">保存基本信息</el-button>
      </el-form>
    </el-card>

    <!-- 采购项列表 -->
    <el-card>
      <template #header>
        <span>采购项明细</span>
        <span class="total-amount" v-if="order?.total_amount">
          合计：¥{{ order.total_amount.toFixed(2) }}
        </span>
      </template>
      <div v-if="isDraft && supplierOptions.length" class="supplier-toolbar">
        <el-select v-model="bulkSupplierId" placeholder="一键选择同一家供应商" clearable style="width:240px">
          <el-option
            v-for="option in bulkSupplierOptions"
            :key="option.supplier_name"
            :label="option.supplier_name"
            :value="option.supplier_name"
          />
        </el-select>
        <el-button type="primary" plain :disabled="!bulkSupplierId" @click="applyBulkSupplier">
          应用到可匹配材料
        </el-button>
      </div>
      <OrderItems :items="editableItems" :editable="isDraft" :supplier-options="supplierOptions" />
    </el-card>

    <!-- 备注 -->
    <el-card v-if="order?.remark">
      <template #header>备注</template>
      {{ order.remark }}
    </el-card>

    <el-dialog
      v-model="inquiryDialogVisible"
      title="询价单已生成"
      width="720px"
      destroy-on-close
    >
      <template v-if="inquiryResult">
        <div class="inquiry-summary">
          <div><span>模板</span>{{ inquiryResult.template_name }}</div>
          <div><span>文件</span>{{ inquiryResult.filename }}</div>
          <div><span>采购项</span>{{ inquiryResult.preview_items.length }} 项预览</div>
        </div>
        <el-table :data="inquiryResult.preview_items" border max-height="320">
          <el-table-column type="index" label="序号" width="70" />
          <el-table-column prop="species" label="品种" min-width="160" />
          <el-table-column prop="spec" label="规格" min-width="130" />
          <el-table-column prop="quantity" label="数量" width="100" />
          <el-table-column prop="unit" label="单位" width="90" />
        </el-table>
      </template>
      <template #footer>
        <el-button @click="inquiryDialogVisible = false">关闭</el-button>
        <el-button type="primary" :loading="downloadLoading" @click="handleDownloadInquiry">
          下载询价单
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, reactive } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft, ArrowDown } from '@element-plus/icons-vue'
import { useOrderStore } from '@/stores/order'
import { ordersApi } from '@/api/orders'
import OrderItems from '@/components/order/OrderItems.vue'

const route = useRoute()
const router = useRouter()
const orderStore = useOrderStore()
const loading = ref(false)
const templates = ref([])
const editableItems = ref([])
const supplierOptions = ref([])
const bulkSupplierId = ref('')
const inquiryResult = ref(null)
const inquiryDialogVisible = ref(false)
const downloadLoading = ref(false)
const orderForm = reactive({ name: '', remark: '' })

const order = computed(() => orderStore.currentOrder)
const isDraft = computed(() => order.value?.status === 'draft')
const canGenerateInquiry = computed(() => (order.value?.items?.length ?? 0) > 0)

const STATUS_MAP = {
  draft: { label: '草稿', type: 'info' },
  pending_approval: { label: '待审批下单', type: 'warning' },
  approved: { label: '待生成下单', type: 'success' },
  ordered: { label: '已下单', type: 'primary' },
  received: { label: '已收货', type: 'success' },
  settled: { label: '已对账', type: '' },
  rejected: { label: '已驳回', type: 'danger' },
}
const statusLabel = (s) => STATUS_MAP[s]?.label ?? s
const statusType = (s) => STATUS_MAP[s]?.type ?? ''

onMounted(async () => {
  loading.value = true
  try {
    await orderStore.fetchOrder(route.params.id)
    editableItems.value = JSON.parse(JSON.stringify(order.value?.items ?? []))
    orderForm.name = order.value?.name ?? ''
    orderForm.remark = order.value?.remark ?? ''
    await loadSupplierOptions()
    templates.value = await ordersApi.inquiryTemplates()
  } finally {
    loading.value = false
  }
})

async function loadSupplierOptions() {
  supplierOptions.value = await ordersApi.supplierOptions(route.params.id)
}

async function handleSaveOrder() {
  loading.value = true
  try {
    await orderStore.updateOrder(order.value.order_id, orderForm)
    ElMessage.success('采购单基本信息已保存')
  } finally {
    loading.value = false
  }
}

async function handleSaveItems() {
  const valid = editableItems.value.every((i) => i.species && i.quantity > 0 && i.unit)
  if (!valid) {
    ElMessage.warning('请完整填写每行的品种、数量和单位')
    return
  }
  loading.value = true
  try {
    await orderStore.saveItems(order.value.order_id, editableItems.value)
    await orderStore.fetchOrder(route.params.id)
    editableItems.value = JSON.parse(JSON.stringify(order.value?.items ?? []))
    await loadSupplierOptions()
    ElMessage.success('保存成功')
  } finally {
    loading.value = false
  }
}

const bulkSupplierOptions = computed(() => {
  const options = supplierOptions.value.flatMap((item) => item.suppliers)
  return [...new Map(options.map((item) => [item.supplier_name, item])).values()]
})

function applyBulkSupplier() {
  editableItems.value.forEach((row) => {
    const options = supplierOptions.value.find((item) => item.item_id === row.item_id)?.suppliers ?? []
    const option = options.find((item) => item.supplier_name === bulkSupplierId.value)
    if (option) {
      row.supplier_quote_item_id = option.quote_item_id
      row.supplier_name = option.supplier_name
      row.supplier_quote_price = option.unit_price
      row.final_price = option.unit_price
      // 小计与手动选择供应商保持同一口径：数量 × 成交价
      row.total_price = row.quantity && option.unit_price
        ? Number(row.quantity) * Number(option.unit_price)
        : null
    }
  })
  ElMessage.success('已为可匹配材料选择供应商并带入成交价')
}

async function handleSubmit() {
  if (editableItems.value.length === 0) {
    ElMessage.warning('请先添加采购项')
    return
  }
  await ElMessageBox.confirm('确认提交审批？提交后不可修改。', '提交确认', { type: 'warning' })
  loading.value = true
  try {
    await handleSaveItems()
    await orderStore.submitOrder(order.value.order_id)
    ElMessage.success('已提交审批')
  } catch {
    // ElMessageBox 取消也会 catch，忽略
  } finally {
    loading.value = false
  }
}

async function handleInquiry(templateId) {
  loading.value = true
  try {
    const data = await ordersApi.generateInquiry(order.value.order_id, templateId)
    inquiryResult.value = data
    inquiryDialogVisible.value = true
    ElMessage.success('询价单已生成，请确认预览后下载')
  } finally {
    loading.value = false
  }
}

async function handleDownloadInquiry() {
  if (!inquiryResult.value) return
  downloadLoading.value = true
  try {
    const blob = await ordersApi.downloadInquiry(order.value.order_id)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = inquiryResult.value.filename
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
    ElMessage.success('询价单下载已开始')
  } finally {
    downloadLoading.value = false
  }
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
  padding-bottom: 32px;
}

.page-header {
  display: flex;
  align-items: center;
  gap: 12px;
}

.order-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
}

.order-id {
  font-size: 18px;
  font-weight: 600;
  color: #303133;
}

.order-title { display: flex; align-items: baseline; gap: 8px; }
.order-number { color: #909399; }
.order-settings :deep(.el-form-item) { margin-bottom: 0; }

.header-actions {
  display: flex;
  gap: 8px;
}

.total-amount {
  float: right;
  font-weight: 600;
  color: #e6a23c;
}

.inquiry-summary {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 16px;
  padding: 12px;
  background: #f5f7fa;
  color: #303133;
}

.inquiry-summary div {
  min-width: 0;
  overflow-wrap: anywhere;
}

.inquiry-summary span {
  display: block;
  margin-bottom: 4px;
  color: #909399;
  font-size: 12px;
}

.download-hint {
  color: #909399;
  font-size: 13px;
}

@media (max-width: 640px) {
  .inquiry-summary {
    grid-template-columns: 1fr;
  }
}
</style>
