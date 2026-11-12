<template>
  <div class="page-layout">
    <!-- 页面头 -->
    <div class="page-header">
      <div class="header-title"><el-button text :icon="ArrowLeft" title="返回上一页" @click="router.back()" /><h2>采购单</h2></div>
      <el-button type="primary" :icon="Plus" @click="showCreate = true">新建采购单</el-button>
    </div>

    <!-- 筛选栏 -->
    <div class="filter-bar">
      <el-select v-model="filterProject" placeholder="全部项目" clearable style="width:160px" @change="load">
        <el-option
          v-for="p in projects"
          :key="p.project_id"
          :label="p.name"
          :value="p.project_id"
        />
      </el-select>
      <el-select v-model="filterStatus" placeholder="全部状态" clearable style="width:140px" @change="load">
        <el-option label="草稿" value="draft" />
        <el-option label="待审批下单" value="pending_approval" />
        <el-option label="已下单" value="ordered" />
        <el-option label="已下单" value="ordered" />
        <el-option label="已收货" value="received" />
        <el-option label="已对账" value="settled" />
        <el-option label="已驳回" value="rejected" />
      </el-select>
    </div>

    <!-- 表格 -->
    <el-table :data="orderStore.orders" style="width:100%" v-loading="loading">
      <el-table-column label="采购单" min-width="180">
        <template #default="{ row }">
          <div>{{ row.name || `采购单 #${row.order_id}` }}</div>
          <small v-if="row.name" class="order-number">#{{ row.order_id }}</small>
        </template>
      </el-table-column>
      <el-table-column label="所属项目" prop="project_name" min-width="160" show-overflow-tooltip />
      <el-table-column label="状态" width="110">
        <template #default="{ row }">
          <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="总金额" width="120">
        <template #default="{ row }">
          {{ row.total_amount ? `¥${row.total_amount.toFixed(2)}` : '-' }}
        </template>
      </el-table-column>
      <el-table-column label="备注" prop="remark" show-overflow-tooltip />
      <el-table-column label="创建时间" width="160">
        <template #default="{ row }">{{ fmtDate(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="160" fixed="right">
        <template #default="{ row }">
          <el-button text type="primary" size="small" @click="goDetail(row.order_id)">详情</el-button>
          <el-button
            v-if="isOwner"
            text
            type="danger"
            :icon="Delete"
            size="small"
            title="删除采购单"
            @click="removeOrder(row)"
          />
        </template>
      </el-table-column>
    </el-table>
  </div>

  <!-- 新建采购单对话框 -->
  <el-dialog v-model="showCreate" title="新建采购单" width="380px">
    <el-form label-position="top">
      <el-form-item label="采购单名称">
        <el-input v-model="newForm.name" maxlength="120" show-word-limit placeholder="例如：滨河景观苗木采购" />
      </el-form-item>
      <el-form-item label="所属项目" required>
        <el-select v-model="newForm.project_id" placeholder="选择项目" style="width:100%">
          <el-option
            v-for="p in projects"
            :key="p.project_id"
            :label="p.name"
            :value="p.project_id"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="备注">
        <el-input v-model="newForm.remark" placeholder="可选" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="showCreate = false">取消</el-button>
      <el-button type="primary" @click="handleCreate">创建</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, Delete, Plus } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useOrderStore } from '@/stores/order'
import { useAuthStore } from '@/stores/auth'
import { projectsApi } from '@/api/projects'
import { ordersApi } from '@/api/orders'

const router = useRouter()
const route = useRoute()
const orderStore = useOrderStore()
const authStore = useAuthStore()
const isOwner = computed(() => authStore.role === 'owner')
const loading = ref(false)
const projects = ref([])
const filterProject = ref(null)
const filterStatus = ref(null)
const showCreate = ref(false)
const newForm = reactive({ project_id: null, name: '', remark: '' })

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

function fmtDate(dt) {
  return dt ? new Date(dt).toLocaleString('zh-CN') : '-'
}

async function load() {
  loading.value = true
  try {
    await orderStore.fetchOrders({
      project_id: filterProject.value || undefined,
      status: filterStatus.value || undefined,
    })
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  const data = await projectsApi.list()
  projects.value = data.items ?? data
  if (route.query.project_id) filterProject.value = Number(route.query.project_id)
  await load()
})

function goDetail(id) {
  router.push(`/orders/${id}`)
}

async function removeOrder(row) {
  try {
    await ElMessageBox.confirm(`确认删除采购单 #${row.order_id}？关联报价管理记录也会删除，但长期材料历史会保留。`, '删除确认', { type: 'warning' })
    await ordersApi.remove(row.order_id)
    ElMessage.success('采购单已删除')
    await load()
  } catch (error) {
    // 取消确认或请求失败均由对话框/请求拦截器处理。
  }
}

async function handleCreate() {
  if (!newForm.project_id) {
    ElMessage.warning('请选择项目')
    return
  }
  try {
    const data = await orderStore.createOrder(newForm.project_id, newForm.name, newForm.remark)
    ElMessage.success('采购单已创建')
    showCreate.value = false
    router.push(`/orders/${data.order_id}`)
  } catch {}
}
</script>

<style scoped>
.page-layout > * { flex-shrink: 0; }
.page-layout {
  padding: 24px;
  height: 100vh;
  min-height: 0;
  max-height: 100vh;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-title { display: flex; align-items: center; gap: 4px; }

.page-header h2 {
  font-size: 20px;
  font-weight: 600;
  color: #303133;
}

.filter-bar {
  display: flex;
  gap: 12px;
}

.order-number { color: #909399; }
</style>
