<script setup lang="ts">
import { computed, ref } from 'vue'
import GeneralPage from './pages/General.vue'
import ProvidersPage from './pages/Providers.vue'
import TranscriberPage from './pages/Transcriber.vue'
import DownloaderPage from './pages/Downloader.vue'
import MonitorPage from './pages/Monitor.vue'

const TABS = [
  { id: 'general', label: '通用', icon: '⚙️', component: GeneralPage },
  { id: 'providers', label: '模型供应商', icon: '🧠', component: ProvidersPage },
  { id: 'transcriber', label: '音频转写配置', icon: '🎙️', component: TranscriberPage },
  { id: 'downloader', label: '下载配置', icon: '🍪', component: DownloaderPage },
  { id: 'monitor', label: '部署监控', icon: '📊', component: MonitorPage },
] as const

const activeTab = ref<typeof TABS[number]['id']>('general')
const ActiveComponent = computed(() => TABS.find(t => t.id === activeTab.value)?.component ?? GeneralPage)
</script>

<template>
  <div class="flex h-screen bg-canvas text-ink font-sans">
    <aside class="w-56 shrink-0 border-r border-line bg-surface flex flex-col">
      <div class="px-4 py-4 border-b border-line">
        <div class="text-lg font-semibold tracking-tight text-ink">BiliNote</div>
        <div class="text-xs text-ink-muted mt-0.5">浏览器插件设置</div>
      </div>
      <nav class="flex-1 overflow-auto py-2" aria-label="设置分区">
        <button
          v-for="tab in TABS"
          :key="tab.id"
          type="button"
          class="w-full text-left px-4 min-h-11 text-sm flex items-center gap-2 transition-colors border-l-2"
          :class="activeTab === tab.id
            ? 'bg-accent-soft text-accent font-medium border-accent'
            : 'text-ink-soft border-transparent hover:bg-raised-hover hover:text-ink'"
          :aria-current="activeTab === tab.id ? 'page' : undefined"
          @click="activeTab = tab.id"
        >
          <span aria-hidden="true">{{ tab.icon }}</span>
          <span>{{ tab.label }}</span>
        </button>
      </nav>
      <div class="px-4 py-2 text-xs text-ink-muted border-t border-line">
        v0.1.0
      </div>
    </aside>

    <main class="flex-1 overflow-auto">
      <component :is="ActiveComponent" />
    </main>
  </div>
</template>
