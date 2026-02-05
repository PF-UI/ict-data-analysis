<template>
  <div class="job-listings-container">
    <el-card>
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
        @row-click="handleRowClick"
      >
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="job_title" label="职位名称" min-width="200" />
        <el-table-column prop="company_name" label="公司名称" min-width="180" />
        <el-table-column prop="salary_range" label="薪资范围" width="150" />
        <el-table-column prop="location" label="工作地点" width="120" />
        <el-table-column prop="openings" label="招聘人数" width="100" align="center" />
        <el-table-column prop="data_year" label="年份" width="100" align="center" />
        <el-table-column prop="created_at" label="创建时间" width="180">
          <template #default="{ row }">
            {{ formatDate(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
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
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Search, Refresh } from '@element-plus/icons-vue'
import { jobListingService, type JobListing, type JobListingQuery } from '@/services/jobListing'
import { ElMessage } from 'element-plus'

const router = useRouter()

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

// 加载数据
const loadData = async () => {
  loading.value = true
  try {
    const params: JobListingQuery = {
      skip: (currentPage.value - 1) * pageSize.value,
      limit: pageSize.value,
    }

    // 只添加非空参数
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

// 搜索
const handleSearch = () => {
  currentPage.value = 1
  loadData()
}

// 重置
const handleReset = () => {
  queryParams.job_title = ''
  queryParams.company_name = ''
  queryParams.location = ''
  queryParams.search_keyword = ''
  queryParams.data_year = undefined
  currentPage.value = 1
  loadData()
}

// 分页大小改变
const handleSizeChange = (size: number) => {
  pageSize.value = size
  currentPage.value = 1
  loadData()
}

// 页码改变
const handlePageChange = (page: number) => {
  currentPage.value = page
  loadData()
}

// 行点击
const handleRowClick = (row: JobListing) => {
  handleViewDetail(row.id)
}

// 查看详情
const handleViewDetail = (id: number) => {
  router.push(`/job-listings/${id}`)
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
  loadData()
})
</script>

<style scoped>
.job-listings-container {
  width: 100%;
}

.card-header h3 {
  margin: 0;
  color: #303133;
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
</style>

