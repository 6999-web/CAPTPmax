<script setup>
import { ref } from 'vue'

const emit = defineEmits(['login-success'])

const username = ref('admin')
const password = ref('')
const isAuthLoading = ref(false)
const errorMsg = ref('')

const handleLogin = () => {
  isAuthLoading.value = true
  errorMsg.value = ''

  window.setTimeout(() => {
    if (username.value === 'admin' && password.value === '123456') {
      emit('login-success')
    } else {
      errorMsg.value = '认证失败：账号或访问口令错误'
    }
    isAuthLoading.value = false
  }, 1000)
}
</script>

<template>
  <div class="login-wrapper">
    <div class="glitch-overlay"></div>
    <div class="login-card">
      <div class="shield-logo">
        <img src="/school_badge.jpg" class="school-logo-img" alt="校徽">
        <h1>CAPTP.OS</h1>
        <p>智能警务实战综合训练平台</p>
      </div>

      <div class="form-body">
        <div class="input-group">
          <label>终端工号</label>
          <input v-model="username" type="text" placeholder="POLICE_ID_001" @keyup.enter="handleLogin">
        </div>
        <div class="input-group">
          <label>访问口令</label>
          <input v-model="password" type="password" placeholder="请输入访问口令" @keyup.enter="handleLogin">
        </div>
        <button class="login-btn" @click="handleLogin" :disabled="isAuthLoading">
          <span v-if="!isAuthLoading">进入终端系统</span>
          <span v-else class="loader"></span>
        </button>
        <p v-if="errorMsg" class="error-msg">{{ errorMsg }}</p>
      </div>

      <div class="footer-info">
        <span>SECURITY LEVEL: 4A</span>
        <span>NODE: GXP-AI-HQ</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.login-wrapper {
  position: fixed;
  inset: 0;
  background: radial-gradient(circle at 50% 50%, #1a2a47 0%, #0a0e1a 100%);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 9999;
  overflow: hidden;
}

.glitch-overlay {
  position: absolute;
  width: 100%;
  height: 100%;
  background-image:
    linear-gradient(rgba(18, 16, 16, 0) 50%, rgba(0, 0, 0, 0.25) 50%),
    linear-gradient(90deg, rgba(255, 0, 0, 0.06), rgba(0, 255, 0, 0.02), rgba(0, 0, 255, 0.06));
  background-size: 100% 2px, 3px 100%;
  pointer-events: none;
}

.login-card {
  width: 400px;
  background: rgba(13, 25, 48, 0.85);
  backdrop-filter: blur(10px);
  border: 1px solid rgba(0, 255, 255, 0.3);
  box-shadow: 0 0 30px rgba(0, 162, 255, 0.2);
  padding: 40px;
  border-radius: 4px;
  position: relative;
}

.shield-logo {
  text-align: center;
  margin-bottom: 40px;
}

.school-logo-img {
  width: 90px;
  height: 90px;
  border-radius: 50%;
  border: 2px solid rgba(0, 229, 255, 0.4);
  box-shadow: 0 0 20px rgba(0, 229, 255, 0.3);
  margin-bottom: 20px;
  object-fit: cover;
}

.shield-logo h1 {
  color: #00e5ff;
  letter-spacing: 4px;
  font-weight: 900;
  margin: 0;
  text-shadow: 0 0 10px rgba(0, 229, 255, 0.5);
}

.shield-logo p {
  color: #a1b8d2;
  font-size: 14px;
  margin-top: 5px;
}

.input-group {
  margin-bottom: 25px;
}

.input-group label {
  display: block;
  color: #00e5ff;
  font-size: 11px;
  text-transform: uppercase;
  margin-bottom: 8px;
  letter-spacing: 1px;
}

.input-group input {
  width: 100%;
  background: rgba(0, 0, 0, 0.3);
  border: 1px solid #1a3a5f;
  padding: 12px;
  color: #fff;
  font-size: 16px;
  outline: none;
  transition: all 0.3s;
  box-sizing: border-box;
}

.input-group input:focus {
  border-color: #00e5ff;
  box-shadow: 0 0 10px rgba(0, 229, 255, 0.2);
}

.login-btn {
  width: 100%;
  background: #0066cc;
  color: white;
  border: none;
  padding: 15px;
  font-weight: bold;
  letter-spacing: 2px;
  cursor: pointer;
  transition: 0.3s;
  margin-top: 10px;
  border: 1px solid transparent;
}

.login-btn:hover {
  background: #0088ff;
  box-shadow: 0 0 20px rgba(0, 136, 255, 0.5);
}

.error-msg {
  color: #ff4d4d;
  font-size: 12px;
  text-align: center;
  margin-top: 15px;
}

.footer-info {
  margin-top: 40px;
  display: flex;
  justify-content: space-between;
  color: #3d5875;
  font-size: 10px;
  font-family: monospace;
}

.loader {
  width: 20px;
  height: 20px;
  border: 2px solid #fff;
  border-bottom-color: transparent;
  border-radius: 50%;
  display: inline-block;
  animation: rotation 1s linear infinite;
}

@keyframes rotation {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}
</style>
