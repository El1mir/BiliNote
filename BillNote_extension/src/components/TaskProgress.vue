<script setup lang="ts">
import { computed } from 'vue'
import { statusIcon, statusLabel } from '~/logic/task-status-label'
import type { TaskStatus } from '~/logic/types'

const props = defineProps<{ status: TaskStatus, message?: string }>()

const STAGE_ORDER: TaskStatus[] = ['PENDING', 'PARSING', 'DOWNLOADING', 'TRANSCRIBING', 'SUMMARIZING', 'FORMATTING', 'SAVING', 'SUCCESS']
const currentIdx = computed(() => STAGE_ORDER.indexOf(props.status))
const isFailed = computed(() => props.status === 'FAILED')
const isDone = computed(() => props.status === 'SUCCESS')
</script>

<template>
  <div class="flex flex-col gap-2" role="status" aria-live="polite">
    <div class="flex items-center gap-2">
      <span
        class="status"
        :class="isFailed ? 'status-failed' : isDone ? 'status-done' : 'status-running'"
      >
        <span aria-hidden="true">{{ statusIcon(status) }}</span>
        {{ statusLabel(status) }}
      </span>
      <span v-if="message" class="text-ink-muted text-xs truncate" :title="message">{{ message }}</span>
    </div>
    <div v-if="!isFailed" class="flex gap-1" aria-hidden="true">
      <div
        v-for="(s, i) in STAGE_ORDER"
        :key="s"
        class="h-1 flex-1 rounded-full transition-colors"
        :class="i <= currentIdx ? 'bg-accent' : 'bg-raised-hover'"
      />
    </div>
    <div v-else class="h-1 rounded-full bg-danger" aria-hidden="true" />
  </div>
</template>
