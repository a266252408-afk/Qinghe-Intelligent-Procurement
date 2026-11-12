<template>
  <el-container class="app-sidebar">
    <!-- 用户信息 -->
    <div class="user-info">
      <div class="user-main">
        <el-avatar :size="32" :icon="UserFilled" />
        <div class="user-meta">
          <div class="identity-line">
            <span class="username" :title="authStore.username">{{ authStore.username }}</span>
            <el-tag size="small" :type="authStore.role === 'owner' ? 'warning' : 'info'">
              {{ authStore.role === 'owner' ? '管理员' : '成员' }}
            </el-tag>
          </div>
          <span v-if="authStore.teamName" class="team-name" :title="authStore.teamName">{{ authStore.teamName }}</span>
        </div>
      </div>
      <div class="user-actions">
        <el-tooltip v-if="authStore.role === 'owner'" content="邀请采购员" placement="bottom">
          <el-button text :icon="UserFilled" aria-label="邀请采购员" @click="showInviteDialog = true" />
        </el-tooltip>
        <el-tooltip content="退出团队" placement="bottom">
          <el-button text :icon="CircleClose" aria-label="退出团队" @click="leaveTeam" />
        </el-tooltip>
        <el-tooltip content="退出登录" placement="bottom">
          <el-button text :icon="SwitchButton" aria-label="退出登录" @click="handleLogout" />
        </el-tooltip>
      </div>
    </div>

    <!-- 快速导航 -->
    <el-menu :router="true" :default-active="$route.path" class="nav-menu">
      <el-menu-item index="/">
        <el-icon><ChatDotRound /></el-icon>
        <span>对话</span>
      </el-menu-item>
      <el-menu-item index="/orders">
        <el-icon><Document /></el-icon>
        <span>采购单</span>
      </el-menu-item>
      <el-menu-item index="/quotes">
        <el-icon><Tickets /></el-icon>
        <span>报价管理</span>
      </el-menu-item>
      <el-menu-item index="/approvals">
        <el-icon><Checked /></el-icon>
        <span>审批</span>
        <el-badge
          v-if="approvalStore.total > 0"
          :value="approvalStore.total"
          class="approval-badge"
        />
      </el-menu-item>
      <el-menu-item index="/supplier-orders">
        <el-icon><ShoppingCart /></el-icon>
        <span>下单管理</span>
      </el-menu-item>
      <el-menu-item index="/receipts">
        <el-icon><Van /></el-icon>
        <span>收货管理</span>
      </el-menu-item>
      <el-menu-item index="/knowledge">
        <el-icon><Collection /></el-icon>
        <span>知识库</span>
      </el-menu-item>
      <el-menu-item index="/memory">
        <el-icon><Clock /></el-icon>
        <span>长期材料记忆</span>
      </el-menu-item>
    </el-menu>

    <el-divider style="margin: 8px 0" />

    <!-- 项目列表 -->
    <div class="section-title">
      <span>项目</span>
      <el-button text :icon="Plus" size="small" @click="showNewProject = true" />
    </div>
    <div class="project-list">
      <div
        v-for="p in projects"
        :key="p.project_id"
        class="project-item"
        :class="{ active: selectedProjectId === p.project_id }"
        @click="selectProject(p)"
      >
        <el-icon><FolderOpened /></el-icon>
        <span>{{ p.name }}</span>
        <el-button
          v-if="authStore.role === 'owner'"
          text
          :icon="Delete"
          size="small"
          title="删除项目"
          @click.stop="removeProject(p)"
        />
      </div>
      <div v-if="projects.length === 0" class="empty-hint">暂无项目</div>
    </div>

    <!-- 会话列表 -->
    <template v-if="selectedProjectId">
      <el-divider style="margin: 8px 0" />
      <div class="section-title">
        <span>对话</span>
        <el-button text :icon="Plus" size="small" @click="newSession" />
      </div>
      <div class="session-list">
        <div
          v-for="s in chatStore.sessions"
          :key="s.session_id"
          class="session-item"
          :class="{ active: chatStore.currentSessionId === s.session_id }"
          @click="chatStore.loadMessages(s.session_id)"
        >
          <el-icon><ChatLineRound /></el-icon>
          <span>{{ s.title }}</span>
          <el-button text :icon="Delete" size="small" title="删除对话" @click.stop="removeSession(s)" />
        </div>
        <div v-if="chatStore.sessions.length === 0" class="empty-hint">点击 + 新建对话</div>
      </div>
    </template>
  </el-container>

  <!-- 新建项目对话框 -->
  <el-dialog v-model="showNewProject" title="新建项目" width="360px">
    <el-input v-model="newProjectName" placeholder="项目名称" @keyup.enter="createProject" />
    <template #footer>
      <el-button @click="showNewProject = false">取消</el-button>
      <el-button type="primary" @click="createProject">创建</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="showInviteDialog" title="邀请采购员加入团队" width="420px">
    <el-form label-position="top">
      <el-form-item label="采购员用户名">
        <el-input v-model="inviteUsername" placeholder="输入已注册的采购员用户名" @keyup.enter="sendInvite" />
      </el-form-item>
    </el-form>
    <div v-if="pendingInvitations.length" class="sent-invitations">
      <div class="sent-title">已发出的邀请</div>
      <div v-for="item in pendingInvitations" :key="item.invitation_id" class="sent-item">
        <span>{{ item.invitee_username }}</span><el-tag size="small">等待确认</el-tag>
      </div>
    </div>
    <template #footer>
      <el-button @click="showInviteDialog = false">关闭</el-button>
      <el-button type="primary" @click="sendInvite">发送邀请</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { SwitchButton, CircleClose, Plus, Delete, UserFilled, Tickets, Clock, ShoppingCart, Van } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { useChatStore } from '@/stores/chat'
import { useApprovalStore } from '@/stores/approval'
import { projectsApi } from '@/api/projects'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const chatStore = useChatStore()
const approvalStore = useApprovalStore()

const projects = ref([])
const selectedProjectId = ref(null)
const showNewProject = ref(false)
const newProjectName = ref('')
const showInviteDialog = ref(false)
const inviteUsername = ref('')
const pendingInvitations = computed(() =>
  authStore.invitations.filter((item) => item.status === 'pending'),
)

onMounted(async () => {
  await authStore.refresh()
  await authStore.fetchInvitations()
  await loadProjects()
  if (projects.value.length > 0) await restoreProject()
  if (authStore.role === 'owner') await approvalStore.fetchPending()
  else approvalStore.clearPending()
})

async function loadProjects() {
  try {
    const data = await projectsApi.list()
    projects.value = data.items ?? data
  } catch {}
}

async function restoreProject() {
  const savedId = sessionStorage.getItem(chatStore.storageKey('project'))
  const project = projects.value.find((item) => String(item.project_id) === savedId)
  await selectProject(project || projects.value[0])
}

async function selectProject(p) {
  selectedProjectId.value = p.project_id
  chatStore.saveSelection(p.project_id)
  chatStore.resetConversation()
  const savedSessionId = sessionStorage.getItem(chatStore.storageKey('session'))
  try {
    await chatStore.loadSessions(p.project_id, savedSessionId)
  } catch {
    chatStore.resetConversation()
  }
}

async function newSession() {
  if (!selectedProjectId.value) return
  await chatStore.createSession(selectedProjectId.value, '新对话')
  router.push('/')
}

async function createProject() {
  if (!newProjectName.value.trim()) return
  try {
    const data = await projectsApi.create(newProjectName.value.trim())
    projects.value.unshift(data)
    await selectProject(data)
    showNewProject.value = false
    newProjectName.value = ''
    ElMessage.success('项目已创建')
  } catch {}
}

async function sendInvite() {
  const username = inviteUsername.value.trim()
  if (!username) {
    ElMessage.warning('请输入采购员用户名')
    return
  }
  try {
    await authStore.sendInvitation(username)
    inviteUsername.value = ''
    ElMessage.success('邀请已发送，等待采购员确认')
  } catch {}
}

async function removeProject(project) {
  try {
    await ElMessageBox.confirm(`确认删除项目“${project.name}”？`, '删除确认', { type: 'warning' })
  } catch {
    return
  }
  try {
    await projectsApi.remove(project.project_id)
    projects.value = projects.value.filter((item) => item.project_id !== project.project_id)
    if (selectedProjectId.value === project.project_id) {
      selectedProjectId.value = null
      chatStore.resetConversation()
      if (projects.value.length > 0) await selectProject(projects.value[0])
      else chatStore.clearSelection()
    }
    ElMessage.success('项目已删除')
  } catch {}
}

async function removeSession(session) {
  try {
    await ElMessageBox.confirm(`确认删除对话“${session.title}”？`, '删除确认', { type: 'warning' })
  } catch {
    return
  }
  try {
    await chatStore.deleteSession(session.session_id)
    ElMessage.success('对话已删除')
  } catch {}
}

function handleLogout() {
  authStore.logout()
  router.push('/login')
}

async function leaveTeam() {
  try {
    await ElMessageBox.confirm('退出团队后，当前账号需要重新接受邀请或加入其他团队。确认退出？', '退出团队', { type: 'warning' })
    await authStore.leaveTeam()
    ElMessage.success('已退出团队')
    router.push('/login')
  } catch {}
}
</script>

<style scoped>
.app-sidebar {
  width: 260px;
  height: 100%;
  background: #f5f7fa;
  border-right: 1px solid #e4e7ed;
  display: flex;
  flex-direction: column;
  padding: 12px 0;
  overflow: hidden;
}

.user-info {
  position: relative;
  min-height: 72px;
  padding: 12px 12px 10px;
  border-bottom: 1px solid #e4e7ed;
}

.user-main {
  display: flex;
  align-items: flex-start;
  gap: 9px;
  min-width: 0;
  padding-right: 96px;
}

.user-meta {
  min-width: 0;
  padding-top: 1px;
}

.identity-line {
  display: flex;
  align-items: center;
  min-width: 0;
  gap: 6px;
  line-height: 20px;
}

.identity-line :deep(.el-tag) {
  flex: 0 0 auto;
}

.user-actions {
  position: absolute;
  top: 10px;
  right: 10px;
  display: flex;
  align-items: center;
  gap: 2px;
}

.user-actions :deep(.el-button) {
  width: 28px;
  height: 28px;
  margin: 0;
  padding: 0;
}

.user-actions :deep(.el-icon) {
  font-size: 16px;
}

.username {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  font-weight: 500;
  color: #303133;
}

.team-name {
  display: block;
  max-width: 100%;
  margin-top: 3px;
  color: #606266;
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sent-invitations {
  border-top: 1px solid #ebeef5;
  padding-top: 12px;
}

.sent-title {
  color: #909399;
  font-size: 12px;
  margin-bottom: 8px;
}

.sent-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 0;
  font-size: 13px;
}

.nav-menu {
  background: transparent;
  border: none;
  padding: 4px 8px;
}

.nav-menu :deep(.el-menu-item) {
  height: 36px;
  border-radius: 6px;
  margin: 2px 0;
  position: relative;
}

.section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 16px;
  font-size: 12px;
  color: #909399;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.project-list,
.session-list {
  flex: 1;
  overflow-y: auto;
  padding: 0 8px;
}

.project-item,
.session-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  color: #606266;
  transition: background 0.15s;
}

.project-item:hover,
.session-item:hover {
  background: #e4e7ed;
}

.project-item.active,
.session-item.active {
  background: #ecf5ff;
  color: #409eff;
}

.empty-hint {
  font-size: 12px;
  color: #c0c4cc;
  text-align: center;
  padding: 12px 0;
}

.approval-badge {
  position: absolute;
  top: 50%;
  right: 16px;
  transform: translateY(-50%);
  line-height: 18px;
}

.approval-badge :deep(.el-badge__content.is-fixed) {
  position: static;
  transform: none;
}
</style>
