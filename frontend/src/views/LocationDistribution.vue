<template>
  <div class="location-distribution-container">
    <el-card>
      <template #header>
        <div class="card-header">
          <h3>2022-2026年招聘数据地理分布</h3>
        </div>
      </template>

      <!-- 所有年份地图网格布局 -->
      <div class="maps-grid">
        <div
          v-for="year in years"
          :key="year"
          class="map-wrapper"
        >
          <div class="map-title">{{ year }}年地理分布</div>
          <div
            :ref="el => setChartRef(el, year)"
            :data-year="year"
            class="map-container"
            v-loading="loadingMaps[year]"
          ></div>
          <div class="map-summary" v-if="statisticsData">
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
import { jobListingService, type LocationStatistics } from '@/services/jobListing'
import { ElMessage } from 'element-plus'

const years = ref<number[]>([2022, 2023, 2024, 2025, 2026])
const loadingMaps = ref<Record<number, boolean>>({})
const statisticsData = ref<LocationStatistics | null>(null)
const chartInstances = ref<Record<number, echarts.ECharts | null>>({})
const chartElements = ref<Record<number, HTMLElement | null>>({})
const chinaMapData = ref<any>(null)

// 检查元素是否有尺寸（优化版：使用 requestAnimationFrame，减少延迟）
const waitForElementSize = (element: HTMLElement, maxAttempts = 5): Promise<boolean> => {
  return new Promise((resolve) => {
    // 先立即检查一次
    if (element.clientWidth > 0 && element.clientHeight > 0) {
      resolve(true)
      return
    }
    
    let attempts = 0
    const checkSize = () => {
      attempts++
      if (element.clientWidth > 0 && element.clientHeight > 0) {
        resolve(true)
      } else if (attempts >= maxAttempts) {
        console.warn(`元素在 ${maxAttempts} 次尝试后仍没有尺寸`)
        resolve(false)
      } else {
        // 使用 requestAnimationFrame 替代 setTimeout，更高效
        requestAnimationFrame(checkSize)
      }
    }
    requestAnimationFrame(checkSize)
  })
}

// 加载中国地图数据
const loadChinaMap = async () => {
  if (chinaMapData.value) {
    return chinaMapData.value
  }

  try {
    // 从本地静态资源加载中国地图 GeoJSON，避免第三方防盗链导致线上不可用
    const response = await fetch('/maps/china-100000_full.json')
    const data = await response.json()
    chinaMapData.value = data
    
    // 注册地图
    echarts.registerMap('china', data)
    
    return data
  } catch (error) {
    console.error('加载中国地图数据失败:', error)
    ElMessage.warning('地图数据加载失败，将使用备用方案')
    
    // 如果网络加载失败，返回 null，后续使用散点图或其他方式展示
    return null
  }
}

// 设置图表引用
const setChartRef = (el: any, year: number) => {
  if (el && el instanceof HTMLElement) {
    chartElements.value[year] = el
  }
}

// 初始化单个地图
const initMap = async (year: number, el: HTMLElement, data: LocationStatistics) => {
  const hasSize = await waitForElementSize(el)
  if (!hasSize) {
    console.error(`地图容器 ${year} 年没有尺寸`)
    loadingMaps.value[year] = false
    return
  }

  if (!chartInstances.value[year]) {
    try {
      chartInstances.value[year] = echarts.init(el)
    } catch (error) {
      console.error(`初始化地图 ${year} 失败:`, error)
      loadingMaps.value[year] = false
      return
    }
  }

  renderYearMap(year, data)
}

// 加载地理分布统计数据（优化版：并行加载，减少等待时间）
const loadLocationStatistics = async () => {
  try {
    // 并行加载地图数据和统计数据，不等待地图数据
    const [mapData, statistics] = await Promise.all([
      loadChinaMap().catch(() => null), // 允许地图加载失败，使用备用方案
      jobListingService.getLocationStatistics(2022, 2026)
    ])
    
    statisticsData.value = statistics
    
    if (statistics.years.length > 0) {
      years.value = statistics.years
    }

    await nextTick()
    
    // 并行初始化所有地图，而不是串行
    const initPromises = years.value.map(async (year) => {
      // 尝试从 ref 获取元素，如果没有则从 DOM 查询
      let el = chartElements.value[year]
      if (!el) {
        el = document.querySelector(`[data-year="${year}"]`) as HTMLElement
        if (el) {
          chartElements.value[year] = el
        }
      }
      
      if (el) {
        loadingMaps.value[year] = true
        try {
          await initMap(year, el, statistics)
        } catch (error) {
          console.error(`初始化 ${year} 年地图失败:`, error)
        } finally {
          loadingMaps.value[year] = false
        }
      }
    })
    
    // 等待所有地图初始化完成
    await Promise.all(initPromises)
  } catch (error: any) {
    ElMessage.error('加载地理分布数据失败: ' + (error.response?.data?.detail || error.message))
    console.error(error)
  }
}

// 渲染某年的地图
const renderYearMap = (year: number, data: LocationStatistics) => {
  const chartInstance = chartInstances.value[year]
  if (!chartInstance) {
    return
  }

  const yearData = data.data[year]
  if (!yearData) {
    return
  }

  // 准备地图数据
  const mapData = data.provinces
    .filter(province => (yearData[province] || 0) > 0)
    .map(province => ({
      name: province,
      value: yearData[province] || 0
    }))

  if (mapData.length === 0) {
    return
  }

  const maxValue = Math.max(...mapData.map(d => d.value))

  // 如果地图数据加载成功，使用地图；否则使用柱状图
  const option: echarts.EChartsOption = chinaMapData.value ? {
    title: {
      text: `${year}年招聘数据地理分布`,
      left: 'center',
      textStyle: {
        fontSize: 16,
        fontWeight: 'bold'
      }
    },
    tooltip: {
      trigger: 'item',
      formatter: (params: any) => {
        if (params.value) {
          return `${params.name}<br/>${params.value} 个职位`
        }
        return `${params.name}<br/>0 个职位`
      }
    },
    visualMap: {
      min: 0,
      max: maxValue,
      left: 'left',
      top: 'bottom',
      text: ['高', '低'],
      calculable: true,
      inRange: {
        color: ['#e0f3ff', '#0066cc']
      },
      textStyle: {
        color: '#333'
      }
    },
    series: [
      {
        name: `${year}年招聘数量`,
        type: 'map',
        map: 'china',
        roam: true, // 允许缩放和拖拽
        label: {
          show: true,
          fontSize: 10
        },
        emphasis: {
          label: {
            show: true,
            fontSize: 12,
            fontWeight: 'bold'
          },
          itemStyle: {
            areaColor: '#389BB7',
            borderWidth: 0.5,
            borderColor: '#fff'
          }
        },
        data: mapData
      }
    ]
  } : {
    // 备用方案：使用柱状图展示省份数据
    title: {
      text: `${year}年招聘数据地理分布`,
      left: 'center',
      textStyle: {
        fontSize: 16,
        fontWeight: 'bold'
      }
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'shadow'
      }
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: mapData.map(d => d.name),
      axisLabel: {
        rotate: 45,
        fontSize: 10
      }
    },
    yAxis: {
      type: 'value',
      name: '职位数量'
    },
    series: [
      {
        name: `${year}年招聘数量`,
        type: 'bar',
        data: mapData.map(d => d.value),
        itemStyle: {
          color: '#5470c6'
        }
      }
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
  await nextTick()
  await loadLocationStatistics()
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
.location-distribution-container {
  width: 100%;
}

.card-header h3 {
  margin: 0;
  color: #303133;
  font-size: 18px;
  font-weight: 600;
}

.maps-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 24px;
  margin-bottom: 30px;
}

.map-wrapper {
  background: #fafafa;
  border-radius: 8px;
  padding: 20px;
  border: 1px solid #ebeef5;
}

.map-title {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 16px;
  text-align: center;
}

.map-container {
  width: 100%;
  height: 500px;
  min-height: 400px;
}

.map-summary {
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
  .maps-grid {
    grid-template-columns: 1fr;
  }
  
  .map-container {
    height: 550px;
  }
}

@media (max-width: 768px) {
  .map-container {
    height: 400px;
  }
  
  .map-wrapper {
    padding: 15px;
  }
}
</style>

