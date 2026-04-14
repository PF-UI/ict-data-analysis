"""
问答系统路由
"""
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.agents.qa_agent import stream_agent_qa_payloads
from app.core.dependencies import get_current_user, get_current_user_ws
from app.agent_runtime.token_budget import estimate_user_question_tokens
from app.core.config import settings
from app.history_database import get_history_db, new_history_session
from app.models.user import User as UserModel
from app.schemas.chat_history import (
    ChatMessageOut,
    ChatSessionOut,
    ChatSessionTitleUpdate,
)
from app.services.chat_history_service import (
    append_chat_message,
    get_or_create_chat_session,
    get_session_for_user,
    list_session_messages,
    list_user_sessions,
)

router = APIRouter()


@router.get("/sessions", response_model=list[ChatSessionOut])
async def list_chat_sessions(
    skip: int = 0,
    limit: int = 50,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_history_db),
):
    """当前用户的会话列表（按最近活跃排序），供前端侧边栏展示。"""
    cap = min(max(limit, 1), 100)
    return list_user_sessions(
        db, user_id=current_user.id, skip=max(skip, 0), limit=cap
    )


@router.get("/sessions/{session_id}/messages", response_model=list[ChatMessageOut])
async def get_chat_messages(
    session_id: str,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_history_db),
):
    """某会话下的消息时间线（按时间升序），供前端主区域展示。"""
    msgs = list_session_messages(
        db, user_id=current_user.id, session_id=session_id
    )
    if msgs is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return msgs


@router.patch("/sessions/{session_id}", response_model=ChatSessionOut)
async def update_chat_session_title(
    session_id: str,
    body: ChatSessionTitleUpdate,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_history_db),
):
    """重命名会话标题（类似参考产品侧边栏可编辑标题）。"""
    row = get_session_for_user(
        db, user_id=current_user.id, session_id=session_id
    )
    if row is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    row.title = body.title.strip()
    db.commit()
    db.refresh(row)
    return row


@router.websocket("/ask/ws")
async def ask_question_ws(websocket: WebSocket):
    """
    WebSocket 问答接口，支持流式响应
    使用方式：ws://host:port/api/v1/qa/ask/ws?token=YOUR_TOKEN
    或通过 Authorization header: Bearer YOUR_TOKEN

    客户端 JSON：{"question": "...", "session_id": "可选，续聊时传入上次返回的 session_id"}
    服务端：start/done 中会返回 session_id；多轮对话仅发送本轮 question，历史由服务端检查点恢复。
    同一会话的用户消息与助手完整回复会写入 PostgreSQL（chat_sessions / chat_messages），供 REST 历史接口展示。
    """
    await websocket.accept()

    current_user = await get_current_user_ws(websocket)
    if not current_user:
        return

    db = new_history_session()
    try:
        data = await websocket.receive_json()
        question = data.get("question", "").strip()
        raw_session = data.get("session_id")
        session_id = (str(raw_session).strip() if raw_session else "") or str(uuid4())
        thread_id = f"user:{current_user.id}:session:{session_id}"

        if not question:
            await websocket.send_json({"type": "error", "error": "问题不能为空"})
            await websocket.close()
            return

        est = estimate_user_question_tokens(
            question, settings.LLM_TOKEN_ESTIMATE_BYTES_DIVISOR
        )
        if est > settings.LLM_MAX_INPUT_TOKENS_PER_TURN:
            await websocket.send_json(
                {
                    "type": "error",
                    "error": "本轮输入过长，已超过模型单轮最大输入长度限制",
                }
            )
            await websocket.close()
            return

        chat_session = get_or_create_chat_session(
            db,
            user_id=current_user.id,
            session_id=session_id,
            question=question,
        )
        append_chat_message(
            db, session=chat_session, role="user", content=question
        )
        db.commit()

        await websocket.send_json(
            {
                "type": "start",
                "question": question,
                "session_id": session_id,
            }
        )

        full_answer = ""
        async for payload in stream_agent_qa_payloads(question, thread_id=thread_id):
            ptype = payload.get("type")
            if ptype == "chunk":
                content = payload.get("content") or ""
                if content:
                    full_answer += content
                    await websocket.send_json({"type": "chunk", "content": content})
            elif ptype in ("tool_start", "tool_end", "tool_error"):
                await websocket.send_json(payload)

        append_chat_message(
            db, session=chat_session, role="assistant", content=full_answer
        )
        db.commit()

        await websocket.send_json(
            {
                "type": "done",
                "answer": full_answer,
                "session_id": session_id,
            }
        )

    except WebSocketDisconnect:
        db.rollback()
        print(f"客户端断开连接: {current_user.email}")
    except Exception as e:
        db.rollback()
        error_msg = str(e)
        print(f"WebSocket 错误: {error_msg}")
        try:
            await websocket.send_json(
                {"type": "error", "error": f"问答服务错误: {error_msg}"}
            )
        except Exception:
            pass
        try:
            await websocket.close()
        except Exception:
            pass
    finally:
        db.close()
