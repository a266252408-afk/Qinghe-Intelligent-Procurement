<template>
  <div class="login-page">
    <div class="login-card">
      <div class="logo">
        <el-icon size="36" color="#409eff"><Tree /></el-icon>
        <h1>园林采购助手</h1>
      </div>

      <el-tabs v-model="activeTab">
        <el-tab-pane label="登录" name="login">
          <el-form :model="loginForm" @submit.prevent="handleLogin" label-position="top">
            <el-form-item label="用户名">
              <el-input v-model="loginForm.username" placeholder="输入用户名" />
            </el-form-item>
            <el-form-item label="密码">
              <el-input
                v-model="loginForm.password"
                type="password"
                placeholder="输入密码"
                show-password
                @keyup.enter="handleLogin"
              />
            </el-form-item>
            <el-button type="primary" :loading="loading" style="width:100%" @click="handleLogin">
              登录
            </el-button>
          </el-form>
        </el-tab-pane>

        <el-tab-pane label="注册" name="register">
          <el-form :model="loginForm" label-position="top">
            <el-form-item label="用户名">
              <el-input v-model="loginForm.username" placeholder="设置用户名" />
            </el-form-item>
            <el-form-item label="密码">
              <el-input v-model="loginForm.password" type="password" placeholder="设置密码" show-password />
            </el-form-item>
            <el-form-item label="账号类型">
              <el-radio-group v-model="loginForm.accountType">
                <el-radio label="admin">管理员</el-radio>
                <el-radio label="purchaser">普通采购员</el-radio>
              </el-radio-group>
            </el-form-item>
            <el-form-item v-if="loginForm.accountType === 'admin'" label="团队名称">
              <el-input v-model="loginForm.teamName" placeholder="管理员注册时创建团队" />
            </el-form-item>
            <el-button type="primary" :loading="loading" style="width:100%" @click="handleRegister">
              注册
            </el-button>
          </el-form>
        </el-tab-pane>
      </el-tabs>

      <div v-if="loggedInNoTeam" class="pending-panel">
        <el-alert title="当前账号还未加入团队，请等待管理员发来邀请。" type="info" :closable="false" />
        <div v-if="authStore.invitations.length" class="invitation-list">
          <div v-for="item in authStore.invitations" :key="item.invitation_id" class="invitation-item">
            <span>{{ item.inviter_username }} 邀请你加入「{{ item.team_name }}」</span>
            <span class="invitation-actions">
              <el-button type="primary" size="small" @click="acceptInvitation(item)">同意</el-button>
              <el-button size="small" @click="rejectInvitation(item)">拒绝</el-button>
            </span>
          </div>
        </div>
        <div v-else class="empty-invitation">暂无待处理邀请</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()

const activeTab = ref('login')
const loading = ref(false)
const loggedInNoTeam = ref(false)  // 已登录但未绑定团队

const loginForm = reactive({ username: '', password: '', accountType: 'purchaser', teamName: '' })

onMounted(async () => {
  if (!authStore.token) return
  try {
    await authStore.refresh()
    if (authStore.hasTeam) router.push('/')
    else {
      loggedInNoTeam.value = true
      await authStore.fetchInvitations()
    }
  } catch {}
})

async function handleLogin() {
  if (!loginForm.username || !loginForm.password) {
    ElMessage.warning('请填写用户名和密码')
    return
  }
  loading.value = true
  try {
    await authStore.login(loginForm.username, loginForm.password)
    if (authStore.hasTeam) {
      router.push('/')
    } else {
      loggedInNoTeam.value = true
      await loadPendingInvitations()
      ElMessage.info('登录成功，请等待管理员邀请')
    }
  } catch {
    // 错误已由 axios 拦截器展示
  } finally {
    loading.value = false
  }
}

async function handleRegister() {
  if (!loginForm.username || !loginForm.password) {
    ElMessage.warning('请填写用户名和密码')
    return
  }
  if (loginForm.accountType === 'admin' && !loginForm.teamName.trim()) {
    ElMessage.warning('管理员注册必须填写团队名称')
    return
  }
  loading.value = true
  try {
    await authStore.register(
      loginForm.username,
      loginForm.password,
      loginForm.accountType,
      loginForm.teamName.trim(),
    )
    if (authStore.hasTeam) {
      ElMessage.success('管理员注册成功，团队已创建')
      router.push('/')
    } else {
      loggedInNoTeam.value = true
      await loadPendingInvitations()
      ElMessage.success('采购员注册成功，请等待管理员邀请')
    }
  } catch {
    // 错误已由 axios 拦截器展示
  } finally {
    loading.value = false
  }
}

async function loadPendingInvitations() {
  await authStore.fetchInvitations()
}

async function acceptInvitation(item) {
  loading.value = true
  try {
    await authStore.acceptInvitation(item.invitation_id)
    ElMessage.success(`已加入团队「${item.team_name}」`)
    router.push('/')
  } catch {
    // 错误已由 axios 拦截器展示
  } finally {
    loading.value = false
  }
}

async function rejectInvitation(item) {
  try {
    await authStore.rejectInvitation(item.invitation_id)
  } catch {
    // 错误已由 axios 拦截器展示
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #e8f4f8 0%, #d4edda 100%);
}

.login-card {
  width: 400px;
  background: white;
  border-radius: 12px;
  padding: 32px;
  box-shadow: 0 4px 24px rgba(0,0,0,0.1);
}

.logo {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 28px;
}

.logo h1 {
  font-size: 20px;
  color: #303133;
  font-weight: 600;
}

.pending-panel {
  margin-top: 20px;
}

.invitation-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 12px;
}

.invitation-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 10px;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: 13px;
}

.invitation-actions {
  display: flex;
  flex-shrink: 0;
}

.empty-invitation {
  padding: 16px 0;
  text-align: center;
  color: #909399;
  font-size: 13px;
}
</style>
