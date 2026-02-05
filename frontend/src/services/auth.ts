import api from './api'

export interface LoginRequest {
  email: string
  password: string
}

export interface RegisterRequest {
  name: string
  email: string
  password: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
}

export interface User {
  id: number
  name: string
  email: string
}

export const authService = {
  // 登录（JSON格式）
  async login(data: LoginRequest): Promise<TokenResponse> {
    return api.post('/auth/login/json', data)
  },

  // 注册
  async register(data: RegisterRequest): Promise<User> {
    return api.post('/auth/register', data)
  },

  // 获取当前用户信息
  async getCurrentUser(): Promise<User> {
    return api.get('/users/me')
  },
}

