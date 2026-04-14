<template>
  <div class="wordcloud-container">
    <el-card>
      <template #header>
        <div class="card-header">
          <h3>2022-2026年招聘要求词云分析</h3>
          <div class="header-controls">
            <el-select v-model="selectedYear" placeholder="选择年份" style="width: 150px" @change="handleYearChange">
              <el-option label="全部年份" value="all" />
              <el-option
                v-for="year in years"
                :key="year"
                :label="`${year}年`"
                :value="year"
              />
            </el-select>
            <el-input-number
              v-model="topN"
              :min="20"
              :max="200"
              :step="10"
              label="显示词数"
              style="width: 150px; margin-left: 10px"
              @change="handleTopNChange"
            />
          </div>
        </div>
      </template>

      <!-- 统计信息 -->
      <div v-if="statisticsData" class="statistics-info">
        <el-descriptions :column="4" border>
          <el-descriptions-item label="总词数">
            {{ statisticsData.total_words.toLocaleString() }}
          </el-descriptions-item>
          <el-descriptions-item label="唯一词汇数">
            {{ statisticsData.unique_words.toLocaleString() }}
          </el-descriptions-item>
          <el-descriptions-item label="显示词数">
            {{ currentWordCloudData.length }}
          </el-descriptions-item>
          <el-descriptions-item label="数据年份">
            {{ statisticsData.years.join(', ') }}
          </el-descriptions-item>
        </el-descriptions>
      </div>

      <!-- 词云图容器 -->
      <div class="wordcloud-wrapper">
        <div
          ref="wordcloudChartRef"
          class="wordcloud-chart"
          v-loading="loading"
        ></div>
      </div>

      <!-- 高频词列表 -->
      <div v-if="currentWordCloudData.length > 0" class="word-list">
        <h4>高频词Top {{ currentWordCloudData.length }}</h4>
        <div class="word-tags">
          <el-tag
            v-for="(item, index) in currentWordCloudData"
            :key="item.name"
            :type="getTagType(index)"
            size="large"
            effect="plain"
            style="margin: 5px; font-size: 14px"
          >
            {{ item.name }} ({{ item.value }})
          </el-tag>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, watch, nextTick } from 'vue'
import * as echarts from 'echarts'
import 'echarts-wordcloud'
import { jobListingService, type WordCloudStatistics, type WordCloudItem } from '@/services/jobListing'
import { ElMessage } from 'element-plus'

const loading = ref(false)
const statisticsData = ref<WordCloudStatistics | null>(null)
const wordcloudChartRef = ref<HTMLElement | null>(null)
const chartInstance = ref<echarts.ECharts | null>(null)
const selectedYear = ref<string | number>('all')
const topN = ref(100)
const years = ref<number[]>([])

// 计算当前要显示的词云数据
const currentWordCloudData = computed(() => {
  if (!statisticsData.value) return []
  
  let data: WordCloudItem[] = []
  
  if (selectedYear.value === 'all') {
    // 显示全部年份的数据
    data = statisticsData.value.wordcloud.slice(0, topN.value)
  } else {
    // 显示指定年份的数据
    const yearData = statisticsData.value.year_statistics[selectedYear.value as number]
    if (yearData) {
      data = Object.entries(yearData)
        .map(([name, value]) => ({ name, value }))
        .sort((a, b) => b.value - a.value)
        .slice(0, topN.value)
    }
  }
  
  return data
})

// 获取标签类型（根据排名）
const getTagType = (index: number): string => {
  if (index < 10) return 'danger'
  if (index < 30) return 'warning'
  if (index < 50) return 'success'
  return 'info'
}

// 加载词云统计数据
const loadWordCloudStatistics = async () => {
  loading.value = true
  try {
    const data = await jobListingService.getWordCloudStatistics(2022, 2026, topN.value, 2)
    statisticsData.value = data
    years.value = data.years
    topN.value = Math.min(100, data.wordcloud.length)
    
    await nextTick()
    renderWordCloud()
  } catch (error: any) {
    ElMessage.error('加载词云数据失败: ' + (error.response?.data?.detail || error.message))
    console.error(error)
  } finally {
    loading.value = false
  }
}

// 渲染词云图
const renderWordCloud = () => {
  if (!wordcloudChartRef.value || !currentWordCloudData.value.length) {
    return
  }

  if (!chartInstance.value) {
    chartInstance.value = echarts.init(wordcloudChartRef.value)
  }

  const data = currentWordCloudData.value
  const maxValue = Math.max(...data.map(d => d.value))
  const minValue = Math.min(...data.map(d => d.value))

  // 定义颜色数组
  const colors = [
    '#5470c6', '#91cc75', '#fac858', '#ee6666', 
    '#73c0de', '#3ba272', '#fc8452', '#9a60b4',
    '#ff6b6b', '#4ecdc4', '#45b7d1', '#f9ca24',
    '#6c5ce7', '#a29bfe', '#fd79a8', '#fdcb6e'
  ]

  const option: echarts.EChartsOption = {
    title: {
      text: selectedYear.value === 'all' 
        ? '招聘要求高频词分析（全部年份）' 
        : `${selectedYear.value}年招聘要求高频词分析`,
      left: 'center',
      top: 10,
      textStyle: {
        fontSize: 18,
        fontWeight: 'bold',
        color: '#303133'
      }
    },
    tooltip: {
      trigger: 'item',
      formatter: (params: any) => {
        return `${params.name}<br/>出现次数: ${params.value}`
      }
    },
    series: [
      {
        type: 'wordCloud',
        shape: 'circle', // 词云形状：'circle', 'cardioid', 'diamond', 'triangle-forward', 'triangle', 'pentagon', 'star'
        sizeRange: [16, 80], // 字体大小范围（增大范围，使差异更明显）
        rotationRange: [0, 0], // 禁用旋转，所有文字水平显示
        rotationStep: 0, // 旋转步长
        gridSize: 12, // 网格大小（增大，减少文字重叠）
        drawOutOfBound: false, // 是否允许词云超出画布范围
        layoutAnimation: true, // 启用布局动画
        textStyle: {
          fontFamily: 'Microsoft YaHei, Arial, sans-serif', // 使用中文字体
          fontWeight: 'bold',
          color: (params: any) => {
            // 根据词频值设置颜色，高频词使用深色，低频词使用浅色
            const ratio = (params.value - minValue) / (maxValue - minValue)
            const colorIndex = Math.floor(ratio * (colors.length - 1))
            return colors[colorIndex] || colors[0]
          }
        },
        emphasis: {
          focus: 'self', // 聚焦时只高亮当前项
          textStyle: {
            shadowBlur: 10,
            shadowColor: '#333'
          }
        },
        data: data,
        // 添加宽度和高度设置，确保词云在容器内正确布局
        width: '100%',
        height: '100%'
      }
    ]
  }

  chartInstance.value.setOption(option, true)
}

// 年份改变处理
const handleYearChange = () => {
  renderWordCloud()
}

// TopN改变处理
const handleTopNChange = () => {
  renderWordCloud()
}

// 响应式调整
const handleResize = () => {
  if (chartInstance.value) {
    chartInstance.value.resize()
  }
}

// 监听数据变化
watch(currentWordCloudData, () => {
  renderWordCloud()
}, { deep: true })

onMounted(async () => {
  await loadWordCloudStatistics()
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  if (chartInstance.value) {
    chartInstance.value.dispose()
  }
  window.removeEventListener('resize', handleResize)
})
</script>

<style scoped>
.wordcloud-container {
  width: 100%;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-header h3 {
  margin: 0;
  color: #303133;
  font-size: 18px;
  font-weight: 600;
}

.header-controls {
  display: flex;
  align-items: center;
}

.statistics-info {
  margin-bottom: 20px;
}

.wordcloud-wrapper {
  width: 100%;
  margin: 20px 0;
}

.wordcloud-chart {
  width: 100%;
  height: 700px;
  min-height: 500px;
}

.word-list {
  margin-top: 30px;
  padding-top: 20px;
  border-top: 1px solid #ebeef5;
}

.word-list h4 {
  margin: 0 0 15px 0;
  color: #303133;
  font-size: 16px;
  font-weight: 600;
}

.word-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}

/* 响应式调整 */
@media (max-width: 1200px) {
  .wordcloud-chart {
    height: 500px;
  }
}

@media (max-width: 768px) {
  .card-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 15px;
  }

  .header-controls {
    width: 100%;
    flex-wrap: wrap;
  }

  .wordcloud-chart {
    height: 400px;
  }
}
</style>

