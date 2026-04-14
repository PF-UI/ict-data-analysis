# 数据库配置与使用说明

本应用涉及**两类数据库**，职责不同，请勿混淆：

| 用途 | 推荐引擎 | 说明 |
|------|-----------|------|
| **业务数据**（用户、招聘岗位等） | **MySQL**（默认） | SQLAlchemy ORM，`DATABASE_URL` |
| **智能体记忆**（多轮对话 checkpoint） | **PostgreSQL** | LangGraph + `langgraph-checkpoint-postgres`，与业务库分离 |

开发阶段可将业务库改为 **SQLite** 做快速验证；**生产环境**建议使用 MySQL（或经充分测试的其他引擎）承载业务，PostgreSQL 仅作记忆库。

完整环境变量说明还可对照根目录 [README.md](../README.md) 与 `app/core/config.py`。

---

## 1. 业务库：`DATABASE_URL`（SQLAlchemy）

在项目根目录 `.env` 中配置，例如：

```env
# MySQL（推荐，与 PyMySQL 驱动）
DATABASE_URL=mysql+pymysql://用户名:密码@127.0.0.1:3306/数据库名

# 连接池（可选）
DB_POOL_SIZE=5
DB_MAX_OVERFLOW=10
DB_POOL_RECYCLE=3600
```

### MySQL 准备步骤

1. 安装并启动 MySQL。  
2. 创建数据库（示例）：

```sql
CREATE DATABASE your_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

3. 授予应用账号相应权限。  
4. 启动 FastAPI 时会在能力范围内**自动建表**（如 `users`、`job_listings` 等，以 `app/models` 为准）。

### SQLite（仅建议本地试跑）

```env
DATABASE_URL=sqlite:///./app.db
```

- 单文件、零安装，适合快速联调。  
- 不建议用于生产；注意备份与并发限制。

### 将业务库改为 PostgreSQL 等

需保证连接串与 SQLAlchemy 驱动一致（例如使用 `postgresql+psycopg://...` 等），并在依赖中安装对应驱动。当前仓库默认开发与文档以 **MySQL + pymysql** 为主。

---

## 2. 智能体记忆库：PostgreSQL

多轮问答、会话列表依赖 **PostgreSQL**，通过以下方式之一配置（优先级见 `Settings.get_agent_memory_database_url()`）：

```env
# 方式 A：显式连接串（推荐）
AGENT_MEMORY_DATABASE_URL=postgresql://用户:密码@localhost:5432/agent_memory?sslmode=disable

# 方式 B：用 DB_* 拼接（勿在 DB_URI 中保留未替换的 {占位符}）
DB_USER=postgres
DB_PASSWORD=你的密码
DB_HOST=localhost
DB_PORT=5432
DB_NAME=agent_memory
PG_SSLMODE=disable
```

可选：

```env
AGENT_MEMORY_POOL_MAX_SIZE=10
```

若记忆库不可用，应用启动时可能报错或日志提示；需先创建数据库并保证网络与账号权限正确。

---

## 3. 主要数据模型（`app/models`）

| 模块 | 表 / 用途 |
|------|-----------|
| `user.py` | 用户注册登录（邮箱、密码哈希等） |
| `job_listing.py` | 招聘岗位 `job_listings` |
| `city_mapping.py` | 城市等映射辅助数据 |
| `history_chat.py` | 与会话/历史相关的 ORM（若启用） |

表结构以代码为准；启动时自动建表行为取决于 `app/database.py` 中的初始化逻辑。

---

## 4. 初始化与自检

应用启动时会调用 `init_db()` 等业务库初始化逻辑。也可在 Python 中手动执行（需在项目根目录保证 `app` 可导入）：

```python
from app.database import init_db
init_db()
```

根目录 `test.py` 提供 MySQL 连通性示例，使用前请改为你的主机与账号（**不要提交真实密码**）。

---

## 5. API 调用示例

以下假设服务运行在 `http://localhost:8000`，前缀为 `/api/v1`。

### 注册

```bash
curl -X POST "http://localhost:8000/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"张三\",\"email\":\"zhangsan@example.com\",\"password\":\"password123\"}"
```

### 登录（JSON）

```bash
curl -X POST "http://localhost:8000/api/v1/auth/login/json" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"zhangsan@example.com\",\"password\":\"password123\"}"
```

### 用户列表（需 Bearer Token）

```bash
curl -X GET "http://localhost:8000/api/v1/users/" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

---

## 6. 数据库迁移（可选）

当前仓库**未强制内置 Alembic 工作流**。若后续需要版本化迁移，可自行在项目内初始化 Alembic，并将模型元数据指向 `app.models`。

---

## 7. 注意事项

1. **密钥**：`.env` 勿提交到 Git；生产环境使用强随机 `SECRET_KEY`。  
2. **密码存储**：用户密码经 bcrypt 哈希，不明文落库。  
3. **双库架构**：业务 MySQL（或 SQLite）与记忆 PostgreSQL 各司其职，避免把 LangGraph checkpoint 与 ORM 混在同一库实例却不做隔离。  
4. **连接池**：`DB_POOL_*` 请按并发与数据库 `max_connections` 调整。  
5. **备份**：定期备份 MySQL业务库与 PostgreSQL 记忆库（若需保留对话历史）。

---

## 8. 故障排查

| 现象 | 排查方向 |
|------|-----------|
| 无法连接业务库 | 检查 `DATABASE_URL`、防火墙、用户权限、库名是否存在 |
| SQLite 权限错误 | 确认进程对 `app.db` 路径有读写权限 |
| 启动失败 / 记忆库报错 | 检查 `AGENT_MEMORY_DATABASE_URL` 或 `DB_*`，确认 PostgreSQL 已启动且库已创建 |
| 表已存在或结构不一致 | 开发环境可谨慎清理后重建；生产应使用迁移工具 |
