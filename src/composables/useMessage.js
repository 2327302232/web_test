let modalInstance = null

export function setMessageModal(instance) {
  modalInstance = instance
}

async function ensureModal() {
  if (modalInstance) return
  const { createApp } = await import('vue')
  const module = await import('../components/MessageModal.vue')
  const MessageModal = module.default
  const container = document.createElement('div')
  document.body.appendChild(container)
  const modalApp = createApp(MessageModal)
  modalInstance = modalApp.mount(container)
}

export async function showMessage(opts = {}) {
  try {
    if (!modalInstance) {
      await ensureModal()
    }
    if (!modalInstance || typeof modalInstance.open !== 'function') {
      throw new Error('message modal unavailable')
    }
    const res = await modalInstance.open(opts)
    return res
  } catch (e) {
    console.error('showMessage error', e)
    return null
  }
}

export default showMessage
