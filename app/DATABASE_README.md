# 数据库配置和使用说明

## 概述

本项目已集成SQLAlchemy数据库支持，**默认使用MySQL数据库**（也可切换为SQLite或PostgreSQL）。

## 环境配置

### 1. .env 文件配置

在项目根目录创建或编辑 `.env` 文件，添加以下数据库配置（第25-32行）：

```env
# 数据库配置（MySQL）
DATABASE_URL=mysql+pymysql://用户名:密码@主机:端口/数据库名
# 示例：
# DATABASE_URL=mysql+pymysql://root:password@localhost:3306/recruitment_kg

# 如果使用SQLite（开发测试），使用：
# DATABASE_URL=sqlite:///./app.db

# 如果使用PostgreSQL，使用：
# DATABASE_URL=postgresql://username:password@localhost:5432/dbname

# 数据库连接池配置
DB_POOL_SIZE=5
DB_MAX_OVERFLOW=10
DB_POOL_RECYCLE=3600
```

### 2. 数据库类型说明

#### MySQL（默认，推荐使用）
```env
DATABASE_URL=mysql+pymysql://root:password@localhost:3306/recruitment_kg
```
**配置说明：**
- `mysql+pymysql`: 使用 PyMySQL 驱动连接 MySQL
- `root`: MySQL 用户名
- `password`: MySQL 密码
- `localhost:3306`: 数据库主机和端口
- `recruitment_kg`: 数据库名称

**使用前准备：**
1. 确保已安装 MySQL 服务器
2. 创建数据库：
   ```sql
   CREATE DATABASE recruitment_kg CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   ```
3. 确保 MySQL 用户有相应权限

#### SQLite（开发测试使用）
```env
DATABASE_URL=sqlite:///./app.db
```
- 无需安装额外数据库服务器
- 数据文件存储在 `app.db`
- 适合快速开发测试

#### PostgreSQL（可选）
```env
DATABASE_URL=postgresql://username:password@localhost:5432/dbname
```
需要在 `requirements.txt` 中添加：
```
psycopg2-binary==2.9.9
```

#### MySQL
```env
DATABASE_URL=mysql+pymysql://username:password@localhost:3306/dbname
```
需要在 `requirements.txt` 中添加：
```
pymysql==1.1.0
```

## 用户表结构

数据库会自动创建 `users` 表，包含以下字段：

| 字段名 | 类型 | 说明 |
|--------|------|------|
| id | Integer | 主键，自增 |
| email | String(255) | 邮箱，唯一索引 |
| name | String(100) | 用户名 |
| hashed_password | String(255) | 密码哈希值 |
| created_at | DateTime | 创建时间 |
| updated_at | DateTime | 更新时间 |

## 数据库初始化

数据库表会在应用启动时自动创建。如果数据库文件不存在，SQLAlchemy会自动创建。

### 手动初始化

如果需要在应用启动前初始化数据库，可以运行：

```python
from app.database import init_db
init_db()
```

## 使用示例

### 1. 注册新用户

```bash
curl -X POST "http://localhost:8000/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "张三",
    "email": "zhangsan@example.com",
    "password": "password123"
  }'
```

### 2. 登录获取Token

```bash
curl -X POST "http://localhost:8000/api/v1/auth/login/json" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "zhangsan@example.com",
    "password": "password123"
  }'
```

### 3. 查询用户列表

```bash
curl -X GET "http://localhost:8000/api/v1/users/" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

## 数据库迁移（可选）

如果未来需要数据库迁移，可以使用 Alembic：

### 初始化 Alembic

```bash
cd app
alembic init alembic
```

### 创建迁移

```bash
alembic revision --autogenerate -m "Initial migration"
```

### 应用迁移

```bash
alembic upgrade head
```

## 项目结构

```
app/
├── database.py          # 数据库连接和会话管理
├── models/
│   ├── __init__.py
│   └── user.py          # 用户表模型
├── core/
│   └── config.py        # 配置文件（包含数据库配置）
└── routers/
    ├── auth.py          # 认证路由（使用数据库）
    └── users.py         # 用户管理路由（使用数据库）
```

## 注意事项

1. **生产环境**：不要使用SQLite，应使用PostgreSQL或MySQL
2. **密码安全**：密码使用bcrypt加密存储，不会明文保存
3. **数据库文件**：SQLite数据库文件 `app.db` 应在 `.gitignore` 中
4. **备份**：定期备份数据库文件
5. **连接池**：生产环境应根据实际负载调整连接池大小

## 故障排查

### 问题：数据库文件未创建

**解决方案**：检查 `DATABASE_URL` 配置是否正确，确保应用有写入权限。

### 问题：表已存在错误

**解决方案**：删除 `app.db` 文件，重启应用会自动重新创建。

### 问题：连接超时

**解决方案**：检查数据库服务是否运行，网络连接是否正常，`DATABASE_URL` 配置是否正确。

