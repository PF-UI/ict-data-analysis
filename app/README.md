# FastAPI 应用模板

这是一个标准的FastAPI项目模板，包含基本的项目结构和示例代码。

## 项目结构

```
app/
├── __init__.py
├── main.py              # 主应用文件
├── requirements.txt     # 依赖文件
├── routers/            # 路由模块
│   ├── __init__.py
│   ├── auth.py         # 认证相关路由
│   └── users.py        # 用户相关路由
└── schemas/            # 数据模式定义
    ├── __init__.py
    ├── auth.py         # 认证数据模式
    └── user.py         # 用户数据模式
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r app/requirements.txt
```

### 2. 运行应用

```bash
# 从项目根目录运行
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 或者从app目录运行
cd app
uvicorn main:app --reload
```

### 3. 访问API文档

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## API端点

### 基础端点
- `GET /` - 根路径，返回欢迎信息
- `GET /health` - 健康检查

### 认证端点 (Auth)
- `POST /api/v1/auth/login` - OAuth2 登录
- `POST /api/v1/auth/login/json` - JSON 格式登录
- `POST /api/v1/auth/register` - 用户注册

### 用户端点 (Users)
- `GET /api/v1/users/` - 获取用户列表
- `GET /api/v1/users/{user_id}` - 获取单个用户
- `POST /api/v1/users/` - 创建新用户
- `PUT /api/v1/users/{user_id}` - 更新用户
- `DELETE /api/v1/users/{user_id}` - 删除用户

## 特性

- ✅ 完整的CRUD操作示例
- ✅ Pydantic数据验证
- ✅ 自动生成API文档
- ✅ CORS中间件配置
- ✅ 模块化路由结构
- ✅ 类型提示支持

## 下一步

1. 配置数据库连接（如SQLAlchemy、MongoDB等）
2. 添加认证和授权（如JWT）
3. 添加日志记录
4. 添加单元测试
5. 配置环境变量管理

