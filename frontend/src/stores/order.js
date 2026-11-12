import { defineStore } from 'pinia'
import { ref } from 'vue'
import { ordersApi } from '@/api/orders'

export const useOrderStore = defineStore('order', () => {
  const orders = ref([])
  const currentOrder = ref(null)
  const total = ref(0)

  async function fetchOrders(params) {
    const data = await ordersApi.list(params)
    orders.value = data.items
    total.value = data.total
  }

  async function fetchOrder(id) {
    currentOrder.value = await ordersApi.get(id)
  }

  async function createOrder(projectId, name, remark) {
    const data = await ordersApi.create(projectId, name, remark)
    orders.value.unshift(data)
    return data
  }

  async function updateOrder(id, data) {
    const result = await ordersApi.update(id, data)
    if (currentOrder.value?.order_id === id) currentOrder.value = result
    return result
  }

  async function saveItems(id, items) {
    return ordersApi.saveItems(id, items)
  }

  async function submitOrder(id) {
    const data = await ordersApi.submit(id)
    if (currentOrder.value?.order_id === id) currentOrder.value.status = data.status
    return data
  }

  function reset() {
    orders.value = []
    currentOrder.value = null
    total.value = 0
  }

  return {
    orders, currentOrder, total,
    fetchOrders, fetchOrder, createOrder, updateOrder, saveItems, submitOrder, reset,
  }
})
