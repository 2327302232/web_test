import { defineStore } from 'pinia'

export const useAppStore = defineStore('app', {
  state: () => ({ appName: 'web_test', ready: true }),
  getters: {
    upperName: (state) => (state.appName || '').toUpperCase()
  },
  actions: {
    setAppName(name) {
      this.appName = name
    }
  }
})
