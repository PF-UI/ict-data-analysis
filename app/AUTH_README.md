# JWT认证使用指南

## 功能概述

本项目已集成JWT（JSON Web Token）身份认证系统，包含以下功能：

- ✅ 用户注册
- ✅ 用户登录（支持OAuth2和JSON两种方式）
- ✅ JWT Token生成和验证
- ✅ 密码加密存储（bcrypt）
- ✅ 受保护的路由（需要认证才能访问）

## 安装依赖

```bash
pip install -r app/requirements.txt
```

## API端点

### 1. 用户注册（不需要认证）

**POST** `/api/v1/auth/register`

**请求体：**
```json
{
  "name": "张三",
  "email": "zhangsan@example.com",
  "password": "your_password"
}
```

**响应：**
```json
{
  "id": 1,
  "name": "张三",
  "email": "zhangsan@example.com"
}
```

### 2. 用户登录（OAuth2格式）

**POST** `/api/v1/auth/login`

**请求格式：** `application/x-www-form-urlencoded`

**参数：**
- `username`: 邮箱地址
- `password`: 密码

**响应：**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

### 3. 用户登录（JSON格式）

**POST** `/api/v1/auth/login/json`

**请求体：**
```json
{
  "email": "admin@example.com",
  "password": "secret"
}
```

**响应：**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

### 4. 访问受保护的路由

所有用户相关的路由都需要认证。在请求头中添加：

```
Authorization: Bearer <your_access_token>
```

**示例：使用curl**
```bash
curl -X GET "http://localhost:8000/api/v1/users/" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

**示例：使用Python requests**
```python
import requests

token = "your_access_token"
headers = {"Authorization": f"Bearer {token}"}
response = requests.get("http://localhost:8000/api/v1/users/", headers=headers)
```

## 测试用户

默认测试用户（密码都是 `secret`）：

1. **管理员**
   - 邮箱: `admin@example.com`
   - 密码: `secret`

2. **普通用户**
   - 邮箱: `user@example.com`
   - 密码: `secret`

## 完整使用流程示例

### 1. 注册新用户

```bash
curl -X POST "http://localhost:8000/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "新用户",
    "email": "newuser@example.com",
    "password": "mypassword123"
  }'
```

### 2. 登录获取Token

```bash
curl -X POST "http://localhost:8000/api/v1/auth/login/json" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "newuser@example.com",
    "password": "mypassword123"
  }'
```

### 3. 使用Token访问受保护的路由

```bash
# 获取用户列表
curl -X GET "http://localhost:8000/api/v1/users/" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"

# 获取特定用户
curl -X GET "http://localhost:8000/api/v1/users/1" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

## 配置说明

JWT配置在 `app/core/config.py` 中：

- `SECRET_KEY`: JWT签名密钥（生产环境应使用环境变量）
- `ALGORITHM`: 加密算法（默认HS256）
- `ACCESS_TOKEN_EXPIRE_MINUTES`: Token过期时间（默认30分钟）

### 使用环境变量配置（推荐）

创建 `.env` 文件：

```env
SECRET_KEY=your-secret-key-here
ACCESS_TOKEN_EXPIRE_MINUTES=60
```

## 安全注意事项

1. **SECRET_KEY**: 生产环境必须使用强随机密钥，不要使用默认值
2. **HTTPS**: 生产环境必须使用HTTPS传输Token
3. **密码强度**: 建议添加密码强度验证
4. **Token刷新**: 考虑实现refresh token机制
5. **数据库**: 当前使用内存存储，生产环境应使用真实数据库

## 项目结构

```
app/
├── core/
│   ├── security.py      # 密码加密、JWT生成/验证
│   ├── dependencies.py  # 认证依赖注入函数
│   └── config.py        # 配置文件
├── routers/
│   ├── auth.py          # 登录、注册路由
│   └── users.py         # 用户管理路由（需要认证）
└── schemas/
    ├── auth.py          # 认证相关数据模型
    └── user.py          # 用户数据模型
```

