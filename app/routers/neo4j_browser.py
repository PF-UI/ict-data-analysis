"""
Neo4j Browser 代理路由
提供只读访问的 Neo4j Browser 功能
"""
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from app.core.dependencies import get_current_user
from app.models.user import User as UserModel
import os

router = APIRouter()

# Neo4j Browser 配置
NEO4J_BROWSER_URL = os.getenv("NEO4J_BROWSER_URL", "http://localhost:7474")


@router.get("/browser")
async def neo4j_browser_redirect(
    current_user: UserModel = Depends(get_current_user)
):
    """
    重定向到 Neo4j Browser（新窗口打开）
    由于 iframe 可能被 X-Frame-Options 阻止，建议在新窗口打开
    """
    return RedirectResponse(url=NEO4J_BROWSER_URL)


@router.get("/browser/url")
async def get_browser_url(
    current_user: UserModel = Depends(get_current_user)
):
    """
    获取 Neo4j Browser URL（用于前端 iframe 或新窗口打开）
    """
    return {
        "url": NEO4J_BROWSER_URL,
        "message": "请在 Neo4j 中配置只读用户以确保安全"
    }
