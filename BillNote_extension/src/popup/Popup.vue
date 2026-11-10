<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { detectPlatform } from '~/logic/platform'
import { settings, settingsReady, tasks, tasksReady, upsertTask } from '~/logic/storage'
import { generateNote, getTaskStatus, resolveImageUrl } from '~/logic/api'
import { fetchBilibiliSubtitle } from '~/logic/bilibili-subtitle'
import { NOTE_DETAILS, NOTE_FORMATS, NOTE_SCENES, type NoteFormat, type TaskRecord } from '~/logic/types'
import { getTaskDisplayTitle, normalizeVideoTitle } from '~/logic/task-display'
import { statusIcon, statusLabel } from '~/logic/task-status-label'
import { useBackendHealth } from '~/composables/useBackendHealth'

const tabUrl = ref<string>('')
const tabTitle = ref<string>('')
const tabId = ref<number | undefined>(undefined)
const platform = computed(() => detectPlatform(tabUrl.value))
const supported = computed(() => platform.value !== null)

const { state: backend, detail: backendDetail } = useBackendHealth()
const booting = ref(true)

const submitting = ref(false)
const errorMsg = ref('')
const activeTaskId = ref<string>('')
const activeTask = computed<TaskRecord | undefined>(() => tasks.value?.find(t => t.taskId === activeTaskId.value))

const backendDown = computed(() => backend.value === 'down')
const loading = computed(() => booting.value || backend.value === 'checking')
const canSubmit = computed(() =>
  supported.value && !submitting.value && !!settings.value.providerId && !backendDown.value)

let pollTimer: ReturnType<typeof setTimeout> | null = null

async function loadActiveTab() {
  try {
    const [tab] = await browser.tabs.query({ active: true, currentWindow: true })
    tabUrl.value = tab?.url ?? ''
    tabTitle.value = tab?.title ?? ''
    tabId.value = tab?.id
  }
  catch (e) {
    console.warn('无法读取当前 tab:', e)
  }
}

async function poll(taskId: string) {
  try {
    const res = await getTaskStatus(taskId)
    upsertTask({
      taskId,
      videoUrl: activeTask.value?.videoUrl ?? tabUrl.value,
      platform: (activeTask.value?.platform ?? platform.value)!,
      status: res.status,
      message: res.message,
      createdAt: activeTask.value?.createdAt ?? Date.now(),
      updatedAt: Date.now(),
      result: res.result ?? activeTask.value?.result,
      title: activeTask.value?.title || normalizeVideoTitle(tabTitle.value),
    })
    if (res.status !== 'SUCCESS' && res.status !== 'FAILED')
      pollTimer = setTimeout(() => poll(taskId), 3000)
  }
  catch (e) {
    errorMsg.value = (e as Error).message
    pollTimer = setTimeout(() => poll(taskId), 5000)
  }
}

async function start() {
  errorMsg.value = ''
  if (backendDown.value) {
    errorMsg.value = '后端不可用，先启动 BiliNote 后端再试'
    return
  }
  if (!supported.value) {
    errorMsg.value = '当前页面不是支持的视频链接'
    return
  }
  if (!settings.value.providerId || !settings.value.modelName) {
    errorMsg.value = '请先去设置页选择供应商和模型'
    return
  }
  submitting.value = true
  try {
    // B 站：在用户浏览器里直接抓字幕（带本地登录态 cookie），跳过后端的 download_subtitles 与音频转写
    const prefetched = platform.value === 'bilibili' ? await fetchBilibiliSubtitle(tabUrl.value) : null
    const formats = settings.value.formats || []
    const { task_id } = await generateNote({
      video_url: tabUrl.value,
      platform: platform.value!,
      quality: settings.value.quality,
      provider_id: settings.value.providerId,
      model_name: settings.value.modelName,
      // backend VideoRequest 同时接受 format 数组与 screenshot/link 单独布尔，从 formats 派生保持单一真相源
      format: [...formats],
      screenshot: formats.includes('screenshot'),
      link: formats.includes('link'),
      scene: settings.value.scene || undefined,
      detail: settings.value.detail || undefined,
      extras: settings.value.extras || undefined,
      video_understanding: settings.value.video_understanding || undefined,
      video_interval: settings.value.video_understanding ? settings.value.video_interval : undefined,
      grid_size: settings.value.video_understanding ? settings.value.grid_size : undefined,
      prefetched_transcript: prefetched ?? undefined,
    })
    activeTaskId.value = task_id
    upsertTask({
      taskId: task_id,
      videoUrl: tabUrl.value,
      platform: platform.value!,
      status: 'PENDING',
      message: '已提交',
      createdAt: Date.now(),
      updatedAt: Date.now(),
      title: normalizeVideoTitle(tabTitle.value),
    })
    poll(task_id)
    // 提交后顺手把侧边栏拉起来，免得用户来回切窗口
    openSidePanel()
  }
  catch (e) {
    errorMsg.value = (e as Error).message
  }
  finally {
    submitting.value = false
  }
}

function openOptions() {
  browser.runtime.openOptionsPage()
}

function toggleFormat(value: NoteFormat, checked: boolean) {
  const cur = settings.value.formats || []
  settings.value.formats = checked
    ? Array.from(new Set([...cur, value]))
    : cur.filter(v => v !== value)
}

async function openSidePanel() {
  // 只能在用户操作触发的同步上下文里调，且需要明确的 tabId
  try {
    const target = tabId.value ?? (await browser.tabs.query({ active: true, currentWindow: true }))[0]?.id
    if (target == null)
      return
    // @ts-expect-error sidePanel 类型在 polyfill 中不全
    if (typeof chrome !== 'undefined' && chrome.sidePanel?.open)
      // @ts-expect-error see above
      await chrome.sidePanel.open({ tabId: target })
  }
  catch (err) {
    console.warn('打开侧边栏失败:', err)
  }
}

function selectTask(id: string) {
  activeTaskId.value = id
  const t = tasks.value?.find(x => x.taskId === id)
  if (t && t.status !== 'SUCCESS' && t.status !== 'FAILED')
    poll(id)
}

const activeCover = computed(() => activeTask.value?.result?.audio_meta?.cover_url as string | undefined)
const activeTitle = computed(() => getTaskDisplayTitle(activeTask.value, tabTitle.value))

function fmtTime(ts?: number) {
  if (!ts)
    return ''
  const d = new Date(ts)
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

onMounted(async () => {
  await Promise.all([settingsReady, tasksReady])
  await loadActiveTab()
  booting.value = false
  const running = tasks.value?.find(t => t.status !== 'SUCCESS' && t.status !== 'FAILED')
  if (running) {
    activeTaskId.value = running.taskId
    poll(running.taskId)
  }
})

onUnmounted(() => {
  if (pollTimer)
    clearTimeout(pollTimer)
})
</script>

<template>
  <main class="w-[400px] max-h-[600px] overflow-y-auto bg-canvas text-ink p-3 flex flex-col gap-3 font-sans">
    <header class="flex items-center justify-between gap-2">
      <div class="flex items-center gap-2 min-w-0">
        <span class="font-semibold text-[15px]">BiliNote</span>
        <PlatformBadge :platform="platform" />
      </div>
      <button class="btn-ghost !px-2" aria-label="打开设置" @click="openOptions">
        设置
      </button>
    </header>

    <div class="text-xs text-ink-muted truncate" :title="normalizeVideoTitle(tabTitle) || tabUrl">
      {{ normalizeVideoTitle(tabTitle) || tabUrl || '当前没有打开的标签页' }}
    </div>

    <!-- 加载态：读设置 / 探测后端 -->
    <div v-if="loading" class="flex items-center gap-2 text-xs text-ink-muted" role="status">
      <span class="spin inline-block" aria-hidden="true">◌</span>
      正在连接后端…
    </div>

    <!-- 后端不可用 -->
    <div v-if="backendDown" class="banner banner-danger" role="alert">
      <span aria-hidden="true">✕</span>
      <span>
        后端不可用<template v-if="backendDetail">（{{ backendDetail }}）</template>，
        <button class="underline" @click="openOptions">去设置后端地址</button>
      </span>
    </div>

    <div v-if="!supported" class="banner banner-warn" role="status">
      <span aria-hidden="true">!</span>
      <span>当前页面不是 BiliNote 支持的视频链接（目前只支持哔哩哔哩 Bilibili）</span>
    </div>

    <form class="section-card !p-2.5" @submit.prevent="start">
      <fieldset class="border-0 m-0 p-0 flex flex-col gap-2" :disabled="!supported || submitting || backendDown">
        <div class="grid grid-cols-3 gap-2 text-xs">
          <label class="flex flex-col gap-1">
            <span class="text-ink-soft">画质</span>
            <select v-model="settings.quality" class="input">
              <option value="fast">快速</option>
              <option value="medium">中等</option>
              <option value="slow">高质</option>
            </select>
          </label>
          <label class="flex flex-col gap-1">
            <span class="text-ink-soft">笔记场景</span>
            <select v-model="settings.scene" class="input">
              <option v-for="s in NOTE_SCENES" :key="s.value" :value="s.value">{{ s.label }}</option>
            </select>
          </label>
          <label class="flex flex-col gap-1">
            <span class="text-ink-soft">笔记详略</span>
            <select v-model="settings.detail" class="input">
              <option v-for="d in NOTE_DETAILS" :key="d.value" :value="d.value">{{ d.label }}</option>
            </select>
          </label>
        </div>

        <div class="flex flex-col gap-1 text-xs">
          <span class="text-ink-soft">输出形式</span>
          <div class="flex flex-wrap gap-x-3 gap-y-1.5">
            <label v-for="f in NOTE_FORMATS" :key="f.value" class="flex items-center gap-1.5">
              <input
                type="checkbox"
                class="accent-accent"
                :checked="(settings.formats || []).includes(f.value)"
                @change="toggleFormat(f.value, ($event.target as HTMLInputElement).checked)"
              >
              {{ f.label }}
            </label>
          </div>
        </div>

        <details class="text-xs">
          <summary class="cursor-pointer text-ink-soft">高级</summary>
          <label class="flex flex-col gap-1 mt-2">
            <span class="text-ink-soft">额外提示词（追加到 prompt 末尾）</span>
            <textarea
              v-model="settings.extras"
              class="input resize-y"
              rows="2"
              placeholder="例如：重点关注游戏开发部分；保留所有专业术语原文"
            />
          </label>
          <label class="flex items-center gap-2 mt-2">
            <input v-model="settings.video_understanding" type="checkbox" class="accent-accent">
            <span class="text-ink-soft">启用视频理解（抽帧拼图喂视觉模型）</span>
          </label>
          <div v-if="settings.video_understanding" class="grid grid-cols-3 gap-2 mt-2">
            <label class="flex flex-col gap-1">
              <span class="text-ink-soft">抽帧间隔(秒)</span>
              <input v-model.number="settings.video_interval" type="number" min="1" max="30" class="input">
            </label>
            <label class="flex flex-col gap-1">
              <span class="text-ink-soft">拼图行</span>
              <input
                :value="settings.grid_size?.[0] ?? 2"
                type="number" min="1" max="10"
                class="input"
                @input="settings.grid_size = [Number(($event.target as HTMLInputElement).value) || 2, settings.grid_size?.[1] ?? 2]"
              >
            </label>
            <label class="flex flex-col gap-1">
              <span class="text-ink-soft">拼图列</span>
              <input
                :value="settings.grid_size?.[1] ?? 2"
                type="number" min="1" max="10"
                class="input"
                @input="settings.grid_size = [settings.grid_size?.[0] ?? 2, Number(($event.target as HTMLInputElement).value) || 2]"
              >
            </label>
          </div>
          <p v-if="settings.video_understanding" class="text-warning mt-1">
            ⚠ 需要选择视觉模型（GPT-4o / Gemini / Claude 等），文字模型会忽略图片
          </p>
        </details>

        <div class="text-xs text-ink-soft">
          <span v-if="settings.providerId && settings.modelName">
            模型：{{ settings.modelName }}
          </span>
          <span v-else class="text-warning">
            ⚠ 未选择供应商/模型，
            <button type="button" class="underline" @click="openOptions">去设置</button>
          </span>
        </div>

        <button type="submit" class="btn-accent" :disabled="!canSubmit">
          {{ submitting ? '提交中…' : '生成笔记' }}
        </button>
      </fieldset>
    </form>

    <div v-if="errorMsg" class="banner banner-danger" role="alert">
      <span aria-hidden="true">✕</span>
      <span class="break-words">{{ errorMsg }}</span>
    </div>

    <!-- 空态 -->
    <p v-if="!activeTask && !loading" class="text-xs text-ink-muted leading-relaxed">
      还没有任务。选好供应商和模型后点「生成笔记」，进度会显示在这里。
    </p>

    <section v-if="activeTask" class="flex flex-col gap-2">
      <div v-if="activeCover || activeTitle" class="flex gap-2.5 items-start">
        <img
          v-if="activeCover"
          :src="resolveImageUrl(activeCover)"
          class="w-20 h-12 object-cover rounded-lg border border-line bg-raised shrink-0"
          alt=""
          @error="($event.target as HTMLImageElement).style.display = 'none'"
        >
        <div class="flex-1 min-w-0">
          <div class="text-sm font-medium leading-snug line-clamp-2 break-words" :title="activeTitle">
            {{ activeTitle || '（未取到标题）' }}
          </div>
          <div class="text-ink-muted text-xs mt-0.5">{{ fmtTime(activeTask.updatedAt) }}</div>
        </div>
      </div>

      <TaskProgress :status="activeTask.status" :message="activeTask.message" />

      <!-- 失败态 -->
      <div v-if="activeTask.status === 'FAILED'" class="banner banner-danger">
        <span aria-hidden="true">✕</span>
        <span class="break-words">{{ activeTask.message || '任务失败' }}</span>
      </div>

      <button
        v-if="activeTask.status === 'SUCCESS'"
        class="btn-accent"
        @click="openSidePanel"
      >
        在侧边栏查看笔记
      </button>
      <button v-else class="btn-secondary" @click="openSidePanel">
        在侧边栏看进度
      </button>
    </section>

    <details v-if="(tasks?.length ?? 0) > 0" class="text-xs">
      <summary class="cursor-pointer text-ink-soft py-1">最近任务（{{ tasks!.length }}）</summary>
      <ul class="mt-1 flex flex-col gap-1 max-h-32 overflow-auto">
        <li
          v-for="t in tasks"
          :key="t.taskId"
          class="flex justify-between items-center gap-2 px-2 py-1.5 rounded-lg cursor-pointer transition-colors"
          :class="t.taskId === activeTaskId ? 'bg-accent-soft text-ink' : 'hover:bg-raised-hover'"
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
    </details>
  </main>
</template>

<style>
.line-clamp-2 { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
</style>
