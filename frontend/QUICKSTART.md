# 快速启动指南

## 前置要求

1. Node.js >= 16.0.0
2. npm 或 yarn 或 pnpm

## 安装步骤

### 1. 安装依赖

```bash
cd frontend
npm install
```

### 2. 启动开发服务器

```bash
npm run dev
```

前端将在 `http://localhost:3000` 启动

### 3. 确保后端服务运行

在另一个终端窗口，启动 FastAPI 后端：

```bash
cd ..
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

后端将在 `http://localhost:8000` 启动

## 访问应用

1. 打开浏览器访问：`http://localhost:3000`
2. 首次使用需要注册账号
3. 登录后即可查看招聘信息列表

## 功能测试

### 测试流程

1. **注册账号**
   - 访问 `/register`
   - 填写姓名、邮箱、密码
   - 点击注册

2. **登录**
   - 访问 `/login`
   - 使用注册的邮箱和密码登录

3. **查看招聘信息**
   - 登录后自动跳转到招聘信息列表
   - 可以搜索、筛选、分页浏览

4. **查看详情**
   - 点击表格行或"查看详情"按钮
   - 查看完整的招聘信息

## 常见问题

### 端口冲突

如果 3000 端口被占用，Vite 会自动使用下一个可用端口。

### 后端连接失败

- 检查后端是否运行在 `http://localhost:8000`
- 检查 `vite.config.ts` 中的代理配置
- 查看浏览器控制台的网络请求

### 依赖安装失败

```bash
# 清除缓存后重试
npm cache clean --force
rm -rf node_modules package-lock.json
npm install
```

