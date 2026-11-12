<template>
  <div>
    <!-- 各供应商报价总额：图 + 表相邻，两种展现方式对照查看 -->
    <div class="chart-section">
      <div class="section-title">各供应商报价总额</div>
      <div ref="barEl" class="chart" />
      <el-table
        v-if="data?.supplier_quote_totals?.length"
        :data="data.supplier_quote_totals"
        border
        size="small"
      >
        <el-table-column prop="supplier_name" label="供应商" min-width="180" />
        <el-table-column prop="total_price" label="报价总额（元）" min-width="150" />
      </el-table>
    </div>

    <!-- 相同材料、相同规格供应商单价：横向条形图（材料多时纵向排布不挤）+ 明细表相邻 -->
    <div class="chart-section">
      <div class="section-title">相同材料、相同规格供应商单价</div>
      <div ref="materialEl" class="chart" :style="{ height: materialChartHeight }" />
      <el-table
        v-if="data?.material_price_comparisons?.length"
        :data="data.material_price_comparisons"
        border
        size="small"
        max-height="420"
      >
        <el-table-column label="材料" prop="species" min-width="130" fixed />
        <el-table-column label="规格" prop="spec" min-width="130" />
        <el-table-column label="单位" prop="unit" width="80" />
        <el-table-column
          v-for="supplier in materialSuppliers"
          :key="supplier"
          :label="supplier"
          min-width="110"
        >
          <template #default="{ row }">{{ materialPrice(row, supplier) ?? '-' }}</template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 多维度评分对比：分组柱状图替代雷达图，供应商少时对比更直观 -->
    <div class="chart-section">
      <div class="section-title">多维度评分对比（满分100）</div>
      <div ref="dimensionEl" class="chart" />
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  data: { type: Object, default: () => ({}) },
})

const barEl = ref(null)
const materialEl = ref(null)
const dimensionEl = ref(null)
let barChart = null
let materialChart = null
let dimensionChart = null

// 与前端柱状图配色保持一致的供应商色板（图例与表格上方图对应）
const SUPPLIER_COLORS = ['#5470c6', '#91cc75', '#fac858', '#ee6666', '#73c0de', '#3ba272', '#fc8452', '#9a60b4']

const materialSuppliers = computed(() => [
  ...new Set(
    (props.data?.material_price_comparisons ?? []).flatMap((item) =>
      item.suppliers.map((supplier) => supplier.supplier_name),
    ),
  ),
])

// 材料数量多时按行数增高图表，避免窗口内放不下
const materialChartHeight = computed(() => {
  const count = props.data?.material_price_comparisons?.length ?? 0
  return `${Math.max(280, count * 46 + 110)}px`
})

function materialPrice(row, supplierName) {
  return row.suppliers.find((supplier) => supplier.supplier_name === supplierName)?.unit_price
}

function renderBar(data) {
  if (!barEl.value) return
  if (!barChart) barChart = echarts.init(barEl.value)
  const totals = data?.supplier_quote_totals ?? []
  barChart.setOption(
    {
      tooltip: { trigger: 'axis' },
      grid: { left: 56, right: 24, top: 24, bottom: 32 },
      xAxis: { type: 'category', data: totals.map((item) => item.supplier_name) },
      yAxis: { type: 'value', name: '元' },
      series: [
        {
          type: 'bar',
          data: totals.map((item) => item.total_price),
          itemStyle: { borderRadius: [4, 4, 0, 0], color: '#409eff' },
          label: { show: true, position: 'top' },
          barMaxWidth: 56,
        },
      ],
    },
    true,
  )
}

function renderMaterialPrices(data) {
  if (!materialEl.value) return
  if (!materialChart) materialChart = echarts.init(materialEl.value)
  const comparisons = data?.material_price_comparisons ?? []
  if (comparisons.length === 0) {
    materialChart.clear()
    return
  }
  const supplierNames = materialSuppliers.value
  // 横向条形图：Y 轴为“材料 + 规格/单位”完整信息，不再斜排截断
  const labels = comparisons.map(
    (item) => `${item.species} ${item.spec || '未填写规格'}${item.unit ? `/${item.unit}` : ''}`,
  )
  materialChart.setOption(
    {
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      legend: { data: supplierNames, type: 'scroll', top: 0 },
      grid: { left: 190, right: 48, top: 36, bottom: 24, containLabel: false },
      xAxis: { type: 'value', name: '元' },
      yAxis: {
        type: 'category',
        data: labels,
        inverse: true,
        axisLabel: { fontSize: 12, interval: 0, width: 180, overflow: 'break' },
        axisTick: { show: false },
      },
      series: supplierNames.map((name) => ({
        name,
        type: 'bar',
        barMaxWidth: 14,
        data: comparisons.map(
          (item) => item.suppliers.find((supplier) => supplier.supplier_name === name)?.unit_price ?? null,
        ),
        label: { show: true, position: 'right', fontSize: 11 },
      })),
      color: SUPPLIER_COLORS,
    },
    true,
  )
}

function renderDimensions(data) {
  if (!dimensionEl.value) return
  if (!dimensionChart) dimensionChart = echarts.init(dimensionEl.value)
  const scores = data?.suppliers ?? data?.scores ?? []
  if (scores.length === 0) {
    dimensionChart.clear()
    return
  }
  const dimensions = [
    { key: 'price_score', name: '价格分' },
    { key: 'history_score', name: '历史分' },
    { key: 'delivery_score', name: '交期分' },
    { key: 'payment_score', name: '付款分' },
  ]
  dimensionChart.setOption(
    {
      tooltip: { trigger: 'axis' },
      legend: { data: dimensions.map((item) => item.name), type: 'scroll', top: 0 },
      grid: { left: 48, right: 24, top: 36, bottom: 32 },
      xAxis: { type: 'category', data: scores.map((item) => item.supplier_name) },
      yAxis: { type: 'value', name: '分', max: 100 },
      series: dimensions.map((dimension) => ({
        name: dimension.name,
        type: 'bar',
        barMaxWidth: 22,
        data: scores.map((item) => Math.round((item[dimension.key] ?? 0) * 1000) / 10),
        label: { show: true, position: 'top', fontSize: 11 },
      })),
      color: SUPPLIER_COLORS,
    },
    true,
  )
}

onMounted(() => {
  renderBar(props.data)
  renderMaterialPrices(props.data)
  renderDimensions(props.data)
  window.addEventListener('resize', resizeCharts)
})

watch(() => props.data, (newData) => {
  renderBar(newData)
  renderMaterialPrices(newData)
  renderDimensions(newData)
})

watch(materialChartHeight, () => {
  // 行数变化引起高度变化后重排画布
  materialChart?.resize()
})

function resizeCharts() {
  barChart?.resize()
  materialChart?.resize()
  dimensionChart?.resize()
}

onUnmounted(() => {
  window.removeEventListener('resize', resizeCharts)
  barChart?.dispose()
  materialChart?.dispose()
  dimensionChart?.dispose()
})
</script>

<style scoped>
.chart {
  width: 100%;
  height: 220px;
}

.chart-section { margin-bottom: 8px; }
.chart-section + .chart-section { margin-top: 20px; }
.section-title { margin: 0 0 10px; color: #303133; font-weight: 600; }
.chart + .el-table { margin-top: 8px; }
</style>
