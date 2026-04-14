# 招聘知识图谱（Recruitment KG）

面向招聘数据的**采集 → 结构化存储 → LLM 图谱构建 → Neo4j 存储 → Web 管理与智能问答**的一体化仓库。后端基于 **FastAPI**，智能问答基于 **LangGraph** 与 Neo4j 图谱工具；前端为 **Vue 3 + Vite**；离线构建流水线在 `Kg/` 中从业务库读取岗位数据并写入图数据库。

## 功能概览

| 模块 | 说明 |
|------|------|
| **数据采集** | `job_recruit_crawler/`：Boss 直聘等渠道采集，导出 Excel（详见子目录 README） |
| **业务库** | MySQL 存储招聘信息，供列表、筛选与详情接口使用 |
| **知识图谱** | `Kg/llm_kg.py`：LLM + `LLMGraphTransformer` 抽取实体与关系，写入 **Neo4j** |
| **API 服务** | `app/`：认证、岗位 CRUD、Neo4j 相关接口、基于图谱的 **QA** |
| **前端** | `frontend/`：登录注册、岗位管理、与后端联调 |

## 技术栈

- **后端**：Python 3.13+、FastAPI、SQLAlchemy、LangChain / LangGraph、Neo4j Driver  
- **记忆与会话**：PostgreSQL（`langgraph-checkpoint-postgres`，与业务 MySQL 分离）  
- **前端**：Vue 3、TypeScript、Vite、Element Plus、Pinia、ECharts  
- **图谱构建**：pandas、langchain-neo4j、自定义/实验性图转换组件（见 `pyproject.toml`）

## 仓库结构

```text
recruitment_kg/
├── app/                    # FastAPI 应用（路由、Agent、Neo4j 服务）
├── frontend/               # Vue 3 前端
├── Kg/                     # 离线：从数据源构建 Neo4j 知识图谱
├── job_recruit_crawler/    # 招聘数据采集脚本
├── config.py               # 根目录 LLM 等共享配置（供脚本 import）
├── pyproject.toml          # Python 依赖与项目元数据
├── .env                    # 本地环境变量（勿提交密钥）
└── README.md               # 本文件
```

更细的数据库说明见 [`app/DATABASE_README.md`](app/DATABASE_README.md)。

## 环境准备

1. **Python**：3.13 及以上（与 `pyproject.toml` 中 `requires-python` 一致）。  
2. **Node.js**：用于前端（建议 LTS）。  
3. **MySQL**：业务库，与 `DATABASE_URL` 一致。  
4. **PostgreSQL**：智能体多轮对话 checkpoint / 历史，需正确配置记忆库连接（见下文）。  
5. **Neo4j**：图数据库；浏览器默认 `http://localhost:7474`（可通过 `NEO4J_BROWSER_URL` 覆盖）。

## 配置说明（`.env`）

在项目根目录创建或编辑 `.env`，**不要**把真实密钥提交到 Git。常用变量如下（值为示例占位，请按本地环境修改）：

```env
# ---------- LLM（OpenAI 兼容接口）----------
LLM_API_KEY=your-api-key
LLM_MODEL=qwen3-max
# 后端 Settings 使用 OPENAI_BASE_URL；Kg 脚本会读 LLM_BASE_URL，建议两者保持一致或分别填写同一网关地址
OPENAI_BASE_URL=http://localhost:3000/v1
LLM_BASE_URL=http://localhost:3000/v1
LLM_TEMPERATURE=0.0

# ---------- 业务库 MySQL（FastAPI ORM）----------
DATABASE_URL=mysql+pymysql://user:password@127.0.0.1:3306/your_db

# ---------- 智能体记忆库 PostgreSQL ----------
# 任选其一：显式 URL，或用 DB_* 拼接（见 app/core/config.py）
AGENT_MEMORY_DATABASE_URL=postgresql://user:password@localhost:5432/agent_memory?sslmode=disable
# DB_USER=...
# DB_PASSWORD=...
# DB_HOST=localhost
# DB_PORT=5432
# DB_NAME=...

# ---------- Neo4j ----------
NEO4J_URI=neo4j://127.0.0.1:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-password

# ---------- JWT ----------
SECRET_KEY=change-me-in-production
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# ---------- CORS（生产建议设为前端域名，逗号分隔；开发可保留 *）----------
# BACKEND_CORS_ORIGINS=https://your.domain

# ---------- Kg 流水线数据源（MySQL / CSV 等，见 llm_kg 内逻辑）----------
DATA_SOURCE=mysql
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=your_user
MYSQL_PASSWORD=your_password
MYSQL_DATABASE=your_db
MYSQL_TABLE=job_listings

# 可选：批量与并发
BATCH_SIZE=10
MAX_WORKERS=5
MAX_RETRIES=3
```

数据库连接自检可使用项目根目录的 `test.py`（内置 MySQL 连接参数，运行前请改为你的本地配置）。

## 安装与运行

### 1. Python 依赖

在仓库根目录执行（推荐使用虚拟环境）：

```bash
pip install -e .
```

若需与 `app/requirements.txt` 完全锁版本，可额外参考该文件；日常开发以 `pyproject.toml` 为准。

### 2. 启动后端 API

在**项目根目录**执行（保证 `app` 包可导入）：

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- 交互式文档：<http://localhost:8000/docs>  
- 健康检查：<http://localhost:8000/health>  
- API 前缀：`/api/v1`

启动阶段会初始化业务库与 Agent 运行时；若 PostgreSQL 记忆库不可用，日志会提示，需按上文配置 `AGENT_MEMORY_DATABASE_URL` 或 `DB_*`。

### 3. 启动前端

```bash
cd frontend
npm install
npm run dev
```

当前 Vite 开发服务器端口为 **3003**，并将 `/api` 代理到 `http://localhost:8000`。生产构建：`npm run build`，产物在 `frontend/dist/`。

### 4. 构建 /更新 Neo4j 知识图谱

确保 `.env` 中 LLM、Neo4j、数据源（如 MySQL）已配置。在仓库根目录：

```bash
python Kg/llm_kg.py
```

脚本会按批从配置的数据源读取岗位数据，调用 LLM 抽取图结构并写入 Neo4j；日志与 token 用量默认写入 `Kg/` 下按日期命名的 `.log` 文件。

### 5. 数据采集（可选）

```bash
cd job_recruit_crawler
pip install -r requirements.txt
python boss_crawler_drission.py
```

详见 [`job_recruit_crawler/README.md`](job_recruit_crawler/README.md)。

## 生产部署（Linux）

见 [deploy/README.md](deploy/README.md)（Nginx、systemd、venv 脚本与校验步骤）。

## 子项目文档

- [前端说明](frontend/README.md)  
- [爬虫说明](job_recruit_crawler/README.md)  
- [数据库与连接串](app/DATABASE_README.md)

## 架构简图

```mermaid
flowchart LR
  Crawler[job_recruit_crawler]
  MySQL[(MySQL 业务库)]
  Kg[Kg/llm_kg.py]
  Neo4j[(Neo4j)]
  API[FastAPI app]
  PG[(PostgreSQL 记忆库)]
  FE[Vue 前端]

  Crawler --> MySQL
  MySQL --> Kg
  Kg --> Neo4j
  MySQL --> API
  Neo4j --> API
  PG --> API
  FE --> API
```

## 注意事项

- **安全**：生产环境务必修改默认 `SECRET_KEY`，限制 CORS 来源，并为数据库与 LLM 密钥使用独立凭证管理。  
- **限流**：`MAX_WORKERS` 等参数需与 LLM 网关配额匹配，避免批量构建时触发限流。  
- **环境变量命名**：应用内 Chat 模型基址以 `OPENAI_BASE_URL` 为准；若仅设置 `LLM_BASE_URL`，请同步设置 `OPENAI_BASE_URL` 或在代码中统一，避免后端与脚本行为不一致。

## 许可证与免责声明

各子模块若包含第三方站点采集逻辑，请遵守目标站点服务条款与当地法律法规；本项目仅供学习与研究参考。
