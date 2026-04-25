<script setup>
import { onMounted, ref } from 'vue'

import { settingsStore } from '../stores/settings'

const cameraDevices = ref([])
const isRefreshing = ref(false)
const cameraError = ref('')
const savedTip = ref('')

const settings = settingsStore.settings

const loadDevices = async (requestPermission = false) => {
  if (!navigator?.mediaDevices?.enumerateDevices) {
    cameraError.value = '当前浏览器不支持媒体设备枚举。'
    return
  }

  isRefreshing.value = true
  cameraError.value = ''

  try {
    if (requestPermission && navigator?.mediaDevices?.getUserMedia) {
      const tempStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false })
      tempStream.getTracks().forEach((track) => track.stop())
    }

    const devices = await navigator.mediaDevices.enumerateDevices()
    cameraDevices.value = devices
      .filter((device) => device.kind === 'videoinput')
      .map((device, index) => ({
        id: device.deviceId,
        label: device.label || `摄像头 ${index + 1}`
      }))

    if (!cameraDevices.value.length) {
      cameraError.value = '未检测到可用摄像头设备。'
      settingsStore.setCameraDeviceId('')
      return
    }

    const matched = cameraDevices.value.some((item) => item.id === settings.cameraDeviceId)
    if (!matched) {
      settingsStore.setCameraDeviceId(cameraDevices.value[0].id)
    }
  } catch (error) {
    cameraError.value = `获取摄像头设备失败：${error.message}`
  } finally {
    isRefreshing.value = false
  }
}

const saveSettings = () => {
  settingsStore.setSourceType(settings.sourceType)
  settingsStore.setCameraDeviceId(settings.cameraDeviceId)
  settingsStore.setRtspUrl(settings.rtspUrl.trim())
  savedTip.value = '设置已保存，射击评估与格斗评估页面会同步使用。'
  window.setTimeout(() => {
    savedTip.value = ''
  }, 2000)
}

onMounted(() => {
  loadDevices(false)
})
</script>

<template>
  <div class="settings-page">
    <div class="page-head row">
      <div>
        <h1>系统设置中心 / SETTINGS HUB</h1>
        <p>统一配置视频源设备与 RTSP 地址，供射击评估和格斗评估模块复用。</p>
      </div>
    </div>

    <div class="settings-grid">
      <section class="panel">
        <div class="panel-title">视频源模式 / SOURCE MODE</div>
        <div class="source-grid">
          <label :class="['source-item', { active: settings.sourceType === 'camera' }]">
            <input
              type="radio"
              name="sourceType"
              value="camera"
              :checked="settings.sourceType === 'camera'"
              @change="settingsStore.setSourceType('camera')"
            >
            本地摄像头
          </label>
          <label :class="['source-item', { active: settings.sourceType === 'rtsp' }]">
            <input
              type="radio"
              name="sourceType"
              value="rtsp"
              :checked="settings.sourceType === 'rtsp'"
              @change="settingsStore.setSourceType('rtsp')"
            >
            RTSP 视频流
          </label>
        </div>
      </section>

      <section class="panel">
        <div class="panel-title">摄像头设备 / CAMERA DEVICE</div>
        <div class="device-row">
          <select
            class="select"
            :value="settings.cameraDeviceId"
            :disabled="!cameraDevices.length"
            @change="settingsStore.setCameraDeviceId($event.target.value)"
          >
            <option value="">自动选择可用设备</option>
            <option v-for="item in cameraDevices" :key="item.id" :value="item.id">{{ item.label }}</option>
          </select>
          <button class="btn action-btn" @click="loadDevices(true)" :disabled="isRefreshing">
            {{ isRefreshing ? '刷新中...' : '刷新设备' }}
          </button>
        </div>
        <p v-if="cameraError" class="warn">{{ cameraError }}</p>
      </section>

      <section class="panel">
        <div class="panel-title">RTSP 地址 / RTSP STREAM</div>
        <input
          class="input"
          type="text"
          placeholder="例如 rtsp://user:password@127.0.0.1:554/stream1"
          :value="settings.rtspUrl"
          @input="settingsStore.setRtspUrl($event.target.value)"
        >
        <p class="tip">当视频源模式为 RTSP 时，射击与格斗模块会通过后端抓帧并实时分析该视频流。</p>
      </section>

      <section class="panel save-panel">
        <button class="btn action-btn" @click="saveSettings">保存设置</button>
        <p v-if="savedTip" class="ok">{{ savedTip }}</p>
      </section>
    </div>
  </div>
</template>

<style scoped>
.settings-page {
  animation: fadeIn 0.35s ease;
}

.settings-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(300px, 1fr));
  gap: 18px;
}

.panel-title {
  color: var(--primary);
  font-size: 12px;
  margin-bottom: 12px;
  letter-spacing: 1px;
  text-transform: uppercase;
  font-weight: 700;
}

.source-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(140px, 1fr));
  gap: 12px;
}

.source-item {
  background: rgba(10, 17, 28, 0.64);
  border: 1px solid #1a3a5f;
  border-radius: 8px;
  padding: 14px;
  color: #a1b8d2;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
}

.source-item.active {
  border-color: var(--primary);
  color: var(--primary);
  background: rgba(0, 229, 255, 0.1);
}

.select,
.input {
  width: 100%;
  background: rgba(9, 14, 24, 0.8);
  border: 1px solid #1a3a5f;
  border-radius: 8px;
  color: #d4e8ff;
  padding: 12px;
  outline: none;
}

.device-row {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 10px;
}

.action-btn {
  padding: 10px 16px;
}

.warn {
  color: #ff9a9a;
  font-size: 13px;
  margin-top: 10px;
}

.tip {
  font-size: 13px;
  margin-top: 10px;
  color: #8aa5c2;
}

.save-panel {
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.ok {
  color: #45ffb4;
  margin-top: 10px;
}

@media (max-width: 900px) {
  .settings-grid {
    grid-template-columns: 1fr;
  }

  .source-grid {
    grid-template-columns: 1fr;
  }
}
</style>
