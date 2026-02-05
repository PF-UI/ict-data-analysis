<template>
  <div class="salary-distribution-container">
    <el-card>
      <template #header>
        <div class="card-header">
          <h3>2022-2025年薪资分布图</h3>
        </div>
      </template>

      <!-- 所有年份图表网格布局 -->
      <div class="charts-grid">
        <div
          v-for="year in years"
          :key="year"
          class="chart-wrapper"
        >
          <div class="chart-title">{{ year }}年薪资分布</div>
          <div
            :ref="el => setChartRef(el, year)"
            :data-year="year"
            class="chart-container"
            v-loading="loadingCharts[year]"
          ></div>
          <div class="chart-summary" v-if="statisticsData">
            共 {{ getYearTotal(year) }} 个职位
          </div>
        </div>
      </div>

      <!-- 统计信息 -->
      <div v-if="statisticsData" class="statistics-info">
        <el-descriptions title="年度统计汇总" :column="4" border>
          <el-descriptions-item
            v-for="year in statisticsData.years"
            :key="year"
            :label="`${year}年`"
          >
            {{ getYearTotal(year) }} 个职位
          </el-descriptions-item>
        </el-descriptions>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import * as echarts from 'echarts'
import { jobListingService, type SalaryStatistics } from '@/services/jobListing'
import { ElMessage } from 'element-plus'

const years = ref<number[]>([2022, 2023, 2024, 2025])
const loadingCharts = ref<Record<number, boolean>>({})
const statisticsData = ref<SalaryStatistics | null>(null)
const chartInstances = ref<Record<number, echarts.ECharts | null>>({})
const chartElements = ref<Record<number, HTMLElement | null>>({})

// 检查元素是否有尺寸
const waitForElementSize = (element: HTMLElement, maxAttempts = 10): Promise<boolean> => {
  return new Promise((resolve) => {
    let attempts = 0
    const checkSize = () => {
      attempts++
      if (element.clientWidth > 0 && element.clientHeight > 0) {
        resolve(true)
      } else if (attempts >= maxAttempts) {
        console.warn(`元素在 ${maxAttempts} 次尝试后仍没有尺寸`)
        resolve(false)
      } else {
        setTimeout(checkSize, 100)
      }
    }
    checkSize()
  })
}

// 设置图表引用（只保存引用，不初始化）
const setChartRef = (el: any, year: number) => {
  if (el && el instanceof HTMLElement) {
    chartElements.value[year] = el
  }
}

// 初始化单个图表
const initChart = async (year: number, el: HTMLElement, data: SalaryStatistics) => {
  // 等待元素有尺寸
  const hasSize = await waitForElementSize(el)
  if (!hasSize) {
    console.error(`图表容器 ${year} 年没有尺寸`)
    loadingCharts.value[year] = false
    return
  }

  // 检查是否已经初始化
  if (!chartInstances.value[year]) {
    try {
      chartInstances.value[year] = echarts.init(el)
    } catch (error) {
      console.error(`初始化图表 ${year} 失败:`, error)
      loadingCharts.value[year] = false
      return
    }
  }

  // 渲染图表
  renderYearChart(year, data)
}

// 加载薪资统计数据
const loadSalaryStatistics = async () => {
  try {
    const data: SalaryStatistics = await jobListingService.getSalaryStatistics(2022, 2025)
    statisticsData.value = data
    
    // 更新年份列表（基于实际数据）
    if (data.years.length > 0) {
      years.value = data.years
    }

    // 等待DOM完全渲染
    await nextTick()
    
    // 再次等待，确保所有元素都已渲染并有尺寸
    await new Promise(resolve => setTimeout(resolve, 100))
    
    // 初始化所有图表
    for (const year of years.value) {
      const el = chartElements.value[year]
      if (el) {
        loadingCharts.value[year] = true
        initChart(year, el, data).finally(() => {
          loadingCharts.value[year] = false
        })
      } else {
        // 如果ref还没有设置，尝试通过选择器查找
        setTimeout(async () => {
          const foundEl = document.querySelector(`[data-year="${year}"]`) as HTMLElement
          if (foundEl) {
            chartElements.value[year] = foundEl
            loadingCharts.value[year] = true
            await initChart(year, foundEl, data)
            loadingCharts.value[year] = false
          }
        }, 200)
      }
    }
  } catch (error: any) {
    ElMessage.error('加载薪资统计数据失败: ' + (error.response?.data?.detail || error.message))
    console.error(error)
  }
}

// 渲染某年的饼图
const renderYearChart = (year: number, data: SalaryStatistics) => {
  const chartInstance = chartInstances.value[year]
  if (!chartInstance) {
    return
  }

  const yearData = data.data[year]
  if (!yearData) {
    return
  }

  // 准备饼图数据（过滤掉为0的数据）
  const pieData = data.categories
    .filter(category => (yearData[category] || 0) > 0)
    .map(category => ({
      name: category,
      value: yearData[category] || 0
    }))

  if (pieData.length === 0) {
    return
  }

  const option: echarts.EChartsOption = {
    tooltip: {
      trigger: 'item',
      formatter: '{a} <br/>{b}: {c} ({d}%)',
      backgroundColor: 'rgba(50, 50, 50, 0.9)',
      borderColor: '#333',
      textStyle: {
        color: '#fff'
      }
    },
    legend: {
      orient: 'vertical',
      left: 'left',
      top: 'middle',
      textStyle: {
        fontSize: 12
      },
      formatter: (name: string) => {
        const item = pieData.find(d => d.name === name)
        return item ? `${name} (${item.value})` : name
      }
    },
    series: [
      {
        name: `${year}年薪资分布`,
        type: 'pie',
        radius: ['40%', '70%'], // 环形图
        center: ['60%', '50%'],
        avoidLabelOverlap: false,
        itemStyle: {
          borderRadius: 10,
          borderColor: '#fff',
          borderWidth: 2
        },
        label: {
          show: true,
          formatter: '{d}%',
          fontSize: 12
        },
        emphasis: {
          label: {
            show: true,
            fontSize: 14,
            fontWeight: 'bold'
          },
          itemStyle: {
            shadowBlur: 10,
            shadowOffsetX: 0,
            shadowColor: 'rgba(0, 0, 0, 0.5)'
          }
        },
        data: pieData
      }
    ],
    color: [
      '#5470c6', '#91cc75', '#fac858', '#ee6666',
      '#73c0de', '#3ba272', '#fc8452', '#9a60b4', '#ea7ccc'
    ]
  }

  chartInstance.setOption(option, true)
}

// 计算某年份的总职位数
const getYearTotal = (year: number): number => {
  if (!statisticsData.value) return 0
  const yearData = statisticsData.value.data[year]
  if (!yearData) return 0
  return Object.values(yearData).reduce((sum, count) => sum + count, 0)
}

// 响应式调整
const handleResize = () => {
  Object.values(chartInstances.value).forEach(instance => {
    if (instance) {
      instance.resize()
    }
  })
}

onMounted(async () => {
  // 等待一个tick确保DOM已渲染
  await nextTick()
  await loadSalaryStatistics()
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  Object.values(chartInstances.value).forEach(instance => {
    if (instance) {
      instance.dispose()
    }
  })
  window.removeEventListener('resize', handleResize)
})
</script>

<style scoped>
.salary-distribution-container {
  width: 100%;
}

.card-header h3 {
  margin: 0;
  color: #303133;
  font-size: 18px;
  font-weight: 600;
}

.charts-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 24px;
  margin-bottom: 30px;
}

.chart-wrapper {
  background: #fafafa;
  border-radius: 8px;
  padding: 20px;
  border: 1px solid #ebeef5;
}

.chart-title {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 16px;
  text-align: center;
}

.chart-container {
  width: 100%;
  height: 400px;
  min-height: 350px;
}

.chart-summary {
  text-align: center;
  margin-top: 12px;
  color: #606266;
  font-size: 14px;
}

.statistics-info {
  margin-top: 30px;
  padding-top: 20px;
  border-top: 1px solid #ebeef5;
}

/* 响应式调整 */
@media (max-width: 1200px) {
  .charts-grid {
    grid-template-columns: 1fr;
  }
  
  .chart-container {
    height: 450px;
  }
}

@media (max-width: 768px) {
  .chart-container {
    height: 350px;
  }
  
  .chart-wrapper {
    padding: 15px;
  }
}
</style>

