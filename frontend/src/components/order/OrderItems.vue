<template>
  <div class="items-table-scroll">
    <el-table
      :data="items"
      style="width:100%;min-width:980px"
      :row-class-name="() => 'item-row'"
    >
    <el-table-column label="品种" prop="species" min-width="120">
      <template #default="{ row, $index }">
        <el-input v-if="editable" v-model="row.species" size="small" />
        <span v-else>{{ row.species }}</span>
      </template>
    </el-table-column>
    <el-table-column label="规格" prop="spec" min-width="120">
      <template #default="{ row }">
        <el-input v-if="editable" v-model="row.spec" size="small" placeholder="如：胸径15cm" />
        <span v-else>{{ row.spec || '-' }}</span>
      </template>
    </el-table-column>
    <el-table-column label="数量" prop="quantity" width="90">
      <template #default="{ row }">
        <el-input-number v-if="editable" v-model="row.quantity" :min="0.01" size="small" controls-position="right" />
        <span v-else>{{ row.quantity }}</span>
      </template>
    </el-table-column>
    <el-table-column label="单位" prop="unit" width="80">
      <template #default="{ row }">
        <el-input v-if="editable" v-model="row.unit" size="small" placeholder="株" />
        <span v-else>{{ row.unit }}</span>
      </template>
    </el-table-column>
    <el-table-column label="单价(元)" prop="unit_price" width="110">
      <template #default="{ row }">
        <el-input-number v-if="editable" v-model="row.unit_price" :min="0" size="small" controls-position="right" :precision="2" />
        <span v-else>{{ row.unit_price ?? '-' }}</span>
      </template>
    </el-table-column>
    <el-table-column label="小计(元)" width="100">
      <template #default="{ row }">
        <el-input-number v-if="editable" v-model="row.total_price" :min="0" :precision="2" size="small" controls-position="right" />
        <span v-else>{{ row.total_price ?? (row.unit_price ? (row.quantity * row.unit_price).toFixed(2) : '-') }}</span>
      </template>
    </el-table-column>
    <template v-if="supplierOptions.length">
      <el-table-column label="供应商" min-width="170">
        <template #default="{ row }">
          <el-select
            v-if="editable && optionsFor(row).length"
            v-model="row.supplier_quote_item_id"
            size="small"
            placeholder="选择供应商"
            @change="selectSupplier(row, $event)"
          >
            <el-option
              v-for="option in optionsFor(row)"
              :key="option.quote_item_id"
              :label="option.supplier_name"
              :value="option.quote_item_id"
            />
          </el-select>
          <span v-else>{{ row.supplier_name || '-' }}</span>
        </template>
      </el-table-column>
    </template>
    <el-table-column label="成交价(元)" width="130">
        <template #default="{ row }">
          <el-input-number
            v-if="editable"
            v-model="row.final_price"
            :min="0"
            :precision="2"
            size="small"
            controls-position="right"
          />
          <span v-else>{{ row.final_price ?? '-' }}</span>
        </template>
    </el-table-column>
    <el-table-column label="供应商报价(元)" width="140">
        <template #default="{ row }">
          <el-input-number v-if="editable" v-model="row.supplier_quote_price" :min="0" :precision="2" size="small" controls-position="right" />
          <span v-else>{{ row.supplier_quote_price ?? '-' }}</span>
        </template>
    </el-table-column>
    <el-table-column v-if="editable" label="" width="50" fixed="right">
      <template #default="{ $index }">
        <el-button text type="danger" :icon="Delete" size="small" @click="removeRow($index)" />
      </template>
    </el-table-column>
    </el-table>
  </div>

  <div v-if="editable" style="margin-top:8px">
    <el-button text type="primary" :icon="Plus" size="small" @click="addRow">添加一行</el-button>
  </div>
</template>

<script setup>
import { Delete, Plus } from '@element-plus/icons-vue'

const props = defineProps({
  items: { type: Array, default: () => [] },
  editable: { type: Boolean, default: false },
  supplierOptions: { type: Array, default: () => [] },
})

const emit = defineEmits(['update:items'])

function addRow() {
  props.items.push({
    species: '', spec: '', quantity: 1, unit: '株', unit_price: null,
    total_price: null, supplier_name: null, supplier_quote_price: null, final_price: null,
  })
}

function removeRow(idx) {
  props.items.splice(idx, 1)
}

function optionsFor(row) {
  return props.supplierOptions.find((item) => item.item_id === row.item_id)?.suppliers ?? []
}

function selectSupplier(row, quoteItemId) {
  const option = optionsFor(row).find((item) => item.quote_item_id === quoteItemId)
  if (!option) return
  row.supplier_name = option.supplier_name
  row.supplier_quote_price = option.unit_price
  row.final_price = option.unit_price
  row.total_price = row.quantity && option.unit_price
    ? Number(row.quantity) * Number(option.unit_price)
    : null
}
</script>

<style scoped>
/* 纵向不再限高：行数多时随页面滚动完整展示，避免最后一行被容器截断；仅保留横向滚动 */
.items-table-scroll {
  overflow-x: auto;
}
</style>
