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
import './style.css'
import App from './App.vue'

createApp(App).mount('#app')
