# Linux 生产部署（Nginx + systemd + venv）

部署前请确认服务器可访问：**Python 3.13+**、**MySQL**、**PostgreSQL**（应用启动必需）、**Neo4j**、以及 **LLM 网关**。环境变量说明见仓库根目录 [README.md](../README.md)。

## 1. 目录与运行用户

建议：

- 代码目录：`/opt/recruitment_kg`（以下示例均以此为准，请按需替换）。
- 运行 systemd 的用户：具备该目录读权限的非 root 用户（如 `www-data` 或专用 `recruitment` 用户）。

```bash
sudo mkdir -p /opt/recruitment_kg
sudo chown -R your-user:your-group /opt/recruitment_kg
# 克隆或 rsync 代码后，在根目录放置生产用 .env
```

## 2. Python 虚拟环境与依赖

在仓库根目录执行（或使用脚本）：

```bash
chmod +x deploy/setup-venv.sh
./deploy/setup-venv.sh
```

若系统无 `python3.13`，请先安装（如 Ubuntu：`deadsnakes` PPA、pyenv 或官方源码）。

## 3. 构建前端

在可安装 Node 的机器上（可与应用服务器同一台）：

```bash
chmod +x deploy/build-frontend.sh
./deploy/build-frontend.sh
```

`frontend/.npmrc` 启用 `legacy-peer-deps`，以便 `echarts` / `echarts-wordcloud` 的 peer 声明在 `npm ci` 下可解析。生产构建为 `vite build`；若需类型检查可另执行 `npm run typecheck`（可能对 Node 大版本较敏感）。

产物为 `frontend/dist/`，由 Nginx 提供静态文件。

## 4. Nginx

将 [nginx/recruitment-kg.conf](nginx/recruitment-kg.conf) 中 `DEPLOY_ROOT` 全部替换为实际路径（如 `/opt/recruitment_kg`），再拷贝到站点配置并启用：

```bash
sudo cp deploy/nginx/recruitment-kg.conf /etc/nginx/sites-available/recruitment-kg
sudo ln -sf /etc/nginx/sites-available/recruitment-kg /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

TLS：在 `server { listen 443 ssl; ... }` 中配置证书路径（本仓库不提供证书申请步骤）。

## 5. systemd（uvicorn）

1. 将 [systemd/recruitment-kg.service](systemd/recruitment-kg.service) 中的 `User`、`Group`、`WorkingDirectory`、`ExecStart` 路径改为你的环境。
2. 安装并启动：

```bash
sudo cp deploy/systemd/recruitment-kg.service /etc/systemd/system/recruitment-kg.service
sudo systemctl daemon-reload
sudo systemctl enable --now recruitment-kg
journalctl -u recruitment-kg -f
```

生产请勿使用 `--reload`。`ExecStart` 中 `--host 127.0.0.1` 表示仅本机可连，由 Nginx 对外。

## 6. 验证

```bash
curl -sS http://127.0.0.1:8000/health
```

浏览器访问站点：登录、岗位列表、智能问答（WebSocket）应正常。

## 7. 安全与 CORS

- 生产务必修改 `SECRET_KEY` 与数据库密码。
- 在 `.env` 中设置 `BACKEND_CORS_ORIGINS` 为前端来源（逗号分隔），例如：`https://your.domain`。与 Nginx 同域部署时仍建议显式填写该域名，避免误用通配。

## 8. 可选

- 离线建图：`python Kg/llm_kg.py`（在已 `source .venv/bin/activate` 且配置好 `.env` 的前提下）。
- 爬虫与浏览器自动化建议与 API 分机部署。
