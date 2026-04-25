<script setup>
import { computed, onMounted, ref, watch } from 'vue'

import { buildApiUrl, readApiPayload } from '../utils/api'

const cases = ref([])
const selectedCaseId = ref('')
const currentQuestionIndex = ref(0)
const currentAnswer = ref('')
const isReasoning = ref(false)
const qaTimeline = ref([])
const canStartTest = ref(false)
const loadError = ref('')

const currentCase = computed(() => cases.value.find((item) => item.id === selectedCaseId.value) ?? null)
const currentQuestion = computed(() => currentCase.value?.questions[currentQuestionIndex.value] ?? '')

const buildFallbackCases = () => [
  {
    id: 'fallback-1',
    title: '竹山缉捕特大报复案',
    material:
      '1993 年，湖北竹山发生特大报复杀人案件。嫌疑人携带凶器在桥面负隅顽抗，抓捕组通过伪装接敌与突然突击实施控制，最终成功完成抓捕。',
    questions: [
      '请先概括该案例的核心警情和第一处置目标。',
      '如果你是第一到场警力，你会如何做首轮口头控制和分工？',
      '在不贸然强攻的前提下，你准备如何创造接触窗口并控制升级风险？',
      '结合本案，请总结一条关键成功经验和一条可优化策略。'
    ],
    source: '前端兜底案例'
  }
]

const appendMessage = (role, content, kind = 'normal') => {
  qaTimeline.value.push({
    role,
    content,
    kind,
    time: new Date().toLocaleTimeString()
  })
}

const resetSession = () => {
  qaTimeline.value = []
  currentQuestionIndex.value = 0
  currentAnswer.value = ''
  canStartTest.value = false

  if (!currentCase.value) return

  appendMessage('assistant', `案例材料：${currentCase.value.title}\n\n${currentCase.value.material}`, 'material')

  if (currentCase.value.questions.length) {
    appendMessage('assistant', `第 1 题：${currentCase.value.questions[0]}`, 'question')
  }
}

const loadCases = async () => {
  loadError.value = ''
  try {
    const response = await fetch(buildApiUrl('/api/tactical-cases'))
    const data = await readApiPayload(response)

    if (!response.ok || !Array.isArray(data.cases) || !data.cases.length) {
      throw new Error(data.detail || '题库接口返回为空')
    }

    cases.value = data.cases
  } catch (error) {
    cases.value = buildFallbackCases()
    loadError.value = `题库读取失败，已切换到前端兜底案例：${error.message}`
  }

  selectedCaseId.value = cases.value[0]?.id || ''
  resetSession()
}

const sendAnswer = async () => {
  const answer = currentAnswer.value.trim()
  if (!answer || isReasoning.value || !currentCase.value || canStartTest.value) return

  appendMessage('user', answer, 'answer')
  currentAnswer.value = ''
  isReasoning.value = true

  try {
    const scenarioContext = `${currentCase.value.material}\n\n当前题目：${currentQuestion.value}`
    const messages = qaTimeline.value.map((item) => ({ role: item.role, content: item.content }))

    const response = await fetch(buildApiUrl('/api/tactical-chat'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        scenario: currentCase.value.title,
        scenarioContext,
        messages
      })
    })

    const data = await readApiPayload(response)
    if (!response.ok) {
      throw new Error(data.detail || '推演链路异常')
    }

    appendMessage('assistant', data.result || '已记录你的处置思路。', 'feedback')
  } catch (error) {
    appendMessage('assistant', `点评失败：${error.message}`, 'feedback')
  } finally {
    isReasoning.value = false
  }

  const nextIndex = currentQuestionIndex.value + 1
  if (nextIndex < currentCase.value.questions.length) {
    currentQuestionIndex.value = nextIndex
    appendMessage('assistant', `第 ${nextIndex + 1} 题：${currentCase.value.questions[nextIndex]}`, 'question')
  } else {
    canStartTest.value = true
    appendMessage('assistant', '当前案例问答已完成，可以切换案例继续训练。', 'summary')
  }
}

watch(selectedCaseId, () => {
  if (selectedCaseId.value) {
    resetSession()
  }
})

onMounted(loadCases)
</script>

<template>
  <section class="tactical-panel">
    <div class="tactical-header">
      <div>
        <h2>战术推演</h2>
        <p>先阅读案例，再按问题逐轮回答，系统会给出现场反馈与下一题。</p>
      </div>

      <label class="case-select">
        <span>案例选择</span>
        <select v-model="selectedCaseId">
          <option v-for="item in cases" :key="item.id" :value="item.id">
            {{ item.title }}
          </option>
        </select>
      </label>
    </div>

    <div v-if="loadError" class="warning-banner">{{ loadError }}</div>

    <div v-if="currentCase" class="case-card">
      <div class="meta-row">
        <strong>{{ currentCase.title }}</strong>
        <span>{{ currentCase.source || '后端题库' }}</span>
      </div>
      <p>{{ currentCase.material }}</p>
    </div>

    <div class="timeline">
      <article
        v-for="(item, index) in qaTimeline"
        :key="`${item.role}-${index}`"
        class="timeline-item"
        :class="item.role"
      >
        <div class="timeline-meta">
          <span>{{ item.role === 'assistant' ? '系统' : '学员' }}</span>
          <span>{{ item.time }}</span>
        </div>
        <pre>{{ item.content }}</pre>
      </article>
    </div>

    <div class="answer-box">
      <div class="current-question">
        <strong>当前题目</strong>
        <p>{{ currentQuestion || '当前案例已完成。' }}</p>
      </div>

      <textarea
        v-model="currentAnswer"
        rows="6"
        placeholder="请输入你的处置思路、口令、站位和后续动作。"
        :disabled="isReasoning || canStartTest"
      />

      <div class="actions">
        <button class="primary-button" @click="sendAnswer" :disabled="isReasoning || canStartTest">
          {{ isReasoning ? '推演中...' : '提交回答' }}
        </button>
      </div>
    </div>
  </section>
</template>

<style scoped>
.tactical-panel {
  display: grid;
  gap: 18px;
}

.tactical-header {
  display: flex;
  justify-content: space-between;
  gap: 20px;
  align-items: end;
}

.tactical-header h2 {
  margin: 0 0 8px;
}

.tactical-header p {
  margin: 0;
  color: var(--app-text-muted);
}

.case-select {
  display: grid;
  gap: 8px;
  min-width: 260px;
}

.case-select select,
textarea {
  width: 100%;
  border: 1px solid var(--app-border);
  border-radius: 14px;
  padding: 12px 14px;
  font: inherit;
  background: rgba(8, 18, 36, 0.88);
  color: var(--app-text);
}

.warning-banner,
.case-card,
.timeline,
.answer-box {
  background: var(--app-surface);
  border: 1px solid var(--app-border);
  border-radius: 20px;
  padding: 18px;
  box-shadow: 0 18px 36px rgba(3, 9, 20, 0.22);
}

.warning-banner {
  color: #ffd98a;
  background: rgba(105, 62, 9, 0.3);
  border-color: rgba(255, 196, 98, 0.24);
}

.meta-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.meta-row span {
  color: var(--app-text-muted);
  font-size: 13px;
}

.timeline {
  display: grid;
  gap: 12px;
  max-height: 460px;
  overflow: auto;
}

.timeline-item {
  border-radius: 16px;
  padding: 14px;
}

.timeline-item.assistant {
  background: rgba(0, 229, 255, 0.08);
  border: 1px solid rgba(0, 229, 255, 0.12);
}

.timeline-item.user {
  background: rgba(125, 255, 198, 0.08);
  border: 1px solid rgba(125, 255, 198, 0.12);
}

.timeline-meta {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
  font-size: 12px;
  color: var(--app-text-muted);
}

pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: inherit;
}

.answer-box {
  display: grid;
  gap: 14px;
}

.current-question p {
  margin: 6px 0 0;
  color: var(--app-text-muted);
}

.actions {
  display: flex;
  justify-content: flex-end;
}

.primary-button {
  border: 0;
  border-radius: 999px;
  padding: 12px 18px;
  background: linear-gradient(135deg, #0088ff 0%, #00b7ff 100%);
  color: white;
  cursor: pointer;
  box-shadow: 0 12px 28px rgba(0, 120, 255, 0.25);
}

.primary-button:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

@media (max-width: 900px) {
  .tactical-header {
    flex-direction: column;
    align-items: stretch;
  }

  .case-select {
    min-width: 0;
  }
}
</style>
