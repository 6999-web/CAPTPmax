<script setup>
import { computed, nextTick, onBeforeUnmount, ref } from 'vue'

import { analyzeLongVideoWithV2, analyzeRtspFrameWithV2, analyzeWithV1Fallback, analyzeWithV2, buildWsUrl } from '../utils/api'
import { settingsStore } from '../stores/settings'

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
const trainingStage = ref('A_RECEIVE_WEAPON')
const successHint = ref('')
const errorCards = ref([])

const SOP_STEPS = [
  { key: 'receive_weapon', label: '领枪' },
  { key: 'initial_check', label: '初次验枪' },
  { key: 'insert_magazine', label: '装弹匣' },
  { key: 'prepare_and_fire', label: '射击' },
  { key: 'post_fire_check', label: '终次验枪' }
]

let recognitionInterval = null
let successFlashTimer = null
let frameCursor = 0
let rtspFrameCursor = 0
let lastFlowStageSent = ''
let wsConnection = null

const shooting = computed(() => v2Result.value?.shooting || null)
const meta = computed(() => v2Result.value?.meta || null)
const attribution = computed(() => v2Result.value?.attribution || null)
const issueCards = computed(() => shooting.value?.primary_issues || [])
const stepReports = computed(() => shooting.value?.step_reports || [])
const uiStageLabel = computed(() => shooting.value?.ui_stage_label || '初次验枪')

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
  const report = stepReports.value.find((item) => item.step_key === stepKey)
  return report?.status || 'pending'
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
        if (msg.event === 'stage:update') trainingStage.value = msg.data.stage || trainingStage.value
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
  if (!wsConnection || wsConnection.readyState !== WebSocket.OPEN || !analysis?.shooting) return
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

const startCamera = async () => {
  if (sourceSettings.sourceType === 'rtsp') {
    if (!sourceSettings.rtspUrl.trim()) {
      alert('请先在系统设置中填写 RTSP 地址。')
      return
    }

    cameraActive.value = true
    resetResult()
    errorCards.value = []
    trainingStage.value = 'A_RECEIVE_WEAPON'
    frameCursor = 0
    rtspFrameCursor = 0
    lastFlowStageSent = ''
    connectCoachSocket()
    startContinuousRecognition()
    return
  }

  try {
    const videoConstraints = sourceSettings.cameraDeviceId
      ? { deviceId: { exact: sourceSettings.cameraDeviceId }, width: { ideal: 1280 }, height: { ideal: 720 } }
      : { facingMode: 'environment', width: { ideal: 1280 }, height: { ideal: 720 } }

    const stream = await navigator.mediaDevices.getUserMedia({ video: videoConstraints })

    mediaStream.value = stream
    cameraActive.value = true
    resetResult()
    errorCards.value = []
    trainingStage.value = 'A_RECEIVE_WEAPON'
    frameCursor = 0
    lastFlowStageSent = ''

    window.setTimeout(() => {
      if (videoElement.value) {
        videoElement.value.srcObject = stream
      }
    }, 100)

    connectCoachSocket()
    startContinuousRecognition()
  } catch (error) {
    console.error('摄像头启动失败', error)
    alert(`无法启动摄像头：${error.message}`)
  }
}

const stopCamera = () => {
  if (recognitionInterval) {
    clearInterval(recognitionInterval)
    recognitionInterval = null
  }

  if (mediaStream.value) {
    mediaStream.value.getTracks().forEach((track) => track.stop())
    mediaStream.value = null
  }

  cameraActive.value = false
  closeCoachSocket()
}

const callV2ByBlob = async (blob) => {
  const frameFile = new File([blob], 'frame.jpg', { type: 'image/jpeg' })
  const { ok, data } = await analyzeWithV2({ file: frameFile, legacyMode: mode.value })
  return ok ? data : null
}

const callV2ByRtsp = async () => {
  const { ok, data } = await analyzeRtspFrameWithV2({
    rtspUrl: sourceSettings.rtspUrl.trim(),
    legacyMode: mode.value,
    frameIndex: rtspFrameCursor++,
    fps: 12
  })
  return ok ? data : null
}

const startContinuousRecognition = () => {
  if (recognitionInterval) {
    clearInterval(recognitionInterval)
  }

  recognitionInterval = window.setInterval(async () => {
    if (isAnalyzing.value || !cameraActive.value) return

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
        await pushCoachPacket(blob, data)
      }
    } catch (error) {
      console.error('连续识别失败', error)
    }
  }, 1000)
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

onBeforeUnmount(() => {
  stopCamera()
  revokePreview()
  revokeCapturedImage()
  if (successFlashTimer) clearTimeout(successFlashTimer)
})
</script>

<template>
  <div class="shooting-container">
    <div class="page-title row">
      <div class="title-main">
        <h1>射击技战术智能评估 / MARKSMANSHIP AI</h1>
        <p>支持图片、视频、摄像头与 RTSP 输入，输出结构化 SOP 评估、违规项和证据帧。</p>
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
          <video v-if="cameraActive" ref="videoElement" autoplay playsinline class="preview-video"></video>
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
          <div class="mode-tip">{{ sourceSettings.sourceType === 'camera' ? '本地摄像头' : 'RTSP 视频流（由后端抓帧分析）' }}</div>
          <div class="camera-btns">
            <button v-if="!cameraActive" class="btn tiny-btn" @click.stop="startCamera">
              {{ sourceSettings.sourceType === 'camera' ? '开启摄像头' : '连接 RTSP' }}
            </button>
            <button v-else class="btn tiny-btn" @click.stop="stopCamera">
              {{ sourceSettings.sourceType === 'camera' ? '关闭摄像头' : '停止 RTSP' }}
            </button>
          </div>
          <div class="ws-state" :class="{ online: wsConnected }">教练流：{{ wsConnected ? '已连接' : '未连接' }}</div>
        </div>

        <div class="mode-selector">
          <div class="selector-label">选择分析模式 / INFERENCE MODE</div>
          <div class="option-grid">
            <label :class="{ selected: mode === 'SHOOTING_POSTURE' }">
              <input type="radio" v-model="mode" value="SHOOTING_POSTURE" hidden> 姿势合规
            </label>
            <label :class="{ selected: mode === 'SHOOTING_TARGET' }">
              <input type="radio" v-model="mode" value="SHOOTING_TARGET" hidden> 流程识别
            </label>
            <label :class="{ selected: mode === 'SHOOTING_WEAPON' }">
              <input type="radio" v-model="mode" value="SHOOTING_WEAPON" hidden> 枪械安全
            </label>
          </div>
        </div>

        <button class="btn full-width" @click="triggerAnalysis" :disabled="!previewUrl || isAnalyzing">
          <span v-if="!isAnalyzing">启动结构化评估</span>
          <span v-else class="analyzing-state">系统推理中...</span>
        </button>
      </div>

      <div ref="resultPanel" class="panel result-panel result-scroll">
        <div class="panel-header">结构化结果 / STRUCTURED OUTPUT</div>

        <div class="section-card">
          <div class="section-head">
            <h3>流程进度</h3>
            <span class="section-tag">当前步骤：{{ uiStageLabel }}</span>
          </div>
          <div class="stage-line">
            <span>训练状态机</span>
            <b>{{ trainingStage }}</b>
          </div>
          <div class="sop-track">
            <div
              v-for="step in SOP_STEPS"
              :key="step.key"
              class="sop-step"
              :class="stepStateClass(step.key)"
            >
              <div class="sop-index">{{ step.label }}</div>
              <div class="sop-state">{{ stepReports.find((item) => item.step_key === step.key)?.status || 'pending' }}</div>
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
          <div v-if="!errorCards.length" class="empty-tip">当前无激活的错误卡片。</div>
        </div>

        <div v-if="shooting" class="report-content">
          <div class="summary-grid">
            <div class="summary-item">
              <span>姿势合规</span>
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
              <small>5 步 SOP</small>
            </div>
            <div class="summary-item" v-if="meta">
              <span>元信息</span>
              <b>{{ meta.device }}</b>
              <small>{{ meta.persons }} 人 / {{ meta.latency_ms?.toFixed?.(1) || 0 }} ms</small>
            </div>
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
.row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 30px; }
.engine-badge { background: #000; border: 1px solid var(--border); padding: 5px 15px; border-radius: 4px; font-family: monospace; font-size: 11px; }
.engine-badge .label { color: #76b900; font-weight: bold; }
.engine-badge .version { color: var(--primary); margin-left: 10px; }

.main-split { display: grid; grid-template-columns: minmax(360px, 42%) minmax(0, 1fr); gap: 24px; flex: 1; min-height: 0; }
.panel { min-height: 0; }
.result-panel { padding-right: 8px; }
.result-scroll { overflow-y: auto; overscroll-behavior: contain; max-height: calc(100vh - 180px); }
.panel-header { border-bottom: 1px solid var(--border); padding-bottom: 15px; margin-bottom: 20px; font-size: 11px; font-weight: bold; color: var(--primary); letter-spacing: 2px; }
.upload-box { width: 100%; height: 260px; background: rgba(0,0,0,0.3); border: 1px dashed #1a3a5f; border-radius: 4px; display: flex; justify-content: center; align-items: center; cursor: pointer; transition: 0.3s; overflow: hidden; margin-bottom: 25px; }
.upload-box:hover { border-color: var(--primary); background: rgba(0, 229, 255, 0.05); }
.upload-placeholder { text-align: center; }
.upload-placeholder .icon { font-size: 30px; opacity: 0.5; margin-bottom: 10px; display: block; }
.upload-placeholder p { font-size: 13px; color: var(--text-dim); margin-top: 5px; }
.preview-img, .preview-video { width: 100%; height: 100%; object-fit: contain; }
.mode-selector { margin-bottom: 30px; }
.camera-status { margin-bottom: 20px; }
.camera-btns { margin-top: 10px; }
.ws-state { margin-top: 8px; font-size: 12px; color: #8092a6; }
.ws-state.online { color: #00e676; }
.tiny-btn { padding: 8px 14px; font-size: 12px; }
.selector-label { font-size: 11px; color: #5c7694; margin-bottom: 12px; font-weight: 700; text-transform: uppercase; }
.mode-tip { margin-bottom: 12px; font-size: 12px; color: #7d92ab; }
.option-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px; }
.option-grid label { background: #0a111c; border: 1px solid #1a3a5f; padding: 12px; text-align: center; font-size: 13px; color: var(--text-dim); cursor: pointer; transition: 0.3s; }
.option-grid label.selected { border-color: var(--primary); color: var(--primary); background: rgba(0, 229, 255, 0.1); }
.full-width { width: 100%; }
.empty-state { text-align: center; margin-top: 100px; color: #2d333b; }
.report-content { color: #fff; line-height: 1.8; display: flex; flex-direction: column; gap: 14px; }
.section-card { border: 1px solid #183451; border-radius: 10px; background: linear-gradient(180deg, rgba(9, 18, 31, 0.95), rgba(7, 14, 24, 0.92)); padding: 14px; }
.section-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 10px; }
.section-head h3 { margin: 0; font-size: 14px; color: var(--primary); }
.section-tag { font-size: 11px; color: #8ea8c4; border: 1px solid #2f4b6a; padding: 3px 8px; border-radius: 999px; }
.stage-line { display: flex; justify-content: space-between; padding: 8px 12px; border: 1px solid #1a3a5f; margin-bottom: 12px; border-radius: 4px; background: rgba(8, 16, 29, 0.75); color: #9db4cd; }
.stage-line b { color: #00cfff; }
.sop-track { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 10px; }
.sop-step { border: 1px solid #1e3a59; border-radius: 8px; padding: 10px; background: rgba(7, 17, 29, 0.86); min-height: 74px; display: flex; flex-direction: column; justify-content: space-between; }
.sop-step.completed { border-color: rgba(0, 255, 170, 0.35); }
.sop-step.current { border-color: rgba(0, 207, 255, 0.6); }
.sop-step.issue { border-color: rgba(255, 99, 99, 0.6); background: rgba(54, 15, 21, 0.6); }
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
@keyframes wave { 0% { height: 10px; } 50% { height: 40px; opacity: 1; } 100% { height: 10px; opacity: 0.3; } }
@media (max-width: 1200px) {
  .summary-grid, .sop-track { grid-template-columns: 1fr 1fr; }
}
@media (max-width: 1080px) {
  .main-split { grid-template-columns: 1fr; }
  .summary-grid, .sop-track, .option-grid { grid-template-columns: 1fr; }
  .result-scroll { max-height: none; }
}
</style>
