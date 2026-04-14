<template>
  <div class="smart-doc-page">
    <aside class="session-sidebar">
      <div class="sidebar-header">
        <span class="sidebar-title">历史会话</span>
        <el-button type="primary" link @click="startNewSession">新对话</el-button>
      </div>
      <el-scrollbar class="session-scroll">
        <div
          v-for="s in sessions"
          :key="s.session_id"
          :class="['session-item', { active: s.session_id === currentSessionId }]"
          @click="selectSession(s.session_id)"
        >
          <div class="session-title">{{ s.title }}</div>
          <div class="session-time">{{ formatSessionTime(s.updated_at) }}</div>
        </div>
        <el-empty
          v-if="!sessions.length && !sessionsLoading"
          description="暂无会话，开始新对话吧"
          :image-size="72"
        />
      </el-scrollbar>
    </aside>

    <div class="main-panel">
      <el-card class="qa-card" shadow="never">
        <div class="chat-container">
          <div class="messages" ref="messagesRef">
            <div
              v-for="(message, index) in messages"
              :key="index"
              :class="['message', message.type]"
            >
              <div class="message-avatar">
                <el-icon v-if="message.type === 'user'"><User /></el-icon>
                <el-icon v-else><ChatDotRound /></el-icon>
              </div>
              <div class="message-content">
                <div class="message-text">
                  {{ message.content }}
                  <span
                    v-if="loading && message.type === 'assistant' && index === currentAnswerIndex"
                    class="cursor"
                  >▋</span>
                </div>
                <div class="message-time">{{ message.time }}</div>
              </div>
            </div>
          </div>

          <div class="input-area">
            <el-input
              v-model="currentQuestion"
              type="textarea"
              :rows="3"
              placeholder="请输入您的问题..."
              @keydown.ctrl.enter="handleSubmit"
              @keydown.meta.enter="handleSubmit"
              :disabled="loading"
            />
            <div class="input-actions">
              <el-button
                type="primary"
                @click="handleSubmit"
                :loading="loading"
                :disabled="!currentQuestion.trim()"
              >
                发送
              </el-button>
              <el-button @click="handleClear">清空</el-button>
            </div>
          </div>
        </div>
      </el-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, onBeforeUnmount, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { User, ChatDotRound } from '@element-plus/icons-vue'
import { qaService, type ChatMessageItem, type ChatSessionItem } from '@/services/qa'

const SESSION_STORAGE_KEY = 'smart_doc_session_id'
const PAGE_TITLE = '智能问答 · ICT数据分析系统'
const savedDocumentTitle =
  typeof document !== 'undefined' ? document.title : ''

interface Message {
  type: 'user' | 'assistant'
  content: string
  time: string
}

const sessions = ref<ChatSessionItem[]>([])
const sessionsLoading = ref(false)
const currentSessionId = ref('')
const messages = ref<Message[]>([])
const currentQuestion = ref('')
const loading = ref(false)
const currentAnswerIndex = ref(-1)
const closeWS = ref<(() => void) | null>(null)
const messagesRef = ref<HTMLElement>()

const formatTime = (date: Date = new Date()) => {
  return date.toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit'
  })
}

const formatSessionTime = (iso: string) => {
  try {
    const d = new Date(iso)
    return d.toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit'
    })
  } catch {
    return ''
  }
}

const scrollToBottom = async () => {
  await nextTick()
  if (messagesRef.value) {
    messagesRef.value.scrollTop = messagesRef.value.scrollHeight
  }
}

async function loadSessions() {
  sessionsLoading.value = true
  try {
    sessions.value = await qaService.listSessions(0, 80)
  } catch {
    sessions.value = []
  } finally {
    sessionsLoading.value = false
  }
}

function mapApiMessage(m: ChatMessageItem): Message {
  const t = m.created_at
    ? new Date(m.created_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    : ''
  const type = m.role === 'user' ? 'user' : 'assistant'
  return { type, content: m.content || '', time: t }
}

async function loadMessagesForSession(sessionId: string) {
  try {
    const rows = await qaService.listMessages(sessionId)
    messages.value = rows.map(mapApiMessage)
    await scrollToBottom()
  } catch {
    messages.value = []
    ElMessage.warning('该会话不存在或已失效，已开启新会话')
    startNewSession()
  }
}

function persistSessionId(id: string) {
  currentSessionId.value = id
  localStorage.setItem(SESSION_STORAGE_KEY, id)
}

async function selectSession(sessionId: string) {
  if (closeWS.value) {
    closeWS.value()
    closeWS.value = null
  }
  loading.value = false
  currentAnswerIndex.value = -1
  persistSessionId(sessionId)
  await loadMessagesForSession(sessionId)
}

function startNewSession() {
  if (closeWS.value) {
    closeWS.value()
    closeWS.value = null
  }
  loading.value = false
  currentAnswerIndex.value = -1
  const id = crypto.randomUUID()
  persistSessionId(id)
  messages.value = []
  currentQuestion.value = ''
}

async function initFromStorage() {
  await loadSessions()
  let id = localStorage.getItem(SESSION_STORAGE_KEY)?.trim()
  if (!id) {
    id = crypto.randomUUID()
    localStorage.setItem(SESSION_STORAGE_KEY, id)
  }
  currentSessionId.value = id
  const exists = sessions.value.some((s) => s.session_id === id)
  if (exists) {
    await loadMessagesForSession(id)
  } else {
    messages.value = []
  }
}

onMounted(() => {
  document.title = PAGE_TITLE
  void initFromStorage()
})

const handleSubmit = async () => {
  const question = currentQuestion.value.trim()
  if (!question || loading.value) {
    return
  }

  if (closeWS.value) {
    closeWS.value()
    closeWS.value = null
  }

  const sid = currentSessionId.value || crypto.randomUUID()
  if (!currentSessionId.value) {
    persistSessionId(sid)
  }

  messages.value.push({
    type: 'user',
    content: question,
    time: formatTime()
  })

  currentQuestion.value = ''
  loading.value = true
  currentAnswerIndex.value = -1
  await scrollToBottom()

  currentAnswerIndex.value = messages.value.length
  messages.value.push({
    type: 'assistant',
    content: '',
    time: formatTime()
  })

  closeWS.value = qaService.askQuestionStream(
    question,
    sid,
    (message) => {
      if (message.type === 'start') {
        if (message.session_id) {
          persistSessionId(message.session_id)
        }
        if (currentAnswerIndex.value >= 0 && currentAnswerIndex.value < messages.value.length) {
          messages.value[currentAnswerIndex.value].content = ''
        }
      } else if (message.type === 'chunk') {
        if (message.content) {
          const idx = currentAnswerIndex.value
          if (idx >= 0 && idx < messages.value.length) {
            messages.value[idx].content += message.content
          }
          void scrollToBottom()
        }
      } else if (message.type === 'done') {
        loading.value = false
        if (message.session_id) {
          persistSessionId(message.session_id)
        }
        if (message.answer && currentAnswerIndex.value >= 0 && currentAnswerIndex.value < messages.value.length) {
          messages.value[currentAnswerIndex.value].content = message.answer
        }
        currentAnswerIndex.value = -1
        closeWS.value = null
        void scrollToBottom()
        void loadSessions()
      } else if (message.type === 'error') {
        loading.value = false
        ElMessage.error(message.error || '提问失败，请稍后重试')
        if (currentAnswerIndex.value >= 0 && currentAnswerIndex.value < messages.value.length) {
          messages.value[currentAnswerIndex.value].content = '抱歉，我遇到了一些问题，请稍后再试。'
        }
        currentAnswerIndex.value = -1
        closeWS.value = null
        void scrollToBottom()
      }
    },
    () => {
      loading.value = false
      ElMessage.error('连接错误，请稍后重试')
      if (currentAnswerIndex.value >= 0 && currentAnswerIndex.value < messages.value.length) {
        messages.value[currentAnswerIndex.value].content = '连接错误，请稍后再试。'
      }
      currentAnswerIndex.value = -1
      closeWS.value = null
      void scrollToBottom()
    },
    () => {
      loading.value = false
      closeWS.value = null
    }
  )
}

const handleClear = () => {
  if (closeWS.value) {
    closeWS.value()
    closeWS.value = null
  }
  messages.value = []
  currentQuestion.value = ''
  loading.value = false
  currentAnswerIndex.value = -1
}

onBeforeUnmount(() => {
  document.title = savedDocumentTitle
  if (closeWS.value) {
    closeWS.value()
  }
})
</script>

<style scoped>
.smart-doc-page {
  display: flex;
  max-width: 1400px;
  margin: 0 auto;
  height: calc(100vh - 100px);
  gap: 0;
  background: #fff;
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
}

.session-sidebar {
  width: 260px;
  flex-shrink: 0;
  border-right: 1px solid #ebeef5;
  display: flex;
  flex-direction: column;
  background: #fafafa;
}

.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  border-bottom: 1px solid #ebeef5;
}

.sidebar-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.session-scroll {
  flex: 1;
  min-height: 0;
}

.session-item {
  padding: 10px 14px;
  cursor: pointer;
  border-bottom: 1px solid #f0f0f0;
  transition: background 0.15s;
}

.session-item:hover {
  background: #f0f2f5;
}

.session-item.active {
  background: #ecf5ff;
  border-left: 3px solid #409eff;
  padding-left: 11px;
}

.session-title {
  font-size: 13px;
  color: #303133;
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.session-time {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}

.main-panel {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.qa-card {
  flex: 1;
  display: flex;
  flex-direction: column;
  height: 100%;
  border: none;
}

.chat-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 480px;
}

.messages {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  background: #f5f7fa;
  border-radius: 4px;
  margin-bottom: 20px;
}

.message {
  display: flex;
  margin-bottom: 20px;
  animation: fadeIn 0.3s;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.message.user {
  flex-direction: row-reverse;
}

.message-avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  font-size: 20px;
}

.message.user .message-avatar {
  background: #409eff;
  color: white;
  margin-left: 12px;
}

.message.assistant .message-avatar {
  background: #67c23a;
  color: white;
  margin-right: 12px;
}

.message-content {
  max-width: 70%;
  display: flex;
  flex-direction: column;
}

.message.user .message-content {
  align-items: flex-end;
}

.message.assistant .message-content {
  align-items: flex-start;
}

.message-text {
  padding: 12px 16px;
  border-radius: 8px;
  word-wrap: break-word;
  white-space: pre-wrap;
  line-height: 1.6;
}

.message.user .message-text {
  background: #409eff;
  color: white;
  border-bottom-right-radius: 2px;
}

.message.assistant .message-text {
  background: white;
  color: #303133;
  border: 1px solid #e4e7ed;
  border-bottom-left-radius: 2px;
}

.message-time {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
  padding: 0 4px;
}

.cursor {
  display: inline-block;
  animation: blink 1s infinite;
  color: #409eff;
}

@keyframes blink {
  0%,
  50% {
    opacity: 1;
  }
  51%,
  100% {
    opacity: 0;
  }
}

.input-area {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.input-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}
</style>
