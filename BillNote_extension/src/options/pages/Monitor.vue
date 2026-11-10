<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { getDeployStatus, getSysHealth } from '~/logic/api'
import type { DeployStatus } from '~/logic/types'

const status = ref<DeployStatus | null>(null)
const health = ref<{ ok: boolean, msg?: string } | null>(null)
const loading = ref(false)
const error = ref('')

async function refresh() {
  loading.value = true
  error.value = ''
  try {
    const [s, h] = await Promise.all([getDeployStatus(), getSysHealth()])
    status.value = s
    health.value = h
  }
  catch (e) {
    error.value = (e as Error).message
  }
  finally {
    loading.value = false
  }
}

onMounted(refresh)
</script>

<template>
  <div class="p-6 max-w-2xl">
    <div class="flex items-center justify-between mb-4">
      <h1 class="text-xl font-bold">部署监控</h1>
      <button class="btn-secondary" :disabled="loading" @click="refresh">
        {{ loading ? '检查中…' : '刷新' }}
      </button>
    </div>

    <div v-if="error" class="text-danger text-sm mb-4">{{ error }}</div>

    <template v-if="status">
      <section class="section-card">
        <h2 class="font-semibold">后端</h2>
        <div class="text-sm">
          <span class="tag bg-success-soft text-success">{{ status.backend.status }}</span>
          <span class="ml-2 text-ink-soft">端口 {{ status.backend.port }}</span>
        </div>
      </section>

      <section class="section-card">
        <h2 class="font-semibold">FFmpeg</h2>
        <div class="text-sm flex items-center gap-3">
          <span
            class="tag"
            :class="status.ffmpeg.available ? 'bg-success-soft text-success' : 'bg-red-100 text-danger'"
          >{{ status.ffmpeg.available ? '可用' : '不可用' }}</span>
          <span v-if="health && !health.ok" class="text-danger text-xs">{{ health.msg }}</span>
        </div>
      </section>

      <section class="section-card">
        <h2 class="font-semibold">CUDA / GPU</h2>
        <div class="text-sm">
          <span
            class="tag"
            :class="status.cuda.available ? 'bg-success-soft text-success' : 'bg-raised text-ink-soft'"
          >{{ status.cuda.available ? '可用' : '不可用' }}</span>
          <div v-if="status.cuda.available" class="mt-1 text-ink-soft text-xs">
            CUDA {{ status.cuda.version }} · {{ status.cuda.gpu_name }}
          </div>
        </div>
      </section>

      <section class="section-card">
        <h2 class="font-semibold">Whisper</h2>
        <div class="text-sm text-ink-soft">
          引擎：<span class="text-ink">{{ status.whisper.transcriber_type }}</span>
          <span v-if="status.whisper.model_size" class="ml-3">
            模型：<span class="text-ink">{{ status.whisper.model_size }}</span>
          </span>
        </div>
      </section>
    </template>
  </div>
</template>
