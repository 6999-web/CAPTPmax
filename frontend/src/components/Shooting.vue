<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'

import { analyzeLongVideoWithV2, analyzeRtspFrameWithV2, analyzeWithV1Fallback, analyzeWithV2, buildWsUrl } from '../utils/api'
import { settingsStore } from '../stores/settings'

const STRUCTURED_STAGES = [
  { key: 'initial_check', label: '初次验枪', prompt: '初次验枪', flowStages: ['check_weapon'] },
  { key: 'insert_magazine', label: '枪弹结合', prompt: '枪弹结合', flowStages: ['insert_magazine'] },
  { key: 'prepare_and_fire', label: '射击', prompt: '射击', flowStages: ['prepare_and_fire'] },
  { key: 'post_fire_check', label: '最终验枪', prompt: '最终验枪', flowStages: ['post_fire_check'] }
]

const STILLNESS_HOLD_MS = 2000
const MOTION_THRESHOLD = 0.02
const MOTION_SAMPLE_WIDTH = 40
const MOTION_SAMPLE_HEIGHT = 24

const fileInput = ref(null)
const selectedFile = ref(null)
const previewUrl = ref(null)
const capturedImage = ref(null)
const mode = ref('SHOOTING_POSTURE')
const isAnalyzing = ref(false)
const feedback = ref('')
const v2Result = ref(null)
const resultPanel = ref(null)
const attributionAnchor = ref(null)

const cameraActive = ref(false)
const videoElement = ref(null)
const mediaStream = ref(null)
const canvasElement = ref(null)
const sourceSettings = settingsStore.settings

const wsConnected = ref(false)
const successHint = ref('')
const errorCards = ref([])
const assessmentActive = ref(false)
const assessmentCompleted = ref(false)
const workflowStageIndex = ref(-1)
const workflowStatusText = ref('点击“启动结构化评估”后开始识别')
const lastMotionScore = ref(0)
const speechSupported = typeof window !== 'undefined' && 'speechSynthesis' in window && 'SpeechSynthesisUtterance' in window

const SOP_STEPS = STRUCTURED_STAGES.map(({ key, label }) => ({ key, label }))

let recognitionInterval = null
let successFlashTimer = null
let frameCursor = 0
let rtspFrameCursor = 0
let lastFlowStageSent = ''
let wsConnection = null
let currentUtterance = null
let speechChain = Promise.resolve()
let stageMatched = false
let stillnessStartedAt = 0
let advancingStage = false
let previousMotionSample = null

const motionCanvas = typeof document !== 'undefined' ? document.createElement('canvas') : null
const motionContext = motionCanvas?.getContext('2d', { willReadFrequently: true }) || null
const availableVoices = ref([])

if (motionCanvas) {
  motionCanvas.width = MOTION_SAMPLE_WIDTH
  motionCanvas.height = MOTION_SAMPLE_HEIGHT
}

const shooting = computed(() => v2Result.value?.shooting || null)
const meta = computed(() => v2Result.value?.meta || null)
const attribution = computed(() => v2Result.value?.attribution || null)
const issueCards = computed(() => shooting.value?.primary_issues || [])
const stepReports = computed(() => shooting.value?.step_reports || [])
const uiStageLabel = computed(() => shooting.value?.ui_stage_label || '初次验枪')
const trainingStage = computed(() => {
  if (assessmentCompleted.value) return '全流程结束'
  return STRUCTURED_STAGES[workflowStageIndex.value]?.label || '待启动'
})
const displayStageLabel = computed(() => (cameraActive.value ? trainingStage.value : uiStageLabel.value))
const actionButtonLabel = computed(() => {
  if (cameraActive.value) {
    return assessmentActive.value ? '停止结构化评估' : '启动结构化评估'
  }
  return isAnalyzing.value ? '系统推理中...' : '启动结构化评估'
})

const refreshVoices = () => {
  if (!speechSupported) return
  availableVoices.value = window.speechSynthesis.getVoices()
}

const pickBestVoice = () => {
  const voices = availableVoices.value
  if (!voices.length) return null

  return (
    voices.find((voice) => /zh|cmn|chinese/i.test(`${voice.lang} ${voice.name}`)) ||
    voices.find((voice) => /xiao|yun|hui|mei|mandarin/i.test(voice.name)) ||
    voices[0]
  )
}

const cancelSpeech = () => {
  if (!speechSupported) return
  if (currentUtterance) {
    currentUtterance.onstart = null
    currentUtterance.onend = null
    currentUtterance.onerror = null
  }
  window.speechSynthesis.cancel()
  currentUtterance = null
}

const speakText = (text) => {
  if (!speechSupported || !text) return Promise.resolve()

  return new Promise((resolve) => {
    const utterance = new SpeechSynthesisUtterance(String(text).trim())
    const voice = pickBestVoice()
    if (voice) utterance.voice = voice
    utterance.lang = voice?.lang || 'zh-CN'
    utterance.rate = 1
    utterance.pitch = 1
    utterance.volume = 1
    utterance.onstart = () => {
      currentUtterance = utterance
    }
    utterance.onend = () => {
      if (currentUtterance === utterance) currentUtterance = null
      resolve()
    }
    utterance.onerror = () => {
      if (currentUtterance === utterance) currentUtterance = null
      resolve()
    }
    window.speechSynthesis.speak(utterance)
  })
}

const queueSpeech = (text) => {
  speechChain = speechChain.then(() => speakText(text))
  return speechChain
}

const revokePreview = () => {
  if (previewUrl.value) {
    URL.revokeObjectURL(previewUrl.value)
    previewUrl.value = null
  }
}

const revokeCapturedImage = () => {
  if (capturedImage.value?.startsWith?.('blob:')) {
    URL.revokeObjectURL(capturedImage.value)
  }
  capturedImage.value = null
}

const setCapturedBlob = (blob) => {
  revokeCapturedImage()
  capturedImage.value = URL.createObjectURL(blob)
}

const resetResult = () => {
  revokeCapturedImage()
  feedback.value = ''
  v2Result.value = null
}

const resetWorkflowTracking = () => {
  assessmentCompleted.value = false
  workflowStageIndex.value = -1
  workflowStatusText.value = '点击“启动结构化评估”后开始识别'
  lastMotionScore.value = 0
  stageMatched = false
  stillnessStartedAt = 0
  advancingStage = false
  previousMotionSample = null
}

const upsertErrorCard = (card) => {
  const idx = errorCards.value.findIndex((item) => item.id === card.id)
  if (idx >= 0) {
    errorCards.value[idx] = card
    return
  }
  errorCards.value.unshift(card)
}

const removeErrorCard = (id) => {
  errorCards.value = errorCards.value.filter((item) => item.id !== id)
}

const flashSuccess = (text) => {
  successHint.value = text
  if (successFlashTimer) clearTimeout(successFlashTimer)
  successFlashTimer = window.setTimeout(() => {
    successHint.value = ''
  }, 1800)
}

const toDataUrl = (blob) => new Promise((resolve, reject) => {
  const reader = new FileReader()
  reader.onload = () => resolve(reader.result)
  reader.onerror = reject
  reader.readAsDataURL(blob)
})

const mapFlowStageToActions = (flowStage) => {
  const map = {
    pass_gun_method_1: ['remove_mag'],
    pass_gun_method_2: ['check_chamber'],
    check_weapon: ['safe_on'],
    insert_magazine: ['insert_mag', 'holster_or_ready'],
    prepare_and_fire: ['draw', 'iso_grip', 'rack_slide', 'fire'],
    post_fire_check: ['final_remove_mag', 'final_check_chamber']
  }
  return map[flowStage] || []
}

const stepStateClass = (stepKey) => {
  const index = STRUCTURED_STAGES.findIndex((item) => item.key === stepKey)
  if (index === -1) return 'pending'
  if (assessmentCompleted.value) return 'completed'
  if (workflowStageIndex.value === -1) return 'pending'
  if (index < workflowStageIndex.value) return 'completed'
  if (index === workflowStageIndex.value) return 'current'
  return 'pending'
}

const connectCoachSocket = () => {
  if (wsConnection) return
  try {
    wsConnection = new WebSocket(buildWsUrl('/api/v2/stream/shooting-coach'))
    wsConnection.onopen = () => {
      wsConnected.value = true
    }
    wsConnection.onclose = () => {
      wsConnected.value = false
      wsConnection = null
    }
    wsConnection.onerror = () => {
      wsConnected.value = false
    }
    wsConnection.onmessage = (evt) => {
      try {
        const msg = JSON.parse(evt.data)
        if (msg.event === 'error:add' || msg.event === 'error:update') upsertErrorCard(msg.data)
        if (msg.event === 'error:remove') removeErrorCard(msg.data.id)
        if (msg.event === 'hint:success') flashSuccess(msg.data.text || '动作已纠正')
      } catch (error) {
        console.warn('教练流消息解析失败', error)
      }
    }
  } catch (error) {
    console.error('连接教练流失败', error)
  }
}

const closeCoachSocket = () => {
  if (!wsConnection) return
  wsConnection.close()
  wsConnection = null
  wsConnected.value = false
}

const pushCoachPacket = async (blob, analysis) => {
  if (!assessmentActive.value || !wsConnection || wsConnection.readyState !== WebSocket.OPEN || !analysis?.shooting) return
  const shootingData = analysis.shooting
  const frameDataUrl = await toDataUrl(blob)

  const actions = shootingData.flow_stage && shootingData.flow_stage !== lastFlowStageSent
    ? mapFlowStageToActions(shootingData.flow_stage)
    : []
  if (shootingData.flow_stage) {
    lastFlowStageSent = shootingData.flow_stage
  }

  wsConnection.send(JSON.stringify({
    event: 'frame',
    frame: frameDataUrl,
    frame_index: frameCursor++,
    actions,
    shooting: {
      posture_compliance: shootingData.posture_compliance,
      flow_order_ok: shootingData.flow_order_ok,
      flow_stage: shootingData.flow_stage,
      violations: shootingData.violations || []
    }
  }))
}

const onFileChange = (event) => {
  const [file] = event.target.files || []
  if (!file) return

  stopCamera()
  revokePreview()
  resetResult()
  selectedFile.value = file
  previewUrl.value = URL.createObjectURL(file)
}

const isLocalhostHost = (hostname) => ['localhost', '127.0.0.1', '::1'].includes(hostname)

const isCameraSecureContext = () => {
  if (typeof window === 'undefined') return true
  return window.isSecureContext || isLocalhostHost(window.location.hostname)
}

const buildCameraConstraints = (cameraId) => ({
  width: { ideal: 1280 },
  height: { ideal: 720 },
  ...(cameraId
    ? { deviceId: { exact: cameraId } }
    : { facingMode: { ideal: 'environment' } })
})

const bindCameraStream = async (stream) => {
  mediaStream.value = stream
  cameraActive.value = true
  workflowStatusText.value = '摄像头已就绪，点击“启动结构化评估”后开始识别'

  window.setTimeout(() => {
    if (videoElement.value) {
      videoElement.value.srcObject = stream
    }
  }, 100)
}

const formatCameraError = (error) => {
  if (!error) {
    return '无法启动摄像头。'
  }

  if (!isCameraSecureContext()) {
    return '当前页面不是安全上下文。请改用 localhost/127.0.0.1 打开，或切换到 HTTPS 后再使用摄像头。'
  }

  if (error.name === 'NotAllowedError') {
    return '浏览器拒绝了摄像头权限。请在地址栏的站点权限里允许摄像头，然后刷新页面重试。'
  }

  if (error.name === 'NotFoundError' || error.name === 'DevicesNotFoundError') {
    return '没有检测到可用摄像头，请检查设备连接和系统隐私权限。'
  }

  if (error.name === 'NotReadableError' || error.name === 'TrackStartError') {
    return '摄像头正在被其他应用占用，请关闭占用程序后重试。'
  }

  if (error.name === 'OverconstrainedError') {
    return '当前保存的摄像头配置不可用，系统已尝试回退默认摄像头。请到设置页重新选择设备。'
  }

  return `无法启动摄像头：${error.message || error.name}`
}

const requestCameraStream = async () => {
  const preferredCameraId = sourceSettings.cameraDeviceId || ''

  try {
    return await navigator.mediaDevices.getUserMedia({
      video: buildCameraConstraints(preferredCameraId),
      audio: false
    })
  } catch (error) {
    const canFallbackToDefault = Boolean(preferredCameraId) && ['OverconstrainedError', 'NotFoundError', 'DevicesNotFoundError'].includes(error?.name)
    if (!canFallbackToDefault) {
      throw error
    }

    settingsStore.setCameraDeviceId('')
    return navigator.mediaDevices.getUserMedia({
      video: buildCameraConstraints(''),
      audio: false
    })
  }
}

const startCamera = async () => {
  resetResult()
  errorCards.value = []
  resetWorkflowTracking()

  if (sourceSettings.sourceType === 'rtsp') {
    if (!sourceSettings.rtspUrl.trim()) {
      alert('请先在系统设置中填写 RTSP 地址。')
      return
    }

    cameraActive.value = true
    workflowStatusText.value = '视频源已连接，点击“启动结构化评估”后开始识别'
    return
  }

  try {
    if (!navigator?.mediaDevices?.getUserMedia) {
      throw new Error('当前浏览器不支持摄像头接口')
    }

    if (!isCameraSecureContext()) {
      throw new DOMException('Camera access requires a secure context', 'NotAllowedError')
    }

    const stream = await requestCameraStream()
    await bindCameraStream(stream)
  } catch (error) {
    console.error('摄像头启动失败', error)
    workflowStatusText.value = formatCameraError(error)
    alert(formatCameraError(error))
  }
}

const stopContinuousRecognition = () => {
  if (recognitionInterval) {
    clearInterval(recognitionInterval)
    recognitionInterval = null
  }
}

const stopStructuredAssessment = ({ completed = false } = {}) => {
  stopContinuousRecognition()
  closeCoachSocket()
  assessmentActive.value = false
  assessmentCompleted.value = completed
  stageMatched = false
  stillnessStartedAt = 0
  advancingStage = false
  previousMotionSample = null
  if (completed) {
    workflowStageIndex.value = STRUCTURED_STAGES.length
    workflowStatusText.value = '全流程结束'
  } else if (cameraActive.value) {
    workflowStatusText.value = '结构化评估已停止，可重新开始'
  }
}

const stopCamera = () => {
  stopStructuredAssessment()

  if (mediaStream.value) {
    mediaStream.value.getTracks().forEach((track) => track.stop())
    mediaStream.value = null
  }

  cameraActive.value = false
  resetWorkflowTracking()
}

const currentLiveMode = () => (assessmentActive.value ? 'SHOOTING_TARGET' : mode.value)

const callV2ByBlob = async (blob) => {
  const frameFile = new File([blob], 'frame.jpg', { type: 'image/jpeg' })
  const { ok, data } = await analyzeWithV2({ file: frameFile, legacyMode: currentLiveMode() })
  return ok ? data : null
}

const callV2ByRtsp = async () => {
  const { ok, data } = await analyzeRtspFrameWithV2({
    rtspUrl: sourceSettings.rtspUrl.trim(),
    legacyMode: currentLiveMode(),
    frameIndex: rtspFrameCursor++,
    fps: 12
  })
  return ok ? data : null
}

const measureMotionScore = async (blob) => {
  if (!motionCanvas || !motionContext || typeof createImageBitmap !== 'function') {
    return 1
  }

  const bitmap = await createImageBitmap(blob)
  motionContext.clearRect(0, 0, MOTION_SAMPLE_WIDTH, MOTION_SAMPLE_HEIGHT)
  motionContext.drawImage(bitmap, 0, 0, MOTION_SAMPLE_WIDTH, MOTION_SAMPLE_HEIGHT)
  if (typeof bitmap.close === 'function') bitmap.close()

  const imageData = motionContext.getImageData(0, 0, MOTION_SAMPLE_WIDTH, MOTION_SAMPLE_HEIGHT).data
  const sample = new Uint8Array(MOTION_SAMPLE_WIDTH * MOTION_SAMPLE_HEIGHT)
  for (let i = 0, pixel = 0; i < imageData.length; i += 4, pixel += 1) {
    sample[pixel] = Math.round((imageData[i] + imageData[i + 1] + imageData[i + 2]) / 3)
  }

  if (!previousMotionSample) {
    previousMotionSample = sample
    return 1
  }

  let diff = 0
  for (let i = 0; i < sample.length; i += 1) {
    diff += Math.abs(sample[i] - previousMotionSample[i])
  }
  previousMotionSample = sample
  return diff / (sample.length * 255)
}

const announceStage = async (text) => {
  workflowStatusText.value = `当前阶段：${text}`
  await queueSpeech(text)
}

const advanceStructuredStage = async () => {
  if (advancingStage) return
  advancingStage = true

  const previousStage = STRUCTURED_STAGES[workflowStageIndex.value]
  stageMatched = false
  stillnessStartedAt = 0

  if (workflowStageIndex.value >= STRUCTURED_STAGES.length - 1) {
    flashSuccess('全流程结束')
    workflowStatusText.value = '全流程结束'
    await queueSpeech('全流程结束')
    stopStructuredAssessment({ completed: true })
    advancingStage = false
    return
  }

  workflowStageIndex.value += 1
  const nextStage = STRUCTURED_STAGES[workflowStageIndex.value]
  flashSuccess(`${previousStage.label}完成，进入${nextStage.label}`)
  workflowStatusText.value = `${previousStage.label}已完成，准备进入${nextStage.label}`
  await announceStage(nextStage.prompt)
  advancingStage = false
}

const updateStructuredWorkflow = async (blob, analysis) => {
  if (!assessmentActive.value || workflowStageIndex.value < 0 || !analysis?.shooting) return

  const stage = STRUCTURED_STAGES[workflowStageIndex.value]
  const shootingData = analysis.shooting
  const motionScore = await measureMotionScore(blob)
  lastMotionScore.value = motionScore

  const stageRecognized = shootingData.flow_order_ok !== false && stage.flowStages.includes(shootingData.flow_stage)
  if (!stageRecognized) {
    stageMatched = false
    stillnessStartedAt = 0
    workflowStatusText.value = `等待识别“${stage.label}”动作`
    return
  }

  if (!stageMatched) {
    stageMatched = true
    stillnessStartedAt = 0
    workflowStatusText.value = `已识别“${stage.label}”，请保持不动 2 秒`
    flashSuccess(`${stage.label}识别完成，请保持不动 2 秒`)
  }

  if (motionScore > MOTION_THRESHOLD) {
    stillnessStartedAt = 0
    workflowStatusText.value = `已识别“${stage.label}”，等待静止确认`
    return
  }

  if (!stillnessStartedAt) {
    stillnessStartedAt = Date.now()
  }

  const holdMs = Date.now() - stillnessStartedAt
  if (holdMs >= STILLNESS_HOLD_MS) {
    await advanceStructuredStage()
    return
  }

  const remainSeconds = ((STILLNESS_HOLD_MS - holdMs) / 1000).toFixed(1)
  workflowStatusText.value = `已识别“${stage.label}”，静止确认中 ${remainSeconds} 秒`
}

const startContinuousRecognition = () => {
  stopContinuousRecognition()

  recognitionInterval = window.setInterval(async () => {
    if (isAnalyzing.value || !cameraActive.value || !assessmentActive.value) return

    if (sourceSettings.sourceType === 'rtsp') {
      try {
        const data = await callV2ByRtsp()
        if (data?.analysis) {
          revokeCapturedImage()
          capturedImage.value = data.frame_b64 ? `data:image/jpeg;base64,${data.frame_b64}` : null
          v2Result.value = data.analysis
          feedback.value = ''
          if (data.frame_b64) {
            const blob = await fetch(`data:image/jpeg;base64,${data.frame_b64}`).then((resp) => resp.blob())
            await updateStructuredWorkflow(blob, data.analysis)
            await pushCoachPacket(blob, data.analysis)
          }
        }
      } catch (error) {
        feedback.value = `RTSP 识别失败：${error.message}`
      }
      return
    }

    if (!videoElement.value || !canvasElement.value) return
    const video = videoElement.value
    if (video.readyState !== 4) return

    const canvas = canvasElement.value
    canvas.width = video.videoWidth
    canvas.height = video.videoHeight
    const context = canvas.getContext('2d')
    context.drawImage(video, 0, 0)

    const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.85))
    if (!blob) return

    try {
      const data = await callV2ByBlob(blob)
      if (data) {
        setCapturedBlob(blob)
        v2Result.value = data
        feedback.value = ''
        await updateStructuredWorkflow(blob, data)
        await pushCoachPacket(blob, data)
      }
    } catch (error) {
      console.error('连续识别失败', error)
    }
  }, 800)
}

const startStructuredAssessment = async () => {
  if (!cameraActive.value) return

  cancelSpeech()
  speechChain = Promise.resolve()
  resetResult()
  errorCards.value = []
  frameCursor = 0
  rtspFrameCursor = 0
  lastFlowStageSent = ''
  previousMotionSample = null
  stageMatched = false
  stillnessStartedAt = 0
  assessmentCompleted.value = false
  assessmentActive.value = true
  workflowStageIndex.value = 0
  workflowStatusText.value = '结构化评估已启动，等待初次验枪'

  connectCoachSocket()
  startContinuousRecognition()
  await announceStage(STRUCTURED_STAGES[0].prompt)
}

const isLikelyVideo = (file) => {
  if (!file) return false
  return file.type.startsWith('video/') || /\.(mp4|mov|avi|mkv|webm)$/i.test(file.name || '')
}

const scrollToAttribution = async () => {
  await nextTick()
  if (attributionAnchor.value?.scrollIntoView) {
    attributionAnchor.value.scrollIntoView({ behavior: 'smooth', block: 'start' })
  } else if (resultPanel.value) {
    resultPanel.value.scrollTop = resultPanel.value.scrollHeight
  }
}

const triggerAnalysis = async () => {
  if (cameraActive.value) {
    if (assessmentActive.value) {
      stopStructuredAssessment()
      return
    }
    await startStructuredAssessment()
    return
  }

  if (!selectedFile.value) return

  isAnalyzing.value = true
  revokeCapturedImage()
  capturedImage.value = previewUrl.value
  feedback.value = ''
  v2Result.value = null

  try {
    const primary = isLikelyVideo(selectedFile.value)
      ? await analyzeLongVideoWithV2({ file: selectedFile.value, legacyMode: mode.value })
      : await analyzeWithV2({ file: selectedFile.value, legacyMode: mode.value })

    if (primary.ok) {
      v2Result.value = primary.data
      if (primary.data?.attribution) {
        await scrollToAttribution()
      }
      return
    }

    const v1 = await analyzeWithV1Fallback({ file: selectedFile.value, legacyMode: mode.value })
    if (v1.ok) {
      feedback.value = v1.data.result || ''
    } else {
      feedback.value = `识别失败：${v1.data.detail || '请检查输入内容。'}`
    }
  } catch (error) {
    feedback.value = `网络通信超时：${error.message}`
  } finally {
    isAnalyzing.value = false
  }
}

onMounted(() => {
  if (speechSupported) {
    refreshVoices()
    window.speechSynthesis.onvoiceschanged = refreshVoices
  }
})

onBeforeUnmount(() => {
  stopCamera()
  revokePreview()
  revokeCapturedImage()
  cancelSpeech()
  if (speechSupported) {
    window.speechSynthesis.onvoiceschanged = null
  }
  if (successFlashTimer) clearTimeout(successFlashTimer)
})
</script>

<template>
  <div class="shooting-container">
    <div class="page-title row">
      <div class="title-main">
        <h1>射击技战术智能评估 / MARKSMANSHIP AI</h1>
        <p>支持图片、视频、摄像头与 RTSP 输入，输出结构化 SOP 评估、问题卡片和关键证据。</p>
      </div>
      <div class="engine-badge">
        <span class="label">CV PIPELINE</span>
        <span class="version">V2+</span>
      </div>
    </div>

    <div class="main-split">
      <div class="panel upload-panel">
        <div class="panel-header">数据源输入 / DATA SOURCE</div>
        <div class="upload-box" @click="!cameraActive && fileInput?.click()">
          <video v-if="cameraActive && sourceSettings.sourceType === 'camera'" ref="videoElement" autoplay playsinline class="preview-video"></video>
          <img v-else-if="capturedImage" :src="capturedImage" alt="识别画面" class="preview-img" />
          <img v-else-if="previewUrl" :src="previewUrl" alt="预览" class="preview-img" />
          <div v-else class="upload-placeholder">
            <span class="icon">+</span>
            <p>点击选择图片或视频进行分析</p>
            <div class="hint">支持 JPG / PNG / MP4 / AVI</div>
          </div>
          <canvas ref="canvasElement" style="display: none;"></canvas>
          <input type="file" ref="fileInput" @change="onFileChange" hidden accept="image/*,video/*">
        </div>

        <div class="camera-status">
          <div class="selector-label">当前视频源 / SOURCE</div>
          <div class="mode-tip">{{ sourceSettings.sourceType === 'camera' ? '本地摄像头实时画面' : 'RTSP 视频流（由后端抓帧分析）' }}</div>
          <div class="camera-btns">
            <button v-if="!cameraActive" class="btn tiny-btn" @click.stop="startCamera">
              {{ sourceSettings.sourceType === 'camera' ? '开启摄像头' : '连接 RTSP' }}
            </button>
            <button v-else class="btn tiny-btn" @click.stop="stopCamera">
              {{ sourceSettings.sourceType === 'camera' ? '关闭摄像头' : '断开 RTSP' }}
            </button>
          </div>
          <div class="ws-state" :class="{ online: wsConnected }">教练流：{{ wsConnected ? '已连接' : '未连接' }}</div>
          <div class="workflow-tip">{{ workflowStatusText }}</div>
          <div v-if="cameraActive && assessmentActive" class="motion-tip">静止判定波动值：{{ lastMotionScore.toFixed(3) }}</div>
        </div>

        <div class="mode-selector">
          <div class="selector-label">选择分析模式 / INFERENCE MODE</div>
          <div class="option-grid">
            <label :class="{ selected: mode === 'SHOOTING_POSTURE' }">
              <input v-model="mode" type="radio" value="SHOOTING_POSTURE" hidden>
              姿态合规
            </label>
            <label :class="{ selected: mode === 'SHOOTING_TARGET' }">
              <input v-model="mode" type="radio" value="SHOOTING_TARGET" hidden>
              流程识别
            </label>
            <label :class="{ selected: mode === 'SHOOTING_WEAPON' }">
              <input v-model="mode" type="radio" value="SHOOTING_WEAPON" hidden>
              枪械安全
            </label>
          </div>
          <div v-if="cameraActive" class="mode-tip inline-tip">实时结构化评估会自动按流程识别优先执行阶段判断，并保留原有问题列举能力。</div>
        </div>

        <button class="btn full-width" @click="triggerAnalysis" :disabled="(!cameraActive && !previewUrl) || isAnalyzing">
          <span>{{ actionButtonLabel }}</span>
        </button>
      </div>

      <div ref="resultPanel" class="panel result-panel result-scroll">
        <div class="panel-header">结构化结果 / STRUCTURED OUTPUT</div>

        <div class="section-card">
          <div class="section-head">
            <h3>流程进度</h3>
            <span class="section-tag">当前步骤：{{ displayStageLabel }}</span>
          </div>
          <div class="stage-line">
            <span>结构化评估状态</span>
            <b>{{ workflowStatusText }}</b>
          </div>
          <div class="sop-track">
            <div
              v-for="step in SOP_STEPS"
              :key="step.key"
              class="sop-step"
              :class="stepStateClass(step.key)"
            >
              <div class="sop-index">{{ step.label }}</div>
              <div class="sop-state">{{ stepStateClass(step.key) }}</div>
            </div>
          </div>
        </div>

        <div v-if="successHint" class="success-flash">{{ successHint }}</div>

        <div class="section-card error-zone">
          <div class="section-head">
            <h3>实时纠错卡片</h3>
            <span class="section-tag">Coach Stream</span>
          </div>
          <transition-group name="error-card" tag="div" class="error-list">
            <div v-for="card in errorCards" :key="card.id" class="error-card-item">
              <div class="error-card-head">
                <span class="tag">{{ card.type }}</span>
                <span class="reason">{{ card.reason }}</span>
              </div>
              <div class="hint-line">改正建议：{{ card.suggestion }}</div>
            </div>
          </transition-group>
          <div v-if="!errorCards.length" class="empty-tip">当前没有激活中的纠错卡片。</div>
        </div>

        <div v-if="shooting" class="report-content">
          <div class="summary-grid">
            <div class="summary-item">
              <span>姿态合规</span>
              <b>{{ shooting.posture_compliance ? '合规' : '不合规' }}</b>
              <small>{{ shooting.posture_score.toFixed(2) }}</small>
            </div>
            <div class="summary-item">
              <span>流程阶段</span>
              <b>{{ shooting.flow_stage }}</b>
              <small>{{ uiStageLabel }}</small>
            </div>
            <div class="summary-item">
              <span>顺序校验</span>
              <b>{{ shooting.flow_order_ok ? '通过' : '未通过' }}</b>
              <small>4 阶段流程</small>
            </div>
            <div v-if="meta" class="summary-item">
              <span>元信息</span>
              <b>{{ meta.device }}</b>
              <small>{{ meta.persons }} 人 / {{ meta.latency_ms?.toFixed?.(1) || 0 }} ms</small>
            </div>
          </div>

          <div class="section-card">
            <div class="section-head">
              <h3>阶段报告</h3>
              <span class="section-tag">{{ stepReports.length }} 项</span>
            </div>
            <div v-if="stepReports.length" class="issue-list">
              <article v-for="report in stepReports" :key="report.step_key" class="issue-card">
                <div class="issue-title">{{ report.step_label_zh }}</div>
                <div class="issue-step">状态：{{ report.status }}</div>
                <p v-if="report.detected_actions.length"><strong>已识别动作：</strong>{{ report.detected_actions.join('、') }}</p>
                <p v-if="report.missing_actions.length"><strong>待补动作：</strong>{{ report.missing_actions.join('、') }}</p>
                <p v-if="report.why_flagged.length"><strong>说明：</strong>{{ report.why_flagged.join('；') }}</p>
              </article>
            </div>
            <div v-else class="empty-tip">当前还没有阶段报告。</div>
          </div>

          <div class="section-card">
            <div class="section-head">
              <h3>主要问题</h3>
              <span class="section-tag">{{ issueCards.length }} 项</span>
            </div>
            <div v-if="issueCards.length" class="issue-list">
              <article v-for="item in issueCards" :key="item.issue_key + '-' + item.step_key" class="issue-card">
                <div class="issue-title">{{ item.title }}</div>
                <div class="issue-step">所在步骤：{{ item.step_label_zh }}</div>
                <p><strong>触发原因：</strong>{{ item.trigger_reason }}</p>
                <p><strong>风险说明：</strong>{{ item.risk }}</p>
                <p><strong>改进建议：</strong>{{ item.improvement_suggestion }}</p>
              </article>
            </div>
            <div v-else class="empty-tip">当前未发现明确的步骤问题。</div>
          </div>

          <div class="section-card">
            <div class="section-head">
              <h3>证据帧</h3>
              <span class="section-tag">Evidence</span>
            </div>
            <ul v-if="shooting.evidence?.length" class="timeline-list">
              <li v-for="item in shooting.evidence" :key="item.frame_index + '-' + item.label">
                帧 {{ item.frame_index }}：{{ item.label }} ({{ item.confidence.toFixed(2) }})
              </li>
            </ul>
            <div v-else class="empty-tip">暂无证据帧。</div>
          </div>

          <div v-if="attribution" ref="attributionAnchor" class="section-card attribution-card">
            <div class="section-head">
              <h3>归因总结</h3>
              <span class="section-tag">CombatDeepAnalyst</span>
            </div>
            <p><strong>结果：</strong>{{ attribution.result }}</p>
            <p><strong>主因：</strong>{{ attribution.primary_reason }}</p>
            <p v-if="attribution.technical_feedback"><strong>技术反馈：</strong>{{ attribution.technical_feedback }}</p>
          </div>
        </div>

        <div v-else-if="feedback" class="report-content text-body">{{ feedback }}</div>

        <div v-else-if="isAnalyzing" class="loading-wave">
          <div class="bar"></div><div class="bar"></div><div class="bar"></div><div class="bar"></div>
        </div>

        <div v-else class="empty-state">
          <div class="p-icon">...</div>
          <p>等待分析任务</p>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.shooting-container { animation: fadeIn 0.4s ease; height: 100%; display: flex; flex-direction: column; }
.row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 30px; gap: 16px; }
.page-title p { margin: 8px 0 0; color: #89a2bd; }
.engine-badge { background: #000; border: 1px solid var(--border); padding: 5px 15px; border-radius: 4px; font-family: monospace; font-size: 11px; }
.engine-badge .label { color: #76b900; font-weight: bold; }
.engine-badge .version { color: var(--primary); margin-left: 10px; }

.main-split { display: grid; grid-template-columns: minmax(360px, 42%) minmax(0, 1fr); gap: 24px; flex: 1; min-height: 0; }
.panel { min-height: 0; }
.result-panel { padding-right: 8px; }
.result-scroll { overflow-y: auto; overscroll-behavior: contain; max-height: calc(100vh - 180px); }
.panel-header { border-bottom: 1px solid var(--border); padding-bottom: 15px; margin-bottom: 20px; font-size: 11px; font-weight: bold; color: var(--primary); letter-spacing: 2px; }

.upload-box { width: 100%; height: 260px; background: rgba(0, 0, 0, 0.3); border: 1px dashed #1a3a5f; border-radius: 4px; display: flex; justify-content: center; align-items: center; cursor: pointer; transition: 0.3s; overflow: hidden; margin-bottom: 25px; }
.upload-box:hover { border-color: var(--primary); background: rgba(0, 229, 255, 0.05); }
.upload-placeholder { text-align: center; }
.upload-placeholder .icon { font-size: 30px; opacity: 0.5; margin-bottom: 10px; display: block; }
.upload-placeholder p { font-size: 13px; color: var(--text-dim); margin: 0; }
.upload-placeholder .hint { margin-top: 8px; font-size: 12px; color: #6f89a6; }
.preview-img, .preview-video { width: 100%; height: 100%; object-fit: contain; }

.mode-selector { margin-bottom: 30px; }
.camera-status { margin-bottom: 20px; }
.camera-btns { margin-top: 10px; }
.ws-state, .workflow-tip, .motion-tip { margin-top: 8px; font-size: 12px; color: #8092a6; }
.ws-state.online { color: #00e676; }
.workflow-tip { line-height: 1.6; }
.motion-tip { color: #9ac3ff; }
.tiny-btn { padding: 8px 14px; font-size: 12px; }
.selector-label { font-size: 11px; color: #5c7694; margin-bottom: 12px; font-weight: 700; text-transform: uppercase; }
.mode-tip { margin-bottom: 12px; font-size: 12px; color: #7d92ab; }
.inline-tip { margin-top: 10px; margin-bottom: 0; }
.option-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
.option-grid label { background: #0a111c; border: 1px solid #1a3a5f; padding: 12px; text-align: center; font-size: 13px; color: var(--text-dim); cursor: pointer; transition: 0.3s; }
.option-grid label.selected { border-color: var(--primary); color: var(--primary); background: rgba(0, 229, 255, 0.1); }
.full-width { width: 100%; }

.empty-state { text-align: center; margin-top: 100px; color: #2d333b; }
.report-content { color: #fff; line-height: 1.8; display: flex; flex-direction: column; gap: 14px; }
.section-card { border: 1px solid #183451; border-radius: 10px; background: linear-gradient(180deg, rgba(9, 18, 31, 0.95), rgba(7, 14, 24, 0.92)); padding: 14px; }
.section-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 10px; }
.section-head h3 { margin: 0; font-size: 14px; color: var(--primary); }
.section-tag { font-size: 11px; color: #8ea8c4; border: 1px solid #2f4b6a; padding: 3px 8px; border-radius: 999px; }
.stage-line { display: flex; justify-content: space-between; gap: 16px; padding: 8px 12px; border: 1px solid #1a3a5f; margin-bottom: 12px; border-radius: 4px; background: rgba(8, 16, 29, 0.75); color: #9db4cd; }
.stage-line b { color: #00cfff; text-align: right; }
.sop-track { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }
.sop-step { border: 1px solid #1e3a59; border-radius: 8px; padding: 10px; background: rgba(7, 17, 29, 0.86); min-height: 74px; display: flex; flex-direction: column; justify-content: space-between; }
.sop-step.completed { border-color: rgba(0, 255, 170, 0.35); }
.sop-step.current { border-color: rgba(0, 207, 255, 0.6); }
.sop-index { font-size: 13px; color: #eef7ff; font-weight: 700; }
.sop-state { font-size: 11px; text-transform: uppercase; color: #8ca6c1; }

.success-flash { background: rgba(0, 180, 80, 0.15); border: 1px solid rgba(0, 255, 136, 0.55); color: #5effaa; padding: 8px 10px; border-radius: 4px; }
.error-list { display: flex; flex-direction: column; gap: 10px; }
.error-card-item { border: 1px solid rgba(255, 80, 80, 0.45); background: rgba(61, 14, 22, 0.5); border-radius: 6px; padding: 10px; }
.error-card-head { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; }
.error-card-head .tag { font-size: 11px; padding: 2px 7px; border-radius: 999px; border: 1px solid rgba(255, 80, 80, 0.55); color: #ff9d9d; }
.error-card-head .reason { font-size: 13px; color: #ffd8d8; }
.hint-line { font-size: 12px; color: #ffd3d3; }

.summary-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }
.summary-item { border: 1px solid #1b3a59; border-radius: 8px; padding: 10px; background: rgba(9, 19, 33, 0.9); display: flex; flex-direction: column; gap: 4px; }
.summary-item span { color: #7f99b4; font-size: 12px; }
.summary-item b { color: #f2fbff; font-size: 15px; }
.summary-item small { color: #90a9c4; font-size: 11px; }

.issue-list { display: flex; flex-direction: column; gap: 12px; }
.issue-card { border: 1px solid #2c4664; border-radius: 8px; padding: 12px; background: rgba(9, 18, 32, 0.92); }
.issue-title { font-size: 15px; font-weight: 700; color: #ecf7ff; }
.issue-step { font-size: 12px; color: #8da7c0; margin-bottom: 8px; }
.timeline-list { margin: 0; padding-left: 18px; }
.timeline-list li { color: #dce7f4; font-size: 13px; margin: 4px 0; }
.empty-tip { color: #6d86a3; font-size: 12px; }
.text-body { white-space: pre-wrap; font-size: 15px; color: #d0d7de; padding: 0 10px; }

.loading-wave { display: flex; justify-content: center; align-items: center; height: 300px; gap: 5px; }
.loading-wave .bar { width: 4px; height: 30px; background: var(--primary); animation: wave 1s infinite ease-in-out; }
.loading-wave .bar:nth-child(2) { animation-delay: 0.1s; }
.loading-wave .bar:nth-child(3) { animation-delay: 0.2s; }
.loading-wave .bar:nth-child(4) { animation-delay: 0.3s; }

.error-card-enter-active, .error-card-leave-active { transition: all 0.25s ease; }
.error-card-enter-from, .error-card-leave-to { opacity: 0; transform: translateY(-6px); }

@keyframes wave {
  0% { height: 10px; }
  50% { height: 40px; opacity: 1; }
  100% { height: 10px; opacity: 0.3; }
}

@media (max-width: 1200px) {
  .summary-grid, .sop-track { grid-template-columns: 1fr 1fr; }
}

@media (max-width: 1080px) {
  .main-split { grid-template-columns: 1fr; }
  .summary-grid, .sop-track, .option-grid { grid-template-columns: 1fr; }
  .result-scroll { max-height: none; }
  .stage-line { flex-direction: column; }
}
</style>
