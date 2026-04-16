<!--
FloatTaskbar.vue
用途：移动端页面通用的悬浮侧边任务栏，包含三个占位按钮与折叠开关。
放置位置：在 `src/App.vue` 根层级引入，确保所有路由页面可见。
折叠行为：本组件内部本地状态控制折叠/展开。收起时仅保留一个较小的展开按钮（无容器背景）；展开时显示全部按钮与半透明容器。
复用：在其他页面复用可直接在模板中插入 <FloatTaskbar /> 或通过 CSS 变量调整外观。
-->
<template>
  <div class="float-wrapper" :class="{ collapsed }" aria-hidden="false">
    <!-- 折叠/展开按钮：控制整个任务栏的收起与展开 (toggle) -->
    <button
      class="toggle-btn"
      @click="toggle"
      :aria-expanded="(!collapsed).toString()"
      :aria-label="collapsed ? '展开任务栏' : '收起任务栏'"
    >
      <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false">
        <path v-if="collapsed" d="M8 5l8 7-8 7V5z" fill="currentColor" />
        <path v-else d="M16 5L8 12l8 7V5z" fill="currentColor" />
      </svg>
    </button>

    <!-- 面板容器：展开时显示，包含三个占位按钮 -->
    <div class="panel" role="navigation" aria-label="浮动任务栏">
      <!-- 四个垂直排列的占位按钮（无业务逻辑，仅视觉占位） -->
      <div class="btn-list" aria-hidden="false">
        <!-- 占位按钮 1: helmet (顶部) -->
        <button class="task-btn" aria-label="helmet" type="button" @click="navigate('/helmet')">
          <img :src="icons[0]" class="task-icon" alt="" />
        </button>
        <!-- 占位按钮 2: me -->
        <button class="task-btn" aria-label="me" type="button" @click="navigate('/me')">
          <img :src="icons[1]" class="task-icon" alt="" />
        </button>
        <!-- 占位按钮 3: config -->
        <button class="task-btn" aria-label="config" type="button" @click="navigate('/config')">
          <img :src="icons[2]" class="task-icon" alt="" />
        </button>
        <!-- 占位按钮 4: log (底部) -->
        <button class="task-btn" aria-label="log" type="button" @click="navigate('/log')">
          <img :src="icons[3]" class="task-icon" alt="" />
        </button>
      </div>
    </div>
  </div>
</template>

<script>
import helmetIcon from '../assets/helmet.svg'
import meIcon from '../assets/me.svg'
import configIcon from '../assets/config.svg'
import logIcon from '../assets/log.svg'

export default {
  name: 'FloatTaskbar',
  data() {
    return {
      // collapsed: true 表示任务栏处于收起状态（仅显示展开按钮）
      // collapsed: false 表示任务栏展开，显示 panel 与占位按钮
      collapsed: true,
      // icons: 从上到下依次为 helmet, me, config, log
      icons: [helmetIcon, meIcon, configIcon, logIcon]
    }
  },
  methods: {
    // 切换折叠状态：由顶部的展开/收起按钮触发
    toggle() {
      this.collapsed = !this.collapsed
    }
    ,
    // 跳转到指定路由
    navigate(path) {
      if (this.$router && path) {
        this.$router.push(path)
      }
      // 点击后自动收起任务栏（可按需修改）
      this.collapsed = true
    }
  }
}
</script>

<style scoped>
/* 可通过覆盖以下变量来自定义外观 */
.float-wrapper {
  /* 容器：定位与安全区处理（外层 wrapper） */
  --ftb-width: 40px; /* 展开后面板宽度（缩小至更紧凑） */
  --ftb-toggle-w: 25px; /* 展开按钮宽度（细长形的较短边） */
  --ftb-toggle-h: 30px; /* 展开按钮高度（细长形的较长边） */
  --ftb-btn-size: clamp(44px, 12vw, 56px); /* 内部占位按钮尺寸，可响应 */
  --ftb-icon-size: 20px; /* icon 图片尺寸 */
  --ftb-gap: 5px;
  --ftb-alpha: 0.20; /* 基础透明度（用于 panel 与 toggle，使其一致） */
  --ftb-bg: rgba(10, 12, 16, var(--ftb-alpha)); /* 稍微降低不透明度，但不要过低 */
  --ftb-accent: rgba(255, 255, 255, 0.74);

  position: fixed;
  top: calc(max(12vh, 56px) + env(safe-area-inset-top));
  left: 0;
  z-index: 1200;
  display: flex;
  flex-direction: column;
  gap: var(--ftb-gap);
  align-items: flex-start;
  -webkit-tap-highlight-color: transparent;
}

.toggle-btn {
  /* 折叠/展开按钮样式：现在为细长圆角矩形，靠边展示 */
  width: var(--ftb-toggle-w);
  height: var(--ftb-toggle-h);
  min-width: 25px;
  min-height: 30px;
  margin-left: 4px; /* 尽量靠边 */
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  position: relative;
  border-radius: 12px; /* 细长方形（圆角矩形） */
  border: none;
  background: var(--ftb-bg); /* 与面板使用相同透明度 */
  color: var(--ftb-accent);
  box-shadow: 0 4px 10px rgba(255, 255, 255, 0.74);
  cursor: pointer;
  transition: transform 220ms, background 200ms, left 200ms;
  z-index: 1220;
  outline: 1px solid transparent !important;
  backface-visibility: hidden;
  -webkit-backface-visibility: hidden;
  transform: translateZ(0);
}

.toggle-btn:active { transform: scale(0.96); }

.panel {
  /* 面板容器样式：半透明背景、模糊与圆角 */
  width: var(--ftb-width);
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--ftb-gap);
  padding: 10px;
  margin-left: 4px;
  background: var(--ftb-bg);
  color: var(--ftb-accent);
  border-radius: 14px;
  box-shadow: 0 6px 20px rgba(255,255,255,0.01);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  transition: width 260ms cubic-bezier(.2,.9,.2,1), opacity 200ms, padding 200ms;
  overflow: hidden;
}

/* 收起时隐藏容器，仅留下外部的 toggle 按钮 */
.float-wrapper.collapsed .panel {
  width: 0;
  padding: 0;
  margin-left: 0;
  opacity: 0;
  pointer-events: none;
  box-shadow: none;
  background: transparent;
}

.btn-list {
  /* 按钮列表：垂直排列三个占位按钮 */
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: center;
}

.task-btn {
  /* 单个占位按钮样式（无业务逻辑，仅视觉占位） */
  width: var(--ftb-btn-size);
  height: var(--ftb-btn-size);
  min-width: 44px;
  min-height: 44px;
  border-radius: 999px;
  border: none;
  background: rgba(0,0,0,0.28); /* 略微降低按钮面板透明度 */
  color: var(--ftb-accent);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: transform 180ms, opacity 180ms;
}

.task-icon {
  width: var(--ftb-icon-size);
  height: var(--ftb-icon-size);
  display: block;
  object-fit: contain;
}

/* 当容器收起时，内部按钮不可交互 */
.float-wrapper.collapsed .btn-list {
  opacity: 0;
  transform: scale(0.96);
  pointer-events: none;
}

/* 仅在移动/窄屏显示，桌面隐藏 */
@media (min-width: 769px) {
  .float-wrapper { display: none !important; }
}

/* 在非常窄的屏幕上调整顶部间距 */
@media (max-width: 420px) {
  .float-wrapper { top: calc(max(12vh, 64px) + env(safe-area-inset-top)); }
}

/* 修复圆角 + 模糊 产生的黑线闪边 */
.panel,
.toggle-btn {
  backface-visibility: hidden;
  -webkit-backface-visibility: hidden;
  transform: translateZ(0);
  outline: 1px solid transparent;
}

</style>
