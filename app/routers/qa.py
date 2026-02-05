"""
问答系统路由
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.core.dependencies import get_current_user_ws
from config import llm
import json

router = APIRouter()


@router.websocket("/ask/ws")
async def ask_question_ws(websocket: WebSocket):
    """
    WebSocket 问答接口，支持流式响应
    使用方式：ws://host:port/api/v1/qa/ask/ws?token=YOUR_TOKEN
    或通过 Authorization header: Bearer YOUR_TOKEN
    """
    await websocket.accept()
    
    # 认证用户
    current_user = await get_current_user_ws(websocket)
    if not current_user:
        return  # 认证失败，连接已关闭
    
    try:
        # 接收问题
        data = await websocket.receive_json()
        question = data.get("question", "").strip()
        
        if not question:
            await websocket.send_json({
                "type": "error",
                "error": "问题不能为空"
            })
            await websocket.close()
            return
        
        # 发送开始标记
        await websocket.send_json({
            "type": "start",
            "question": question
        })
        
        # 使用流式调用 LLM
        full_answer = ""
        async for chunk in llm.astream(question):
            # 提取内容
            content = ""
            if hasattr(chunk, 'content'):
                content = chunk.content
            elif isinstance(chunk, str):
                content = chunk
            else:
                content = str(chunk)
            
            if content:
                full_answer += content
                # 逐块发送
                await websocket.send_json({
                    "type": "chunk",
                    "content": content
                })
        
        # 发送完成标记
        await websocket.send_json({
            "type": "done",
            "answer": full_answer
        })
        
    except WebSocketDisconnect:
        print(f"客户端断开连接: {current_user.email}")
    except Exception as e:
        error_msg = str(e)
        print(f"❌ WebSocket 错误: {error_msg}")
        try:
            await websocket.send_json({
                "type": "error",
                "error": f"问答服务错误: {error_msg}"
            })
        except:
            pass
        try:
            await websocket.close()
        except:
            pass
