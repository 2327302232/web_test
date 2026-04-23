import { defineStore } from 'pinia';

const STORAGE_KEY = 'ride:selection:v1';

function loadPersisted() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { selected: [], meta: {}, lastUpdatedAt: 0 };
    return JSON.parse(raw);
  } catch (e) {
    console.warn('[trackSelection] Failed to load from localStorage', e);
    return { selected: [], meta: {}, lastUpdatedAt: 0 };
  }
}

function persist(state) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      selected: state.selected,
      meta: state.meta,
      lastUpdatedAt: Date.now(),
    }));
  } catch (e) {
    console.warn('[trackSelection] Failed to persist to localStorage', e);
  }
}

export const useTrackSelection = defineStore('trackSelection', {
  state: () => ({
    selected: [], // Array<string>
    meta: {},     // Record<string, meta>
    lastUpdatedAt: 0,
    ...loadPersisted(),
  }),
  getters: {
    isSelected: (state) => (segmentId) => state.selected.includes(segmentId),
    selectedSet: (state) => new Set(state.selected),
    count: (state) => state.selected.length,
  },
  actions: {
    registerMeta(segmentId, meta) {
      if (!segmentId) return;
      this.meta[segmentId] = meta;
      persist(this);
      console.debug('[trackSelection] registerMeta', segmentId, meta);
    },
    select(segmentId) {
      if (!this.selected.includes(segmentId)) {
        this.selected.push(segmentId);
        persist(this);
        console.debug('[trackSelection] select', segmentId);
      }
    },
    unselect(segmentId) {
      const idx = this.selected.indexOf(segmentId);
      if (idx !== -1) {
        this.selected.splice(idx, 1);
        persist(this);
        console.debug('[trackSelection] unselect', segmentId);
      }
    },
    toggle(segmentId) {
      if (this.selected.includes(segmentId)) {
        this.unselect(segmentId);
      } else {
        this.select(segmentId);
      }
    },
    bulkSelect(arrayOfIds) {
      this.selected = Array.from(new Set(arrayOfIds));
      persist(this);
      console.debug('[trackSelection] bulkSelect', arrayOfIds);
    },
    setSelected(arrayOfIds) {
      this.selected = Array.from(new Set(arrayOfIds));
      persist(this);
      console.debug('[trackSelection] setSelected', arrayOfIds);
    },
    clear() {
      this.selected = [];
      persist(this);
      console.debug('[trackSelection] clear');
    },
  },
});
