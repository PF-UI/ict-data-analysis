import os
import ast
import json
import pandas as pd
from dotenv import load_dotenv
from langchain_community.document_loaders import DataFrameLoader
from langchain_openai import ChatOpenAI

# Corrected imports for newer LangChain versions
from langchain_core.documents import Document
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.exceptions import OutputParserException

from neo4j import Neo4jGraph
from pathlib import Path
import pickle

# 1. 加载环境变量
load_dotenv()

# ==================== 定义 GraphDocument 数据类 ====================
from dataclasses import dataclass, field
from typing import Any, List

@dataclass
class Node:
    """代表图中的节点"""
    id: str
    type: str
    properties: dict = field(default_factory=dict)

@dataclass
class Relationship:
    """代表图中的关系"""
    source: str
    target: str
    type: str
    properties: dict = field(default_factory=dict)

@dataclass
class GraphDocument:
    """代表从文本提取的图"""
    nodes: List[Node] = field(default_factory=list)
    relationships: List[Relationship] = field(default_factory=list)
    source: Document = None

# ===================== 自定义图转换器 =====================
class CustomLLMGraphTransformer:
    """
    自定义 LLM 图转换器，使用提示词 + JSON 解析器
    """
    def __init__(self, llm, allowed_nodes, allowed_relationships):
        self.llm = llm
        self.allowed_nodes = allowed_nodes
        self.allowed_relationships = allowed_relationships
        
        # 定义图提取的 JSON Schema
        self.prompt_template = PromptTemplate(
            template="""
你是一个专业的知识图谱提取助手，需要从职位需求文本中提取节点和关系。
严格遵守以下规则：
1. 节点类型只能是：{allowed_nodes}
2. 关系类型只能是：{allowed_relationships}
3. 每个节点必须包含 'id' (唯一标识)、'type' (节点类型)、'properties' (属性字典，至少包含 name)
4. 每个关系必须包含 'source' (源节点 id)、'target' (目标节点 id)、'type' (关系类型)、'properties' (属性字典，可为空)
5. 只输出 JSON 格式，不要输出任何额外文本、解释或换行
6. 输出结构必须是：{{"nodes": [...], "relationships": [...]}}

职位需求文本：
{text}
            """,
            input_variables=["text"],
            partial_variables={
                "allowed_nodes": ", ".join(allowed_nodes),
                "allowed_relationships": ", ".join(allowed_relationships)
            }
        )
        # 初始化 JSON 解析器
        self.parser = JsonOutputParser()

    def convert_to_graph_documents(self, documents):
        """
        将文档转换为图文档
        """
        graph_documents = []
        for doc in documents:
            try:
                # 1. 构建提示词
                prompt = self.prompt_template.format(text=doc.page_content)
                # 2. 调用 LLM 获取原始输出
                response = self.llm.invoke(prompt)
                raw_output = response.content.strip()
                
                # 3. 解析 JSON
                parsed = self.parser.parse(raw_output)
                
                # 4. 转换为 Node 和 Relationship 对象
                nodes = [
                    Node(
                        id=node.get("id"),
                        type=node.get("type"),
                        properties=node.get("properties", {})
                    )
                    for node in parsed.get("nodes", [])
                ]
                relationships = [
                    Relationship(
                        source=rel.get("source"),
                        target=rel.get("target"),
                        type=rel.get("type"),
                        properties=rel.get("properties", {})
                    )
                    for rel in parsed.get("relationships", [])
                ]
                
                # 5. 构建 GraphDocument
                graph_doc = GraphDocument(
                    nodes=nodes,
                    relationships=relationships,
                    source=doc
                )
                graph_documents.append(graph_doc)
                
            except OutputParserException as e:
                print(f"❌ 解析文档失败 (JSON 格式错误): {e}")
                print(f"原始输出: {raw_output if 'raw_output' in locals() else 'N/A'}")
            except Exception as e:
                print(f"❌ 处理文档失败: {e}")
                print(f"文档内容: {doc.page_content[:100]}...")
                
        return graph_documents


def clean_data(csv_path):
    """
    清洗数据：处理 CSV 中的 requirements 字段，将其从字符串形式的列表转换为纯文本
    """
    df = pd.read_csv(csv_path)
    
    # 处理 CSV 中 requirements 字段的脏数据
    def parse_req(text):
        try:
            # 清洗奇怪的字符串格式
            cleaned = text.replace("[', '", "").replace("', '", " ").replace("']", "")
            return cleaned
        except:
            return text

    df['requirements_text'] = df['requirements'].apply(parse_req)
    
    # 过滤掉不完整的行
    df = df.dropna(subset=['company_name', 'job_title'])
    
    return df


# ===================== 本地缓存管理 =====================
class CacheManager:
    """管理图数据的本地缓存"""
    
    def __init__(self, cache_dir="./graph_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.graph_cache_file = self.cache_dir / "graph_documents.pkl"
        self.metadata_cache_file = self.cache_dir / "metadata.json"
    
    def has_cache(self):
        """检查是否存在缓存"""
        return self.graph_cache_file.exists() and self.metadata_cache_file.exists()
    
    def load_from_cache(self):
        """从缓存加载图文档"""
        if not self.has_cache():
            return None, None
        
        try:
            with open(self.graph_cache_file, 'rb') as f:
                graph_documents = pickle.load(f)
            
            with open(self.metadata_cache_file, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            
            print(f"✅ 从缓存加载 {len(graph_documents)} 个图文档")
            return graph_documents, metadata
        except Exception as e:
            print(f"⚠️ 加载缓存失败: {e}")
            return None, None
    
    def save_to_cache(self, graph_documents, metadata):
        """保存图文档到缓存"""
        try:
            # 保存二进制图数据
            with open(self.graph_cache_file, 'wb') as f:
                pickle.dump(graph_documents, f)
            
            # 保存元数据（JSON 格式，便于查看）
            with open(self.metadata_cache_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)
            
            print(f"✅ 图数据已保存到缓存: {self.graph_cache_file}")
            print(f"✅ 元数据已保存到缓存: {self.metadata_cache_file}")
        except Exception as e:
            print(f"❌ 保存缓存失败: {e}")
    
    def clear_cache(self):
        """清除缓存"""
        if self.graph_cache_file.exists():
            self.graph_cache_file.unlink()
        if self.metadata_cache_file.exists():
            self.metadata_cache_file.unlink()
        print("✅ 缓存已清除")


def build_graph():
    print("🚀 开始处理数据...")
    
    # 初始化缓存管理器
    cache_manager = CacheManager()
    
    # 2. 读取并清洗数据
    df = clean_data("joblist.csv")
    print(f"📊 数据加载完成，共 {len(df)} 条有效数据")

    # 使用 DataFrameLoader，指定 'requirements_text' 作为主要内容
    loader = DataFrameLoader(df, page_content_column="requirements_text")
    documents = loader.load()

    # 检查缓存是否存在
    cached_graph_docs, cached_metadata = cache_manager.load_from_cache()
    
    if cached_graph_docs is not None:
        print("\n💡 检测到缓存，选择:")
        choice = input("  1. 使用缓存数据（跳过 LLM 调用）\n  2. 重新生成（清除缓存）\n请选择 (1/2): ").strip()
        
        if choice == "1":
            graph_documents = cached_graph_docs
            print(f"✅ 使用缓存的 {len(graph_documents)} 个图文档")
        else:
            print("🔄 清除缓存，重新生成...")
            cache_manager.clear_cache()
            graph_documents = extract_and_cache_graphs(
                documents, cache_manager
            )
    else:
        print("📥 未找到缓存，开始 LLM 提取...")
        graph_documents = extract_and_cache_graphs(
            documents, cache_manager
        )

    # 6. 添加元数据关联
    for i, graph_doc in enumerate(graph_documents):
        original_doc = documents[i] if i < len(documents) else None
        if original_doc:
            # 从元数据中获取公司和职位信息
            company_name = original_doc.metadata.get("company_name")
            job_title = original_doc.metadata.get("job_title")
            # 补全节点属性
            for node in graph_doc.nodes:
                if node.type == "Company" and "name" not in node.properties:
                    node.properties["name"] = company_name
                if node.type == "Job" and "name" not in node.properties:
                    node.properties["name"] = job_title

    print(f"\n🧩 准备存入 Neo4j (共 {len(graph_documents)} 个图文档)")

    # 7. 存入 Neo4j
    try:
        load_to_neo4j(graph_documents)
        print("✅ 知识图谱构建完毕！请访问 http://localhost:7474 查看")
    except Exception as e:
        print(f"⚠️ Neo4j 连接失败: {e}")
        print("💡 但是图数据已保存到本地缓存，可以稍后重试")
        print(f"   缓存位置: ./graph_cache/")


def extract_and_cache_graphs(documents, cache_manager):
    """提取图文档并保存到缓存"""
    
    # 3. 初始化 LLM
    try:
        from config import llm  # 优先导入你的自定义配置
    except ImportError:
        # 备用方案：直接初始化 OpenAI 兼容的 LLM
        llm = ChatOpenAI(
            model="gpt-3.5-turbo",
            temperature=0,
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL")  # Qwen oneAPI 地址
        )

    # 4. 定义图谱 Schema
    allowed_nodes = ["Job", "Company", "Skill", "Location"]
    allowed_relationships = ["OFFERED_BY", "LOCATED_IN", "REQUIRES_SKILL"]

    # 5. 使用自定义转换器
    transformer = CustomLLMGraphTransformer(
        llm=llm,
        allowed_nodes=allowed_nodes,
        allowed_relationships=allowed_relationships
    )

    print("🧠 LLM 正在分析文本并提取图结构 (这可能需要一点时间)...")
    
    try:
        graph_documents = transformer.convert_to_graph_documents(documents)
    except Exception as e:
        error_msg = str(e)
        print("\n" + "="*60)
        print("❌ 图提取失败")
        print("="*60)
        print(f"错误信息: {error_msg}")
        print("\n💡 建议的解决方案:")
        print("  1. 检查提示词是否足够明确，可调整 prompt_template 中的指令")
        print("  2. 确认 Qwen 模型版本，建议使用最新版 Qwen3-Max")
        print("  3. 查看模型原始输出，确认是否为合法 JSON")
        print("="*60 + "\n")
        raise
    
    print("--------------------------------")
    print(f"提取到 {len(graph_documents)} 个图文档")
    if graph_documents:
        sample = graph_documents[0]
        print(f"示例节点数: {len(sample.nodes)}")
        print(f"示例关系数: {len(sample.relationships)}")
    print("--------------------------------")
    
    # 保存到缓存
    metadata = {
        "total_documents": len(graph_documents),
        "total_nodes": sum(len(doc.nodes) for doc in graph_documents),
        "total_relationships": sum(len(doc.relationships) for doc in graph_documents),
        "timestamp": pd.Timestamp.now().isoformat(),
        "sample_nodes": len(graph_documents[0].nodes) if graph_documents else 0,
        "sample_relationships": len(graph_documents[0].relationships) if graph_documents else 0
    }
    cache_manager.save_to_cache(graph_documents, metadata)
    
    return graph_documents


def load_to_neo4j(graph_documents):
    """将图文档加载到 Neo4j"""
    
    graph = Neo4jGraph(
        url=os.getenv("NEO4J_URI"),
        username=os.getenv("NEO4J_USER"),
        password=os.getenv("NEO4J_PASSWORD")
    )
    
    # 开发阶段清空数据库 (生产环境注释掉)
    graph.query("MATCH (n) DETACH DELETE n")
    
    # 手动将 GraphDocument 转换为 Neo4j 可接受的格式
    nodes_created = 0
    relationships_created = 0
    
    for graph_doc in graph_documents:
        # 创建节点
        for node in graph_doc.nodes:
            props_str = ", ".join(
                [f"{k}: {json.dumps(v)}" for k, v in node.properties.items()]
            )
            query = f"CREATE (:{node.type} {{id: {json.dumps(node.id)}, {props_str}}})"
            try:
                graph.query(query)
                nodes_created += 1
            except Exception as e:
                print(f"⚠️ 节点创建失败 ({node.id}): {e}")
        
        # 创建关系
        for rel in graph_doc.relationships:
            query = f"""
            MATCH (source {{id: {json.dumps(rel.source)}}})
            MATCH (target {{id: {json.dumps(rel.target)}}})
            CREATE (source)-[:{rel.type}]->(target)
            """
            try:
                graph.query(query)
                relationships_created += 1
            except Exception as e:
                print(f"⚠️ 关系创建失败 ({rel.source}-{rel.type}-{rel.target}): {e}")
    
    # 刷新模式
    graph.refresh_schema()
    
    print(f"\n📊 Neo4j 数据加载统计:")
    print(f"  - 创建节点数: {nodes_created}")
    print(f"  - 创建关系数: {relationships_created}")


if __name__ == "__main__":
    build_graph()