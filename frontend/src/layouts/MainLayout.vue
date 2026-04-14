<template>
  <el-container class="layout-container">
    <el-header class="header">
      <div class="header-left">
        <h2>ICT数据分析系统</h2>
        <div class="header-nav">
          <div 
            :class="['nav-item', { 'is-active': activeMenu === '/qa' }]"
            @click="handleNavClick('/qa')"
          >
            智能问答
          </div>
          <div 
            :class="['nav-item', { 'is-active': activeMenu === '/job-listings' || activeMenu.startsWith('/job-listings') }]"
            @click="handleNavClick('/job-listings')"
          >
            招聘列表
          </div>
          <div 
            :class="['nav-item', { 'is-active': activeMenu === '/salary-distribution' }]"
            @click="handleNavClick('/salary-distribution')"
          >
            薪资分布
          </div>
          <div 
            :class="['nav-item', { 'is-active': activeMenu === '/location-distribution' }]"
            @click="handleNavClick('/location-distribution')"
          >
            地理分布
          </div>
          <div 
            :class="['nav-item', { 'is-active': activeMenu === '/wordcloud' }]"
            @click="handleNavClick('/wordcloud')"
          >
            词云分析
          </div>
          <div 
            :class="['nav-item', { 'is-active': activeMenu === '/neo4j' }]"
            @click="handleNavClick('/neo4j')"
          >
            知识图谱
          </div>
        </div>
      </div>
      <div class="header-right">
        <el-dropdown @command="handleCommand">
          <span class="user-info">
            <el-icon><User /></el-icon>
            {{ authStore.user?.name || '用户' }}
            <el-icon class="el-icon--right"><arrow-down /></el-icon>
          </span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="logout">退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </el-header>
    
    <el-main class="main-content">
      <router-view />
    </el-main>
  </el-container>
</template>

<script setup lang="ts">
import { onMounted, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { User, ArrowDown } from '@element-plus/icons-vue'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

const activeMenu = computed(() => {
  return route.path
})

onMounted(() => {
  authStore.loadUser()
})

const handleNavClick = (path: string) => {
  router.push(path)
}

const handleCommand = (command: string) => {
  if (command === 'logout') {
    authStore.logout()
    router.push('/login')
  }
}
</script>

<style scoped>
.layout-container {
  min-height: 100vh;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: #fff;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  padding: 0 20px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 30px;
}

.header-left h2 {
  margin: 0;
  color: #303133;
  font-size: 20px;
  white-space: nowrap;
}

.header-nav {
  display: flex;
  align-items: center;
  gap: 0;
  height: 60px;
}

.nav-item {
  padding: 0 24px;
  height: 60px;
  line-height: 60px;
  cursor: pointer;
  color: #606266;
  font-size: 14px;
  border-bottom: 2px solid transparent;
  transition: all 0.3s;
  white-space: nowrap;
}

.nav-item:hover {
  color: #409eff;
}

.nav-item.is-active {
  color: #409eff;
  border-bottom-color: #409eff;
  font-weight: 500;
}

.header-right {
  display: flex;
  align-items: center;
}

.user-info {
  display: flex;
  align-items: center;
  cursor: pointer;
  color: #606266;
  font-size: 14px;
}

.user-info .el-icon {
  margin-right: 5px;
}

.main-content {
  background: #f5f7fa;
  padding: 20px;
}
</style>

