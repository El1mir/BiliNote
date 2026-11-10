<script setup lang="ts">
import { computed } from 'vue'
import type { Platform } from '~/logic/types'
import { PLATFORM_LABELS } from '~/logic/platform'

const props = defineProps<{ platform: Platform | null }>()

const cls = computed(() => (props.platform ? 'tag' : 'tag text-ink-muted'))
const label = computed(() => (props.platform ? PLATFORM_LABELS[props.platform] : '未识别'))
</script>

<template>
  <span class="tag" :class="cls">{{ label }}</span>
</template>
