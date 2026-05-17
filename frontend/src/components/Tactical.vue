<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { buildApiUrl, readApiPayload } from '../utils/api'

const TIGER_OPEN = '/tiger-open.jpg'
const TIGER_CLOSED = '/tiger-closed.jpg'

const cases = ref([])
const selectedCaseId = ref('')
const currentQuestionIndex = ref(0)
const currentAnswer = ref('')
const isReasoning = ref(false)
const qaTimeline = ref([])
const canStartTest = ref(false)
const loadError = ref('')
const isAvatarSpeaking = ref(false)
const speechEnabled = ref(true)
const isListening = ref(false)
const recognitionError = ref('')
const videoQuestionStarted = ref(false)
const caseVideoRef = ref(null)

const speechSupported =
  typeof window !== 'undefined' &&
  'speechSynthesis' in window &&
  'SpeechSynthesisUtterance' in window

const SpeechRecognitionCtor =
  typeof window !== 'undefined'
    ? window.SpeechRecognition || window.webkitSpeechRecognition || null
    : null

const recognitionSupported = Boolean(SpeechRecognitionCtor)

let mouthTimer = null
let blinkTimer = null
let currentUtterance = null
let speechChain = Promise.resolve()
let voiceRefreshTimer = null
let recognition = null
const availableVoices = ref([])

const currentCase = computed(() => cases.value.find((item) => item.id === selectedCaseId.value) ?? null)
const currentQuestion = computed(() => currentCase.value?.questions[currentQuestionIndex.value] ?? '')
const isVideoCase = computed(
  () => currentCase.value?.mediaType === 'video' && Boolean(currentCase.value?.mediaUrl)
)
const displayQuestion = computed(() => {
  if (isVideoCase.value && !videoQuestionStarted.value) {
    return '请先播放案件视频。视频播放结束后，虎警教官会主动提问。'
  }
  return currentQuestion.value || '当前案例已完成。'
})
const avatarImage = computed(() => (isAvatarSpeaking.value ? TIGER_OPEN : TIGER_CLOSED))
const avatarBlinking = computed(() => !isAvatarSpeaking.value)
const avatarStatus = computed(() => {
  if (isListening.value) return '正在听取回答'
  if (isReasoning.value) return '正在分析'
  if (!speechSupported) return '当前浏览器不支持语音播报'
  if (!speechEnabled.value) return '语音已关闭'
  return ''
})
const canUseMicrophone = computed(
  () =>
    recognitionSupported &&
    !isReasoning.value &&
    !canStartTest.value &&
    !isAvatarSpeaking.value &&
    Boolean(currentCase.value) &&
    (!isVideoCase.value || videoQuestionStarted.value)
)

const buildFallbackCases = () => [
  {
    id: 'fallback-1',
    title: '竹山缉捕特大报复案',
    material:
      '1993年，湖北竹山发生特大报复杀人案件。嫌疑人携带凶器在桥面负隅顽抗，抓捕组通过伪装接敌与突然控制完成抓捕。',
    questions: [
      '请先概括该案的核心警情和第一处置目标。',
      '如果你是第一到场警力，你会如何做首轮口头控制和分工？',
      '在不贸然强攻的前提下，你准备如何创造接触窗口并控制升级风险？',
      '结合本案，请总结一条关键成功经验和一条可优化策略。'
    ],
    source: '前端兜底案例'
  }
]

const stopMouthAnimation = () => {
  if (mouthTimer) {
    clearInterval(mouthTimer)
    mouthTimer = null
  }
  isAvatarSpeaking.value = false
}

const scheduleBlink = () => {
  if (blinkTimer) {
    clearTimeout(blinkTimer)
  }
  blinkTimer = window.setTimeout(() => {
    blinkTimer = null
    if (!isAvatarSpeaking.value) {
      scheduleBlink()
    }
  }, 2400 + Math.random() * 1800)
}

const startMouthAnimation = () => {
  stopMouthAnimation()
  if (blinkTimer) {
    clearTimeout(blinkTimer)
    blinkTimer = null
  }
  isAvatarSpeaking.value = true
  mouthTimer = window.setInterval(() => {
    isAvatarSpeaking.value = !isAvatarSpeaking.value
  }, 180)
}

const normalizeTextForSpeech = (text) => String(text || '').replace(/\s+/g, ' ').trim()

const pickBestVoice = () => {
  const voices = availableVoices.value
  if (!voices.length) return null

  return (
    voices.find((voice) => /zh|cmn|chinese/i.test(`${voice.lang} ${voice.name}`)) ||
    voices.find((voice) => /xiao|yun|hui|mei|mandarin/i.test(voice.name)) ||
    voices[0]
  )
}

const refreshVoices = () => {
  if (!speechSupported) return
  availableVoices.value = window.speechSynthesis.getVoices()
}

const cancelSpeech = () => {
  if (!speechSupported) return
  if (currentUtterance) {
    currentUtterance.onend = null
    currentUtterance.onerror = null
    currentUtterance.onstart = null
  }
  window.speechSynthesis.cancel()
  currentUtterance = null
  stopMouthAnimation()
  scheduleBlink()
}

const speakText = (text) => {
  const spokenText = normalizeTextForSpeech(text)
  if (!spokenText || !speechSupported || !speechEnabled.value) {
    return Promise.resolve()
  }

  return new Promise((resolve) => {
    const utterance = new SpeechSynthesisUtterance(spokenText)
    const voice = pickBestVoice()
    if (voice) utterance.voice = voice
    utterance.lang = voice?.lang || 'zh-CN'
    utterance.rate = 1
    utterance.pitch = 1
    utterance.volume = 1

    utterance.onstart = () => {
      currentUtterance = utterance
      startMouthAnimation()
    }
    utterance.onend = () => {
      if (currentUtterance === utterance) currentUtterance = null
      stopMouthAnimation()
      resolve()
    }
    utterance.onerror = () => {
      if (currentUtterance === utterance) currentUtterance = null
      stopMouthAnimation()
      resolve()
    }

    window.speechSynthesis.speak(utterance)
  })
}

const queueSpeech = (text) => {
  speechChain = speechChain.then(() => speakText(text))
  return speechChain
}

const appendMessage = (role, content, kind = 'normal') => {
  qaTimeline.value.push({
    role,
    content,
    kind,
    time: new Date().toLocaleTimeString()
  })

  if (role === 'assistant' && ['material', 'feedback', 'summary', 'question'].includes(kind)) {
    void queueSpeech(content)
  }
}

const stopRecognition = () => {
  if (recognition) {
    recognition.onresult = null
    recognition.onerror = null
    recognition.onend = null
    recognition.onstart = null
    recognition.stop()
    recognition = null
  }
  isListening.value = false
}

const startRecognition = () => {
  if (!recognitionSupported || !canUseMicrophone.value) return

  recognitionError.value = ''
  currentAnswer.value = ''
  cancelSpeech()

  recognition = new SpeechRecognitionCtor()
  recognition.lang = 'zh-CN'
  recognition.interimResults = true
  recognition.continuous = false
  recognition.maxAlternatives = 1

  recognition.onstart = () => {
    isListening.value = true
  }

  recognition.onresult = (event) => {
    let transcript = ''
    for (let index = 0; index < event.results.length; index += 1) {
      transcript += event.results[index][0]?.transcript || ''
    }
    currentAnswer.value = transcript.trim()
  }

  recognition.onerror = (event) => {
    const messageMap = {
      'no-speech': '没有识别到语音，请再试一次。',
      'audio-capture': '没有检测到可用麦克风。',
      'not-allowed': '麦克风权限被拒绝，请允许浏览器访问麦克风。',
      aborted: '录音已取消。'
    }
    recognitionError.value = messageMap[event.error] || `语音识别失败：${event.error}`
  }

  recognition.onend = () => {
    recognition = null
    isListening.value = false
  }

  recognition.start()
}

const toggleMicrophone = () => {
  if (isListening.value) {
    stopRecognition()
    return
  }
  startRecognition()
}

const askCurrentQuestion = () => {
  if (!currentCase.value?.questions.length) return
  appendMessage('assistant', `第 ${currentQuestionIndex.value + 1} 题：${currentCase.value.questions[currentQuestionIndex.value]}`, 'question')
}

const resetSession = async () => {
  stopRecognition()
  cancelSpeech()
  speechChain = Promise.resolve()
  qaTimeline.value = []
  currentQuestionIndex.value = 0
  currentAnswer.value = ''
  canStartTest.value = false
  videoQuestionStarted.value = false
  recognitionError.value = ''

  if (!currentCase.value) return

  if (isVideoCase.value) {
    appendMessage(
      'assistant',
      `案件视频已加载：${currentCase.value.title}`,
      'normal'
    )
    return
  }

  appendMessage('assistant', `案件材料：${currentCase.value.title}\n\n${currentCase.value.material}`, 'material')
  askCurrentQuestion()
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
    loadError.value = `题库读取失败，已切换为前端兜底案例：${error.message}`
  }

  selectedCaseId.value = cases.value[0]?.id || ''
  await resetSession()
}

const sendAnswer = async () => {
  const answer = currentAnswer.value.trim()
  if (!answer || isReasoning.value || !currentCase.value || canStartTest.value) return
  if (isVideoCase.value && !videoQuestionStarted.value) return

  stopRecognition()
  appendMessage('user', answer, 'answer')
  currentAnswer.value = ''
  recognitionError.value = ''
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
    askCurrentQuestion()
  } else {
    canStartTest.value = true
    appendMessage('assistant', '当前案例问答已完成，可以切换案例继续训练。', 'summary')
  }
}

const toggleSpeech = async () => {
  speechEnabled.value = !speechEnabled.value
  if (!speechEnabled.value) {
    cancelSpeech()
    speechChain = Promise.resolve()
    return
  }

  const latestAssistantMessage = [...qaTimeline.value].reverse().find((item) => item.role === 'assistant')
  if (latestAssistantMessage) {
    await queueSpeech(latestAssistantMessage.content)
  }
}

const isVideoAudible = (videoElement) => Boolean(videoElement && !videoElement.muted && videoElement.volume > 0)

const handleVideoPlay = () => {
  if (isVideoAudible(caseVideoRef.value)) {
    startMouthAnimation()
  }
}

const handleVideoPause = () => {
  if (!currentUtterance) {
    stopMouthAnimation()
    scheduleBlink()
  }
}

const handleVideoVolumeChange = () => {
  const videoElement = caseVideoRef.value
  if (!videoElement || videoElement.paused || videoElement.ended) return

  if (isVideoAudible(videoElement)) {
    startMouthAnimation()
  } else if (!currentUtterance) {
    stopMouthAnimation()
    scheduleBlink()
  }
}

const handleVideoEnded = async () => {
  stopMouthAnimation()
  scheduleBlink()

  if (!isVideoCase.value || videoQuestionStarted.value || !currentCase.value?.questions.length) {
    return
  }

  videoQuestionStarted.value = true
  appendMessage('assistant', `案件视频已播放完成，下面开始提问。`, 'summary')
  askCurrentQuestion()
}

watch(selectedCaseId, async () => {
  if (selectedCaseId.value) {
    await resetSession()
  }
})

onMounted(async () => {
  if (speechSupported) {
    refreshVoices()
    window.speechSynthesis.onvoiceschanged = refreshVoices
    voiceRefreshTimer = window.setTimeout(refreshVoices, 800)
  }
  scheduleBlink()
  await loadCases()
})

onBeforeUnmount(() => {
  if (blinkTimer) {
    clearTimeout(blinkTimer)
    blinkTimer = null
  }
  if (voiceRefreshTimer) {
    clearTimeout(voiceRefreshTimer)
    voiceRefreshTimer = null
  }
  if (speechSupported) {
    window.speechSynthesis.onvoiceschanged = null
  }
  stopRecognition()
  cancelSpeech()
})
</script>

<template>
  <section class="tactical-panel">
    <div class="layout">
      <div class="main-column">
        <div class="tactical-header">
          <div>
            <h2>战术推演</h2>
            <p>视频播报结束后由虎警教官主动提问，学员使用麦克风回答。</p>
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
          <video
            v-if="currentCase.mediaType === 'video' && currentCase.mediaUrl"
            ref="caseVideoRef"
            class="case-video"
            :src="buildApiUrl(currentCase.mediaUrl)"
            controls
            preload="metadata"
            @play="handleVideoPlay"
            @pause="handleVideoPause"
            @ended="handleVideoEnded"
            @volumechange="handleVideoVolumeChange"
          ></video>
          <p v-if="currentCase.mediaType !== 'video'">{{ currentCase.material }}</p>
        </div>

        <div class="timeline">
          <article
            v-for="(item, index) in qaTimeline"
            :key="`${item.role}-${index}`"
            class="timeline-item"
            :class="item.role"
          >
            <div class="timeline-meta">
              <span>{{ item.role === 'assistant' ? '虎警教官' : '学员' }}</span>
              <span>{{ item.time }}</span>
            </div>
            <pre>{{ item.content }}</pre>
          </article>
        </div>

        <div class="answer-box">
          <div class="current-question">
            <strong>当前题目</strong>
            <p>{{ displayQuestion }}</p>
          </div>

          <div class="transcript-box" :class="{ listening: isListening }">
            <strong>语音识别结果</strong>
            <p v-if="currentAnswer">{{ currentAnswer }}</p>
            <p v-else>{{ isListening ? '正在聆听，请开始回答。' : '点击“开启麦克风”后开始语音回答。' }}</p>
          </div>

          <div v-if="recognitionError" class="warning-banner mic-warning">{{ recognitionError }}</div>

          <div class="actions mic-actions">
            <button
              class="secondary-button"
              @click="toggleMicrophone"
              :disabled="!canUseMicrophone"
            >
              {{ isListening ? '停止麦克风' : '开启麦克风' }}
            </button>
            <button
              class="primary-button"
              @click="sendAnswer"
              :disabled="isReasoning || canStartTest || !currentAnswer.trim()"
            >
              {{ isReasoning ? '推演中...' : '提交语音回答' }}
            </button>
          </div>
        </div>
      </div>

      <aside class="avatar-panel">
        <div class="avatar-card">
          <div class="avatar-stage">
            <div class="avatar-figure" :class="{ speaking: isAvatarSpeaking }">
              <img :src="avatarImage" alt="虎警教官" class="avatar-image">
              <div class="eye-mask left" :class="{ blinking: avatarBlinking }"></div>
              <div class="eye-mask right" :class="{ blinking: avatarBlinking }"></div>
            </div>
          </div>

          <div class="avatar-meta">
            <div>
              <h3>虎警教官</h3>
            </div>
            <span v-if="avatarStatus" class="avatar-status">{{ avatarStatus }}</span>
          </div>

          <div class="avatar-actions">
            <button class="secondary-button" @click="toggleSpeech" :disabled="!speechSupported">
              {{ speechEnabled ? '关闭语音' : '开启语音' }}
            </button>
            <span class="speech-hint">
              {{
                recognitionSupported
                  ? '支持麦克风语音输入'
                  : '当前浏览器不支持麦克风语音识别'
              }}
            </span>
          </div>

          <div class="avatar-box">
            <strong>当前播报</strong>
            <p v-if="qaTimeline.length">{{ qaTimeline[qaTimeline.length - 1].content }}</p>
            <p v-else>等待案例加载。</p>
          </div>
        </div>
      </aside>
    </div>
  </section>
</template>

<style scoped>
.tactical-panel {
  display: grid;
}

.layout {
  display: grid;
  grid-template-columns: minmax(0, 1.55fr) 340px;
  gap: 18px;
}

.main-column,
.avatar-panel {
  min-width: 0;
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

.case-select select {
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
.answer-box,
.avatar-card {
  background: var(--app-surface);
  border: 1px solid var(--app-border);
  border-radius: 20px;
  padding: 18px;
  box-shadow: 0 18px 36px rgba(3, 9, 20, 0.22);
}

.main-column {
  display: grid;
  gap: 18px;
}

.warning-banner {
  color: #ffd98a;
  background: rgba(105, 62, 9, 0.3);
  border-color: rgba(255, 196, 98, 0.24);
}

.mic-warning {
  padding: 12px 14px;
}

.meta-row,
.avatar-meta {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
  align-items: start;
}

.meta-row span,
.avatar-meta p,
.avatar-status,
.timeline-meta,
.speech-hint {
  color: var(--app-text-muted);
  font-size: 13px;
}

.case-card p,
.avatar-box p,
.current-question p,
.transcript-box p {
  margin: 6px 0 0;
  color: var(--app-text-muted);
  line-height: 1.7;
}

.case-video {
  width: 100%;
  margin-top: 12px;
  border-radius: 12px;
  background: #000;
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

.transcript-box {
  min-height: 124px;
  padding: 14px;
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.07);
  background: rgba(255, 255, 255, 0.03);
}

.transcript-box.listening {
  border-color: rgba(0, 229, 255, 0.32);
  box-shadow: inset 0 0 0 1px rgba(0, 229, 255, 0.1);
}

.actions {
  display: flex;
  justify-content: flex-end;
}

.mic-actions {
  gap: 10px;
  flex-wrap: wrap;
}

.primary-button,
.secondary-button {
  border: 0;
  border-radius: 999px;
  padding: 12px 18px;
  color: white;
  cursor: pointer;
}

.primary-button {
  background: linear-gradient(135deg, #0088ff 0%, #00b7ff 100%);
  box-shadow: 0 12px 28px rgba(0, 120, 255, 0.25);
}

.secondary-button {
  background: rgba(0, 229, 255, 0.14);
  border: 1px solid rgba(0, 229, 255, 0.18);
}

.primary-button:disabled,
.secondary-button:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.avatar-card {
  display: grid;
  gap: 16px;
  position: sticky;
  top: 18px;
}

.avatar-stage {
  min-height: 420px;
  display: grid;
  place-items: center;
  border-radius: 16px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.04), rgba(0, 136, 255, 0.06));
  border: 1px solid rgba(255, 255, 255, 0.06);
  overflow: hidden;
}

.avatar-image {
  width: 100%;
  max-width: 300px;
  height: auto;
  object-fit: contain;
}

.avatar-figure {
  position: relative;
  width: 100%;
  max-width: 300px;
}

.eye-mask {
  position: absolute;
  top: 25.5%;
  width: 13%;
  height: 9%;
  border-radius: 999px;
  background: #f7b54b;
  transform-origin: center;
  transform: scaleY(0.05);
  opacity: 0;
  pointer-events: none;
}

.eye-mask.left {
  left: 28%;
}

.eye-mask.right {
  right: 28%;
}

.eye-mask.blinking {
  animation: blink-eye 4s infinite;
}

.avatar-figure.speaking .eye-mask {
  animation: none;
  opacity: 0;
}

.avatar-meta {
  margin-bottom: 0;
}

.avatar-meta h3 {
  margin: 0;
}

.avatar-meta p {
  margin: 6px 0 0;
}

.avatar-status {
  padding: 8px 10px;
  border-radius: 999px;
  background: rgba(0, 229, 255, 0.08);
  border: 1px solid rgba(0, 229, 255, 0.12);
  white-space: nowrap;
}

.avatar-actions {
  display: grid;
  gap: 8px;
}

.avatar-box {
  padding: 14px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.05);
}

@media (max-width: 1100px) {
  .layout {
    grid-template-columns: 1fr;
  }

  .avatar-card {
    position: static;
  }
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

@keyframes blink-eye {
  0%,
  44%,
  48%,
  100% {
    transform: scaleY(0.05);
    opacity: 0;
  }

  45%,
  47% {
    transform: scaleY(1);
    opacity: 1;
  }
}
</style>
