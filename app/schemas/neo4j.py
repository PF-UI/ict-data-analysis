"""
Neo4j 相关的数据模式
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any


class QueryRequest(BaseModel):
    """Cypher 查询请求"""
    query: str = Field(..., description="Cypher 查询语句（只读）")
    parameters: Optional[Dict[str, Any]] = Field(None, description="查询参数")


class SearchRequest(BaseModel):
    """节点搜索请求"""
    label: Optional[str] = Field(None, description="节点标签")
    property_key: Optional[str] = Field(None, description="属性键")
    property_value: Optional[str] = Field(None, description="属性值")
    limit: int = Field(50, ge=1, le=1000, description="返回数量限制")
