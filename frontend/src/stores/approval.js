import { defineStore } from 'pinia'
import { ref } from 'vue'
import { approvalsApi } from '@/api/approvals'

export const useApprovalStore = defineStore('approval', () => {
  const pendingList = ref([])
  const total = ref(0)

  function clearPending() {
    pendingList.value = []
    total.value = 0
  }

  async function fetchPending() {
    const data = await approvalsApi.list()
    pendingList.value = data.items ?? data
    total.value = data.total ?? pendingList.value.length
  }

  async function approve(id) {
    const data = await approvalsApi.approve(id)
    pendingList.value = pendingList.value.filter((o) => o.order_id !== id)
    return data
  }

  async function reject(id, reason) {
    const data = await approvalsApi.reject(id, reason)
    pendingList.value = pendingList.value.filter((o) => o.order_id !== id)
    return data
  }

  return { pendingList, total, clearPending, fetchPending, approve, reject }
})
