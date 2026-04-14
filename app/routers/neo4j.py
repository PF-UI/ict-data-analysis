"""
Neo4j 只读查询路由
"""
from fastapi import APIRouter, Depends, HTTPException, status
from typing import Optional, Dict, Any, List
from app.schemas.neo4j import QueryRequest, SearchRequest
from app.core.dependencies import get_current_user
from app.models.user import User as UserModel
from app.services.neo4j_service import Neo4jReadOnlyService

router = APIRouter()


@router.get("/stats")
async def get_statistics(
    current_user: UserModel = Depends(get_current_user)
):
    """获取 Neo4j 统计信息"""
    neo4j_service = Neo4jReadOnlyService()
    try:
        node_count = neo4j_service.get_node_count()
        relationship_count = neo4j_service.get_relationship_count()
        return {
            "nodes": node_count,
            "relationships": relationship_count
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取统计信息失败: {str(e)}"
        )
    finally:
        neo4j_service.close()


@router.post("/query")
async def execute_query(
    request: QueryRequest,
    current_user: UserModel = Depends(get_current_user)
):
    """执行只读 Cypher 查询"""
    neo4j_service = Neo4jReadOnlyService()
    try:
        results = neo4j_service.execute_readonly_query(
            request.query,
            request.parameters
        )
        return {"results": results}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"查询执行失败: {str(e)}"
        )
    finally:
        neo4j_service.close()


@router.post("/search")
async def search_nodes(
    request: SearchRequest,
    current_user: UserModel = Depends(get_current_user)
):
    """搜索节点"""
    neo4j_service = Neo4jReadOnlyService()
    try:
        nodes = neo4j_service.search_nodes(
            label=request.label,
            property_key=request.property_key,
            property_value=request.property_value,
            limit=request.limit
        )
        return {"nodes": nodes}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"搜索失败: {str(e)}"
        )
    finally:
        neo4j_service.close()


@router.get("/nodes")
async def get_nodes(
    limit: int = 100,
    current_user: UserModel = Depends(get_current_user)
):
    """获取所有节点"""
    neo4j_service = Neo4jReadOnlyService()
    try:
        nodes = neo4j_service.get_all_nodes(limit=min(limit, 1000))
        return {"nodes": nodes}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取节点失败: {str(e)}"
        )
    finally:
        neo4j_service.close()


@router.get("/nodes/{node_id}")
async def get_node_by_id(
    node_id: int,
    current_user: UserModel = Depends(get_current_user)
):
    """根据 ID 获取节点详情"""
    neo4j_service = Neo4jReadOnlyService()
    try:
        node = neo4j_service.get_node_by_id(node_id)
        if not node:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="节点不存在"
            )
        return node
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取节点失败: {str(e)}"
        )
    finally:
        neo4j_service.close()


@router.get("/relationships")
async def get_relationships(
    limit: int = 100,
    current_user: UserModel = Depends(get_current_user)
):
    """获取所有关系"""
    neo4j_service = Neo4jReadOnlyService()
    try:
        relationships = neo4j_service.get_all_relationships(limit=min(limit, 1000))
        return {"relationships": relationships}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取关系失败: {str(e)}"
        )
    finally:
        neo4j_service.close()
