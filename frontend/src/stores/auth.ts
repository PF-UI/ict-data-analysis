import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { authService, type LoginRequest, type RegisterRequest, type User } from '@/services/auth'
import { ElMessage } from 'element-plus'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem('token'))
  const user = ref<User | null>(null)

  const isAuthenticated = computed(() => !!token.value)

  const login = async (data: LoginRequest) => {
    try {
      const response = await authService.login(data)
      // 先设置 token 到 localStorage 和 store
      const accessToken = response.access_token
      console.log('✅ 登录成功，收到 token:', accessToken.substring(0, 20) + '...')
      
      token.value = accessToken
      localStorage.setItem('token', accessToken)
      
      // 验证 token 是否已保存
      const savedToken = localStorage.getItem('token')
      console.log('💾 Token 已保存到 localStorage:', savedToken ? savedToken.substring(0, 20) + '...' : 'null')
      
      // 等待一小段时间，确保 localStorage 写入完成
      await new Promise(resolve => setTimeout(resolve, 50))
      
      // 获取用户信息（使用新获取的 token）
      try {
        console.log('🔍 开始获取用户信息...')
        const userInfo = await authService.getCurrentUser()
        user.value = userInfo
        console.log('✅ 用户信息获取成功:', userInfo)
      } catch (error) {
        console.error('❌ 获取用户信息失败', error)
        // 如果获取用户信息失败，不清除 token，让用户可以先登录
        // 用户信息可以在后续页面加载时再获取
      }
      
      ElMessage.success('登录成功')
      return true
    } catch (error) {
      console.error('❌ 登录失败', error)
      ElMessage.error('登录失败，请检查用户名和密码')
      return false
    }
  }

  const register = async (data: RegisterRequest) => {
    try {
      await authService.register(data)
      ElMessage.success('注册成功，请登录')
      return true
    } catch (error) {
      return false
    }
  }

  /** @param silent 为 true 时不弹「已退出登录」（例如由全局 401 拦截器清理会话时） */
  const logout = (silent = false) => {
    token.value = null
    user.value = null
    localStorage.removeItem('token')
    if (!silent) {
      ElMessage.success('已退出登录')
    }
  }

  const loadUser = async () => {
    if (!token.value) return
    
    try {
      user.value = await authService.getCurrentUser()
    } catch (error) {
      console.error('加载用户信息失败', error)
      // 401 时全局拦截器已提示并清理会话，避免再弹「已退出登录」
      logout(true)
    }
  }

  return {
    token,
    user,
    isAuthenticated,
    login,
    register,
    logout,
    loadUser,
  }
})

