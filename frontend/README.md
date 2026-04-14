# 招聘知识图谱 - 前端

Vue 3 + Vite + TypeScript + Element Plus 单页应用，对接仓库根目录的 FastAPI（`/api/v1`）。总览与启动顺序见仓库根目录 [README.md](../README.md)。

## 技术栈

| 类别 | 技术 |
|------|------|
| 框架 | Vue 3、TypeScript |
| 构建 | Vite 5 |
| UI | Element Plus、@element-plus/icons-vue |
| 路由与状态 | Vue Router、Pinia |
| 请求 | Axios（`baseURL: '/api/v1'`） |
| 可视化 | ECharts、echarts-wordcloud |

## 目录结构

```text
frontend/
├── src/
│   ├── views/              # 页面
│   │   ├── Login.vue / Register.vue
│   │   ├── QAPage.vue # 智能问答（默认首页 `/` → `/qa`）
│   │   ├── JobListings.vue / JobDetail.vue
│   │   ├── SalaryDistribution.vue / LocationDistribution.vue
│   │   ├── WordCloud.vue
│   │   └── Neo4jViewer.vue
│   ├── layouts/MainLayout.vue
│   ├── components/
│   ├── router/index.ts
│   ├── stores/auth.ts
│   ├── services/           # api.ts、auth、jobListing、qa、neo4j
│   ├── App.vue
│   └── main.ts
├── vite.config.ts
├── package.json
└── index.html
```

## 安装与脚本

```bash
cd frontend
npm install   # 或 yarn / pnpm
npm run dev     # 开发
npm run build   # 类型检查 + 生产构建 → dist/
npm run preview # 本地预览构建结果
npm run lint    # ESLint
```

## 开发服务器与代理

- **本地地址**：<http://localhost:3003>（端口以 `vite.config.ts` 中 `server.port` 为准）。
- **接口代理**：浏览器请求以 `/api` 开头时，由 Vite 转发到 `http://localhost:8000`，例如：
  - 前端 Axios `baseURL` 为 `/api/v1`
  - 实际请求：`http://localhost:3003/api/v1/...` → `http://localhost:8000/api/v1/...`
- **WebSocket**：代理配置中已启用 `ws: true`，便于需要 WS 的接口。

当前代理片段如下（完整配置见 `vite.config.ts`）：

```typescript
server: {
  port: 3003,
  proxy: {
    '/api': {
      target: 'http://localhost:8000',
      changeOrigin: true,
      ws: true,
    },
  },
}
```

## 环境变量（可选）

构建或部署若需写死后端地址，可在 `frontend` 下创建 `.env` / `.env.production`：

```env
# 示例：生产环境直连后端（需与打包时代码读取方式一致）
# VITE_API_BASE_URL=https://api.example.com/api/v1
```

开发模式下通常**无需**配置：沿用相对路径 `/api/v1` 即可走 Vite 代理。

## 路由与功能

| 路径 | 说明 |
|------|------|
| `/login`、`/register` | 登录、注册（未登录可访问） |
| `/qa` | 智能问答（登录后默认进入） |
| `/job-listings`、`/job-listings/:id` | 招聘列表与详情 |
| `/salary-distribution`、`/location-distribution` | 薪资 / 地域分布 |
| `/wordcloud` | 词云 |
| `/neo4j` | Neo4j 相关展示（与后端 Neo4j 接口配合） |

路由守卫：除登录、注册外，其余页面需已登录（Token 在 Pinia / localStorage 中维护）。

## 与后端协作

1. 先启动 API：`uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`（在仓库根目录）。
2. 再执行 `npm run dev`。
3. 文档与调试：<http://localhost:8000/docs>。

## 常见问题

**无法访问接口**  
确认本机 `8000` 端口已监听、代理目标未被防火墙拦截；浏览器开发者工具查看请求是否 404/502。

**登录后仍跳回登录页**  
检查 `/api/v1/users/me` 是否返回 200、响应里用户信息是否正常；确认请求头携带 `Authorization: Bearer <token>`。

**列表为空**  
确认 MySQL 业务库中 `job_listings` 等表有数据，并与后端 `DATABASE_URL` 一致。
