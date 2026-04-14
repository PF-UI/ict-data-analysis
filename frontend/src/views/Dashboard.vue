<template>
  <div class="dashboard-container">
    <!-- 两列布局：左侧招聘列表，右侧薪资分布 -->
    <el-row :gutter="20">
      <!-- 左侧：招聘信息列表 -->
      <el-col :xs="24" :sm="24" :md="14" :lg="14" :xl="14">
        <el-card class="dashboard-card">
          <template #header>
            <div class="card-header">
              <h3>招聘信息列表</h3>
            </div>
          </template>

          <!-- 搜索和筛选区域 -->
          <el-form :model="queryParams" inline class="search-form">
            <el-form-item label="关键词搜索">
              <el-input
                v-model="queryParams.search_keyword"
                placeholder="搜索职位、公司、要求等"
                clearable
                style="width: 300px"
                @keyup.enter="handleSearch"
              >
                <template #prefix>
                  <el-icon><Search /></el-icon>
                </template>
              </el-input>
            </el-form-item>

            <el-form-item label="职位名称">
              <el-input
                v-model="queryParams.job_title"
                placeholder="请输入职位名称"
                clearable
                style="width: 200px"
              />
            </el-form-item>

            <el-form-item label="公司名称">
              <el-input
                v-model="queryParams.company_name"
                placeholder="请输入公司名称"
                clearable
                style="width: 200px"
              />
            </el-form-item>

            <el-form-item label="工作地点">
              <el-input
                v-model="queryParams.location"
                placeholder="请输入工作地点"
                clearable
                style="width: 200px"
              />
            </el-form-item>

            <el-form-item label="数据年份">
              <el-input-number
                v-model="queryParams.data_year"
                placeholder="请输入年份"
                :min="2000"
                :max="2100"
                clearable
                style="width: 150px"
              />
            </el-form-item>

            <el-form-item>
              <el-button type="primary" @click="handleSearch" :icon="Search">
                搜索
              </el-button>
              <el-button @click="handleReset" :icon="Refresh">
                重置
              </el-button>
            </el-form-item>
          </el-form>

          <!-- 招聘信息列表 -->
          <el-table
            v-loading="loading"
            :data="jobListings"
            stripe
            style="width: 100%"
            max-height="600"
            @row-click="handleRowClick"
          >
            <el-table-column prop="id" label="ID" width="80" />
            <el-table-column prop="job_title" label="职位名称" min-width="150" show-overflow-tooltip />
            <el-table-column prop="company_name" label="公司名称" min-width="150" show-overflow-tooltip />
            <el-table-column prop="salary_range" label="薪资范围" width="120" />
            <el-table-column prop="location" label="工作地点" width="100" />
            <el-table-column prop="data_year" label="年份" width="80" align="center" />
            <el-table-column label="操作" width="100" fixed="right">
              <template #default="{ row }">
                <el-button
                  type="primary"
                  link
                  size="small"
                  @click.stop="handleViewDetail(row.id)"
                >
                  查看详情
                </el-button>
              </template>
            </el-table-column>
          </el-table>

          <!-- 分页 -->
          <div class="pagination-container">
            <el-pagination
              v-model:current-page="currentPage"
              v-model:page-size="pageSize"
              :page-sizes="[10, 20, 50, 100]"
              :total="total"
              layout="total, sizes, prev, pager, next, jumper"
              @size-change="handleSizeChange"
              @current-change="handlePageChange"
            />
          </div>
        </el-card>
      </el-col>

      <!-- 右侧：薪资分布图 -->
      <el-col :xs="24" :sm="24" :md="10" :lg="10" :xl="10">
        <el-card class="dashboard-card">
          <template #header>
            <div class="card-header">
              <h3>2022-2026年薪资分布</h3>
            </div>
          </template>

          <!-- 年份标签页 -->
          <el-tabs v-model="activeYear" @tab-change="handleYearChange" class="salary-tabs">
            <el-tab-pane
              v-for="year in years"
              :key="year"
              :label="`${year}年`"
              :name="String(year)"
            >
              <div
                :ref="el => setChartRef(el, year)"
                :data-year="year"
                class="chart-container"
                v-loading="loadingCharts[year]"
              ></div>
            </el-tab-pane>
          </el-tabs>

          <!-- 统计信息 -->
          <div v-if="statisticsData" class="statistics-info">
            <el-descriptions title="年度统计" :column="2" border size="small">
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
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, onUnmounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { Search, Refresh } from '@element-plus/icons-vue'
import { jobListingService, type JobListing, type JobListingQuery, type SalaryStatistics } from '@/services/jobListing'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'

const router = useRouter()

// 招聘列表相关
const loading = ref(false)
const jobListings = ref<JobListing[]>([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(20)

const queryParams = reactive<JobListingQuery>({
  job_title: '',
  company_name: '',
  location: '',
  search_keyword: '',
  data_year: undefined,
})

// 薪资分布图相关
const activeYear = ref('2022')
const years = ref<number[]>([2022, 2023, 2024, 2025, 2026])
const loadingCharts = ref<Record<number, boolean>>({})
const statisticsData = ref<SalaryStatistics | null>(null)
const chartInstances = ref<Record<number, echarts.ECharts | null>>({})

// 设置图表引用
const setChartRef = (el: any, year: number) => {
  if (el && el instanceof HTMLElement && !chartInstances.value[year]) {
    chartInstances.value[year] = echarts.init(el)
    // 如果数据已加载，立即渲染
    if (statisticsData.value) {
      renderYearChart(year, statisticsData.value)
    }
  }
}

// 加载招聘列表数据
const loadJobListings = async () => {
  loading.value = true
  try {
    const params: JobListingQuery = {
      skip: (currentPage.value - 1) * pageSize.value,
      limit: pageSize.value,
    }

    if (queryParams.job_title) params.job_title = queryParams.job_title
    if (queryParams.company_name) params.company_name = queryParams.company_name
    if (queryParams.location) params.location = queryParams.location
    if (queryParams.search_keyword) params.search_keyword = queryParams.search_keyword
    if (queryParams.data_year) params.data_year = queryParams.data_year

    const response = await jobListingService.getJobListings(params)
    jobListings.value = response.items
    total.value = response.total
  } catch (error) {
    ElMessage.error('加载数据失败')
    console.error(error)
  } finally {
    loading.value = false
  }
}

// 加载薪资统计数据
const loadSalaryStatistics = async () => {
  try {
    const data: SalaryStatistics = await jobListingService.getSalaryStatistics(2022, 2026)
    statisticsData.value = data
    
    // 更新年份列表（基于实际数据）
    if (data.years.length > 0) {
      years.value = data.years
      if (!years.value.includes(Number(activeYear.value))) {
        activeYear.value = String(years.value[0])
      }
    }

    // 等待DOM更新后再渲染图表
    await nextTick()
    
    // 延迟确保所有图表容器都已渲染
    setTimeout(() => {
      for (const year of years.value) {
        const el = document.querySelector(`[data-year="${year}"]`) as HTMLElement
        if (el) {
          if (!chartInstances.value[year]) {
            chartInstances.value[year] = echarts.init(el)
          }
          renderYearChart(year, data)
        }
      }
    }, 500)
  } catch (error: any) {
    ElMessage.error('加载薪资统计数据失败: ' + (error.response?.data?.detail || error.message))
    console.error(error)
  }
}

// 渲染某年的饼图
const renderYearChart = async (year: number, data: SalaryStatistics) => {
  loadingCharts.value[year] = true
  
  await nextTick()
  
  const chartInstance = chartInstances.value[year]
  if (!chartInstance) {
    loadingCharts.value[year] = false
    return
  }

  const yearData = data.data[year]
  if (!yearData) {
    loadingCharts.value[year] = false
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
    loadingCharts.value[year] = false
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
  loadingCharts.value[year] = false
}

// 年份切换
const handleYearChange = (year: string) => {
  activeYear.value = year
  // 确保图表已初始化并渲染
  nextTick(() => {
    const yearNum = Number(year)
    if (statisticsData.value) {
      const chartInstance = chartInstances.value[yearNum]
      if (chartInstance) {
        renderYearChart(yearNum, statisticsData.value)
      } else {
        // 延迟一点，等待DOM更新
        setTimeout(() => {
          const el = document.querySelector(`[data-year="${year}"]`) as HTMLElement
          if (el) {
            chartInstances.value[yearNum] = echarts.init(el)
            if (statisticsData.value) {
              renderYearChart(yearNum, statisticsData.value)
            }
          }
        }, 100)
      }
    }
  })
}

// 计算某年份的总职位数
const getYearTotal = (year: number): number => {
  if (!statisticsData.value) return 0
  const yearData = statisticsData.value.data[year]
  if (!yearData) return 0
  return Object.values(yearData).reduce((sum, count) => sum + count, 0)
}

// 搜索
const handleSearch = () => {
  currentPage.value = 1
  loadJobListings()
}

// 重置
const handleReset = () => {
  queryParams.job_title = ''
  queryParams.company_name = ''
  queryParams.location = ''
  queryParams.search_keyword = ''
  queryParams.data_year = undefined
  currentPage.value = 1
  loadJobListings()
}

// 分页大小改变
const handleSizeChange = (size: number) => {
  pageSize.value = size
  currentPage.value = 1
  loadJobListings()
}

// 页码改变
const handlePageChange = (page: number) => {
  currentPage.value = page
  loadJobListings()
}

// 行点击
const handleRowClick = (row: JobListing) => {
  handleViewDetail(row.id)
}

// 查看详情
const handleViewDetail = (id: number) => {
  router.push(`/job-listings/${id}`)
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
  await loadJobListings()
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
.dashboard-container {
  width: 100%;
  min-height: calc(100vh - 100px);
}

.dashboard-card {
  margin-bottom: 20px;
  height: 100%;
}

.card-header h3 {
  margin: 0;
  color: #303133;
  font-size: 18px;
  font-weight: 600;
}

.search-form {
  margin-bottom: 20px;
}

.pagination-container {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}

:deep(.el-table__row) {
  cursor: pointer;
}

:deep(.el-table__row:hover) {
  background-color: #f5f7fa;
}

.salary-tabs {
  margin-bottom: 20px;
}

.chart-container {
  width: 100%;
  height: 500px;
  min-height: 400px;
}

.statistics-info {
  margin-top: 20px;
  padding-top: 20px;
  border-top: 1px solid #ebeef5;
}

/* 响应式调整 */
@media (max-width: 768px) {
  .chart-container {
    height: 400px;
  }
}
</style>

