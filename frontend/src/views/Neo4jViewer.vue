<template>
  <div class="neo4j-viewer">
    <el-card>
      <template #header>
        <div class="card-header">
          <h2>Neo4j 知识图谱浏览器</h2>
          <div>
            <el-tag type="warning">只读模式</el-tag>
            <el-button
              type="primary"
              style="margin-left: 10px"
              @click="openBrowserInNewTab"
            >
              在新窗口打开 Neo4j Browser
            </el-button>
          </div>
        </div>
      </template>

      <!-- 统计信息 -->
      <el-row :gutter="20" class="stats-row">
        <el-col :span="12">
          <el-card shadow="hover">
            <template #header>
              <span>节点统计</span>
            </template>
            <div v-if="stats.nodes && Object.keys(stats.nodes).length > 0">
              <div v-for="(count, label) in stats.nodes" :key="label" class="stat-item">
                <el-tag>{{ label || '未分类' }}</el-tag>
                <span class="stat-count">{{ count }}</span>
              </div>
            </div>
            <el-skeleton v-else :rows="3" animated />
          </el-card>
        </el-col>
        <el-col :span="12">
          <el-card shadow="hover">
            <template #header>
              <span>关系统计</span>
            </template>
            <div v-if="stats.relationships && Object.keys(stats.relationships).length > 0">
              <div v-for="(count, type) in stats.relationships" :key="type" class="stat-item">
                <el-tag type="success">{{ type }}</el-tag>
                <span class="stat-count">{{ count }}</span>
              </div>
            </div>
            <el-skeleton v-else :rows="3" animated />
          </el-card>
        </el-col>
      </el-row>

      <!-- 查询区域 -->
      <el-card class="query-card" shadow="hover">
        <template #header>
          <span>自定义查询（只读）</span>
        </template>
        <el-form :model="queryForm" label-width="100px">
          <el-form-item label="Cypher 查询">
            <el-input
              v-model="queryForm.query"
              type="textarea"
              :rows="4"
              placeholder="例如: MATCH (n:Company) RETURN n LIMIT 10"
            />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" @click="executeQuery" :loading="queryLoading">
              执行查询
            </el-button>
            <el-button @click="resetQuery">重置</el-button>
          </el-form-item>
        </el-form>
      </el-card>

      <!-- 搜索结果 -->
      <el-card v-if="queryResults.length > 0" class="results-card" shadow="hover">
        <template #header>
          <span>查询结果 ({{ queryResults.length }} 条)</span>
        </template>
        <el-table :data="queryResults" border stripe max-height="400">
          <el-table-column
            v-for="(_cell, key) in queryResults[0]"
            :key="key"
            :prop="key"
            :label="key"
            min-width="150"
          >
            <template #default="{ row }">
              <span v-if="typeof row[key] === 'object'">
                {{ JSON.stringify(row[key]) }}
              </span>
              <span v-else>{{ row[key] }}</span>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <!-- 节点列表 -->
      <el-card class="nodes-card" shadow="hover">
        <template #header>
          <div class="card-header-actions">
            <span>节点列表</span>
            <div>
              <el-input
                v-model="searchForm.label"
                placeholder="节点标签"
                style="width: 150px; margin-right: 10px"
                clearable
              />
              <el-input
                v-model="searchForm.property_value"
                placeholder="搜索属性值"
                style="width: 200px; margin-right: 10px"
                clearable
              />
              <el-button type="primary" @click="searchNodes" :loading="searchLoading">
                搜索
              </el-button>
              <el-button @click="loadAllNodes">加载全部</el-button>
            </div>
          </div>
        </template>
        <el-table :data="nodes" border stripe v-loading="nodesLoading" max-height="400">
          <el-table-column prop="id" label="ID" width="80" />
          <el-table-column label="标签" width="150">
            <template #default="{ row }">
              <el-tag
                v-for="label in row.labels"
                :key="label"
                style="margin-right: 5px"
              >
                {{ label }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="属性">
            <template #default="{ row }">
              <el-descriptions :column="2" size="small" border>
                <el-descriptions-item
                  v-for="(value, key) in row.properties"
                  :key="key"
                  :label="key"
                >
                  {{ value }}
                </el-descriptions-item>
              </el-descriptions>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="100">
            <template #default="{ row }">
              <el-button size="small" @click="viewNodeDetail(row.id)">
                详情
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <!-- 节点详情对话框 -->
      <el-dialog v-model="nodeDetailVisible" title="节点详情" width="800px">
        <div v-if="selectedNode">
          <el-descriptions title="节点信息" :column="2" border>
            <el-descriptions-item label="ID">{{ selectedNode.id }}</el-descriptions-item>
            <el-descriptions-item label="标签">
              <el-tag
                v-for="label in selectedNode.labels"
                :key="label"
                style="margin-right: 5px"
              >
                {{ label }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item
              v-for="(value, key) in selectedNode.properties"
              :key="key"
              :label="key"
              :span="2"
            >
              {{ value }}
            </el-descriptions-item>
          </el-descriptions>
          <el-divider />
          <h3>关联关系</h3>
          <el-table :data="selectedNode.relationships" border v-if="selectedNode.relationships && selectedNode.relationships.length > 0">
            <el-table-column prop="relationship.type" label="关系类型" width="150" />
            <el-table-column label="关联节点">
              <template #default="{ row }">
                <el-tag
                  v-for="label in row.node.labels"
                  :key="label"
                  style="margin-right: 5px"
                >
                  {{ label }}
                </el-tag>
                <span>{{ JSON.stringify(row.node.properties) }}</span>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-else description="暂无关联关系" />
        </div>
      </el-dialog>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { neo4jService } from '@/services/neo4j'
import type { Neo4jNode } from '@/services/neo4j'

const stats = ref<{ nodes: Record<string, number>; relationships: Record<string, number> }>({
  nodes: {},
  relationships: {},
})

const queryForm = ref({
  query: 'MATCH (n) RETURN n LIMIT 10',
})

const queryResults = ref<any[]>([])
const queryLoading = ref(false)

const searchForm = ref({
  label: '',
  property_value: '',
})

const nodes = ref<Neo4jNode[]>([])
const nodesLoading = ref(false)
const searchLoading = ref(false)

const nodeDetailVisible = ref(false)
const selectedNode = ref<any>(null)

const browserUrl = ref('http://localhost:7474')

// 加载统计信息
const loadStats = async () => {
  try {
    const data = await neo4jService.getStats()
    stats.value = data
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '加载统计信息失败')
  }
}

// 执行查询
const executeQuery = async () => {
  if (!queryForm.value.query.trim()) {
    ElMessage.warning('请输入查询语句')
    return
  }

  queryLoading.value = true
  try {
    const data = await neo4jService.executeQuery({
      query: queryForm.value.query,
    })
    queryResults.value = data.results || []
    ElMessage.success('查询执行成功')
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '查询执行失败')
    queryResults.value = []
  } finally {
    queryLoading.value = false
  }
}

// 重置查询
const resetQuery = () => {
  queryForm.value.query = 'MATCH (n) RETURN n LIMIT 10'
  queryResults.value = []
}

// 搜索节点
const searchNodes = async () => {
  searchLoading.value = true
  try {
    const data = await neo4jService.searchNodes({
      label: searchForm.value.label || undefined,
      property_value: searchForm.value.property_value || undefined,
      limit: 100,
    })
    nodes.value = data.nodes || []
    ElMessage.success(`找到 ${nodes.value.length} 个节点`)
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '搜索失败')
  } finally {
    searchLoading.value = false
  }
}

// 加载所有节点
const loadAllNodes = async () => {
  nodesLoading.value = true
  try {
    const data = await neo4jService.getNodes(100)
    nodes.value = data.nodes || []
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '加载节点失败')
  } finally {
    nodesLoading.value = false
  }
}

// 查看节点详情
const viewNodeDetail = async (nodeId: number) => {
  try {
    const data = await neo4jService.getNodeById(nodeId)
    selectedNode.value = data
    nodeDetailVisible.value = true
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '获取节点详情失败')
  }
}

// 在新窗口打开 Neo4j Browser
const openBrowserInNewTab = async () => {
  try {
    const data = await neo4jService.getBrowserUrl()
    window.open(data.url, '_blank')
  } catch (error: any) {
    // 如果获取失败，使用默认 URL
    window.open(browserUrl.value, '_blank')
  }
}

onMounted(() => {
  loadStats()
  loadAllNodes()
  // 获取 Browser URL
  neo4jService.getBrowserUrl().then((data) => {
    browserUrl.value = data.url
  }).catch(() => {
    // 使用默认值
  })
})
</script>

<style scoped>
.neo4j-viewer {
  max-width: 1400px;
  margin: 0 auto;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.stats-row {
  margin-bottom: 20px;
}

.stat-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.stat-count {
  font-weight: bold;
  color: #409eff;
}

.query-card,
.results-card,
.nodes-card {
  margin-top: 20px;
}

.card-header-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
