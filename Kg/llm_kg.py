import os
import json
import time
import hashlib
import logging
import threading
import pandas as pd
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
import json_repair

# LangChain 核心依赖
from langchain_core.documents import Document
from langchain_community.document_loaders import DataFrameLoader
from langchain_neo4j import Neo4jGraph
from LLMGraphTransformer import LLMGraphTransformer
from LLMGraphTransformer.schema import NodeSchema, RelationshipSchema

#导入模型
import sys
from pathlib import Path
# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
from config import llm
# 异常处理与重试
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    RetryError
)
from langchain_core.exceptions import OutputParserException
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableLambda

# 配置日志
# 获取当前文件所在目录（Kg/）
log_dir = Path(__file__).parent
log_file = log_dir / f"llm_kg_{time.strftime('%Y%m%d')}.log"
# LLM token 用量单独文件（首行：系统/模板提示词 token；后续：每次调用的输入/输出 token）
token_usage_log_file = log_dir / f"llm_kg_tokens_{time.strftime('%Y%m%d')}.log"

# 创建文件处理器（追加模式）
file_handler = logging.FileHandler(log_file, encoding='utf-8', mode='a')
file_handler.setLevel(logging.INFO)
file_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
file_handler.setFormatter(file_formatter)

# 创建控制台处理器
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
console_handler.setFormatter(console_formatter)

# 配置根日志记录器
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[console_handler, file_handler]
)
logger = logging.getLogger("JobKGEngineer")
logger.info(f"日志文件已创建: {log_file}")
logger.info(f"Token 用量日志（单独文件）: {token_usage_log_file}")


def _extract_usage_from_ai_message(result: Any) -> Dict[str, Any]:
    """从 AIMessage / ChatResult 兼容结构中提取 token_usage 字典。"""
    md = getattr(result, "response_metadata", None) or {}
    if not isinstance(md, dict):
        return {}
    u = md.get("token_usage") or md.get("usage")
    if isinstance(u, dict):
        return u
    return {}


def _estimate_system_prompt_tokens(base_llm, text: str) -> tuple[int, str]:
    """
    估算「单条 HumanMessage 文本」的 token 数。
    优先用 LangChain；对 qwen 等未实现 get_num_tokens_from_messages 的模型回退到 tiktoken(cl100k_base)，
    再失败则用极简字符启发式（仅作数量级参考）。
    返回 (token 数, 方法标记)。
    """
    try:
        n = base_llm.get_num_tokens_from_messages([HumanMessage(content=text)])
        return int(n), "langchain_native"
    except Exception as e:
        err = str(e)
        logger.debug(f"LangChain 本地 token 计数不可用，将回退: {err[:300]}")
        try:
            import tiktoken

            enc = tiktoken.get_encoding("cl100k_base")
            n = len(enc.encode(text))
            logger.info(f"系统提示词 token 估算（tiktoken cl100k_base，近似）: {n}")
            return n, "tiktoken_cl100k_base_approx"
        except Exception as e2:
            n = max(1, len(text) // 2)
            logger.warning(
                f"系统提示词 token 使用字符启发式估算: n={n}（tiktoken 失败: {e2!s}）"
            )
            return n, "chars_div2_fallback"


def build_token_logging_llm_runnable(base_llm, token_log_path: Path, static_prompt_text: str) -> RunnableLambda:
    """
    包装 ChatModel：首行写入「系统/模板提示词」token 估算（input_text 为空时的完整模板）；
    之后每次 invoke 追加一行本次 API 返回的 prompt/completion/total tokens。
    """
    lock = threading.Lock()
    call_count = [0]

    def _write_system_prompt_line() -> None:
        with lock:
            with open(token_log_path, "a", encoding="utf-8") as f:
                ts = time.strftime("%Y-%m-%d %H:%M:%S")
                n, method = _estimate_system_prompt_tokens(base_llm, static_prompt_text)
                f.write(
                    f"{ts}\tSYSTEM_PROMPT_TEMPLATE\tprompt_tokens={n}\tmethod={method}\n"
                )

    _write_system_prompt_line()

    def _invoke_with_token_log(input, config=None, **kwargs):
        result = base_llm.invoke(input, config=config, **kwargs)
        with lock:
            call_count[0] += 1
            ncall = call_count[0]
            usage = _extract_usage_from_ai_message(result)
            pt = usage.get("prompt_tokens") or usage.get("input_tokens")
            ct = usage.get("completion_tokens") or usage.get("output_tokens")
            tt = usage.get("total_tokens")
            ts = time.strftime("%Y-%m-%d %H:%M:%S")
            with open(token_log_path, "a", encoding="utf-8") as f:
                if usage:
                    f.write(
                        f"{ts}\tcall#{ncall}\tprompt_tokens={pt}\t"
                        f"completion_tokens={ct}\ttotal_tokens={tt}\n"
                    )
                else:
                    f.write(
                        f"{ts}\tcall#{ncall}\tprompt_tokens=\tcompletion_tokens=\t"
                        f"total_tokens=\tnote=no_usage_in_response_metadata\n"
                    )
        return result

    return RunnableLambda(_invoke_with_token_log)


# ==================== 1. 环境配置与常量定义 ====================
env_path = project_root / ".env"
load_dotenv(dotenv_path=env_path)  # 加载 .env 文件中的环境变量

# LLM 配置
LLM_MODEL = os.getenv("LLM_MODEL", "qwen3-max")
LLM_API_KEY = os.getenv("LLM_API_KEY")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.0"))

# Neo4j 配置
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

# MySQL 配置
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "pf123456")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "zpsj")
MYSQL_TABLE = os.getenv("MYSQL_TABLE", "job_listings_copy")
# 调试：打印实际使用的值（不打印密码）
logger.info(f"MySQL配置: host={MYSQL_HOST}, port={MYSQL_PORT}, user={MYSQL_USER}, database={MYSQL_DATABASE}")

# 批量处理配置
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "10"))
# MAX_WORKERS: 并发线程数（同时进行的 LLM 请求数量），不是每秒请求数
# 例如：MAX_WORKERS=5 表示最多同时有 5 个线程在调用 LLM API
# 实际请求频率取决于：MAX_WORKERS × (每个请求的耗时)
# 注意：如果您的 API 限制是 RPM（每分钟请求数），需要根据请求耗时和 RPM 限制来计算合适的 MAX_WORKERS
# 例如：RPM=600，每个请求耗时 45 秒，则 MAX_WORKERS 应该设置为 600/60 = 10（假设请求是串行的）
# 但实际上由于请求是并行的，MAX_WORKERS 可以设置得更小，如 5-8
MAX_WORKERS = int(os.getenv("MAX_WORKERS", "4"))  # 根据 LLM 接口限流调整
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))  # 提取失败重试次数

# 请求间隔（秒）：控制每个批次请求之间的最小间隔，用于限流
# 例如：REQUEST_INTERVAL=0.1 表示每个批次请求之间至少间隔 0.1 秒
# 如果设置为 0，则不限制请求间隔
# 注意：这个参数控制的是批次之间的间隔，不是单个请求的间隔
REQUEST_INTERVAL = float(os.getenv("REQUEST_INTERVAL", "0"))  # 默认不限制

# 数据源配置
DATA_SOURCE = os.getenv("DATA_SOURCE", "mysql")  # csv 或 mysql
CSV_PATH = os.getenv("CSV_PATH", "joblist.csv")

# 图谱 Schema（适配招聘场景）
NODE_SCHEMAS = [
    # 第一个节点类型：具体招聘（JobPosting）
    NodeSchema(
        type="JobPosting",  # 节点类型标识（核心），唯一区分不同节点类型
        properties=["name", "salary", "experience_requirement"],  # 该类型节点包含的属性
        description="Represents a specific job posting with detailed information (e.g., salary, requirements)"
    ),
    # 第二个节点类型：公司（Company）
    NodeSchema(
        type="Company",
        properties=["name", "industry", "scale"],  # 公司节点的核心属性：名称、所属行业、规模
        description="Represents a company that offers job positions"
    ),
    # 第四个节点类型：技能（Skill）
    NodeSchema(
        type="Skill",
        properties=["name", "skill_type"],  # 技能节点属性：技能名称、技能类型（如技术技能/软技能）
        description="Technical or soft skill required for a job (e.g., Python, SQL, Communication)"
    ),
    # 第五个节点类型：地点（Location）
    NodeSchema(
        type="Location",
        properties=["name", "city", "province"],
        description=(
            "Administrative location at country/province/city level only. "
            "Rules: (1) Province node: name and province use the same standard name (e.g. 湖北省); leave city empty. "
            "(2) City node: name matches city (e.g. 武汉市); set province to its parent province; city can repeat name for clarity. "
            "(3) Country node: e.g. 中国; province/city empty. No street/building/floor."
        ),
    ),
    # 第六个节点类型：年份（Year）
    NodeSchema(
        type="Year",
        properties=["name"],  # 年份名称（如"2024"、"2025"）
        description="Represents a year for job posting statistics (e.g., 2024, 2025)"
    )
]

RELATIONSHIP_SCHEMAS = [
    # 关系1：具体招聘（JobPosting）由公司（Company）提供（OFFERED_BY）
    RelationshipSchema("JobPosting", "OFFERED_BY", "Company"),
    # 关系2：具体招聘（JobPosting）位于（LOCATED_IN）地点（Location）
    RelationshipSchema("JobPosting", "LOCATED_IN", "Location"),
    # 关系3：具体招聘（JobPosting）需要技能（REQUIRES_SKILL）技能（Skill），且该关系有属性「熟练度等级」
    RelationshipSchema("JobPosting", "REQUIRES_SKILL", "Skill", ["proficiency_level"]),
    # 关系4：公司（Company）位于（LOCATED_IN）地点（Location）
    RelationshipSchema("Company", "LOCATED_IN", "Location"),
    # 关系5：地点层级（城市 Location 属于 省份 Location）
    RelationshipSchema("Location", "BELONGS_TO", "Location"),
    # 关系6：具体招聘（JobPosting）与统计年份（Year）；关系类型为 YEAR（勿与标签 Year 混淆）
    RelationshipSchema("JobPosting", "YEAR", "Year"),
]

# 额外提取规则（与 NODE_SCHEMAS / RELATIONSHIP_SCHEMAS 一致；勿引入未在 schema 中声明的类型）
ADDITIONAL_INSTRUCTIONS = """
【全局】
1. 节点展示名、实体名用中文（技能名可用约定俗成的中英文，如 Python）。
2. 每个节点 id 唯一，格式 [Type]_[hash]，如 JobPosting_8f3a9d。
3. 仅抽取文本中明确出现的信息，禁止臆造公司名、地点、技能；与下述「必须连边」冲突时，**宁可少建节点，不可编造**。
4. REQUIRES_SKILL 关系必须带属性 proficiency_level（如 熟练、精通、了解）。

【Company】
5. name 须为真实公司全称或常用简称；禁止「公司」「本公司」「我司」等泛称。
6. 无明确公司名则**不要**创建 Company，也不要为其连边。

【Location】
7. 仅国家/省/市层级；禁止街道、楼宇、楼层。
8. name 为标准地名（如 湖北省、武汉市）；禁止用「工作地点」等描述语。
9. 省级节点：name 与 province 一致；city 留空。市级节点：name 与 city 一致；province 填所属省。
10. 文本同时出现省和市时：建两个 Location 节点，并建 **市 Location -[BELONGS_TO]-> 省 Location**（方向：城市指向省份）。

【JobPosting】
11. 表示一条招聘岗位；填充 name、salary、experience_requirement 等已声明属性。

【关系 — 对「已抽取」的节点必须满足】
12. 若存在 Company：JobPosting -[OFFERED_BY]-> Company。
13. 若存在 Location：JobPosting -[LOCATED_IN]-> Location（可连到市或省节点，与文本一致）。
14. 若同时存在 Company 与 Location：Company -[LOCATED_IN]-> Location（通常与岗位工作地点一致）。
15. 若 metadata 含 data_year：JobPosting -[YEAR]-> Year（Year.name 与该年份一致，如 2026）。
16. 多条招聘混在同一文本时，按条拆分，勿合并不同岗位。

【图连通性】
17. 除孤立禁止项外，已抽取的节点应通过上述关系连成图；未抽取的 Company 不要求 12、14。
"""

# ==================== 2. 核心工程化组件 ====================
@dataclass
class ExtractionResult:
    """提取结果封装，便于缓存和传输"""
    nodes: List[Dict[str, Any]] = field(default_factory=list)
    relationships: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    success: bool = True
    error_msg: str = ""

def clean_company_nodes(nodes: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], Dict[str, str]]:
    """
    清洗 Company 节点：过滤无效名称，确保必填字段
    返回: (清洗后的节点列表, ID映射字典 {原始ID: 新ID})
    """
    cleaned = []
    id_mapping = {}  # 原始ID -> 新ID的映射
    invalid_names = {"公司", "本公司", "我司", "该公司", "此公司"}
    
    for node in nodes:
        if node.get("type") != "Company":
            cleaned.append(node)
            continue
        
        # 保存原始ID
        original_id = str(node.get("id", ""))
        
        # 过滤缺少 name 的节点
        node_name = node.get("properties", {}).get("name", "").strip()
        if not node_name:
            logger.warning(f"过滤无效 Company 节点：缺少 name 属性 - {node}")
            continue
        
        # 过滤不规范名称
        if node_name in invalid_names or len(node_name) < 2:
            logger.warning(f"过滤无效 Company 节点：名称不规范 - {node_name}")
            continue
        
        # 标准化 ID（确保基于有效名称生成）
        new_id = f"Company_{hashlib.md5(node_name.encode('utf-8')).hexdigest()[:6]}"
        node["id"] = new_id
        
        # 建立映射（如果原始ID存在且与新ID不同）
        if original_id and original_id != new_id:
            id_mapping[original_id] = new_id
        
        cleaned.append(node)
    
    return cleaned, id_mapping

def clean_location_nodes(nodes: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], Dict[str, str]]:
    """
    清洗 Location 节点：过滤详细地址，标准化层级，去重相同名称
    返回: (清洗后的节点列表, ID映射字典 {原始ID: 新ID})
    """
    cleaned = []
    invalid_names = {"工作地点", "上班地址", "办公地点", "工作地址"}
    # 关键词过滤：包含这些词的为详细地址
    detail_keywords = {"栋", "楼", "室", "号", "路", "街", "巷", "大厦", "广场", "小区"}
    
    # 用于去重的字典：标准化名称 -> 节点
    location_dict = {}
    id_mapping = {}  # 原始ID -> 新ID的映射
    
    for node in nodes:
        if node.get("type") != "Location":
            cleaned.append(node)
            continue
        
        # 保存原始ID
        original_id = str(node.get("id", ""))
        
        node_name = node.get("properties", {}).get("name", "").strip()
        if not node_name:
            logger.warning(f"过滤无效 Location 节点：缺少 name 属性 - {node}")
            continue
        
        if node_name in invalid_names:
            logger.warning(f"过滤无效 Location 节点：名称不规范 - {node_name}")
            continue
        
        if any(keyword in node_name for keyword in detail_keywords):
            logger.warning(f"过滤无效 Location 节点：详细地址 - {node_name}")
            continue
        
        # 标准化名称
        normalized_name = node_name.replace("市", "").replace("省", "").replace("自治区", "").replace("特别行政区", "").strip()
        
        props = node.get("properties", {})
        if props.get("province"):
            props["province"] = props["province"].replace("省", "").replace("自治区", "").replace("特别行政区", "").strip()
        if props.get("city"):
            props["city"] = props["city"].replace("市", "").strip()
        
        # 基于标准化名称生成 ID
        new_id = f"Location_{hashlib.md5(normalized_name.encode('utf-8')).hexdigest()[:6]}"
        
        # 如果已存在相同标准化名称的节点，合并属性
        if normalized_name in location_dict:
            existing_node = location_dict[normalized_name]
            existing_props = existing_node.get("properties", {})
            existing_id = str(existing_node.get("id", ""))
            
            # 如果合并节点，建立原始ID到合并后节点ID的映射
            if original_id and original_id != existing_id:
                id_mapping[original_id] = existing_id
            
            if props.get("province") and not existing_props.get("province"):
                existing_props["province"] = props["province"]
            if props.get("city") and not existing_props.get("city"):
                existing_props["city"] = props["city"]
            
            existing_name = existing_props.get("name", normalized_name)
            if len(node_name) < len(existing_name):
                existing_props["name"] = node_name
            elif existing_name == normalized_name and node_name != normalized_name:
                existing_props["name"] = node_name
            
            existing_node["properties"] = existing_props
            logger.debug(f"合并 Location 节点: {node_name} -> {normalized_name} (ID: {new_id})")
        else:
            # 新节点，建立原始ID到新ID的映射
            if original_id and original_id != new_id:
                id_mapping[original_id] = new_id
            
            props["name"] = node_name if node_name != normalized_name else normalized_name
            node["id"] = new_id
            node["properties"] = props
            location_dict[normalized_name] = node
    
    cleaned.extend(location_dict.values())
    return cleaned, id_mapping

def clean_year_nodes(nodes: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], Dict[str, str]]:
    """
    清洗 Year 节点：去重相同年份的节点，确保相同年份使用相同的 ID
    
    返回: (清洗后的节点列表, ID映射字典 {原始ID: 新ID})
    """
    cleaned = []
    id_mapping = {}  # 原始ID -> 新ID的映射
    year_dict = {}  # 年份名称 -> Year 节点
    
    for node in nodes:
        if node.get("type") != "Year":
            cleaned.append(node)
            continue
        
        # 保存原始ID
        original_id = str(node.get("id", ""))
        
        # 获取年份名称
        year_name = node.get("properties", {}).get("name", "").strip()
        if not year_name:
            logger.warning(f"过滤无效 Year 节点：缺少 name 属性 - {node}")
            continue
        
        # 标准化年份名称（确保是4位数字）
        try:
            year_int = int(year_name)
            year_name = str(year_int)  # 标准化为字符串
        except (ValueError, TypeError):
            logger.warning(f"过滤无效 Year 节点：年份格式不正确 - {year_name}")
            continue
        
        # 基于年份名称生成标准 ID
        standard_id = f"Year_{year_name}"
        
        # 如果该年份已存在，使用已存在的节点，并建立 ID 映射
        if year_name in year_dict:
            existing_node = year_dict[year_name]
            existing_id = str(existing_node.get("id", ""))
            
            # 如果原始ID与标准ID不同，建立映射
            if original_id and original_id != existing_id:
                id_mapping[original_id] = existing_id
                logger.debug(f"合并 Year 节点: {original_id} -> {existing_id} (年份: {year_name})")
        else:
            # 新节点，使用标准 ID
            node["id"] = standard_id
            node["properties"]["name"] = year_name
            year_dict[year_name] = node
            
            # 如果原始ID与标准ID不同，建立映射
            if original_id and original_id != standard_id:
                id_mapping[original_id] = standard_id
                logger.debug(f"标准化 Year 节点 ID: {original_id} -> {standard_id} (年份: {year_name})")
    
    # 将去重后的 Year 节点添加到结果中
    cleaned.extend(year_dict.values())
    return cleaned, id_mapping

def extract_years_from_postings(
    nodes: List[Dict[str, Any]], 
    relationships: List[Dict[str, Any]],
    metadata: Dict[str, Any] = None
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    从 metadata 中提取年份，创建 Year 节点并建立 JobPosting -> YEAR -> Year 关系
    
    Args:
        nodes: 节点列表
        relationships: 关系列表
        metadata: 文档的 metadata（包含 data_year 字段）
    
    返回: (更新后的节点列表, 更新后的关系列表)
    """
    # 获取所有 JobPosting 节点
    job_posting_nodes = [n for n in nodes if n.get("type") == "JobPosting"]
    
    if not job_posting_nodes:
        logger.warning(f"extract_years_from_postings: 没有找到 JobPosting 节点")
        return nodes, relationships
    
    if not metadata:
        logger.warning(f"extract_years_from_postings: metadata 为空")
        return nodes, relationships
    
    # 从 metadata 中提取年份
    data_year = metadata.get("data_year")
    logger.info(f"extract_years_from_postings: 从 metadata 获取 data_year = {data_year}, 完整 metadata keys: {list(metadata.keys())}")
    if not data_year:
        # 如果没有 data_year，尝试从 created_at 中提取年份
        created_at = metadata.get("created_at")
        if created_at:
            try:
                from datetime import datetime
                if isinstance(created_at, str):
                    # 尝试解析日期字符串
                    dt = datetime.strptime(created_at[:10], "%Y-%m-%d")
                    data_year = dt.year
                elif hasattr(created_at, 'year'):
                    data_year = created_at.year
            except Exception as e:
                logger.debug(f"无法从 created_at 提取年份: {e}")
    
    if not data_year:
        logger.warning(f"extract_years_from_postings: 无法提取年份，data_year={data_year}, created_at={metadata.get('created_at')}")
        return nodes, relationships
    
    # 标准化年份（转换为字符串）
    year_str = str(data_year).strip()
    if not year_str or len(year_str) != 4:
        logger.warning(f"无效的年份格式: {data_year}")
        return nodes, relationships
    
    # 创建 Year 节点 ID
    year_id = f"Year_{year_str}"
    
    # 检查 Year 节点是否已存在
    year_node_exists = any(n.get("id") == year_id for n in nodes)
    
    new_nodes = nodes.copy()
    if not year_node_exists:
        # 创建 Year 节点
        year_node = {
            "id": year_id,
            "type": "Year",
            "properties": {
                "name": year_str
            }
        }
        new_nodes.append(year_node)
        logger.debug(f"创建 Year 节点: {year_id} ({year_str})")
    
    # 为每个 JobPosting 建立 YEAR 关系
    new_relationships = relationships.copy()
    existing_rels = set()
    for r in relationships:
        try:
            if isinstance(r, dict):
                source = str(r.get("source", ""))
                rel_type = str(r.get("type", ""))
                target = str(r.get("target", ""))
                if source and target and rel_type:
                    existing_rels.add((source, rel_type, target))
        except Exception:
            continue
    
    for posting in job_posting_nodes:
        posting_id = str(posting.get("id", ""))
        
        # 检查关系是否已存在
        rel_key = (posting_id, "YEAR", year_id)
        if rel_key not in existing_rels:
            new_relationships.append({
                "source": posting_id,
                "target": year_id,
                "type": "YEAR",
                "properties": {}
            })
            existing_rels.add(rel_key)
            logger.info(f"建立年份关系: {posting_id} -> YEAR -> {year_id} ({year_str})")
    
    return new_nodes, new_relationships

def clean_relationships(
    relationships: List[Dict[str, Any]], 
    valid_node_ids: set,
    id_mapping: Dict[str, str] = None
) -> List[Dict[str, Any]]:
    """
    清洗关系：更新节点ID并过滤无效关系
    
    Args:
        relationships: 原始关系列表
        valid_node_ids: 清洗后所有有效节点的ID集合
        id_mapping: 原始ID到新ID的映射字典
    
    Returns:
        清洗后的关系列表
    """
    if id_mapping is None:
        id_mapping = {}
    
    cleaned = []
    for rel in relationships:
        source_id = str(rel.get("source", ""))
        target_id = str(rel.get("target", ""))
        
        # 使用映射更新节点ID
        if source_id in id_mapping:
            source_id = id_mapping[source_id]
            rel["source"] = source_id
        
        if target_id in id_mapping:
            target_id = id_mapping[target_id]
            rel["target"] = target_id
        
        # 检查更新后的节点ID是否存在
        if source_id in valid_node_ids and target_id in valid_node_ids:
            cleaned.append(rel)
        else:
            # 对于 YEAR 关系，输出更详细的日志
            if rel.get('type') == 'YEAR':
                logger.warning(f"⚠️ 过滤 YEAR 关系: {source_id} -> YEAR -> {target_id}")
                logger.warning(f"   source_id 在 valid_node_ids 中: {source_id in valid_node_ids}")
                logger.warning(f"   target_id 在 valid_node_ids 中: {target_id in valid_node_ids}")
                logger.warning(f"   valid_node_ids 包含 Year 节点: {any('Year_' in str(nid) for nid in valid_node_ids)}")
            else:
                logger.warning(f"过滤无效关系: {source_id}-{rel.get('type', '')}-{target_id} (节点不存在)")
    
    return cleaned
    
def supplement_missing_relationships(nodes: List[Dict[str, Any]], relationships: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """补充缺失的关系：确保 JobPosting-Company、JobPosting-Location、Company-Location 关系存在"""
    # 构建节点索引：按类型分组
    job_posting_nodes = [n for n in nodes if n.get("type") == "JobPosting"]
    company_nodes = [n for n in nodes if n.get("type") == "Company"]
    location_nodes = [n for n in nodes if n.get("type") == "Location"]
    
    # 构建现有关系集合（用于快速查找）
    existing_rels = set()
    for rel in relationships:
        try:
            if not isinstance(rel, dict):
                logger.warning(f"跳过无效关系格式: {type(rel)}")
                continue
            source = str(rel.get("source", ""))
            rel_type = str(rel.get("type", ""))
            target = str(rel.get("target", ""))
            if source and target and rel_type:
                rel_key = (source, rel_type, target)
                existing_rels.add(rel_key)
        except Exception as e:
            logger.warning(f"处理关系时出错，跳过: {e}, 关系: {rel}")
            continue
    
    supplemented = relationships.copy()
    
    # 1. 补充 JobPosting -> OFFERED_BY -> Company 关系（一对一，不是多对多）
    if job_posting_nodes and company_nodes:
        for job_posting in job_posting_nodes:
            job_posting_id = str(job_posting.get("id", ""))
            
            # 检查该 JobPosting 是否已经有 OFFERED_BY 关系
            has_offered_by = any(
                isinstance(rel, dict) and 
                str(rel.get("source", "")) == job_posting_id and 
                rel.get("type") == "OFFERED_BY"
                for rel in relationships
            )
            
            if not has_offered_by:
                # 如果只有一个 Company，直接连接
                if len(company_nodes) == 1:
                    company_id = str(company_nodes[0].get("id", ""))
                    rel_key = (job_posting_id, "OFFERED_BY", company_id)
                    if rel_key not in existing_rels:
                        supplemented.append({
                            "source": job_posting_id,
                            "target": company_id,
                            "type": "OFFERED_BY",
                            "properties": {}
                        })
                        logger.debug(f"补充关系: {job_posting_id} -> OFFERED_BY -> {company_id}")
                        existing_rels.add(rel_key)
                # 如果有多个 Company，不自动补充（需要LLM明确提取）
    
    # 2. 补充 JobPosting -> LOCATED_IN -> Location 关系（类似逻辑）
    if job_posting_nodes and location_nodes:
        for job_posting in job_posting_nodes:
            job_posting_id = str(job_posting.get("id", ""))
            
            # 检查该 JobPosting 是否已经有 LOCATED_IN 关系
            has_located_in = any(
                isinstance(rel, dict) and 
                str(rel.get("source", "")) == job_posting_id and 
                rel.get("type") == "LOCATED_IN"
                for rel in relationships
            )
            
            if not has_located_in:
                # 如果只有一个 Location，直接连接
                if len(location_nodes) == 1:
                    location_id = str(location_nodes[0].get("id", ""))
                    rel_key = (job_posting_id, "LOCATED_IN", location_id)
                    if rel_key not in existing_rels:
                        supplemented.append({
                            "source": job_posting_id,
                            "target": location_id,
                            "type": "LOCATED_IN",
                            "properties": {}
                        })
                        logger.debug(f"补充关系: {job_posting_id} -> LOCATED_IN -> {location_id}")
                        existing_rels.add(rel_key)
    
    # 3. 补充 Company -> LOCATED_IN -> Location 关系（类似逻辑）
    if company_nodes and location_nodes:
        for company in company_nodes:
            company_id = str(company.get("id", ""))
            
            # 检查该 Company 是否已经有 LOCATED_IN 关系
            has_located_in = any(
                isinstance(rel, dict) and 
                str(rel.get("source", "")) == company_id and 
                rel.get("type") == "LOCATED_IN"
                for rel in relationships
            )
            
            if not has_located_in:
                # 如果只有一个 Location，直接连接
                if len(location_nodes) == 1:
                    location_id = str(location_nodes[0].get("id", ""))
                    rel_key = (company_id, "LOCATED_IN", location_id)
                    if rel_key not in existing_rels:
                        supplemented.append({
                            "source": company_id,
                            "target": location_id,
                            "type": "LOCATED_IN",
                            "properties": {}
                        })
                        logger.debug(f"补充关系: {company_id} -> LOCATED_IN -> {location_id}")
                        existing_rels.add(rel_key)
    
    return supplemented
    
class ProcessStateManager:
    """处理状态管理器（实现断点续传 - 使用范围查询优化）"""
    def __init__(self, state_file: str = "./Kg/process_state.json"):
        self.state_file = Path(state_file)
        self.state_file.parent.mkdir(exist_ok=True)
        self._init_state()
    
    def _init_state(self):
        """初始化状态文件"""
        if not self.state_file.exists():
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump({
                    "last_extracted_id": 0,
                    "last_imported_id": 0,
                    "failed_ids": [],
                    "last_update": None
                }, f, ensure_ascii=False, indent=2)
        else:
            # 兼容旧格式：迁移到 extracted/imported 双游标
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    state = json.load(f)
                changed = False

                # 最旧格式：processed_ids -> last_processed_id
                if "processed_ids" in state and "last_processed_id" not in state:
                    processed_ids = state.get("processed_ids", [])
                    last_id = max(processed_ids) if processed_ids else 0
                    state["last_processed_id"] = last_id
                    del state["processed_ids"]
                    logger.info(f"迁移状态格式: processed_ids -> last_processed_id={last_id}")
                    changed = True

                # 旧格式：last_processed_id -> 双游标（默认两者一致）
                if "last_processed_id" in state:
                    last_id = int(state.get("last_processed_id") or 0)
                    if "last_extracted_id" not in state:
                        state["last_extracted_id"] = last_id
                        changed = True
                    if "last_imported_id" not in state:
                        state["last_imported_id"] = last_id
                        changed = True
                    del state["last_processed_id"]
                    changed = True

                # 新字段兜底
                if "last_extracted_id" not in state:
                    state["last_extracted_id"] = 0
                    changed = True
                if "last_imported_id" not in state:
                    state["last_imported_id"] = 0
                    changed = True
                if "failed_ids" not in state:
                    state["failed_ids"] = []
                    changed = True
                if "last_update" not in state:
                    state["last_update"] = None
                    changed = True

                if changed:
                    with open(self.state_file, "w", encoding="utf-8") as f:
                        json.dump(state, f, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.warning(f"状态文件迁移失败: {e}")
    
    def load_state(self) -> Dict[str, Any]:
        """加载处理状态"""
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                state = json.load(f)
                # 兜底，保证关键字段存在
                state.setdefault("last_extracted_id", int(state.get("last_processed_id", 0) or 0))
                state.setdefault("last_imported_id", int(state.get("last_processed_id", 0) or 0))
                state.setdefault("failed_ids", [])
                state.setdefault("last_update", None)
                return state
        except Exception as e:
            logger.error(f"加载状态文件失败: {e}")
            return {"last_extracted_id": 0, "last_imported_id": 0, "failed_ids": [], "last_update": None}
    
    def save_state(self, last_extracted_id: int, last_imported_id: int, failed_ids: List[int]):
        """保存处理状态"""
        try:
            state = {
                "last_extracted_id": int(last_extracted_id),
                "last_imported_id": int(last_imported_id),
                "failed_ids": failed_ids,
                "last_update": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存状态文件失败: {e}")
    
    def get_last_extracted_id(self) -> int:
        """获取最后成功提取的ID"""
        state = self.load_state()
        return int(state.get("last_extracted_id", 0) or 0)

    def get_last_imported_id(self) -> int:
        """获取最后成功入库的ID（续跑依据）"""
        state = self.load_state()
        return int(state.get("last_imported_id", 0) or 0)

    def get_last_processed_id(self) -> int:
        """兼容旧调用：返回 last_imported_id 作为“已处理”进度"""
        return self.get_last_imported_id()
    
    def get_failed_ids(self) -> set:
        """获取失败的ID集合"""
        state = self.load_state()
        return set(state.get("failed_ids", []))
    
    def update_last_extracted_id(self, record_id: int):
        """更新最后提取ID（只保留最大的ID）"""
        state = self.load_state()
        current_last = int(state.get("last_extracted_id", 0) or 0)
        if record_id > current_last:
            state["last_extracted_id"] = int(record_id)
            state["last_update"] = time.strftime("%Y-%m-%d %H:%M:%S")
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)

    def update_last_imported_id(self, record_id: int):
        """更新最后入库ID（只保留最大的ID）"""
        state = self.load_state()
        current_last = int(state.get("last_imported_id", 0) or 0)
        if record_id > current_last:
            state["last_imported_id"] = int(record_id)
            state["last_update"] = time.strftime("%Y-%m-%d %H:%M:%S")
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
    
    def add_failed(self, record_id: int):
        """添加失败记录"""
        state = self.load_state()
        failed_ids = state.get("failed_ids", [])
        if record_id not in failed_ids:
            failed_ids.append(record_id)
            state["failed_ids"] = failed_ids
            state["last_update"] = time.strftime("%Y-%m-%d %H:%M:%S")
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
    
    def remove_failed(self, record_id: int):
        """从失败列表中移除记录（处理成功后调用）"""
        state = self.load_state()
        failed_ids = state.get("failed_ids", [])
        if record_id in failed_ids:
            failed_ids.remove(record_id)
            state["failed_ids"] = failed_ids
            state["last_update"] = time.strftime("%Y-%m-%d %H:%M:%S")
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
    
    def clear_state(self):
        """清空状态（重新开始）"""
        self.save_state(0, 0, [])

class CacheManager:
    """图谱提取结果缓存管理器（基于文件系统）"""
    def __init__(self, cache_dir: str = "./Kg/job_kg_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.cache_index_file = self.cache_dir / "cache_index.json"  # 缓存索引（哈希→文件名）
        self._init_cache_index()

    def _init_cache_index(self):
        """初始化缓存索引文件"""
        if not self.cache_index_file.exists():
            with open(self.cache_index_file, "w", encoding="utf-8") as f:
                json.dump({}, f, ensure_ascii=False, indent=2)

    def _get_doc_hash(self, doc_content: str) -> str:
        """生成文档内容的哈希值作为缓存键"""
        return hashlib.md5(doc_content.encode("utf-8")).hexdigest()
    
    def _serialize_metadata(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """序列化 metadata，将 Timestamp 等不可序列化的对象转换为字符串"""
        serialized = {}
        for key, value in metadata.items():
            if value is None:
                serialized[key] = None
            elif isinstance(value, (str, int, float, bool)):
                serialized[key] = value
            elif hasattr(value, 'strftime'):  # Timestamp, datetime 等
                serialized[key] = str(value)
            elif isinstance(value, (list, tuple)):
                serialized[key] = [str(v) if hasattr(v, 'strftime') else v for v in value]
            elif isinstance(value, dict):
                serialized[key] = self._serialize_metadata(value)
            else:
                # 其他类型转换为字符串
                serialized[key] = str(value)
        return serialized
    
    def _serialize_list(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """序列化节点或关系列表，处理其中的 Timestamp 等不可序列化对象"""
        serialized = []
        for item in items:
            if isinstance(item, dict):
                serialized_item = {}
                for key, value in item.items():
                    if value is None:
                        serialized_item[key] = None
                    elif isinstance(value, (str, int, float, bool)):
                        serialized_item[key] = value
                    elif hasattr(value, 'strftime'):  # Timestamp, datetime 等
                        serialized_item[key] = str(value)
                    elif isinstance(value, dict):
                        serialized_item[key] = self._serialize_metadata(value)
                    elif isinstance(value, (list, tuple)):
                        serialized_item[key] = [str(v) if hasattr(v, 'strftime') else v for v in value]
                    else:
                        serialized_item[key] = str(value)
                serialized.append(serialized_item)
            else:
                serialized.append(item)
        return serialized

    def has_cache(self, doc: Document) -> bool:
        """检查文档是否有缓存"""
        doc_hash = self._get_doc_hash(doc.page_content)
        with open(self.cache_index_file, "r", encoding="utf-8") as f:
            cache_index = json.load(f)
        return doc_hash in cache_index

    def load_cache(self, doc: Document) -> Optional[ExtractionResult]:
        """加载文档的缓存结果"""
        doc_hash = self._get_doc_hash(doc.page_content)
        with open(self.cache_index_file, "r", encoding="utf-8") as f:
            cache_index = json.load(f)
        
        if doc_hash not in cache_index:
            return None
        
        cache_file = self.cache_dir / cache_index[doc_hash]
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                return ExtractionResult(**json.load(f))
        except Exception as e:
            logger.error(f"加载缓存失败: {e}")
            return None

    def save_cache(self, doc: Document, result: ExtractionResult):
        """保存文档的提取结果到缓存"""
        doc_hash = self._get_doc_hash(doc.page_content)
        cache_file = self.cache_dir / f"{doc_hash}.json"
        
        # 准备可序列化的数据（处理 Timestamp 等不可序列化的对象）
        cache_data = {
            "nodes": self._serialize_list(result.nodes),
            "relationships": self._serialize_list(result.relationships),
            "metadata": self._serialize_metadata(result.metadata),
            "success": result.success,
            "error_msg": result.error_msg
        }
        
        # 保存提取结果
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
        
        # 更新缓存索引
        with open(self.cache_index_file, "r", encoding="utf-8") as f:
            cache_index = json.load(f)
        cache_index[doc_hash] = cache_file.name
        with open(self.cache_index_file, "w", encoding="utf-8") as f:
            json.dump(cache_index, f, ensure_ascii=False, indent=2)
        
        logger.debug(f"缓存已保存: {cache_file.name}")

    def clear_cache(self):
        """清空所有缓存"""
        # 删除缓存文件
        for file in self.cache_dir.glob("*.json"):
            if file != self.cache_index_file:
                file.unlink()
        # 清空索引
        with open(self.cache_index_file, "w", encoding="utf-8") as f:
            json.dump({}, f, ensure_ascii=False, indent=2)
        logger.info("✅ 所有缓存已清空")


def sanitize_llm_graph_json(parsed_json: Any) -> Dict[str, Any]:
    """
    丢弃指向不存在节点 id 的关系，避免 LLMGraphTransformer 在 _parse_and_clean_json 里
    因 Relationship(source/target=None) 触发 Pydantic 校验失败。
    """
    if not isinstance(parsed_json, dict):
        return {"nodes": [], "relationships": []}
    nodes = parsed_json.get("nodes") or []
    if not isinstance(nodes, list):
        nodes = []
    rels = parsed_json.get("relationships") or []
    if not isinstance(rels, list):
        rels = []
    node_ids: set[str] = set()
    for n in nodes:
        if isinstance(n, dict) and n.get("id") is not None:
            n["id"] = str(n["id"])
            node_ids.add(n["id"])
    filtered: List[Dict[str, Any]] = []
    dropped = 0
    for r in rels:
        if not isinstance(r, dict):
            dropped += 1
            continue
        s, t = r.get("source"), r.get("target")
        if s is None or t is None:
            dropped += 1
            continue
        ss, tt = str(s), str(t)
        if ss not in node_ids or tt not in node_ids:
            dropped += 1
            continue
        # 与 node_map 键一致（避免 JSON 中数字 id 与字符串 id 混用导致 lookup 为 None）
        filtered.append({**r, "source": ss, "target": tt})
    if dropped:
        logger.warning(
            f"已丢弃 {dropped} 条无效关系（source/target 不在 nodes 列表或为空），避免解析崩溃"
        )
    parsed_json["nodes"] = nodes
    parsed_json["relationships"] = filtered
    return parsed_json


class RobustLLMGraphTransformer:
    """带重试和异常处理的 LLMGraphTransformer 封装"""
    def __init__(self):
        # 初始化 LLM
        self.llm = llm
        # 初始化官方 LLMGraphTransformer（先挂原始 llm 以生成与库一致的 prompt）
        self.transformer = LLMGraphTransformer(
            llm=self.llm,
            allowed_nodes=NODE_SCHEMAS,
            allowed_relationships=RELATIONSHIP_SCHEMAS,
            additional_instructions=ADDITIONAL_INSTRUCTIONS
        )
        # Token 用量单独写入 token_usage_log_file：首行系统/模板提示词 token，后续每次调用一行
        static_prompt_text = self.transformer.prompt.format(input_text="")
        logged_runnable = build_token_logging_llm_runnable(
            self.llm, token_usage_log_file, static_prompt_text
        )
        self.transformer.chain = self.transformer.prompt | logged_runnable

    def _convert_to_graph_document_safe(self, document: Document, config: Any = None):
        """
        与 LLMGraphTransformer.convert_to_graph_document 等价，但在解析前对 JSON 做关系清洗，
        避免关系引用缺失节点导致 Pydantic ValidationError。
        """
        from LLMGraphTransformer.main import _parse_and_clean_json, _format_graph
        from LLMGraphTransformer.schema import GraphDocument

        text = document.page_content
        raw_schema = self.transformer.chain.invoke({"input_text": text}, config=config)
        if not isinstance(raw_schema, str):
            raw_schema = raw_schema.content
        parsed_json = json_repair.loads(raw_schema)
        parsed_json = sanitize_llm_graph_json(parsed_json)
        parsed_nodes, parsed_rels = _parse_and_clean_json(parsed_json)
        nodes, relationships = _format_graph(parsed_nodes, parsed_rels)
        nodes, relationships = self.transformer.graph_strict_mode_filtering(nodes, relationships)
        return GraphDocument(nodes=nodes, relationships=relationships, source=document)

    @retry(
        stop=stop_after_attempt(MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((OutputParserException, Exception)),
        reraise=True
    )
    def extract_single_doc(self, doc: Document) -> ExtractionResult:
        """提取单个文档的图谱数据（带重试和清洗）"""
        try:
            # 执行提取
            graph_doc = self._convert_to_graph_document_safe(doc)
            
            # 转换为字典格式
            nodes = []
            for node in graph_doc.nodes:
                node_dict = {
                    "id": str(node.id),
                    "type": str(node.type),
                    "properties": {k: str(v) for k, v in (node.properties.items() if node.properties else {})}
                }
                nodes.append(node_dict)
            
            relationships = []
            for rel in graph_doc.relationships:
                # 检查 source 和 target 是否为 None
                if rel.source is None or rel.target is None:
                    logger.warning(f"过滤无效关系: source或target为None - type={rel.type}")
                    continue
                
                try:
                    source_id = str(rel.source.id) if hasattr(rel.source, 'id') else str(rel.source)
                    target_id = str(rel.target.id) if hasattr(rel.target, 'id') else str(rel.target)
                    
                    # 再次检查转换后的ID是否有效
                    if not source_id or not target_id or source_id == "None" or target_id == "None":
                        logger.warning(f"过滤无效关系: source_id={source_id}, target_id={target_id}")
                        continue
                    
                    rel_dict = {
                        "source": source_id,
                        "target": target_id,
                        "type": str(rel.type),
                        "properties": {k: str(v) for k, v in (rel.properties.items() if rel.properties else {})}
                    }
                    relationships.append(rel_dict)
                except Exception as e:
                    logger.warning(f"处理关系时出错，跳过: {e}")
                    continue
            
            # ========== 关键新增：节点清洗（返回ID映射）==========
            nodes, company_id_mapping = clean_company_nodes(nodes)
            nodes, location_id_mapping = clean_location_nodes(nodes)
            nodes, year_id_mapping = clean_year_nodes(nodes)
            # 合并所有ID映射
            all_id_mapping = {**company_id_mapping, **location_id_mapping, **year_id_mapping}
            # ===================================================
            
            # ========== 关键新增：关系清洗（使用ID映射更新关系）==========
            # 获取清洗后所有有效节点的 ID 集合
            valid_node_ids = {str(node.get("id", "")) for node in nodes}
            relationships = clean_relationships(relationships, valid_node_ids, all_id_mapping)
            # ============================================================
            
            # ========== 关键新增：补充缺失的关系 ==========
            relationships = supplement_missing_relationships(nodes, relationships)
            # ============================================
            
            return ExtractionResult(
                nodes=nodes,
                relationships=relationships,
                metadata=doc.metadata,
                success=True
            )
        except RetryError as e:
            logger.error(f"重试{MAX_RETRIES}次后仍提取失败: {doc.page_content[:50]}...")
            return ExtractionResult(
                success=False,
                error_msg=str(e),
                metadata=doc.metadata
            )
        except Exception as e:
            logger.error(f"提取异常: {e}, 文档内容: {doc.page_content[:50]}...")
            return ExtractionResult(
                success=False,
                error_msg=str(e),
                metadata=doc.metadata
            )

    @retry(
        stop=stop_after_attempt(MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((OutputParserException, Exception)),
        reraise=True
    )
    def extract_batch_docs(self, batch_docs: List[Document], merged_doc: Document) -> List[ExtractionResult]:
        """批量提取多个文档的图谱数据（合并为一个LLM调用）"""
        try:
            # 执行提取（一次性处理整个批次）
            graph_doc = self._convert_to_graph_document_safe(merged_doc)
            
            # 转换为字典格式
            all_nodes = []
            for node in graph_doc.nodes:
                node_dict = {
                    "id": str(node.id),
                    "type": str(node.type),
                    "properties": {k: str(v) for k, v in (node.properties.items() if node.properties else {})}
                }
                all_nodes.append(node_dict)
            
            all_relationships = []
            for rel in graph_doc.relationships:
                # 检查 source 和 target 是否为 None
                if rel.source is None or rel.target is None:
                    logger.warning(f"过滤无效关系: source或target为None - type={rel.type}")
                    continue
                
                try:
                    source_id = str(rel.source.id) if hasattr(rel.source, 'id') else str(rel.source)
                    target_id = str(rel.target.id) if hasattr(rel.target, 'id') else str(rel.target)
                    
                    # 再次检查转换后的ID是否有效
                    if not source_id or not target_id or source_id == "None" or target_id == "None":
                        logger.warning(f"过滤无效关系: source_id={source_id}, target_id={target_id}")
                        continue
                    
                    rel_dict = {
                        "source": source_id,
                        "target": target_id,
                        "type": str(rel.type),
                        "properties": {k: str(v) for k, v in (rel.properties.items() if rel.properties else {})}
                    }
                    all_relationships.append(rel_dict)
                except Exception as e:
                    logger.warning(f"处理关系时出错，跳过: {e}")
                    continue
            
            # ========== 节点清洗（返回ID映射）==========
            all_nodes, company_id_mapping = clean_company_nodes(all_nodes)
            all_nodes, location_id_mapping = clean_location_nodes(all_nodes)
            all_nodes, year_id_mapping = clean_year_nodes(all_nodes)
            # 合并所有ID映射
            all_id_mapping = {**company_id_mapping, **location_id_mapping, **year_id_mapping}
            # ===================================================
            
            # ========== 关系清洗（使用ID映射更新关系）==========
            # 获取清洗后所有有效节点的 ID 集合
            valid_node_ids = {str(node.get("id", "")) for node in all_nodes}
            all_relationships = clean_relationships(all_relationships, valid_node_ids, all_id_mapping)
            # ============================================================
            
            # ========== 补充缺失的关系 ==========
            all_relationships = supplement_missing_relationships(all_nodes, all_relationships)
            # ============================================
            
            # 为每个文档创建结果（年份关系由 LLM 直接提取，不需要后处理）
            batch_results = []
            for idx, doc in enumerate(batch_docs):
                batch_results.append(ExtractionResult(
                    nodes=all_nodes,  # 包含所有节点的列表（包括 Year 节点，如果 LLM 提取了）
                    relationships=all_relationships,  # 包含所有关系的列表（包括 YEAR 关系，如果 LLM 提取了）
                    metadata=doc.metadata,  # 使用原始文档的metadata
                    success=True
                ))
            
            return batch_results
        except RetryError as e:
            logger.error(f"重试{MAX_RETRIES}次后仍批量提取失败: {merged_doc.page_content[:50]}...")
            # 返回失败结果
            return [
                ExtractionResult(
                    success=False,
                    error_msg=str(e),
                    metadata=doc.metadata
                )
                for doc in batch_docs
            ]
        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            logger.error(f"批量提取异常: {e}")
            logger.error(f"错误详情: {error_detail}")
            logger.error(f"文档内容: {merged_doc.page_content[:100]}...")
            # 返回失败结果
            return [
                ExtractionResult(
                    success=False,
                    error_msg=f"{str(e)}: {error_detail[:200]}",  # 包含更多错误信息
                    metadata=doc.metadata
                )
                for doc in batch_docs
            ]

# ==================== 3. 数据处理与提取函数 ====================
def parse_requirements(text):
    """处理 requirements 字段（字符串列表转纯文本）"""
    if pd.isna(text):
        return ""
    try:
        # 清洗不规则的字符串格式
        cleaned = text.replace("[', '", "").replace("', '", " ").replace("']", "").strip()
        return cleaned
    except:
        return str(text)

def load_job_data_from_mysql(
    last_processed_id: int = 0,
    failed_ids: set = None,
    limit: int = None
) -> pd.DataFrame:
    """从MySQL数据库加载招聘数据（使用范围查询优化）"""
    try:
        from sqlalchemy import create_engine, text
        
        # 构建MySQL连接字符串
        connection_string = f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}?charset=utf8mb4"
        engine = create_engine(connection_string, pool_pre_ping=True)
        
        # 构建查询条件（使用范围查询，高效）
        where_parts = []
        
        # 主要条件：id > last_processed_id（未处理的数据）
        if last_processed_id > 0:
            where_parts.append(f"id > {last_processed_id}")
        
        # 失败的数据需要重试：id IN (failed_ids)
        if failed_ids and len(failed_ids) > 0:
            ids_str = ','.join(map(str, failed_ids))
            where_parts.append(f"id IN ({ids_str})")
        
        # 构建 WHERE 子句
        if where_parts:
            # 如果有多个条件，使用 OR 连接（id > last_processed_id OR id IN (failed_ids)）
            where_clause = f"WHERE ({' OR '.join(where_parts)})"
        else:
            where_clause = ""
        
        limit_clause = f"LIMIT {limit}" if limit else ""
        
        query = f"""
            SELECT 
                id, job_title, company_name, salary_range, location,
                openings, requirements, search_keyword, data_year, created_at
            FROM {MYSQL_TABLE}
            {where_clause}
            ORDER BY id ASC
            {limit_clause}
        """
        
        logger.info(f"从MySQL加载数据: {MYSQL_DATABASE}.{MYSQL_TABLE}")
        df = pd.read_sql(text(query), engine)
        engine.dispose()
        
        logger.info(f"从数据库读取原始数据行数: {len(df)}")
        # 供 build_job_kg 判断「是否还有下一页」：须用清洗前行数，不能用 dropna 后的 len(df)
        df.attrs["mysql_raw_rows"] = int(len(df))
        
        # 处理 requirements 字段
        df["requirements_text"] = df["requirements"].apply(parse_requirements)
        
        # 过滤空值和无效行
        df = df.dropna(subset=["company_name", "job_title", "requirements_text"])
        df = df[df["requirements_text"].str.len() > 10]  # 过滤过短的文本
        
        logger.info(f"清洗后有效数据行数: {len(df)}")
        return df
    except ImportError:
        logger.error("需要安装 pymysql 和 sqlalchemy: pip install pymysql sqlalchemy")
        raise
    except Exception as e:
        logger.error(f"从MySQL加载数据失败: {e}")
        raise

def clean_job_data(csv_path: str = "joblist.csv") -> pd.DataFrame:
    """清洗招聘 CSV 数据"""
    try:
        df = pd.read_csv(csv_path)
        logger.info(f"从CSV读取原始数据行数: {len(df)}")
        
        # 处理 requirements 字段
        df["requirements_text"] = df["requirements"].apply(parse_requirements)
        
        # 过滤空值和无效行
        df = df.dropna(subset=["company_name", "job_title", "requirements_text"])
        df = df[df["requirements_text"].str.len() > 10]  # 过滤过短的文本
        
        logger.info(f"清洗后有效数据行数: {len(df)}")
        return df
    except Exception as e:
        logger.error(f"数据清洗失败: {e}")
        raise

def load_job_data(last_processed_id: int = 0, failed_ids: set = None, limit: int = None) -> pd.DataFrame:
    """加载招聘数据（支持MySQL和CSV）"""
    if DATA_SOURCE.lower() == "mysql":
        return load_job_data_from_mysql(last_processed_id, failed_ids, limit)
    else:
        # CSV模式不支持断点续传，返回所有数据
        return clean_job_data(CSV_PATH)

def batch_extract_graph(
    documents: List[Document], 
    cache_manager: CacheManager,
    state_manager: ProcessStateManager = None
) -> Tuple[List[ExtractionResult], int]:
    """批量并行提取图谱数据（带缓存和断点续传，按BATCH_SIZE分组）"""
    start_time = time.time()
    transformer = RobustLLMGraphTransformer()
    results = []
    
    # 从状态管理器获取现有状态
    existing_failed = state_manager.get_failed_ids() if state_manager else set()
    
    # 本次批次提取成功的最大ID和失败ID
    max_extracted_id = 0
    new_failed_ids = set()
    
    # 分批次处理
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # 提交任务（按批次合并文档）
        future_to_batch = {}
        
        for i in range(0, len(documents), BATCH_SIZE):
            batch_docs = documents[i:i+BATCH_SIZE]
            
            # 检查批次中是否有缓存
            batch_cached_docs = []
            batch_uncached_docs = []
            
            for doc in batch_docs:
                if cache_manager.has_cache(doc):
                    batch_cached_docs.append(doc)
                else:
                    batch_uncached_docs.append(doc)
            
            # 处理有缓存的文档
            for doc in batch_cached_docs:
                record_id = doc.metadata.get("id")
                cached_result = cache_manager.load_cache(doc)
                results.append(cached_result)
                
                if state_manager and record_id and cached_result.success:
                    if record_id in existing_failed:
                        state_manager.remove_failed(record_id)
                    try:
                        record_id_int = int(record_id)
                        max_extracted_id = max(max_extracted_id, record_id_int)
                    except (ValueError, TypeError):
                        pass
                    logger.debug(f"使用缓存: {doc.metadata.get('job_title')}")
            
            # 处理没有缓存的文档（合并为一个批次）
            if batch_uncached_docs:
                # 合并批次文档为一个文档
                merged_content = []
                merged_metadata = {}
                
                for doc in batch_uncached_docs:
                    # 添加分隔符和文档内容
                    job_title = doc.metadata.get('job_title', 'Unknown')
                    company_name = doc.metadata.get('company_name', '')
                    data_year = doc.metadata.get('data_year', '')
                    if not data_year:
                        created_at = doc.metadata.get('created_at')
                        if created_at:
                            try:
                                from datetime import datetime
                                if isinstance(created_at, str):
                                    dt = datetime.strptime(created_at[:10], "%Y-%m-%d")
                                    data_year = dt.year
                                elif hasattr(created_at, 'year'):
                                    data_year = created_at.year
                            except Exception:
                                pass
                    
                    merged_content.append(f"=== 职位 {job_title} (公司: {company_name}) ===\n")
                    if data_year:
                        merged_content.append(f"年份: {data_year}\n")
                    merged_content.append(doc.page_content)
                    merged_content.append("\n\n")
                    
                    # 合并metadata（保留第一个文档的metadata作为主metadata）
                    if not merged_metadata:
                        merged_metadata = doc.metadata.copy()
                
                # 创建合并后的文档
                merged_doc = Document(
                    page_content="\n".join(merged_content),
                    metadata=merged_metadata
                )
                
                # 如果设置了请求间隔，在提交任务前等待
                if REQUEST_INTERVAL > 0:
                    time.sleep(REQUEST_INTERVAL)
                
                # 提交批次提取任务
                future = executor.submit(transformer.extract_batch_docs, batch_uncached_docs, merged_doc)
                future_to_batch[future] = batch_uncached_docs
        
        # 处理完成的任务并保存缓存
        for future in as_completed(future_to_batch):
            batch_docs = future_to_batch[future]
            try:
                batch_results = future.result()  # 返回批次中每个文档的结果列表
                
                for idx, result in enumerate(batch_results):
                    if idx < len(batch_docs):
                        doc = batch_docs[idx]
                        record_id = doc.metadata.get("id")
                        results.append(result)
                        
                        # 仅当提取成功时保存缓存
                        if result.success:
                            if state_manager and record_id and record_id in existing_failed:
                                state_manager.remove_failed(record_id)
                            
                            if state_manager and record_id:
                                try:
                                    record_id_int = int(record_id)
                                    max_extracted_id = max(max_extracted_id, record_id_int)
                                except (ValueError, TypeError):
                                    pass
                            
                            # 保存缓存
                            try:
                                cache_manager.save_cache(doc, result)
                            except Exception as cache_err:
                                logger.warning(f"缓存保存失败 (继续执行): {cache_err}")
                        else:
                            # 记录失败
                            if state_manager and record_id:
                                new_failed_ids.add(record_id)
                                state_manager.add_failed(record_id)
                        
                        logger.info(f"提取完成: {doc.metadata.get('job_title')} (成功: {result.success}, ID: {record_id})")
            except Exception as e:
                logger.error(f"批量提取异常: {e}")
                # 为批次中所有文档创建失败结果
                for doc in batch_docs:
                    result = ExtractionResult(
                        success=False,
                        error_msg=str(e),
                        metadata=doc.metadata
                    )
                    results.append(result)
                    record_id = doc.metadata.get("id")
                    if state_manager and record_id:
                        new_failed_ids.add(record_id)
                        state_manager.add_failed(record_id)
    
    # 保存提取游标（入库游标由主流程在每批入库成功后更新）
    if state_manager and max_extracted_id > 0:
        current_last_id = state_manager.get_last_extracted_id()
        if max_extracted_id > current_last_id:
            state_manager.update_last_extracted_id(max_extracted_id)
            logger.info(f"提取游标已更新: last_extracted_id={max_extracted_id}, 新增失败 {len(new_failed_ids)} 条")
    
    # 统计提取结果
    success_count = sum(1 for r in results if r.success)
    fail_count = len(results) - success_count
    total_time = time.time() - start_time
    
    logger.info(f"\n=== 批量提取统计 ===")
    logger.info(f"总文档数: {len(documents)}")
    logger.info(f"成功提取: {success_count}")
    logger.info(f"提取失败: {fail_count}")
    logger.info(f"总耗时: {total_time:.2f} 秒")
    
    return results, max_extracted_id

# ==================== 4. Neo4j 导入函数 ====================

def load_to_neo4j_with_validation(results: List[ExtractionResult]):
    """带数据校验的 Neo4j 导入"""
    # 初始化 Neo4j 连接
    try:
            graph = Neo4jGraph(
                url=NEO4J_URI,
                username=NEO4J_USER,
                password=NEO4J_PASSWORD
            )
            logger.info("✅ 成功连接 Neo4j (新版)")
        
    except Exception as e:
        logger.error(f"❌ Neo4j 连接失败: {e}")
        raise

    # 开发环境清空数据库（生产环境注释）
    #graph.query("MATCH (n) DETACH DELETE n")
    #logger.info("✅ Neo4j 数据库已清空")

    # 统计变量
    total_nodes_created = 0
    total_rels_created = 0
    existing_nodes = set()

    # 先查询已存在的节点 ID（避免重复创建）
    try:
        existing_nodes_data = graph.query("MATCH (n) RETURN n.id AS id")
        existing_nodes = {str(row["id"]) for row in existing_nodes_data}
        logger.info(f"✅ 已存在节点数: {len(existing_nodes)}")
    except Exception as e:
        logger.warning(f"查询已存在节点失败，将跳过重复校验: {e}")

    skipped_failed = 0
    first_failed_msg: Optional[str] = None
    skipped_rel_missing = 0
    skipped_rel_endpoints = 0
    failed_nodes = 0
    failed_rels = 0
    sample_rel_missing: Optional[str] = None
    sample_rel_endpoints: Optional[str] = None
    sample_node_err: Optional[str] = None
    sample_rel_err: Optional[str] = None

    # 批量导入
    for result in results:
        if not result.success:
            skipped_failed += 1
            if first_failed_msg is None and result.error_msg:
                first_failed_msg = str(result.error_msg)[:200]
            continue
        
        # 1. 创建节点
        for node in result.nodes:
            node_id = str(node.get("id", ""))  # 确保是字符串
            node_type = str(node.get("type", ""))
            properties = node.get("properties", {})
            
            # 跳过空ID或已存在的节点
            if not node_id or node_id in existing_nodes:
                continue
            
            # 构建节点创建语句
            try:
                # 合并 id 到属性中
                all_props = {"id": node_id, **properties}
                # 安全构建属性字符串
                props_str = ", ".join([f"{k}: ${k}" for k in all_props.keys()])
                query = f"CREATE (n:{node_type} {{{props_str}}})"
                graph.query(query, params=all_props)
                total_nodes_created += 1
                existing_nodes.add(node_id)
                logger.debug(f"创建节点成功: {node_type} - {node_id}")
            except Exception as e:
                failed_nodes += 1
                if sample_node_err is None:
                    sample_node_err = f"{node_id}: {e}"
                logger.debug(f"创建节点失败 {node_id}: {e}")
        
        # 2. 创建关系
        for rel in result.relationships:
            # 确保所有ID都是字符串
            source_id = str(rel.get("source", ""))
            target_id = str(rel.get("target", ""))
            rel_type = str(rel.get("type", ""))
            rel_props = rel.get("properties", {})
            
            # 校验必要字段
            if not source_id or not target_id or not rel_type:
                skipped_rel_missing += 1
                if sample_rel_missing is None:
                    sample_rel_missing = f"{source_id}-{rel_type}-{target_id}"
                continue
            
            # 检查源/目标节点是否存在
            if source_id not in existing_nodes or target_id not in existing_nodes:
                skipped_rel_endpoints += 1
                if sample_rel_endpoints is None:
                    sample_rel_endpoints = f"{source_id}-{rel_type}-{target_id}"
                continue
            
            # 构建关系创建语句（优化：避免笛卡尔积警告）
            try:
                if rel_props:
                    # 有关系属性
                    props_str = ", ".join([f"{k}: ${k}" for k in rel_props.keys()])
                    query = f"""
                    MATCH (s {{id: $source_id}})
                    MATCH (t {{id: $target_id}})
                    MERGE (s)-[r:{rel_type} {{{props_str}}}]->(t)
                    RETURN r
                    """
                    params = {"source_id": source_id, "target_id": target_id, **rel_props}
                else:
                    # 无关系属性
                    query = f"""
                    MATCH (s {{id: $source_id}})
                    MATCH (t {{id: $target_id}})
                    MERGE (s)-[r:{rel_type}]->(t)
                    RETURN r
                    """
                    params = {"source_id": source_id, "target_id": target_id}
                
                result = graph.query(query, params=params)
                # 只有当关系被创建时才计数（MERGE 可能返回已存在的关系）
                if result:
                    total_rels_created += 1
                logger.debug(f"创建关系成功: {source_id}-{rel_type}-{target_id}")
            except Exception as e:
                failed_rels += 1
                if sample_rel_err is None:
                    sample_rel_err = f"{source_id}-{rel_type}-{target_id}: {e}"
                logger.debug(f"创建关系失败 {source_id}-{rel_type}-{target_id}: {e}")

    if skipped_failed:
        logger.warning(
            f"跳过失败的提取结果共 {skipped_failed} 条"
            + (f"，示例: {first_failed_msg}" if first_failed_msg else "")
        )
    if skipped_rel_missing or skipped_rel_endpoints or failed_nodes or failed_rels:
        parts = []
        if skipped_rel_missing:
            parts.append(f"关系缺字段 {skipped_rel_missing} 条" + (f"（例: {sample_rel_missing}）" if sample_rel_missing else ""))
        if skipped_rel_endpoints:
            parts.append(f"端点未入库 {skipped_rel_endpoints} 条" + (f"（例: {sample_rel_endpoints}）" if sample_rel_endpoints else ""))
        if failed_nodes:
            parts.append(f"创建节点异常 {failed_nodes} 次" + (f"（例: {sample_node_err}）" if sample_node_err else ""))
        if failed_rels:
            parts.append(f"创建关系异常 {failed_rels} 次" + (f"（例: {sample_rel_err}）" if sample_rel_err else ""))
        logger.warning("Neo4j 导入跳过/异常汇总: " + "；".join(parts))

    # 刷新 Neo4j 模式
    graph.refresh_schema()

    # 打印导入统计
    logger.info(f"\n=== Neo4j 导入统计 ===")
    logger.info(f"新增节点数: {total_nodes_created}")
    logger.info(f"新增关系数: {total_rels_created}")
    logger.info(f"✅ Neo4j 导入完成！可访问 http://localhost:7474 查看")

# ==================== 5. 主流程函数 ====================

def build_job_kg(resume: bool = True, batch_limit: int = 500):
    """
    构建招聘知识图谱主流程（支持断点续传和分批处理）
    
    Args:
        resume: 是否启用断点续传（跳过已处理的记录）
        batch_limit: 每次从数据库读取的数据量（默认500条），每10条为一组传入LLM
    """
    logger.info("🚀 开始构建招聘知识图谱...")
    logger.info(f"数据源: {DATA_SOURCE}, LLM批次大小: {BATCH_SIZE}, 数据库批次: {batch_limit}")
    
    # 1. 初始化组件
    cache_manager = CacheManager()
    state_manager = ProcessStateManager() if DATA_SOURCE.lower() == "mysql" else None
    
    # 清空缓存/状态（可选）
    #cache_manager.clear_cache()  # 如需重新提取，取消注释
    # if state_manager:
    #     state_manager.clear_state()  # 如需重新开始，取消注释
    
    total_processed = 0
    
    # 2. 分批处理数据（支持断点续传）
    iteration = 0
    max_iterations = 10000  # 防止无限循环的安全限制
    
    while iteration < max_iterations:
        iteration += 1
        
        # 新批次开始前，清理上一批次的缓存（只保留当前批次的缓存）
        if iteration > 1:
            logger.info("🧹 清理上一批次的缓存...")
            cache_manager.clear_cache()
        
        # 获取断点续传状态（使用范围查询优化）
        last_imported_id = state_manager.get_last_imported_id() if state_manager and resume else 0
        failed_ids = state_manager.get_failed_ids() if state_manager else set()
        
        # 加载数据（使用范围查询：id > last_processed_id OR id IN (failed_ids)）
        logger.info(f"\n=== 加载数据批次 (第 {iteration} 次循环) ===")
        logger.info(f"最后入库ID: {last_imported_id}, 失败记录数: {len(failed_ids)}")
        
        df = load_job_data(
            last_processed_id=last_imported_id if resume else 0,
            failed_ids=failed_ids if resume else None,
            limit=batch_limit
        )
        
        if df.empty:
            logger.info("✅ 没有更多数据需要处理")
            break
        
        logger.info(f"本次加载数据行数: {len(df)}")
        
        # 3. 加载为 LangChain Document
        # 确保 data_year 字段被包含在 metadata 中
        loader = DataFrameLoader(df, page_content_column="requirements_text")
        documents = loader.load()
        
        # 验证 metadata 中是否包含 data_year
        if documents and "data_year" not in documents[0].metadata:
            logger.warning("⚠️ 警告：metadata 中缺少 data_year 字段，年份关系可能无法建立")
            logger.warning(f"可用字段: {list(documents[0].metadata.keys())}")
        else:
            logger.debug(f"✅ metadata 包含 data_year 字段，示例值: {documents[0].metadata.get('data_year') if documents else 'N/A'}")
        
        # ========== 关键修改：将 metadata 信息合并到 page_content ==========
        for doc in documents:
            # 从 metadata 中获取公司和地点信息
            company_name = doc.metadata.get("company_name", "")
            location = doc.metadata.get("location", "")
            job_title = doc.metadata.get("job_title", "")
            data_year = doc.metadata.get("data_year", "")
            if not data_year:
                created_at = doc.metadata.get("created_at")
                if created_at:
                    try:
                        from datetime import datetime
                        if isinstance(created_at, str):
                            dt = datetime.strptime(created_at[:10], "%Y-%m-%d")
                            data_year = dt.year
                        elif hasattr(created_at, 'year'):
                            data_year = created_at.year
                    except Exception:
                        pass
            
            # 构建补充信息文本
            supplement_text = []
            if company_name:
                supplement_text.append(f"公司名称：{company_name}")
            if location:
                supplement_text.append(f"工作地点：{location}")
            if job_title:
                supplement_text.append(f"职位名称：{job_title}")
            if data_year:
                supplement_text.append(f"年份：{data_year}")
            
            # 将补充信息添加到 page_content 开头
            if supplement_text:
                doc.page_content = "\n".join(supplement_text) + "\n\n" + doc.page_content
        # ====================================================================
        
        logger.info(f"✅ 加载文档数: {len(documents)}")
        
        # 4. 批量提取图谱（每次处理BATCH_SIZE条）
        extraction_results, batch_max_extracted_id = batch_extract_graph(documents, cache_manager, state_manager)
        total_processed += len(documents)
        
        logger.info(f"累计已处理: {total_processed} 条记录")
        
        # 每批导入：确保“入库成功后再推进入库游标”
        logger.info(f"\n=== 开始导入 Neo4j（第 {iteration} 批） ===")
        logger.info(f"本批提取结果数: {len(extraction_results)}")
        load_to_neo4j_with_validation(extraction_results)
        if state_manager and batch_max_extracted_id > 0:
            state_manager.update_last_imported_id(batch_max_extracted_id)
            logger.info(f"入库游标已更新: last_imported_id={batch_max_extracted_id}")

        # 状态记录
        if state_manager:
            current_last_imported_id = state_manager.get_last_imported_id()
            current_last_extracted_id = state_manager.get_last_extracted_id()
            current_failed = state_manager.get_failed_ids()
            logger.info(
                f"当前状态: 提取游标={current_last_extracted_id}, "
                f"入库游标={current_last_imported_id}, 失败 {len(current_failed)} 条"
            )
        
        # 如果本次没有处理任何新数据（全部跳过），说明没有新数据需要处理
        actual_processed = len(extraction_results)
        if actual_processed == 0:
            # 所有数据都被跳过了（已处理），说明没有新数据
            logger.info("✅ 本次批次所有数据都已处理过，退出循环")
            break
        
        # 处理完当前批次，记录状态
        logger.info(f"✅ 当前批次（清洗后 {len(df)} 条）处理完成，状态已保存")
        
        # 若 MySQL 本次 SQL 返回行数 < limit，说明无下一页；不能用清洗后行数（否则易误判提前退出）
        if DATA_SOURCE.lower() == "mysql":
            raw_rows = int(df.attrs.get("mysql_raw_rows", len(df)))
            if raw_rows < batch_limit:
                logger.info("✅ 所有数据处理完成（MySQL 本页原始行数未达批次上限），退出循环")
                break
        elif len(df) < batch_limit:
            logger.info("✅ 所有数据处理完成，退出循环")
            break
        
        # 继续处理下一批数据（循环继续，不退出）
        logger.info(f"✅ 已处理完 {len(df)} 条数据，继续处理下一批...")
    
    if iteration >= max_iterations:
        logger.warning(f"⚠️ 达到最大迭代次数 {max_iterations}，强制退出循环")
    
    logger.info("🎉 招聘知识图谱构建完成！")

# ==================== 6. 入口函数 ====================
if __name__ == "__main__":
    try:
        build_job_kg()
    except Exception as e:
        logger.error(f"❌ 主流程执行失败: {e}", exc_info=True)
        raise