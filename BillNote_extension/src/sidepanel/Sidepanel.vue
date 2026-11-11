<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { getTaskStatus, resolveImageUrl } from '~/logic/api'
import { tasks, tasksReady, settingsReady, upsertTask } from '~/logic/storage'
import type { TaskRecord } from '~/logic/types'
import { getTaskDisplayTitle } from '~/logic/task-display'
import { statusIcon, statusLabel } from '~/logic/task-status-label'
import { useBackendHealth } from '~/composables/useBackendHealth'

const activeTaskId = ref<string>('')
const activeTask = computed<TaskRecord | undefined>(() => tasks.value?.find(t => t.taskId === activeTaskId.value))
const errorMsg = ref('')
const showHistory = ref(false)
const booting = ref(true)

const { state: backend, detail: backendDetail } = useBackendHealth()

const isDone = computed(() => activeTask.value?.status === 'SUCCESS')
const isFailed = computed(() => activeTask.value?.status === 'FAILED')
const isRunning = computed(() => !!activeTask.value && !isDone.value && !isFailed.value)
const backendDown = computed(() => backend.value === 'down')
const loading = computed(() => booting.value || backend.value === 'checking')

let pollTimer: ReturnType<typeof setTimeout> | null = null

async function poll(taskId: string) {
  try {
    const res = await getTaskStatus(taskId)
    const cur = tasks.value?.find(t => t.taskId === taskId)
    if (cur) {
      upsertTask({
        ...cur,
        status: res.status,
        message: res.message,
        result: res.result ?? cur.result,
        updatedAt: Date.now(),
        title: cur.title || getTaskDisplayTitle(cur),
      })
    }
    if (res.status !== 'SUCCESS' && res.status !== 'FAILED')
      pollTimer = setTimeout(() => poll(taskId), 3000)
  }
  catch (e) {
    errorMsg.value = (e as Error).message
    pollTimer = setTimeout(() => poll(taskId), 5000)
  }
}

function selectTask(id: string) {
  if (pollTimer) {
    clearTimeout(pollTimer)
    pollTimer = null
  }
  activeTaskId.value = id
  showHistory.value = false
  const t = tasks.value?.find(x => x.taskId === id)
  if (t && t.status !== 'SUCCESS' && t.status !== 'FAILED')
    poll(id)
}

function openOptions() {
  browser.runtime.openOptionsPage()
}

async function copyMarkdown() {
  const md = activeTask.value?.result?.markdown
  if (md)
    await navigator.clipboard.writeText(md)
}

function safeFilename(name: string): string {
  return (name || 'bilinote')
    .replace(/[\\/:*?"<>|]/g, '_')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 120) || 'bilinote'
}

function downloadMarkdown() {
  const md = activeTask.value?.result?.markdown
  if (!md)
    return
  const title = safeFilename(getTaskDisplayTitle(activeTask.value))
  const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${title}.md`
  a.click()
  URL.revokeObjectURL(url)
}

const activeTitle = computed(() => getTaskDisplayTitle(activeTask.value))

const activeCover = computed(() =>
  (activeTask.value?.result?.audio_meta as { cover_url?: string } | undefined)?.cover_url)

onMounted(async () => {
  await Promise.all([settingsReady, tasksReady])
  booting.value = false
  const latest = tasks.value?.[0]
  if (latest) {
    activeTaskId.value = latest.taskId
    if (latest.status !== 'SUCCESS' && latest.status !== 'FAILED')
      poll(latest.taskId)
  }
})

onUnmounted(() => {
  if (pollTimer)
    clearTimeout(pollTimer)
})
</script>

<template>
  <main class="w-full h-full flex flex-col bg-canvas text-ink font-sans text-sm">
    <header class="flex items-center justify-between gap-2 px-3 py-2 border-b border-line shrink-0 bg-surface">
      <div class="font-semibold">BiliNote</div>
      <div class="flex items-center gap-1">
        <button
          v-if="(tasks?.length ?? 0) > 0"
          class="btn-ghost !px-2 !text-xs"
          :class="{ 'bg-accent-soft text-accent': showHistory }"
          :aria-expanded="showHistory"
          aria-controls="history-panel"
          @click="showHistory = !showHistory"
        >
          历史 {{ tasks?.length }}
        </button>
        <button class="btn-ghost !px-2 !text-xs" aria-label="打开设置" @click="openOptions">
          设置
        </button>
      </div>
    </header>

    <!-- 历史弹层 -->
    <div
      v-if="showHistory"
      id="history-panel"
      class="border-b border-line bg-raised px-2 py-2 max-h-60 overflow-auto shrink-0"
    >
      <ul class="flex flex-col gap-0.5 text-xs">
        <li
          v-for="t in tasks"
          :key="t.taskId"
          class="flex items-center gap-2 px-2 py-2 rounded-lg cursor-pointer min-h-11 transition-colors"
          :class="t.taskId === activeTaskId ? 'bg-accent-soft' : 'hover:bg-raised-hover'"
          :aria-current="t.taskId === activeTaskId ? 'true' : undefined"
          @click="selectTask(t.taskId)"
        >
          <span class="truncate flex-1" :title="getTaskDisplayTitle(t)">
            {{ getTaskDisplayTitle(t) }}
          </span>
          <span class="status" :class="t.status === 'SUCCESS' ? 'status-done' : t.status === 'FAILED' ? 'status-failed' : 'status-running'">
            {{ statusIcon(t.status) }} {{ statusLabel(t.status) }}
          </span>
        </li>
      </ul>
    </div>

    <div v-if="errorMsg" class="banner banner-danger mx-3 mt-2 shrink-0" role="alert">
      <span aria-hidden="true">✕</span><span class="break-words">{{ errorMsg }}</span>
    </div>

    <!-- 后端不可用 -->
    <div v-if="backendDown" class="banner banner-danger mx-3 mt-2 shrink-0" role="alert">
      <span aria-hidden="true">✕</span>
      <span>
        后端不可用<template v-if="backendDetail">（{{ backendDetail }}）</template>，
        <button class="underline" @click="openOptions">去设置后端地址</button>
      </span>
    </div>

    <!-- 加载态 -->
    <section v-if="loading" class="flex-1 flex items-center justify-center gap-2 text-ink-muted text-xs" role="status">
      <span class="spin" aria-hidden="true">◌</span> 正在连接后端…
    </section>

    <!-- 空态 -->
    <section
      v-else-if="!activeTask"
      class="flex-1 flex flex-col items-center justify-center gap-3 text-ink-muted text-xs px-6 text-center"
    >
      <p class="leading-relaxed">
        还没有任务。在视频页点悬浮按钮、在 popup 提交，或右键菜单选「用 BiliNote 总结」。
      </p>
      <button class="btn-secondary" :disabled="backendDown" @click="openOptions">
        打开设置
      </button>
    </section>

    <section v-else class="flex-1 flex flex-col min-h-0">
      <div class="flex items-center gap-2 px-3 py-2 border-b border-line shrink-0 bg-surface">
        <img
          v-if="activeCover"
          :src="resolveImageUrl(activeCover)"
          class="w-12 h-7 object-cover rounded bg-raised shrink-0 border border-line"
          alt=""
          @error="($event.target as HTMLImageElement).style.display = 'none'"
        >
        <a
          class="text-sm font-medium leading-tight line-clamp-1 break-all flex-1 min-w-0 hover:text-accent"
          :href="activeTask.videoUrl"
          target="_blank"
          :title="activeTitle || activeTask.videoUrl"
        >{{ activeTitle }}</a>
        <span
          class="status shrink-0"
          :class="isDone ? 'status-done' : isFailed ? 'status-failed' : 'status-running'"
          :title="activeTask.message"
        >
          <span aria-hidden="true">{{ statusIcon(activeTask.status) }}</span>
          {{ statusLabel(activeTask.status) }}
        </span>
      </div>

      <div v-if="isRunning" class="px-3 py-2 border-b border-line shrink-0">
        <TaskProgress :status="activeTask.status" :message="activeTask.message" />
      </div>
      <div
        v-else-if="isDone && activeTask.result?.markdown"
        class="flex items-center gap-2 px-3 py-1.5 border-b border-line shrink-0 text-xs bg-surface"
      >
        <span class="tag bg-accent-soft text-accent border-accent-ring">Markdown</span>
        <div class="flex-1" />
        <button class="btn-secondary !text-xs" title="复制 Markdown" @click="copyMarkdown">
          复制
        </button>
        <button class="btn-secondary !text-xs" title="下载 .md" @click="downloadMarkdown">
          下载
        </button>
      </div>

      <div class="flex-1 overflow-auto min-h-0">
        <MarkdownView
          v-if="isDone && activeTask.result?.markdown"
          :markdown="activeTask.result.markdown"
          :title="(activeTask.result.audio_meta as { title?: string } | undefined)?.title"
          :hide-actions="true"
        />
        <div v-else-if="isFailed" class="p-4">
          <div class="banner banner-danger">
            <span aria-hidden="true">✕</span>
            <span class="break-words">{{ activeTask.message || '任务失败' }}</span>
          </div>
        </div>
      </div>
    </section>
  </main>
</template>

<style>
.line-clamp-1 { display: -webkit-box; -webkit-line-clamp: 1; -webkit-box-orient: vertical; overflow: hidden; }
</style>
