import api from './api'

export interface QuestionRequest {
  question: string
}

export interface QuestionResponse {
  question: string
  answer: string
}

export interface ChatSessionItem {
  id: number
  session_id: string
  title: string
  created_at: string
  updated_at: string
}

export interface ChatMessageItem {
  id: number
  role: string
  content_type: string
  content: string
  created_at: string
}

export interface WSMessage {
  type: 'start' | 'chunk' | 'done' | 'error'
  question?: string
  content?: string
  answer?: string
  error?: string
  session_id?: string
}

export type WSMessageHandler = (message: WSMessage) => void
export type WSErrorHandler = (error: Event) => void
export type WSCloseHandler = () => void

export const qaService = {
  async listSessions(skip = 0, limit = 50): Promise<ChatSessionItem[]> {
    return api.get('/qa/sessions', { params: { skip, limit } })
  },

  async listMessages(sessionId: string): Promise<ChatMessageItem[]> {
    return api.get(`/qa/sessions/${encodeURIComponent(sessionId)}/messages`)
  },

  /**
   * 提问（POST 方式，保留作为备选）
   */
  async askQuestion(question: string): Promise<QuestionResponse> {
    return api.post('/qa/ask', { question })
  },

  /**
   * 通过 WebSocket 提问（流式响应）
   */
  askQuestionStream(
    question: string,
    sessionId: string,
    onMessage: WSMessageHandler,
    onError?: WSErrorHandler,
    onClose?: WSCloseHandler
  ): () => void {
    const token = localStorage.getItem('token')
    if (!token) {
      onError?.(new Event('未找到认证令牌'))
      return () => {}
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host
    const wsUrl = `${protocol}//${host}/api/v1/qa/ask/ws?token=${encodeURIComponent(token)}`

    const ws = new WebSocket(wsUrl)

    ws.onopen = () => {
      ws.send(JSON.stringify({ question, session_id: sessionId }))
    }

    ws.onmessage = (event) => {
      try {
        const message: WSMessage = JSON.parse(event.data)
        onMessage(message)
      } catch (error) {
        console.error('解析 WebSocket 消息失败:', error)
        onMessage({
          type: 'error',
          error: '消息解析失败'
        })
      }
    }

    ws.onerror = (error) => {
      console.error('WebSocket 错误:', error)
      onError?.(error)
    }

    ws.onclose = () => {
      onClose?.()
    }

    return () => {
      if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
        ws.close()
      }
    }
  },
}
