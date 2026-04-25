<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'

import Login from './components/Login.vue'

const isLoggedIn = ref(false)
const currentTime = ref('')
const route = useRoute()
const router = useRouter()
let timer = null

const navItems = [
  { to: '/shooting', label: '射击评估' },
  { to: '/grappling', label: '格斗评估' },
  { to: '/tactical', label: '战术推演' },
  { to: '/settings', label: '系统设置' }
]

const pageTitle = computed(() => {
  const current = navItems.find((item) => item.to === route.path)
  return current?.label || 'CAPTP.OS'
})

const updateTime = () => {
  currentTime.value = new Date().toLocaleString('zh-CN', { hour12: false })
}

onMounted(() => {
  updateTime()
  timer = setInterval(updateTime, 1000)
})

onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
})

const handleLoginSuccess = () => {
  isLoggedIn.value = true
}

const logout = () => {
  isLoggedIn.value = false
  router.push('/')
}
</script>

<template>
  <div class="app-shell">
    <Login v-if="!isLoggedIn" @login-success="handleLoginSuccess" />

    <template v-else>
      <header class="top-bar">
        <div>
          <div class="brand">CAPTP.OS</div>
          <div class="subtitle">警务实战综合训练平台</div>
        </div>
        <div class="top-actions">
          <span class="clock">{{ currentTime }}</span>
          <button class="ghost-button" @click="logout">退出登录</button>
        </div>
      </header>

      <div class="layout">
        <aside class="sidebar">
          <div class="sidebar-title">功能导航</div>
          <nav class="nav-list">
            <RouterLink
              v-for="item in navItems"
              :key="item.to"
              :to="item.to"
              class="nav-link"
              :class="{ active: route.path === item.to }"
            >
              {{ item.label }}
            </RouterLink>
          </nav>
        </aside>

        <main class="content">
          <div class="content-header">
            <h1>{{ pageTitle }}</h1>
            <RouterLink to="/settings" class="settings-link">进入设置</RouterLink>
          </div>
          <RouterView />
        </main>
      </div>
    </template>
  </div>
</template>

<style scoped>
.app-shell {
  min-height: 100vh;
  background: var(--app-bg);
  color: var(--app-text);
}

.top-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 28px;
  border-bottom: 1px solid var(--app-border);
  background: rgba(8, 18, 36, 0.78);
  backdrop-filter: blur(12px);
  box-shadow: 0 18px 40px rgba(1, 8, 18, 0.28);
}

.brand {
  font-size: 24px;
  font-weight: 700;
  letter-spacing: 0.04em;
}

.subtitle {
  margin-top: 4px;
  color: var(--app-text-muted);
  font-size: 14px;
}

.top-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.clock {
  color: var(--app-text-muted);
  font-size: 14px;
}

.ghost-button,
.settings-link {
  border: 1px solid var(--button-blue-border);
  background: linear-gradient(135deg, var(--button-blue-start) 0%, var(--button-blue-end) 100%);
  color: #f8fbff;
  box-shadow: 0 12px 28px var(--button-blue-shadow);
  border-radius: 999px;
  padding: 10px 16px;
  font-size: 14px;
  text-decoration: none;
  cursor: pointer;
}

.layout {
  display: grid;
  grid-template-columns: 240px 1fr;
  min-height: calc(100vh - 89px);
}

.sidebar {
  padding: 24px 18px;
  border-right: 1px solid var(--app-border);
  background: linear-gradient(180deg, rgba(8, 18, 36, 0.92) 0%, rgba(10, 14, 26, 0.96) 100%);
}

.sidebar-title {
  font-size: 13px;
  color: var(--app-text-muted);
  margin-bottom: 12px;
}

.nav-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.nav-link {
  display: block;
  padding: 12px 14px;
  border-radius: 14px;
  color: var(--app-text);
  text-decoration: none;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid transparent;
}

.nav-link.active {
  background: rgba(0, 229, 255, 0.14);
  border-color: var(--app-border-strong);
  color: var(--primary);
}

.content {
  padding: 28px;
  background:
    radial-gradient(circle at top right, rgba(0, 229, 255, 0.07), transparent 24%),
    transparent;
}

.content-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  margin-bottom: 20px;
}

.content-header h1 {
  margin: 0;
  font-size: 28px;
  color: #f4f9ff;
}

@media (max-width: 900px) {
  .layout {
    grid-template-columns: 1fr;
  }

  .sidebar {
    border-right: 0;
    border-bottom: 1px solid rgba(17, 24, 39, 0.08);
  }

  .content-header {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
