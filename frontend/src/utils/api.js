const resolveDefaultBaseUrl = () => {
  if (typeof window === 'undefined') {
    return 'http://127.0.0.1:6063'
  }

  const protocol = window.location.protocol === 'https:' ? 'https:' : 'http:'
  const hostname = window.location.hostname || '127.0.0.1'
  return `${protocol}//${hostname}:6063`
}

const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL || resolveDefaultBaseUrl()

export const API_BASE_URL = configuredBaseUrl.replace(/\/$/, '')
export const WS_BASE_URL = API_BASE_URL.replace(/^http/i, 'ws')

export const buildApiUrl = (path) => `${API_BASE_URL}${path}`
export const buildWsUrl = (path) => `${WS_BASE_URL}${path}`

export const readApiPayload = async (response) => {
  const rawText = await response.text()
  if (!rawText) {
    return {}
  }

  try {
    return JSON.parse(rawText)
  } catch {
    return { detail: rawText }
  }
}

const mapLegacyModeToV2 = (legacyMode) => {
  if (legacyMode === 'SHOOTING_POSTURE' || legacyMode === 'SHOOTING_WEAPON') return 'shooting_posture'
  if (legacyMode === 'SHOOTING_TARGET' || legacyMode === 'SHOOTING_FLOW') return 'shooting_flow'
  if (legacyMode === 'COMBAT_FIGHT') return 'combat_action'
  return 'combat_full'
}

export const analyzeWithV2 = async ({ file, legacyMode }) => {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('mode', mapLegacyModeToV2(legacyMode))

  const response = await fetch(buildApiUrl('/api/v2/analyze/file'), {
    method: 'POST',
    body: formData
  })

  const data = await readApiPayload(response)
  return { ok: response.ok, data }
}

export const analyzeLongVideoWithV2 = async ({ file, legacyMode }) => {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('mode', mapLegacyModeToV2(legacyMode))

  const response = await fetch(buildApiUrl('/api/v2/analyze/long-video'), {
    method: 'POST',
    body: formData
  })

  const data = await readApiPayload(response)
  return { ok: response.ok, data }
}

export const analyzeCombatPreviewWithV2 = async ({ files, legacyMode, durationSeconds = 0 }) => {
  const formData = new FormData()
  files.forEach((file) => formData.append('frames', file))
  formData.append('mode', mapLegacyModeToV2(legacyMode))
  formData.append('duration_seconds', String(durationSeconds))

  const response = await fetch(buildApiUrl('/api/v2/analyze/combat-preview'), {
    method: 'POST',
    body: formData
  })

  const data = await readApiPayload(response)
  return { ok: response.ok, data }
}

export const analyzeShootingPreviewWithV2 = async ({ files, legacyMode, durationSeconds = 0 }) => {
  const formData = new FormData()
  files.forEach((file) => formData.append('frames', file))
  formData.append('mode', mapLegacyModeToV2(legacyMode))
  formData.append('duration_seconds', String(durationSeconds))

  const response = await fetch(buildApiUrl('/api/v2/analyze/shooting-preview'), {
    method: 'POST',
    body: formData
  })

  const data = await readApiPayload(response)
  return { ok: response.ok, data }
}

export const analyzeCombatVideoFastWithV2 = async ({
  files,
  manifest,
  legacyMode,
  strategy = 'adaptive',
  durationSeconds = 0,
  clientExtractMs = 0
}) => {
  const formData = new FormData()
  files.forEach((file) => formData.append('frames', file))
  formData.append('manifest', JSON.stringify(manifest))
  formData.append('mode', mapLegacyModeToV2(legacyMode))
  formData.append('strategy', strategy)
  formData.append('duration_seconds', String(durationSeconds))
  formData.append('client_extract_ms', String(clientExtractMs))

  const response = await fetch(buildApiUrl('/api/v2/analyze/combat-video-fast'), {
    method: 'POST',
    body: formData
  })

  const data = await readApiPayload(response)
  return { ok: response.ok, data }
}

export const analyzeRtspFrameWithV2 = async ({ rtspUrl, legacyMode, frameIndex = 0, fps = 12 }) => {
  const response = await fetch(buildApiUrl('/api/v2/analyze/rtsp-frame'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      url: rtspUrl,
      mode: mapLegacyModeToV2(legacyMode),
      frame_index: frameIndex,
      fps
    })
  })

  const data = await readApiPayload(response)
  return { ok: response.ok, data }
}

export const analyzeWithV1Fallback = async ({ file, legacyMode }) => {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('mode', legacyMode)

  const response = await fetch(buildApiUrl('/api/analyze-vision'), {
    method: 'POST',
    body: formData
  })

  const data = await readApiPayload(response)
  return { ok: response.ok, data }
}
