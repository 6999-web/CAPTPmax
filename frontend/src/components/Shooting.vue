<script setup>
import { computed, nextTick, onBeforeUnmount, ref } from 'vue'

import {
  analyzeLongVideoWithV2,
  analyzeRtspFrameWithV2,
  analyzeShootingPreviewWithV2,
  analyzeWithV1Fallback,
  analyzeWithV2
} from '../utils/api'
import { settingsStore } from '../stores/settings'

const MOTION_SAMPLE_WIDTH = 40
const MOTION_SAMPLE_HEIGHT = 24
const SHOOTING_REVIEW_MODE = 'SHOOTING_POSTURE'
const MAX_ASSESSMENT_SECONDS = 10
const CAPTURE_INTERVAL_MS = 200
const MAX_CAPTURED_FRAMES = 50

const fileInput = ref(null)
const selectedFile = ref(null)
const previewUrl = ref(null)
const capturedImage = ref(null)
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

const assessmentActive = ref(false)
const assessmentCompleted = ref(false)
const workflowStatusText = ref('点击“开始训练记录”后开始采集，结束后统一输出姿态问题和评分')
const lastMotionScore = ref(0)
const pendingFinalReview = ref(false)

let recognitionInterval = null
let frameCursor = 0
let rtspFrameCursor = 0
let previousMotionSample = null
let assessmentFrameFiles = []
let assessmentStartedAt = 0
let captureInFlight = false
let assessmentTimeout = null

const motionCanvas = typeof document !== 'undefined' ? document.createElement('canvas') : null
const motionContext = motionCanvas?.getContext('2d', { willReadFrequently: true }) || null

if (motionCanvas) {
  motionCanvas.width = MOTION_SAMPLE_WIDTH
  motionCanvas.height = MOTION_SAMPLE_HEIGHT
}

const shooting = computed(() => v2Result.value?.shooting || null)
const meta = computed(() => v2Result.value?.meta || null)
const attribution = computed(() => v2Result.value?.attribution || null)
const issueCards = computed(() => shooting.value?.primary_issues || [])
const finalScore = computed(() => Math.round((shooting.value?.posture_score || 0) * 100))
const dimensionScores = computed(() => shooting.value?.dimension_scores || [])

const dimensionBarWidth = (score) => `${Math.max(0, Math.min(100, Math.round((score || 0) * 100)))}%`
const dimensionScoreText = (score) => Math.round((score || 0) * 100)

const actionButtonLabel = computed(() => {
  if (cameraActive.value) {
    if (pendingFinalReview.value) return '正在生成统一评估'
    return assessmentActive.value ? '结束并生成评估' : '开始训练记录'
  }
  return isAnalyzing.value ? '系统评估中...' : '开始评估'
})

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
  assessmentActive.value = false
  assessmentCompleted.value = false
  workflowStatusText.value = '点击“开始训练记录”后开始采集，结束后统一输出姿态问题和评分'
  lastMotionScore.value = 0
  pendingFinalReview.value = false
  previousMotionSample = null
  captureInFlight = false
  if (assessmentTimeout) {
    clearTimeout(assessmentTimeout)
    assessmentTimeout = null
  }
}

const appendAssessmentFrame = (blob) => {
  if (!assessmentActive.value || pendingFinalReview.value || !blob) return
  if (assessmentFrameFiles.length >= MAX_CAPTURED_FRAMES) return
  const file = new File([blob], `shooting-frame-${String(frameCursor).padStart(4, '0')}.jpg`, {
    type: 'image/jpeg'
  })
  frameCursor += 1
  assessmentFrameFiles.push(file)
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
  ...(cameraId ? { deviceId: { exact: cameraId } } : { facingMode: { ideal: 'environment' } })
})

const bindCameraStream = async (stream) => {
  mediaStream.value = stream
  cameraActive.value = true
  workflowStatusText.value = '摄像头已就绪，点击“开始训练记录”后开始采集'

  window.setTimeout(() => {
    if (videoElement.value) {
      videoElement.value.srcObject = stream
    }
  }, 100)
}

const formatCameraError = (error) => {
  if (!error) return '无法启动摄像头。'
  if (!isCameraSecureContext()) {
    return '当前页面不是安全上下文。请使用 localhost/127.0.0.1 或 HTTPS 后再试。'
  }
  if (error.name === 'NotAllowedError') {
    return '浏览器拒绝了摄像头权限，请在地址栏的站点权限里允许摄像头。'
  }
  if (error.name === 'NotFoundError' || error.name === 'DevicesNotFoundError') {
    return '没有检测到可用摄像头，请检查设备连接和系统权限。'
  }
  if (error.name === 'NotReadableError' || error.name === 'TrackStartError') {
    return '摄像头正在被其他程序占用，请关闭占用程序后重试。'
  }
  if (error.name === 'OverconstrainedError') {
    return '当前保存的摄像头配置不可用，请到设置页重新选择设备。'
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
    const canFallbackToDefault = Boolean(preferredCameraId)
      && ['OverconstrainedError', 'NotFoundError', 'DevicesNotFoundError'].includes(error?.name)

    if (!canFallbackToDefault) throw error

    settingsStore.setCameraDeviceId('')
    return navigator.mediaDevices.getUserMedia({
      video: buildCameraConstraints(''),
      audio: false
    })
  }
}

const startCamera = async () => {
  resetResult()
  resetWorkflowTracking()

  if (sourceSettings.sourceType === 'rtsp') {
    if (!sourceSettings.rtspUrl.trim()) {
      alert('请先在系统设置中填写 RTSP 地址。')
      return
    }

    cameraActive.value = true
    workflowStatusText.value = 'RTSP 视频源已连接，点击“开始训练记录”后开始采集'
    return
  }

  try {
    if (!navigator?.mediaDevices?.getUserMedia) {
      throw new Error('当前浏览器不支持摄像头接口。')
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
  assessmentActive.value = false
  assessmentCompleted.value = completed
  previousMotionSample = null
  captureInFlight = false
  if (assessmentTimeout) {
    clearTimeout(assessmentTimeout)
    assessmentTimeout = null
  }

  if (completed) {
    workflowStatusText.value = '训练记录结束，统一评估结果已生成'
  } else if (cameraActive.value) {
    workflowStatusText.value = '训练记录已停止，可重新开始'
  }
}

const finalizeStructuredAssessment = async () => {
  if (pendingFinalReview.value) return

  stopContinuousRecognition()
  assessmentActive.value = false

  if (!assessmentFrameFiles.length) {
    stopStructuredAssessment({ completed: true })
    feedback.value = '本次训练没有采集到有效画面。'
    return
  }

  pendingFinalReview.value = true
  workflowStatusText.value = '正在生成统一姿态评估结果'

  try {
    const durationSeconds = assessmentStartedAt
      ? Math.min(MAX_ASSESSMENT_SECONDS, Math.max(1, (Date.now() - assessmentStartedAt) / 1000))
      : 0

    const { ok, data } = await analyzeShootingPreviewWithV2({
      files: assessmentFrameFiles,
      legacyMode: SHOOTING_REVIEW_MODE,
      durationSeconds
    })

    if (!ok) {
      feedback.value = data?.detail || '统一姿态评估失败'
      return
    }

    v2Result.value = data
    feedback.value = ''
    stopStructuredAssessment({ completed: true })
    workflowStatusText.value = '训练已完成，姿态问题清单和总评分已生成'
  } catch (error) {
    feedback.value = `统一姿态评估失败：${error.message}`
  } finally {
    pendingFinalReview.value = false
    assessmentFrameFiles = []
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

const callV2ByRtsp = async () => {
  const { ok, data } = await analyzeRtspFrameWithV2({
    rtspUrl: sourceSettings.rtspUrl.trim(),
    legacyMode: SHOOTING_REVIEW_MODE,
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

const startContinuousRecognition = () => {
  stopContinuousRecognition()

  recognitionInterval = window.setInterval(async () => {
    if (captureInFlight || !cameraActive.value || !assessmentActive.value || pendingFinalReview.value) return
    captureInFlight = true

    try {
      if (sourceSettings.sourceType === 'rtsp') {
        const data = await callV2ByRtsp()
        if (data?.frame_b64) {
          revokeCapturedImage()
          capturedImage.value = `data:image/jpeg;base64,${data.frame_b64}`
          const blob = await fetch(`data:image/jpeg;base64,${data.frame_b64}`).then((resp) => resp.blob())
          appendAssessmentFrame(blob)
          lastMotionScore.value = await measureMotionScore(blob)
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

      setCapturedBlob(blob)
      appendAssessmentFrame(blob)
      lastMotionScore.value = await measureMotionScore(blob)
    } catch (error) {
      console.error('连续采集失败', error)
    } finally {
      captureInFlight = false
    }
  }, CAPTURE_INTERVAL_MS)
}

const startStructuredAssessment = async () => {
  if (!cameraActive.value) return

  resetResult()
  frameCursor = 0
  rtspFrameCursor = 0
  previousMotionSample = null
  assessmentFrameFiles = []
  assessmentStartedAt = Date.now()
  assessmentCompleted.value = false
  pendingFinalReview.value = false
  assessmentActive.value = true
  workflowStatusText.value = `正在记录训练画面，系统将在 ${MAX_ASSESSMENT_SECONDS} 秒后自动完成评估`

  startContinuousRecognition()
  assessmentTimeout = window.setTimeout(() => {
    finalizeStructuredAssessment()
  }, MAX_ASSESSMENT_SECONDS * 1000)
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
      await finalizeStructuredAssessment()
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
      ? await analyzeLongVideoWithV2({ file: selectedFile.value, legacyMode: SHOOTING_REVIEW_MODE })
      : await analyzeWithV2({ file: selectedFile.value, legacyMode: SHOOTING_REVIEW_MODE })

    if (primary.ok) {
      v2Result.value = primary.data
      if (primary.data?.attribution) {
        await scrollToAttribution()
      }
      return
    }

    const v1 = await analyzeWithV1Fallback({ file: selectedFile.value, legacyMode: SHOOTING_REVIEW_MODE })
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

onBeforeUnmount(() => {
  stopCamera()
  revokePreview()
  revokeCapturedImage()
})
</script>

<template>
  <div class="shooting-container">
    <div class="page-title row">
      <div class="title-main">
        <h1>射击技战术智能评估 / MARKSMANSHIP AI</h1>
        <p>支持图片、视频、摄像头和 RTSP 输入，单次评估最长 10 秒，结束后统一输出射击姿态问题清单与总评分。</p>
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
          <video
            v-if="cameraActive && sourceSettings.sourceType === 'camera'"
            ref="videoElement"
            autoplay
            playsinline
            class="preview-video"
          ></video>
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
          <div class="mode-tip">
            {{ sourceSettings.sourceType === 'camera' ? '本地摄像头实时画面（单次评估最长 10 秒）' : 'RTSP 视频流（单次评估最长 10 秒）' }}
          </div>
          <div class="camera-btns">
            <button v-if="!cameraActive" class="btn tiny-btn" @click.stop="startCamera">
              {{ sourceSettings.sourceType === 'camera' ? '开启摄像头' : '连接 RTSP' }}
            </button>
            <button v-else class="btn tiny-btn" @click.stop="stopCamera">
              {{ sourceSettings.sourceType === 'camera' ? '关闭摄像头' : '断开 RTSP' }}
            </button>
          </div>
          <div class="workflow-tip">{{ workflowStatusText }}</div>
          <div v-if="cameraActive && assessmentActive" class="motion-tip">
            画面运动幅度：{{ lastMotionScore.toFixed(3) }}
          </div>
        </div>

        <button class="btn full-width" @click="triggerAnalysis" :disabled="((!cameraActive && !previewUrl) || isAnalyzing || pendingFinalReview)">
          <span>{{ actionButtonLabel }}</span>
        </button>
      </div>

      <div ref="resultPanel" class="panel result-panel result-scroll">
        <div class="panel-header">统一评估结果 / FINAL REVIEW</div>

        <div class="section-card">
          <div class="section-head">
            <h3>训练状态</h3>
          </div>
          <div class="stage-line">
            <span>当前状态</span>
            <b>{{ workflowStatusText }}</b>
          </div>
        </div>

        <div class="section-card">
          <div class="section-head">
            <h3>评估模式</h3>
            <span class="section-tag">Posture Review</span>
          </div>
          <div class="empty-tip">
            当前页面只做射击姿态采集与复核。训练过程中不再实时推进流程，也不逐条打断；结束后统一汇总全部不重复问题、对应证据截图和总评分。
          </div>
        </div>

        <div v-if="shooting" class="report-content">
          <div class="summary-grid">
            <div class="summary-item">
              <span>综合评分</span>
              <b>{{ finalScore }}/100</b>
              <small>{{ shooting.posture_score.toFixed(2) }}</small>
            </div>
            <div class="summary-item">
              <span>姿态结论</span>
              <b>{{ shooting.posture_compliance ? '合规' : '需改进' }}</b>
              <small>{{ issueCards.length }} 项不重复问题</small>
            </div>
            <div class="summary-item">
              <span>评估方式</span>
              <b>{{ meta?.analysis_phase === 'final' ? '训练后统一复核' : '单次评估' }}</b>
              <small>{{ shooting.evidence?.length || 0 }} 帧证据</small>
            </div>
            <div v-if="meta" class="summary-item">
              <span>元信息</span>
              <b>{{ meta.device }}</b>
              <small>{{ meta.persons }} 人 / {{ meta.latency_ms?.toFixed?.(1) || 0 }} ms</small>
            </div>
          </div>

          <div class="section-card">
            <div class="section-head">
              <h3>综合评分图表</h3>
              <span class="section-tag">6 Dimensions</span>
            </div>
            <div class="dimension-chart" v-if="dimensionScores.length">
              <div v-for="item in dimensionScores" :key="item.key" class="dimension-row">
                <div class="dimension-meta">
                  <span>{{ item.label_zh }}</span>
                  <b>{{ dimensionScoreText(item.score) }}</b>
                </div>
                <div class="dimension-track">
                  <div class="dimension-fill" :style="{ width: dimensionBarWidth(item.score) }"></div>
                </div>
              </div>
            </div>
            <div v-else class="empty-tip">暂无维度评分数据。</div>
          </div>

          <div class="section-card">
            <div class="section-head">
              <h3>统一问题清单</h3>
              <span class="section-tag">{{ issueCards.length }} 项</span>
            </div>
            <div v-if="issueCards.length" class="issue-list">
              <article v-for="item in issueCards" :key="item.issue_key + '-' + item.step_key" class="issue-card">
                <div class="issue-title">{{ item.title }}</div>
                <div class="issue-step">所在环节：{{ item.step_label_zh }}</div>
                <p><strong>触发原因：</strong>{{ item.trigger_reason }}</p>
                <p><strong>风险说明：</strong>{{ item.risk }}</p>
                <p><strong>改进建议：</strong>{{ item.improvement_suggestion }}</p>
              </article>
            </div>
            <div v-else class="empty-tip">当前未发现明确的姿态问题。</div>
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

        <div v-else-if="isAnalyzing || pendingFinalReview" class="loading-wave">
          <div class="bar"></div><div class="bar"></div><div class="bar"></div><div class="bar"></div>
        </div>

        <div v-else class="empty-state">
          <div class="p-icon">...</div>
          <p>等待评估任务</p>
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

.camera-status { margin-bottom: 24px; }
.camera-btns { margin-top: 10px; }
.workflow-tip, .motion-tip { margin-top: 8px; font-size: 12px; color: #8092a6; }
.workflow-tip { line-height: 1.6; }
.motion-tip { color: #9ac3ff; }
.tiny-btn { padding: 8px 14px; font-size: 12px; }
.selector-label { font-size: 11px; color: #5c7694; margin-bottom: 12px; font-weight: 700; text-transform: uppercase; }
.mode-tip { margin-bottom: 12px; font-size: 12px; color: #7d92ab; }
.full-width { width: 100%; }

.empty-state { text-align: center; margin-top: 100px; color: #2d333b; }
.report-content { color: #fff; line-height: 1.8; display: flex; flex-direction: column; gap: 14px; }
.section-card { border: 1px solid #183451; border-radius: 10px; background: linear-gradient(180deg, rgba(9, 18, 31, 0.95), rgba(7, 14, 24, 0.92)); padding: 14px; }
.section-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 10px; }
.section-head h3 { margin: 0; font-size: 14px; color: var(--primary); }
.section-tag { font-size: 11px; color: #8ea8c4; border: 1px solid #2f4b6a; padding: 3px 8px; border-radius: 999px; }
.stage-line { display: flex; justify-content: space-between; gap: 16px; padding: 8px 12px; border: 1px solid #1a3a5f; border-radius: 4px; background: rgba(8, 16, 29, 0.75); color: #9db4cd; }
.stage-line b { color: #00cfff; text-align: right; }

.summary-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }
.summary-item { border: 1px solid #1b3a59; border-radius: 8px; padding: 10px; background: rgba(9, 19, 33, 0.9); display: flex; flex-direction: column; gap: 4px; }
.summary-item span { color: #7f99b4; font-size: 12px; }
.summary-item b { color: #f2fbff; font-size: 15px; }
.summary-item small { color: #90a9c4; font-size: 11px; }

.dimension-chart { display: flex; flex-direction: column; gap: 12px; }
.dimension-row { display: flex; flex-direction: column; gap: 6px; }
.dimension-meta { display: flex; align-items: center; justify-content: space-between; gap: 12px; color: #d9e6f5; font-size: 13px; }
.dimension-meta b { color: #f3fbff; min-width: 36px; text-align: right; }
.dimension-track { width: 100%; height: 12px; border-radius: 999px; background: rgba(17, 35, 56, 0.95); border: 1px solid #244565; overflow: hidden; }
.dimension-fill { height: 100%; border-radius: 999px; background: linear-gradient(90deg, #1fb6ff 0%, #00e5ff 100%); box-shadow: 0 0 10px rgba(0, 229, 255, 0.25); }

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

@keyframes wave {
  0% { height: 10px; }
  50% { height: 40px; opacity: 1; }
  100% { height: 10px; opacity: 0.3; }
}

@media (max-width: 1200px) {
  .summary-grid { grid-template-columns: 1fr 1fr; }
}

@media (max-width: 1080px) {
  .main-split { grid-template-columns: 1fr; }
  .summary-grid { grid-template-columns: 1fr; }
  .result-scroll { max-height: none; }
  .stage-line { flex-direction: column; }
}
</style>
