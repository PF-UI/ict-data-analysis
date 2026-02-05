<template>
  <div class="qa-page">
    <el-card class="qa-card">
      <template #header>
        <div class="card-header">
          <h2>智能问答系统</h2>
        </div>
      </template>
      
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
              <div class="message-text">{{ message.content }}</div>
              <div class="message-time">{{ message.time }}</div>
            </div>
          </div>
          <div v-if="streamingMessage" class="message assistant">
            <div class="message-avatar">
              <el-icon><ChatDotRound /></el-icon>
            </div>
            <div class="message-content">
              <div class="message-text">
                {{ streamingMessage }}
                <span class="cursor">▋</span>
              </div>
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
</template>

<script setup lang="ts">
import { ref, nextTick, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import { User, ChatDotRound, Loading } from '@element-plus/icons-vue'
import { qaService } from '@/services/qa'

interface Message {
  type: 'user' | 'assistant'
  content: string
  time: string
}

const messages = ref<Message[]>([])
const currentQuestion = ref('')
const loading = ref(false)
const streamingMessage = ref('')
const currentAnswerIndex = ref(-1)
const closeWS = ref<(() => void) | null>(null)
const messagesRef = ref<HTMLElement>()

const formatTime = (date: Date = new Date()) => {
  return date.toLocaleTimeString('zh-CN', { 
    hour: '2-digit', 
    minute: '2-digit' 
  })
}

const scrollToBottom = async () => {
  await nextTick()
  if (messagesRef.value) {
    messagesRef.value.scrollTop = messagesRef.value.scrollHeight
  }
}

const handleSubmit = async () => {
  const question = currentQuestion.value.trim()
  if (!question || loading.value) {
    return
  }

  // 如果已有连接，先关闭
  if (closeWS.value) {
    closeWS.value()
    closeWS.value = null
  }

  // 添加用户消息
  messages.value.push({
    type: 'user',
    content: question,
    time: formatTime()
  })

  // 清空输入框
  currentQuestion.value = ''
  loading.value = true
  streamingMessage.value = ''
  currentAnswerIndex.value = -1
  await scrollToBottom()

  // 添加一个占位的助手消息，用于流式更新
  currentAnswerIndex.value = messages.value.length
  messages.value.push({
    type: 'assistant',
    content: '',
    time: formatTime()
  })

  // 使用 WebSocket 流式获取回答
  closeWS.value = qaService.askQuestionStream(
    question,
    (message) => {
      if (message.type === 'start') {
        // 开始接收
        streamingMessage.value = ''
        if (currentAnswerIndex.value >= 0 && currentAnswerIndex.value < messages.value.length) {
          messages.value[currentAnswerIndex.value].content = ''
        }
      } else if (message.type === 'chunk') {
        // 接收数据块
        if (message.content) {
          streamingMessage.value += message.content
          if (currentAnswerIndex.value >= 0 && currentAnswerIndex.value < messages.value.length) {
            messages.value[currentAnswerIndex.value].content = streamingMessage.value
          }
          scrollToBottom()
        }
      } else if (message.type === 'done') {
        // 完成
        loading.value = false
        streamingMessage.value = ''
        if (message.answer && currentAnswerIndex.value >= 0 && currentAnswerIndex.value < messages.value.length) {
          messages.value[currentAnswerIndex.value].content = message.answer
        }
        currentAnswerIndex.value = -1
        closeWS.value = null
        scrollToBottom()
      } else if (message.type === 'error') {
        // 错误
        loading.value = false
        streamingMessage.value = ''
        ElMessage.error(message.error || '提问失败，请稍后重试')
        if (currentAnswerIndex.value >= 0 && currentAnswerIndex.value < messages.value.length) {
          messages.value[currentAnswerIndex.value].content = '抱歉，我遇到了一些问题，请稍后再试。'
        }
        currentAnswerIndex.value = -1
        closeWS.value = null
        scrollToBottom()
      }
    },
    (error) => {
      loading.value = false
      streamingMessage.value = ''
      ElMessage.error('连接错误，请稍后重试')
      if (currentAnswerIndex.value >= 0 && currentAnswerIndex.value < messages.value.length) {
        messages.value[currentAnswerIndex.value].content = '连接错误，请稍后再试。'
      }
      currentAnswerIndex.value = -1
      closeWS.value = null
      scrollToBottom()
    },
    () => {
      // 连接关闭
      loading.value = false
      streamingMessage.value = ''
      closeWS.value = null
    }
  )
}

const handleClear = () => {
  // 关闭 WebSocket 连接
  if (closeWS.value) {
    closeWS.value()
    closeWS.value = null
  }
  messages.value = []
  currentQuestion.value = ''
  loading.value = false
  streamingMessage.value = ''
  currentAnswerIndex.value = -1
}

// 组件卸载时关闭连接
onBeforeUnmount(() => {
  if (closeWS.value) {
    closeWS.value()
  }
})
</script>

<style scoped>
.qa-page {
  max-width: 1200px;
  margin: 0 auto;
  height: calc(100vh - 100px);
  display: flex;
  flex-direction: column;
}

.qa-card {
  flex: 1;
  display: flex;
  flex-direction: column;
  height: 100%;
}

.card-header h2 {
  margin: 0;
  color: #303133;
  font-size: 20px;
}

.chat-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 500px;
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
  0%, 50% {
    opacity: 1;
  }
  51%, 100% {
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

.is-loading {
  animation: rotating 2s linear infinite;
}

@keyframes rotating {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}
</style>
