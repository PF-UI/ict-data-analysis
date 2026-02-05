<template>
  <div class="job-detail-container">
    <el-card v-loading="loading">
      <template #header>
        <div class="card-header">
          <el-button
            type="primary"
            link
            :icon="ArrowLeft"
            @click="handleBack"
          >
            返回列表
          </el-button>
          <h3>招聘信息详情</h3>
        </div>
      </template>

      <div v-if="jobListing" class="detail-content">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="ID">
            {{ jobListing.id }}
          </el-descriptions-item>
          <el-descriptions-item label="创建时间">
            {{ formatDate(jobListing.created_at) }}
          </el-descriptions-item>
          <el-descriptions-item label="职位名称" :span="2">
            <el-tag type="primary" size="large">{{ jobListing.job_title }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="公司名称" :span="2">
            <el-tag type="success" size="large">{{ jobListing.company_name }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="薪资范围">
            {{ jobListing.salary_range || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="工作地点">
            <el-icon><Location /></el-icon>
            {{ jobListing.location || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="招聘人数">
            {{ jobListing.openings || '-' }} 人
          </el-descriptions-item>
          <el-descriptions-item label="数据年份">
            {{ jobListing.data_year || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="搜索关键词">
            {{ jobListing.search_keyword || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="职位要求" :span="2">
            <div class="requirements-content">
              {{ jobListing.requirements || '暂无要求' }}
            </div>
          </el-descriptions-item>
        </el-descriptions>
      </div>

      <el-empty v-else description="招聘信息不存在" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ArrowLeft, Location } from '@element-plus/icons-vue'
import { jobListingService, type JobListing } from '@/services/jobListing'
import { ElMessage } from 'element-plus'

const router = useRouter()
const route = useRoute()

const loading = ref(false)
const jobListing = ref<JobListing | null>(null)

// 加载详情
const loadDetail = async () => {
  const id = Number(route.params.id)
  if (!id) {
    ElMessage.error('无效的ID')
    router.push('/job-listings')
    return
  }

  loading.value = true
  try {
    jobListing.value = await jobListingService.getJobListing(id)
  } catch (error: any) {
    if (error?.response?.status === 404) {
      ElMessage.error('招聘信息未找到')
    } else {
      ElMessage.error('加载详情失败')
    }
    router.push('/job-listings')
  } finally {
    loading.value = false
  }
}

// 返回列表
const handleBack = () => {
  router.push('/job-listings')
}

// 格式化日期
const formatDate = (dateString: string) => {
  if (!dateString) return '-'
  const date = new Date(dateString)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

onMounted(() => {
  loadDetail()
})
</script>

<style scoped>
.job-detail-container {
  width: 100%;
}

.card-header {
  display: flex;
  align-items: center;
  gap: 15px;
}

.card-header h3 {
  margin: 0;
  color: #303133;
}

.detail-content {
  padding: 20px 0;
}

.requirements-content {
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.6;
  color: #606266;
  padding: 10px;
  background-color: #f5f7fa;
  border-radius: 4px;
  min-height: 100px;
}
</style>

