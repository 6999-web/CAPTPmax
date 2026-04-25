<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'

import { analyzeLongVideoWithV2, analyzeRtspFrameWithV2, analyzeWithV1Fallback, analyzeWithV2 } from '../utils/api'
import { settingsStore } from '../stores/settings'

const fileInput = ref(null)
const selectedFile = ref(null)
const previewUrl = ref(null)
const capturedImage = ref(null)
const isVideo = ref(false)
const mode = ref('COMBAT_SCORING')
const isAnalyzing = ref(false)
const feedback = ref('')
const v2Result = ref(null)

const cameraActive = ref(false)
const videoElement = ref(null)
const mediaStream = ref(null)
const canvasElement = ref(null)
const sourceSettings = settingsStore.settings
let recognitionInterval = null
let rtspFrameCursor = 0

const metricLabels = {
  distance_score: '距离压缩',
  impact_score: '打击强度',
  guard_open_score: '护架暴露',
  balance_break_score: '重心破坏',
  stability_score: '自身稳定',
  explosiveness_score: '爆发力',
  reaction_lag_score: '反应滞后'
}

const combat = computed(() => v2Result.value?.combat || null)
const meta = computed(() => v2Result.value?.meta || null)
const reviewCards = computed(() => combat.value?.review_cards || [])
const supportedActions = computed(() => combat.value?.supported_actions || [])
const actionCount = computed(() => combat.value?.actions?.length || 0)
const hitCount = computed(() => combat.value?.hit_events?.length || 0)
const highImpactCards = computed(() => reviewCards.value.filter((item) => item.damage_zh !== '未形成有效击中').length)

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

const onFileChange = (event) => {
  const [file] = event.target.files || []
  if (!file) return

  stopCamera()
  revokePreview()
  resetResult()
  selectedFile.value = file
  isVideo.value = file.type.startsWith('video/')
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
    rtspFrameCursor = 0
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

    window.setTimeout(() => {
      if (videoElement.value) {
        videoElement.value.srcObject = stream
      }
    }, 100)

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
}

const analyzeRtspFrame = async () => {
  const { ok, data } = await analyzeRtspFrameWithV2({
    rtspUrl: sourceSettings.rtspUrl.trim(),
    legacyMode: mode.value,
    frameIndex: rtspFrameCursor++,
    fps: 12
  })
  if (!ok) {
    throw new Error(data.detail || 'RTSP 分析失败')
  }

  revokeCapturedImage()
  capturedImage.value = data.frame_b64 ? `data:image/jpeg;base64,${data.frame_b64}` : null
  v2Result.value = data.analysis
  feedback.value = ''
}

const startContinuousRecognition = () => {
  if (recognitionInterval) {
    clearInterval(recognitionInterval)
  }

  recognitionInterval = window.setInterval(async () => {
    if (isAnalyzing.value || !cameraActive.value) return

    if (sourceSettings.sourceType === 'rtsp') {
      try {
        await analyzeRtspFrame()
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

    const frameFile = new File([blob], 'frame.jpg', { type: 'image/jpeg' })

    try {
      const { ok, data } = await analyzeWithV2({ file: frameFile, legacyMode: mode.value })
      if (ok) {
        setCapturedBlob(blob)
        v2Result.value = data
        feedback.value = ''
      }
    } catch (error) {
      console.error('连续识别失败', error)
    }
  }, 1000)
}

const triggerAnalysis = async () => {
  if (!selectedFile.value) return

  isAnalyzing.value = true
  revokeCapturedImage()
  capturedImage.value = previewUrl.value
  feedback.value = ''
  v2Result.value = null

  try {
    const primary = isVideo.value
      ? await analyzeLongVideoWithV2({ file: selectedFile.value, legacyMode: mode.value })
      : await analyzeWithV2({ file: selectedFile.value, legacyMode: mode.value })

    if (primary.ok) {
      v2Result.value = primary.data
      return
    }

    const v1 = await analyzeWithV1Fallback({ file: selectedFile.value, legacyMode: mode.value })
    if (v1.ok) {
      feedback.value = v1.data.result || ''
    } else {
      feedback.value = `识别失败：${v1.data.detail || '请更换更清晰的训练画面后重试。'}`
    }
  } catch (error) {
    feedback.value = `通信超时：${error.message}`
  } finally {
    isAnalyzing.value = false
  }
}

const pickTopLabel = (items, fallback) => {
  if (!items.length) return fallback

  const counts = new Map()
  items.forEach((item) => {
    const key = item || fallback
    counts.set(key, (counts.get(key) || 0) + 1)
  })

  return [...counts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] || fallback
}

const overallSummary = computed(() => {
  const cards = reviewCards.value
  const topAction = pickTopLabel(cards.map((item) => item.action_zh).filter(Boolean), '暂未识别到明确动作')
  const topDamage = pickTopLabel(cards.map((item) => item.damage_zh).filter(Boolean), '未形成明确击中结果')
  const topReason = pickTopLabel(cards.map((item) => item.evade_failure_reason_zh).filter(Boolean), '画面证据不足，暂时无法稳定判断')
  const stability = Number(combat.value?.stability || 0)
  const fatigueLevel = combat.value?.fatigue?.level || '未评估'

  return {
    topAction,
    topDamage,
    topReason,
    fatigueLevel,
    stability,
    overviewText: cards.length
      ? `本次样本共产出 ${cards.length} 条复盘结果，以“${topAction}”为主，主要表现为“${topDamage}”。`
      : '本次样本尚未形成稳定的实战复盘卡片，当前以系统聚合指标为主。',
    rhythmText: highImpactCards.value
      ? `有效击打 ${highImpactCards.value} 次，当前对抗节奏已经出现明确的攻防转换。`
      : '当前更偏向试探或距离拉扯阶段，尚未形成稳定有效击打。',
    riskText: stability < 0.45
      ? '整体稳定性偏低，后续应优先关注重心回收、脚步调整和攻击后的自我保护。'
      : '整体稳定性尚可，后续应继续关注连续对抗后的节奏变化与防守空档。'
  }
})

const metricEntries = (metrics) => Object.entries(metricLabels).map(([key, label]) => ({
  key,
  label,
  value: Number(metrics?.[key] || 0)
}))

const confidenceText = (value) => `${Math.round((Number(value) || 0) * 100)}%`
const metricWidth = (value) => `${Math.round((Number(value) || 0) * 100)}%`
const cardImage = (imageB64) => imageB64 ? `data:image/jpeg;base64,${imageB64}` : ''

onBeforeUnmount(() => {
  stopCamera()
  revokePreview()
  revokeCapturedImage()
})
</script>

<template>
  <div class="grappling-container">
    <div class="header-row">
      <h1>格斗技战术评估 / COMBAT AI</h1>
      <div class="status-indicator">
        <span class="label">SKELETON_PIPELINE</span>
        <span class="val">ACTIVE</span>
      </div>
    </div>

    <div class="grid-layout">
      <div class="panel left-capture">
        <div class="panel-header">实战画面输入 / INPUT</div>
        <div class="upload-area" @click="fileInput?.click()">
          <div v-if="!previewUrl && !capturedImage && !cameraActive" class="placeholder">
            <div class="badge">SENSING</div>
            <p>上传图片或视频，输出中文复盘卡片与动作总表</p>
          </div>
          <img v-if="capturedImage" :src="capturedImage" alt="识别画面" class="preview-img">
          <img v-else-if="previewUrl && !isVideo" :src="previewUrl" class="preview-img">
          <video v-else-if="previewUrl && isVideo" :src="previewUrl" class="preview-video" autoplay loop muted playsinline></video>
          <video v-if="cameraActive && sourceSettings.sourceType === 'camera'" ref="videoElement" autoplay playsinline class="preview-video"></video>
          <canvas ref="canvasElement" style="display: none;"></canvas>
          <input type="file" ref="fileInput" @change="onFileChange" hidden accept="image/*,video/*">
        </div>

        <div class="camera-btns" v-if="!selectedFile">
          <div class="mode-tip">当前视频源：{{ sourceSettings.sourceType === 'camera' ? '本地摄像头' : 'RTSP 视频流' }}</div>
          <button v-if="!cameraActive" class="btn accent-btn" @click.stop="startCamera">
            {{ sourceSettings.sourceType === 'camera' ? '开启摄像头' : '连接 RTSP' }}
          </button>
          <button v-else class="btn accent-btn" @click.stop="stopCamera">
            {{ sourceSettings.sourceType === 'camera' ? '关闭摄像头' : '停止 RTSP' }}
          </button>
        </div>

        <div class="mode-selector-panel">
          <div class="label">分析模式</div>
          <div class="btn-group">
            <button :class="{ active: mode === 'COMBAT_FIGHT' }" @click="mode = 'COMBAT_FIGHT'">动作识别</button>
            <button :class="{ active: mode === 'COMBAT_SCORING' }" @click="mode = 'COMBAT_SCORING'">全量分析</button>
          </div>
        </div>

        <div class="controls">
          <button class="btn accent-btn" @click="triggerAnalysis" :disabled="!previewUrl || isAnalyzing">
            <span v-if="!isAnalyzing">执行结构化评估</span>
            <span v-else>神经网络推理中...</span>
          </button>
        </div>
      </div>

      <div class="panel right-analytics scrollable">
        <div class="panel-header">实战复盘面板 / REVIEW CARDS</div>

        <template v-if="combat">
          <div class="summary-strip">
            <div class="summary-tile">
              <span>复盘卡片</span>
              <strong>{{ reviewCards.length }}</strong>
            </div>
            <div class="summary-tile">
              <span>动作次数</span>
              <strong>{{ actionCount }}</strong>
            </div>
            <div class="summary-tile">
              <span>有效打击</span>
              <strong>{{ highImpactCards }}</strong>
            </div>
            <div class="summary-tile">
              <span>命中事件</span>
              <strong>{{ hitCount }}</strong>
            </div>
            <div class="summary-tile">
              <span>稳定性</span>
              <strong>{{ (combat.stability || 0).toFixed(2) }}</strong>
            </div>
            <div class="summary-tile">
              <span>延迟</span>
              <strong>{{ meta?.latency_ms?.toFixed?.(1) || 0 }} ms</strong>
            </div>
          </div>

          <div class="subtle-info">人数 {{ meta?.persons || 0 }} / 设备 {{ meta?.device || '-' }} / 体力 {{ combat.fatigue?.level || '-' }}</div>

          <div class="block">
            <div class="block-title-row">
              <h3>本次识别总览</h3>
              <span class="block-tag">按时间顺序输出</span>
            </div>

            <div class="overview-panel">
              <div class="overview-lead">{{ overallSummary.overviewText }}</div>
              <div class="overview-grid">
                <div class="overview-box">
                  <span>主要动作</span>
                  <strong>{{ overallSummary.topAction }}</strong>
                </div>
                <div class="overview-box">
                  <span>主要结果</span>
                  <strong>{{ overallSummary.topDamage }}</strong>
                </div>
                <div class="overview-box">
                  <span>主要原因</span>
                  <strong>{{ overallSummary.topReason }}</strong>
                </div>
                <div class="overview-box">
                  <span>体力 / 稳定性</span>
                  <strong>{{ overallSummary.fatigueLevel }} / {{ overallSummary.stability.toFixed(2) }}</strong>
                </div>
              </div>
              <div class="overview-notes">
                <p>{{ overallSummary.rhythmText }}</p>
                <p>{{ overallSummary.riskText }}</p>
              </div>
            </div>

            <div v-if="reviewCards.length" class="review-card-list">
              <article v-for="card in reviewCards" :key="card.card_id" class="review-card">
                <div class="card-media">
                  <img v-if="card.image_b64" :src="cardImage(card.image_b64)" :alt="card.action_zh" class="review-shot">
                  <div v-else class="shot-placeholder">暂无截图</div>
                  <div class="time-chip">{{ card.timestamp }}</div>
                </div>

                <div class="card-content">
                  <div class="card-head">
                    <div>
                      <div class="card-title">{{ card.action_zh }}</div>
                      <div class="card-subtitle">{{ card.summary_zh }}</div>
                    </div>
                    <div class="confidence-pill">{{ confidenceText(card.confidence) }}</div>
                  </div>

                  <div class="fact-grid">
                    <div class="fact-box">
                      <span>造成伤害</span>
                      <strong>{{ card.damage_zh }}</strong>
                    </div>
                    <div class="fact-box">
                      <span>未躲闪原因</span>
                      <strong>{{ card.evade_failure_reason_zh }}</strong>
                    </div>
                    <div class="fact-box">
                      <span>攻击对象</span>
                      <strong>{{ card.target_zh }}</strong>
                    </div>
                    <div class="fact-box">
                      <span>对抗编号</span>
                      <strong>A{{ card.attacker_id ?? '-' }} / B{{ card.defender_id ?? '-' }}</strong>
                    </div>
                  </div>

                  <div class="metrics-panel">
                    <div v-for="metric in metricEntries(card.metrics)" :key="card.card_id + metric.key" class="metric-row">
                      <span>{{ metric.label }}</span>
                      <div class="metric-bar">
                        <div class="metric-fill" :style="{ width: metricWidth(metric.value) }"></div>
                      </div>
                      <b>{{ metric.value.toFixed(2) }}</b>
                    </div>
                  </div>
                </div>
              </article>
            </div>
            <div v-else class="empty-inline">当前样本未形成可复盘的格斗卡片。</div>
          </div>

          <div class="block">
            <div class="block-title-row">
              <h3>系统支持动作总表</h3>
              <span class="block-tag">固定中文动作库</span>
            </div>

            <div class="support-grid" v-if="supportedActions.length">
              <article v-for="item in supportedActions" :key="item.action_code" class="support-card">
                <div class="support-title">{{ item.action_zh }}</div>
                <div class="support-code">{{ item.action_code }}</div>
                <p>{{ item.description_zh }}</p>
                <div class="support-line"><span>典型效果</span><strong>{{ item.typical_damage_zh }}</strong></div>
                <div class="reason-tags">
                  <span v-for="reason in item.common_evade_failure_reasons_zh" :key="item.action_code + reason">{{ reason }}</span>
                </div>
              </article>
            </div>
            <div v-else class="empty-inline">当前未返回动作总表。</div>
          </div>
        </template>

        <div v-else-if="feedback" class="text-content">{{ feedback }}</div>

        <div v-else-if="isAnalyzing" class="dna-spinner">
          <div class="dot"></div><div class="dot"></div><div class="dot"></div>
        </div>

        <div v-else class="empty-notif">等待输入视频或图像进行格斗分析...</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.grappling-container { animation: fadeIn 0.4s ease; height: 100%; display: flex; flex-direction: column; }
.header-row { display: flex; justify-content: space-between; align-items: flex-end; margin-bottom: 30px; }
.status-indicator { font-family: monospace; font-size: 10px; background: #000; border: 1px solid var(--border); padding: 5px 12px; }
.status-indicator .label { color: #5c7694; margin-right: 10px; }
.status-indicator .val { color: var(--primary); font-weight: bold; }
.grid-layout { display: grid; grid-template-columns: minmax(380px, 44%) minmax(0, 1fr); gap: 24px; align-items: start; flex: 1; min-height: 0; }
.panel-header { border-bottom: 1px solid var(--border); padding-bottom: 15px; margin-bottom: 25px; font-size: 11px; text-transform: uppercase; color: var(--primary); letter-spacing: 2px; }
.upload-area { width: 100%; aspect-ratio: 16/10; background: rgba(0,0,0,0.5); border: 1px solid #1a3a5f; margin-bottom: 20px; cursor: pointer; display: flex; justify-content: center; align-items: center; position: relative; overflow: hidden; }
.upload-area::after { content: ''; position: absolute; inset: 10px; border: 1px solid rgba(0,229,255,0.05); pointer-events: none; }
.mode-selector-panel { margin-bottom: 25px; }
.mode-selector-panel .label { font-size: 11px; color: #5c7694; margin-bottom: 10px; font-weight: bold; }
.mode-tip { margin-top: 10px; font-size: 12px; color: #7d92ab; }
.btn-group { display: flex; gap: 10px; }
.btn-group button { flex: 1; background: #0a111c; border: 1px solid #1a3a5f; color: #a1b8d2; padding: 8px; font-size: 12px; cursor: pointer; transition: 0.3s; }
.btn-group button.active { border-color: var(--primary); color: var(--primary); background: rgba(0,229,255,0.1); }
.placeholder { text-align: center; }
.badge { background: var(--primary); color: #000; display: inline-block; padding: 2px 8px; font-size: 10px; font-weight: 800; margin-bottom: 15px; }
.placeholder p { font-size: 13px; color: #3d5875; }
.preview-img, .preview-video { width: 100%; height: 100%; object-fit: contain; }
.controls .accent-btn { width: 100%; border-radius: 2px; }
.right-analytics { height: 100%; min-height: 420px; background: radial-gradient(circle at top right, rgba(32, 215, 255, 0.08), transparent 24%), linear-gradient(180deg, rgba(8, 18, 29, 0.98), rgba(7, 13, 24, 0.95)); }
.scrollable { overflow-y: auto; }
.empty-notif { height: 100%; display: flex; align-items: center; justify-content: center; color: #2d333b; font-size: 14px; font-style: italic; text-align: center; padding: 40px; }
.summary-strip { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 10px; margin-bottom: 12px; }
.summary-tile { border: 1px solid #1a3a5f; background: rgba(9, 17, 29, 0.92); padding: 10px; border-radius: 8px; }
.summary-tile span { display: block; color: #7895b5; font-size: 11px; margin-bottom: 6px; }
.summary-tile strong { color: #f3fbff; font-size: 17px; }
.subtle-info { font-size: 12px; color: #89a4c4; margin-bottom: 8px; }
.block { margin-top: 12px; border-top: 1px dashed #1a3a5f; padding-top: 14px; }
.block-title-row { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 10px; }
.block h3 { margin: 0; font-size: 14px; color: var(--primary); }
.block-tag { border: 1px solid rgba(0, 229, 255, 0.22); color: #87bfd8; font-size: 11px; border-radius: 999px; padding: 3px 8px; }
.overview-panel { border: 1px solid rgba(32, 215, 255, 0.18); background: linear-gradient(180deg, rgba(10, 21, 34, 0.96), rgba(6, 13, 23, 0.92)); border-radius: 12px; padding: 16px; margin-bottom: 14px; box-shadow: 0 16px 32px rgba(0, 0, 0, 0.22); }
.overview-lead { color: #eef8ff; font-size: 14px; line-height: 1.8; margin-bottom: 14px; }
.overview-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin-bottom: 12px; }
.overview-box { border: 1px solid #1b3a59; background: rgba(5, 12, 22, 0.8); border-radius: 10px; padding: 12px; }
.overview-box span { display: block; color: #7290b2; font-size: 11px; margin-bottom: 6px; }
.overview-box strong { color: #f4fbff; font-size: 14px; line-height: 1.6; }
.overview-notes { display: grid; gap: 8px; }
.overview-notes p { margin: 0; color: #9ec0dd; font-size: 13px; line-height: 1.7; }
.review-card-list { display: flex; flex-direction: column; gap: 14px; }
.review-card { display: grid; grid-template-columns: minmax(180px, 220px) minmax(0, 1fr); gap: 14px; border: 1px solid rgba(32, 215, 255, 0.18); background: rgba(9, 17, 28, 0.95); border-radius: 12px; overflow: hidden; box-shadow: 0 18px 40px rgba(0, 0, 0, 0.28); }
.card-media { position: relative; min-height: 188px; background: linear-gradient(180deg, rgba(8, 17, 28, 0.7), rgba(3, 7, 12, 0.95)); display: flex; align-items: center; justify-content: center; }
.review-shot { width: 100%; height: 100%; object-fit: cover; }
.shot-placeholder { color: #57718c; font-size: 13px; }
.time-chip { position: absolute; top: 10px; left: 10px; background: rgba(5, 12, 22, 0.88); color: #7fe9ff; border: 1px solid rgba(0, 229, 255, 0.22); border-radius: 999px; padding: 4px 8px; font-size: 11px; }
.card-content { padding: 14px 16px 16px; }
.card-head { display: flex; justify-content: space-between; gap: 12px; margin-bottom: 12px; }
.card-title { font-size: 18px; color: #f1f9ff; font-weight: 800; }
.card-subtitle { margin-top: 4px; font-size: 13px; line-height: 1.6; color: #9ec0dd; }
.confidence-pill { white-space: nowrap; color: #8ff3d9; border: 1px solid rgba(143, 243, 217, 0.32); padding: 5px 10px; border-radius: 999px; font-size: 12px; height: fit-content; }
.fact-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin-bottom: 12px; }
.fact-box { border: 1px solid #1b3a59; background: rgba(5, 12, 22, 0.85); border-radius: 8px; padding: 10px; }
.fact-box span { display: block; color: #7290b2; font-size: 11px; margin-bottom: 4px; }
.fact-box strong { color: #eef8ff; font-size: 14px; line-height: 1.5; }
.metrics-panel { display: grid; gap: 8px; }
.metric-row { display: grid; grid-template-columns: 72px minmax(0, 1fr) 40px; gap: 10px; align-items: center; font-size: 12px; color: #90a8c2; }
.metric-bar { height: 8px; background: rgba(18, 37, 58, 0.9); border-radius: 999px; overflow: hidden; }
.metric-fill { height: 100%; background: linear-gradient(90deg, #2be3ff, #46ffa2); border-radius: inherit; }
.metric-row b { color: #dff8ff; font-size: 12px; text-align: right; }
.support-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.support-card { border: 1px solid #1b3a59; background: rgba(9, 17, 28, 0.92); border-radius: 10px; padding: 14px; }
.support-title { color: #eef8ff; font-size: 16px; font-weight: 800; }
.support-code { color: #6ca6bf; font-size: 11px; margin-top: 3px; text-transform: uppercase; letter-spacing: 1px; }
.support-card p { color: #98b8d5; font-size: 13px; line-height: 1.7; margin: 10px 0 12px; }
.support-line { display: grid; gap: 4px; margin-bottom: 10px; }
.support-line span { color: #7392b4; font-size: 11px; }
.support-line strong { color: #eff8ff; font-size: 13px; line-height: 1.6; }
.reason-tags { display: flex; flex-wrap: wrap; gap: 8px; }
.reason-tags span { border: 1px solid rgba(0, 229, 255, 0.2); background: rgba(0, 229, 255, 0.08); color: #9ae4f3; border-radius: 999px; padding: 4px 8px; font-size: 11px; }
.empty-inline { color: #6d86a3; font-size: 12px; padding: 6px 0; }
.text-content { font-size: 15px; color: #d1dcf0; line-height: 1.8; white-space: pre-wrap; font-family: 'PingFang SC', sans-serif; }
.dna-spinner { display: flex; justify-content: center; align-items: center; height: 300px; gap: 10px; }
.dna-spinner .dot { width: 12px; height: 12px; background: var(--primary); border-radius: 50%; animation: orbit 1s infinite alternate; }
.dna-spinner .dot:nth-child(2) { animation-delay: 0.2s; }
.dna-spinner .dot:nth-child(3) { animation-delay: 0.4s; }
@keyframes orbit { from { transform: scale(0.5) translateY(-20px); opacity: 0.2; } to { transform: scale(1.2) translateY(20px); opacity: 1; } }
@media (max-width: 1400px) {
  .summary-strip { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}
@media (max-width: 1080px) {
  .grid-layout { grid-template-columns: 1fr; }
  .review-card { grid-template-columns: 1fr; }
  .support-grid, .fact-grid, .summary-strip, .overview-grid { grid-template-columns: 1fr; }
  .card-media { min-height: 220px; }
}
</style>
