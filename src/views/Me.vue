<template>
  <div class="panel-view" style="padding:16px;">

    <div class="me-header">
      <h2>个人中心</h2>
    </div>

    <div v-if="!user">
      <div class="auth-tabs">
        <button :class="{active: mode==='login'}" @click="mode='login'">登录</button>
        <button :class="{active: mode==='register'}" @click="mode='register'">注册</button>
      </div>

      <div v-if="mode==='login'" class="auth-form">
        <label class="field">用户名： <input v-model="loginForm.username" placeholder="用户名" /></label>
        <label class="field">密码： <input v-model="loginForm.password" type="password" placeholder="密码" /></label>
        <div class="actions">
          <button class="log-btn" @click="login" :disabled="isLoading">登录</button>
        </div>
        <div v-if="authError" class="error">{{ authError }}</div>
      </div>

      <div v-else class="auth-form">
        <label class="field">用户名： <input v-model="regForm.username" placeholder="用户名" /></label>
        <label class="field">密码： <input v-model="regForm.password" type="password" placeholder="密码" /></label>
        <label class="field">显示名： <input v-model="regForm.displayName" placeholder="显示名 (可选)" /></label>
        <div class="actions">
          <button class="log-btn" @click="register" :disabled="isLoading">注册</button>
        </div>
        <div v-if="authError" class="error">{{ authError }}</div>
      </div>
    </div>

    <div v-else>
      <div class="me-user">
        <div>已登录: <strong>{{ user.username }}</strong><span v-if="user.displayName">（{{ user.displayName }}）</span></div>
        <div style="margin-top:8px;"><button class="log-btn" @click="logout">退出</button></div>
      </div>

      <div class="card">
        <h3>添加设备</h3>
        <label class="field">设备 ID： <input v-model="deviceForm.deviceId" placeholder="例如 dev-001" /></label>
        <label class="field">设备名称： <input v-model="deviceForm.name" placeholder="可选" /></label>
        <label class="field">序列号： <input v-model="deviceForm.serial" placeholder="可选" /></label>
        <div class="actions">
          <button class="log-btn" @click="addDevice" :disabled="isLoading">添加设备</button>
        </div>
        <div v-if="deviceMsg" class="info">{{ deviceMsg }}</div>
      </div>

      <div class="card" style="margin-top:12px;">
        <h3>我的设备</h3>
        <div v-if="devices.length === 0" class="log-empty">尚无设备。</div>
        <ul v-else class="device-list">
          <li v-for="d in devices" :key="d.deviceId" class="device-item">
            <div><strong>{{ d.deviceId }}</strong> <span class="device-name">{{ d.name || '—' }}</span></div>
            <div class="device-meta">序列号: {{ d.serial || '—' }} ；创建: {{ formatTs(d.createdAt) }}</div>
          </li>
        </ul>
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
onMounted(() => { document.title = '骑行头盔用户站-Me' })

const backendBase = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8787'

const user = ref(JSON.parse(localStorage.getItem('ride_user') || 'null'))
const mode = ref('login')
const loginForm = ref({ username: '', password: '' })
const regForm = ref({ username: '', password: '', displayName: '' })
const authError = ref('')
const isLoading = ref(false)

const deviceForm = ref({ deviceId: '', name: '', serial: '' })
const deviceMsg = ref('')
const devices = ref([])

function saveUserToStorage(u) {
  if (u) localStorage.setItem('ride_user', JSON.stringify(u))
  else localStorage.removeItem('ride_user')
}

async function register() {
  authError.value = ''
  if (!regForm.value.username || !regForm.value.password) { authError.value = '用户名与密码为必填'; return }
  isLoading.value = true
  try {
    const res = await fetch(`${backendBase.replace(/\/$/, '')}/api/test/register`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username: regForm.value.username, password: regForm.value.password, displayName: regForm.value.displayName }) })
    const j = await res.json()
    if (!res.ok && !j) { authError.value = '注册失败'; return }
    const u = { id: j.id || j.row?.id, username: j.username || regForm.value.username, displayName: j.displayName || j.row?.display_name }
    user.value = u
    saveUserToStorage(u)
    deviceMsg.value = ''
    await refreshDevices()
  } catch (e) {
    console.error('register error', e)
    authError.value = e?.message || String(e)
  } finally { isLoading.value = false }
}

async function login() {
  authError.value = ''
  if (!loginForm.value.username || !loginForm.value.password) { authError.value = '用户名与密码为必填'; return }
  isLoading.value = true
  try {
    const res = await fetch(`${backendBase.replace(/\/$/, '')}/api/test/login`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username: loginForm.value.username, password: loginForm.value.password }) })
    if (res.status === 401) { authError.value = '用户名或密码错误'; return }
    const j = await res.json()
    user.value = { id: j.id, username: j.username, displayName: j.displayName }
    saveUserToStorage(user.value)
    await refreshDevices()
  } catch (e) {
    console.error('login error', e)
    authError.value = e?.message || String(e)
  } finally { isLoading.value = false }
}

function logout() { user.value = null; saveUserToStorage(null); devices.value = []; deviceForm.value = { deviceId: '', name: '', serial: '' }; deviceMsg.value = '' }

function formatTs(ts) {
  if (!ts) return '—'
  const n = Number(ts)
  if (!Number.isFinite(n)) return String(ts)
  const ms = n < 1e12 ? Math.round(n * 1000) : Math.round(n)
  return new Date(ms).toLocaleString()
}

async function refreshDevices() {
  if (!user.value) { devices.value = []; return }
  try {
    const res = await fetch(`${backendBase.replace(/\/$/, '')}/api/devices`)
    if (!res.ok) { console.warn('failed to list devices', res.status); devices.value = []; return }
    const j = await res.json()
    const all = Array.isArray(j.devices) ? j.devices : []
    devices.value = all.filter(d => {
      const uid = d.userId !== undefined ? d.userId : (d.user_id !== undefined ? d.user_id : null)
      return uid != null && String(uid) === String(user.value.id)
    })
  } catch (e) {
    console.error('refreshDevices error', e)
    devices.value = []
  }
}

async function addDevice() {
  deviceMsg.value = ''
  if (!user.value) { deviceMsg.value = '请先登录'; return }
  if (!deviceForm.value.deviceId) { deviceMsg.value = '设备 ID 为必填'; return }
  isLoading.value = true
  try {
    const body = { deviceId: deviceForm.value.deviceId, name: deviceForm.value.name || null, serial: deviceForm.value.serial || null, userId: user.value.id }
    const res = await fetch(`${backendBase.replace(/\/$/, '')}/api/devices`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
    const j = await res.json()
    if (!res.ok) { deviceMsg.value = '添加设备失败: ' + (j?.error || res.status); return }
    if (j && j.existing) {
      deviceMsg.value = '设备已存在（已关联或重复）。'
    } else {
      deviceMsg.value = '设备已添加。'
    }
    deviceForm.value.deviceId = ''
    deviceForm.value.name = ''
    deviceForm.value.serial = ''
    await refreshDevices()
  } catch (e) {
    console.error('addDevice error', e)
    deviceMsg.value = e?.message || String(e)
  } finally { isLoading.value = false }
}

if (user.value) refreshDevices()
</script>

<style scoped>
.panel-view {
  max-width: 900px;
  margin: 0 auto;
  color: #222;
}
.me-header h2 { margin: 0 0 12px 0; }
.auth-tabs { display:flex; gap:8px; margin-bottom:12px }
.auth-tabs button { padding:8px 12px; border-radius:8px; border:1px solid #e3eaf2; background:#fff }
.auth-tabs button.active { background:#2196f3; color:#fff; border-color:#1976d2 }
.auth-form .field { display:block; margin:8px 0 }
.field input { padding:8px 10px; border-radius:6px; border:1px solid #dfeefb; width:100% }
.actions { margin-top:8px }
.log-btn { background: #2196f3; color: #fff; border: none; border-radius: 8px; padding: 8px 18px; font-size: 15px; font-weight: 500; cursor: pointer; }
.card { background:#fff; border-radius:10px; padding:12px; border:1px solid #eef6ff }
.log-empty { color: #888; background: #f7fafd; border-radius: 8px; padding: 12px; text-align: center }
.device-list { list-style:none; padding:0; margin:0 }
.device-item { padding:8px 0; border-bottom:1px solid #f0f6fb }
.device-meta { color:#666; font-size:13px }
.error { color:#c00; margin-top:8px }
.info { color:#1976d2; margin-top:8px }
</style>
