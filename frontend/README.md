# 招聘数据管理系统 - 前端

基于 Vue 3 + Vite + TypeScript + Element Plus 的前端项目。

## 技术栈

- **Vue 3** - 渐进式 JavaScript 框架
- **TypeScript** - 类型安全的 JavaScript
- **Vite** - 下一代前端构建工具
- **Element Plus** - Vue 3 组件库
- **Vue Router** - 官方路由管理器
- **Pinia** - 状态管理
- **Axios** - HTTP 客户端

## 项目结构

```
frontend/
├── src/
│   ├── views/          # 页面组件
│   │   ├── Login.vue           # 登录页
│   │   ├── Register.vue        # 注册页
│   │   ├── JobListings.vue     # 招聘信息列表页
│   │   └── JobDetail.vue       # 招聘信息详情页
│   ├── layouts/        # 布局组件
│   │   └── MainLayout.vue      # 主布局
│   ├── components/     # 公共组件
│   ├── router/         # 路由配置
│   │   └── index.ts
│   ├── stores/         # Pinia 状态管理
│   │   └── auth.ts             # 认证状态
│   ├── services/       # API 服务
│   │   ├── api.ts              # Axios 配置
│   │   ├── auth.ts             # 认证 API
│   │   └── jobListing.ts       # 招聘信息 API
│   ├── App.vue         # 根组件
│   └── main.ts         # 入口文件
├── index.html          # HTML 模板
├── vite.config.ts      # Vite 配置
├── tsconfig.json       # TypeScript 配置
└── package.json        # 项目依赖
```

## 安装依赖

```bash
cd frontend
npm install
# 或
yarn install
# 或
pnpm install
```

## 开发

```bash
npm run dev
```

前端服务将运行在 `http://localhost:3000`

## 构建

```bash
npm run build
```

构建产物将输出到 `dist/` 目录。

## 预览构建结果

```bash
npm run preview
```

## 功能特性

### 1. 用户认证
- ✅ 用户登录
- ✅ 用户注册
- ✅ JWT Token 管理
- ✅ 路由守卫

### 2. 招聘信息管理
- ✅ 招聘信息列表（分页）
- ✅ 多条件搜索和筛选
  - 关键词搜索
  - 职位名称
  - 公司名称
  - 工作地点
  - 数据年份
- ✅ 招聘信息详情查看
- ✅ 响应式设计

## API 配置

前端通过代理访问后端 API：

- 开发环境：`http://localhost:3000` → 代理到 `http://localhost:8000/api/v1`
- 生产环境：需要配置实际的后端地址

代理配置在 `vite.config.ts` 中：

```typescript
server: {
  proxy: {
    '/api': {
      target: 'http://localhost:8000',
      changeOrigin: true,
    },
  },
}
```

## 环境变量

可以创建 `.env` 文件配置环境变量：

```env
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

## 主要页面

### 登录页 (`/login`)
- 邮箱/密码登录
- 表单验证
- 跳转到注册页

### 注册页 (`/register`)
- 用户注册
- 密码确认验证
- 跳转到登录页

### 招聘信息列表 (`/job-listings`)
- 搜索和筛选功能
- 分页展示
- 点击行查看详情
- 响应式表格

### 招聘信息详情 (`/job-listings/:id`)
- 详细信息展示
- 返回列表按钮

## 注意事项

1. **后端服务**：确保后端 FastAPI 服务运行在 `http://localhost:8000`
2. **CORS**：后端已配置 CORS，允许所有来源（开发环境）
3. **认证**：招聘信息接口不需要认证，但前端路由需要登录才能访问
4. **Token 存储**：Token 存储在 localStorage 中

## 开发建议

1. 使用 Vue DevTools 调试
2. 使用 Element Plus 官方文档查找组件
3. API 调用统一使用 `services` 目录下的服务
4. 状态管理使用 Pinia stores

## 常见问题

### 1. 无法连接后端 API
- 检查后端服务是否运行
- 检查 `vite.config.ts` 中的代理配置
- 检查浏览器控制台的错误信息

### 2. 登录后无法获取用户信息
- 检查后端 `/api/v1/users/me` 接口是否正常
- 检查 Token 是否正确传递

### 3. 招聘信息列表为空
- 检查数据库是否有数据
- 检查 API 响应是否正确
- 查看浏览器网络请求

