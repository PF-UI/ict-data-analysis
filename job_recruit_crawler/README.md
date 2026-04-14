# Boss 直聘数据采集（job_recruit_crawler）

从 Boss 直聘按 **ICT 等关键词**采集招聘岗位数据：使用 **DrissionPage** 监听列表接口，并可按需点击侧栏补全职位描述。导出为 Excel，便于导入 MySQL 或进入本仓库的图谱构建流程（`Kg/llm_kg.py`）。

> 仓库总览、环境变量与 Neo4j / API 启动方式见根目录 [README.md](../README.md)。

## 功能要点

- 可配置关键词、城市、翻页与无头模式等（`config.py`）。
- 运行期可能需在浏览器中**手动登录** Boss直聘，脚本会等待登录完成。
- 输出目录默认为 `output/`，生成带时间戳的 **`.xlsx`**（字段由采集逻辑决定：岗位、公司、薪资、地点、描述/职责/要求等）。

## 目录结构

```text
job_recruit_crawler/
├── boss_crawler_drission.py   # 入口脚本
├── config.py                  # ICT_KEYWORDS、CITIES、CRAWLER_CONFIG 等
├── requirements.txt
├── output/                    # 导出文件（通常已 gitignore）
└── README.md
```

## 环境要求

- **Python**：建议与主项目一致 **3.13+**（根目录 `pyproject.toml`）；若使用本目录独立虚拟环境，至少 **3.10+** 并自行验证 DrissionPage 兼容性。
- **浏览器**：DrissionPage 依赖本机浏览器环境；按 DrissionPage 文档配置驱动/内核。

## 安装

在**本目录**安装最小依赖（与主仓库依赖不冲突时可共用同一 venv）：

```bash
cd job_recruit_crawler
pip install -r requirements.txt
```

若已在仓库根目录执行过 `pip install -e .`，通常已包含 `DrissionPage`、`pandas`、`openpyxl` 等，可直接运行脚本。

## 使用

```bash
cd job_recruit_crawler
python boss_crawler_drission.py
```

运行前编辑 `config.py`：

- `ICT_KEYWORDS`：搜索关键词列表  
- `CITIES`：城市  
- `CRAWLER_CONFIG`：最大页数、是否无头、是否点击侧栏补全详情等  

## 与主项目数据流（简要）

1. 本脚本导出 `output/*.xlsx`。  
2. 自行导入或 ETL 至 MySQL（表如 `job_listings`，与 `app.models.job_listing` 字段对齐）。  
3. 在仓库根目录运行 `Kg/llm_kg.py`，将岗位数据写入 **Neo4j**。  
4. **FastAPI** 与**前端**通过业务库与 Neo4j 相关接口提供服务。

## 依赖说明（requirements.txt）

- `DrissionPage`：浏览器自动化与网络监听  
- `pandas`、`openpyxl`：表格读写  
- `python-dotenv`：可选读取环境变量（若脚本中使用）

## 合规与免责声明

- 控制请求频率，避免对目标站点造成过大压力。  
- 遵守网站服务条款及当地法律法规；仅供学习研究，勿用于违法用途或商业侵权场景。
