// Canvas 性能补丁：为频繁读取像素的场景默认打开 willReadFrequently
;(function() {
	const origGetContext = HTMLCanvasElement.prototype.getContext
	HTMLCanvasElement.prototype.getContext = function(type, opts) {
		if (type === '2d') {
			const newOpts = Object.assign({}, typeof opts === 'object' ? opts : {}, { willReadFrequently: true })
			return origGetContext.call(this, type, newOpts)
		}
		return origGetContext.call(this, type, opts)
	}
})()

import { createApp } from 'vue'
import { createPinia } from 'pinia'
import './style.css'
import App from './App.vue'
import router from './router'
import MessageModal from './components/MessageModal.vue'
import { setMessageModal } from './composables/useMessage'
import PointInfoPanel from './components/PointInfoPanel.vue'
import { setPointPanel } from './composables/usePointPanel'
import panelIcons from './lib/panelIcons'

// Debug: wrap global fetch to log which backend URL the frontend actually requests.
try {
	if (typeof window !== 'undefined' && window.fetch) {
		const backendBase = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8888'
		console.info('[backend] frontend backendBase =', backendBase)
		const _origFetch = window.fetch.bind(window)
		window.fetch = async function(input, init) {
			try {
				let method = (init && init.method) || 'GET'
				let reqUrl = ''
				if (input && input.url) reqUrl = input.url
				else reqUrl = String(input || '')

				let resolved = reqUrl
				try {
					// resolve relative paths against backendBase so logs show actual network target
					if (reqUrl && !/^[a-zA-Z]+:\/\//.test(reqUrl)) {
						// treat leading '/' or 'api' or './' as backend-relative
						resolved = new URL(reqUrl, backendBase).href
					}
				} catch (e) {
					// fallback to original
				}

				console.debug(`[fetch] ${method} ${reqUrl} -> ${resolved}`)
			} catch (e) {
				try { console.debug('[fetch] log error', e) } catch (ee) {}
			}
			return _origFetch(input, init)
		}
	}
} catch (e) {
	// ignore in environments without window
}

const app = createApp(App)
app.use(router)
app.use(createPinia())
app.mount('#app')

// Mount a global MessageModal instance so showMessage 可以全局使用
try {
	const modalContainer = document.createElement('div')
	document.body.appendChild(modalContainer)
	const modalApp = createApp(MessageModal)
	const modalInstance = modalApp.mount(modalContainer)
	setMessageModal(modalInstance)
} catch (e) {
	// 若失败则在 useMessage 中回退到懒加载挂载
	console.warn('mount MessageModal failed, will lazy-init when needed', e)
}

// Mount a global PointInfoPanel instance so showPointPanel 可以全局使用
try {
	const panelContainer = document.createElement('div')
	document.body.appendChild(panelContainer)
	const panelApp = createApp(PointInfoPanel)
	const panelInstance = panelApp.mount(panelContainer)
		setPointPanel(panelInstance)
		// set default icons imported from a dedicated module (mimic FloatTaskbar style)
		try {
			if (panelInstance && typeof panelInstance.setIcons === 'function' && panelIcons) {
				panelInstance.setIcons(panelIcons)
			}
		} catch (e) {
			// ignore if assets aren't present or bundler doesn't resolve
		}
} catch (e) {
	console.warn('mount PointInfoPanel failed, will lazy-init when needed', e)
}
