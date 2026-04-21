let panelInstance = null

export function setPointPanel(instance) {
  panelInstance = instance
}

export function closePointPanel() {
  try {
    if (panelInstance && typeof panelInstance.close === 'function') {
      try { panelInstance.close({ action: 'closed-by-navigate' }) } catch (e) { /* ignore */ }
    }
  } catch (e) {
    console.warn('closePointPanel error', e)
  }
}

async function ensurePanel() {
  if (panelInstance) return
  const { createApp } = await import('vue')
  const module = await import('../components/PointInfoPanel.vue')
  const PointInfoPanel = module.default
  const container = document.createElement('div')
  document.body.appendChild(container)
  const panelApp = createApp(PointInfoPanel)
  panelInstance = panelApp.mount(container)
}

export async function showPointPanel(opts = {}) {
  try {
    if (!panelInstance) await ensurePanel()
    if (!panelInstance || typeof panelInstance.open !== 'function') {
      throw new Error('point panel unavailable')
    }
    const res = await panelInstance.open(opts)
    return res
  } catch (e) {
    console.error('showPointPanel error', e)
    return null
  }
}

export default showPointPanel
