<template>
  <div class="page-layout">
    <div class="page-header">
      <div class="header-title"><el-button text :icon="ArrowLeft" title="返回上一页" @click="$router.back()" /><h2>待审批下单申请</h2></div>
      <el-button text :icon="Refresh" @click="load">刷新</el-button>
    </div>

    <el-table v-if="canApprove" :data="approvalStore.pendingList" v-loading="loading" style="width:100%">
      <el-table-column label="采购单" min-width="180">
        <template #default="{ row }">
          <div>{{ row.name || `采购单 #${row.order_id}` }}</div>
          <small v-if="row.name" class="order-number">#{{ row.order_id }}</small>
        </template>
      </el-table-column>
      <el-table-column label="提交人" prop="creator_name" width="100" />
      <el-table-column label="总金额" width="120">
        <template #default="{ row }">
          {{ row.total_amount ? `¥${row.total_amount.toFixed(2)}` : '-' }}
        </template>
      </el-table-column>
      <el-table-column label="提交时间" width="160">
        <template #default="{ row }">{{ fmtDate(row.submitted_at || row.updated_at) }}</template>
      </el-table-column>
      <el-table-column label="备注" prop="remark" show-overflow-tooltip />
      <el-table-column label="操作" width="160" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="success" @click="handleApprove(row.order_id)">通过下单</el-button>
          <el-button size="small" type="danger" @click="openRejectDialog(row.order_id)">驳回下单</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div v-if="!canApprove" class="empty-hint">
      <el-icon size="48" color="#c0c4cc"><Checked /></el-icon>
      <p>当前账号没有审批权限</p>
    </div>
    <div v-else-if="approvalStore.pendingList.length === 0 && !loading" class="empty-hint">
      <el-icon size="48" color="#c0c4cc"><Checked /></el-icon>
      <p>暂无待审批下单申请</p>
    </div>
  </div>

  <!-- 驳回对话框 -->
  <el-dialog v-model="rejectDialogVisible" title="驳回原因" width="360px">
    <el-input
      v-model="rejectReason"
      type="textarea"
      :rows="3"
      placeholder="请填写驳回原因（必填）"
    />
    <template #footer>
      <el-button @click="rejectDialogVisible = false">取消</el-button>
    <el-button type="danger" @click="handleReject">确认驳回下单</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { ArrowLeft, Refresh } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { useApprovalStore } from '@/stores/approval'

const authStore = useAuthStore()
const approvalStore = useApprovalStore()
const canApprove = computed(() => authStore.role === 'owner')
const loading = ref(false)
const rejectDialogVisible = ref(false)
const rejectReason = ref('')
const rejectTargetId = ref(null)

function fmtDate(dt) {
  return dt ? new Date(dt).toLocaleString('zh-CN') : '-'
}

async function load() {
  if (!canApprove.value) {
    approvalStore.clearPending()
    return
  }
  loading.value = true
  try {
    await approvalStore.fetchPending()
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  if (canApprove.value) await load()
  else approvalStore.clearPending()
})

async function handleApprove(id) {
  loading.value = true
  try {
    await approvalStore.approve(id)
    ElMessage.success('下单申请已通过')
  } finally {
    loading.value = false
  }
}

function openRejectDialog(id) {
  rejectTargetId.value = id
  rejectReason.value = ''
  rejectDialogVisible.value = true
}

async function handleReject() {
  if (!rejectReason.value.trim()) {
    ElMessage.warning('驳回原因不能为空')
    return
  }
  loading.value = true
  try {
    await approvalStore.reject(rejectTargetId.value, rejectReason.value.trim())
    rejectDialogVisible.value = false
    ElMessage.success('下单申请已驳回，可修改后重新提交')
  } finally {
    loading.value = false
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
}

.order-number { color: #909399; }

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

.empty-hint {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 48px 0;
  color: #c0c4cc;
  font-size: 14px;
}
</style>
