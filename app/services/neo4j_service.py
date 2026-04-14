"""
Neo4j 只读查询服务
"""
import os
from typing import List, Dict, Any, Optional
from neo4j import GraphDatabase
import re

class Neo4jReadOnlyService:
    """Neo4j 只读服务，确保所有查询都是只读的"""
    
    def __init__(self):
        self.uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self.user = os.getenv("NEO4J_USER", "neo4j")
        self.password = os.getenv("NEO4J_PASSWORD", "password")
        self.driver = None
    
    def _get_driver(self):
        """获取数据库驱动（懒加载）"""
        if self.driver is None:
            self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
        return self.driver
    
    def _validate_readonly_query(self, query: str) -> bool:
        """
        验证查询是否为只读操作
        禁止的操作：CREATE, DELETE, DETACH, REMOVE, SET, MERGE, FOREACH, DROP
        """
        query_upper = query.upper().strip()
        
        # 禁止的关键字
        forbidden_keywords = [
            'CREATE', 'DELETE', 'DETACH', 'REMOVE', 
            'SET', 'MERGE', 'FOREACH', 'DROP', 'ALTER'
        ]
        
        # 检查是否包含禁止的关键字
        for keyword in forbidden_keywords:
            # 使用单词边界匹配，避免误判（如 "MATCH" 中包含 "ATCH"）
            pattern = r'\b' + re.escape(keyword) + r'\b'
            if re.search(pattern, query_upper):
                return False
        
        return True
    
    def execute_readonly_query(self, query: str, parameters: Optional[Dict] = None) -> List[Dict[str, Any]]:
        """
        执行只读查询
        只允许 MATCH, RETURN, WHERE, WITH, ORDER BY, LIMIT 等只读操作
        """
        if not self._validate_readonly_query(query):
            raise ValueError("只允许执行只读查询，禁止 CREATE、DELETE、SET 等写操作")
        
        driver = self._get_driver()
        with driver.session() as session:
            result = session.run(query, parameters or {})
            records = []
            for record in result:
                records.append(dict(record))
            return records
    
    def get_node_count(self) -> Dict[str, int]:
        """获取节点统计信息"""
        query = """
        MATCH (n)
        RETURN labels(n) as labels, count(n) as count
        ORDER BY count DESC
        """
        results = self.execute_readonly_query(query)
        return {", ".join(r["labels"]) if r["labels"] else "未分类": r["count"] for r in results}
    
    def get_relationship_count(self) -> Dict[str, int]:
        """获取关系统计信息"""
        query = """
        MATCH ()-[r]->()
        RETURN type(r) as type, count(r) as count
        ORDER BY count DESC
        """
        results = self.execute_readonly_query(query)
        return {r["type"]: r["count"] for r in results}
    
    def get_all_nodes(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取所有节点（限制数量）"""
        query = """
        MATCH (n)
        RETURN n
        LIMIT $limit
        """
        results = self.execute_readonly_query(query, {"limit": limit})
        nodes = []
        for record in results:
            node = record["n"]
            nodes.append({
                "id": node.id,
                "labels": list(node.labels),
                "properties": dict(node)
            })
        return nodes
    
    def get_all_relationships(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取所有关系（限制数量）"""
        query = """
        MATCH (a)-[r]->(b)
        RETURN a, r, b
        LIMIT $limit
        """
        results = self.execute_readonly_query(query, {"limit": limit})
        relationships = []
        for record in results:
            relationships.append({
                "source": {
                    "id": record["a"].id,
                    "labels": list(record["a"].labels),
                    "properties": dict(record["a"])
                },
                "relationship": {
                    "type": record["r"].type,
                    "properties": dict(record["r"])
                },
                "target": {
                    "id": record["b"].id,
                    "labels": list(record["b"].labels),
                    "properties": dict(record["b"])
                }
            })
        return relationships
    
    def search_nodes(self, label: Optional[str] = None, property_key: Optional[str] = None, 
                    property_value: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """搜索节点"""
        if label and property_key and property_value:
            query = f"""
            MATCH (n:{label})
            WHERE n.{property_key} CONTAINS $value
            RETURN n
            LIMIT $limit
            """
            params = {"value": property_value, "limit": limit}
        elif label:
            query = f"""
            MATCH (n:{label})
            RETURN n
            LIMIT $limit
            """
            params = {"limit": limit}
        else:
            query = """
            MATCH (n)
            RETURN n
            LIMIT $limit
            """
            params = {"limit": limit}
        
        results = self.execute_readonly_query(query, params)
        nodes = []
        for record in results:
            node = record["n"]
            nodes.append({
                "id": node.id,
                "labels": list(node.labels),
                "properties": dict(node)
            })
        return nodes
    
    def get_node_by_id(self, node_id: int) -> Optional[Dict[str, Any]]:
        """根据 ID 获取节点及其关系"""
        query = """
        MATCH (n)
        WHERE id(n) = $node_id
        OPTIONAL MATCH (n)-[r]-(related)
        RETURN n, collect(DISTINCT {rel: r, node: related}) as relationships
        """
        results = self.execute_readonly_query(query, {"node_id": node_id})
        if not results:
            return None
        
        record = results[0]
        node = record["n"]
        relationships = []
        for rel_item in record["relationships"]:
            if rel_item["rel"] is not None:
                relationships.append({
                    "relationship": {
                        "type": rel_item["rel"].type,
                        "properties": dict(rel_item["rel"])
                    },
                    "node": {
                        "id": rel_item["node"].id,
                        "labels": list(rel_item["node"].labels),
                        "properties": dict(rel_item["node"])
                    } if rel_item["node"] else None
                })
        
        return {
            "id": node.id,
            "labels": list(node.labels),
            "properties": dict(node),
            "relationships": relationships
        }
    
    def close(self):
        """关闭数据库连接"""
        if self.driver:
            self.driver.close()
            self.driver = None
