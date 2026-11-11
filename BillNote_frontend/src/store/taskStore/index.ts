import { create } from 'zustand'
import {
  deleteTaskRecord,
  deleteTaskRecords,
  get_task_status,
  listTasks,
  type BatchDeleteResult,
  type TaskListRow,
} from '@/services/note.ts'
import type { TaskDetail } from '@/utils/taskStatus'

/**
 * 历史数据容错：早期版本把 markdown 存成「版本数组」（新版本前插），
 * 所以取最新一版要取 `md[0]`，不是 `md[md.length - 1]`。
 * 版本功能已删除（spec 008），这里只负责把旧数据读出最新一版。
 */
export const readLatestMarkdown = (md: unknown): string => {
  if (Array.isArray(md)) {
    const first: unknown = md[0]
    if (typeof first === 'string') return first
    if (
      first &&
      typeof first === 'object' &&
      typeof (first as { content?: unknown }).content === 'string'
    ) {
      return (first as { content: string }).content
    }
    return ''
  }
  return typeof md === 'string' ? md : ''
}

export type TaskStatus =
  | 'PENDING'
  | 'PARSING'
  | 'DOWNLOADING'
  | 'TRANSCRIBING'
  | 'SUMMARIZING'
  | 'FORMATTING'
  | 'SAVING'
  | 'RUNNING'
  | 'SUCCESS'
  | 'FAILED'
  | 'FAILD'

export type TaskStage =
  | 'queued'
  | 'parsing'
  | 'fetching_subtitles'
  | 'downloading_video'
  | 'downloading_audio'
  | 'transcribing'
  | 'planning_frames'
  | 'extracting_frames'
  | 'building_grids'
  | 'summarizing'
  | 'post_processing'
  | 'saving'
  | 'success'
  | 'failed'

export interface TaskProgress {
  stage?: TaskStage | string | null
  stageLabel?: string | null
  progress?: number | null
  stageProgress?: number | null
  message?: string | null
  detail?: TaskDetail | null
  updatedAt?: string | null
  revision?: number
}

export interface AudioMeta {
  /**
   * 视频封面地址。**只有当前正在看的那篇笔记需要它**（右上角 VideoBanner）。
   *
   * 用户决策 m08608 第三条「前端也不要存预览图片」：任务列表里 195 条各自
   * 记住一个封面 URL，刷新页面就会对外打 195 个 image_proxy 请求。列表行
   * 一律留空（见 `stripCover`），只有 `rehydrateTask` 单篇回填结果时才写入。
   */
  cover_url: string
  duration: number
  file_path: string
  platform: string
  // 后端原样透传的平台字段，形状随平台而变（uploader / webpage_url …），
  // 调用方（VideoBanner 等）直接按属性取用，所以这里用宽松的记录类型而不是 unknown。
  raw_info: Record<string, unknown> | null
  title: string
  video_id: string
}

export interface Segment {
  start: number
  end: number
  text: string
}

export interface Transcript {
  full_text: string
  language: string
  raw: unknown
  segments: Segment[]
}
/**
 * 提交给后端的表单快照。这里是「前端记下的表单原样」，只用于回显与重试，
 * 所以字段全部可选、并带索引签名容纳各平台的额外选项（scene / detail / format / 截图与
 * OCR 选项等）。之前实现层就是 `formData: any`，收窄成必填会打断 NoteForm 等
 * 消费方（它们提交的对象确实不含 link/screenshot）。
 */
export interface TaskFormData {
  video_url?: string
  link?: boolean
  screenshot?: boolean
  platform?: string
  quality?: string
  model_name?: string
  provider_id?: string
  task_id?: string
  format?: string[]
  scene?: string
  detail?: string
  extras?: string
  video_understanding?: boolean
  video_interval?: number
  sampling_mode?: 'interval' | 'smart' | 'hybrid'
  max_frames?: number
  frames_per_second?: number
  frame_limit_mode?: 'total' | 'per_second'
  ocr_assist?: boolean | null
  batch_mode?: boolean
  grid_size?: [number, number]
  [key: string]: unknown
}

export interface Task {
  id: string
  // 单一 markdown 字符串。历史数据可能是版本数组，读取一律走 readLatestMarkdown()。
  markdown: string
  transcript: Transcript
  status: TaskStatus
  stage?: TaskStage | string | null
  stageLabel?: string | null
  progress?: number | null
  stageProgress?: number | null
  message?: string | null
  detail?: TaskDetail | null
  updatedAt?: string | null
  revision?: number
  platform: string
  /** 所属笔记分组；null = 未分组。与后端 `group_id` 对应，列表重载时以服务端为准。 */
  groupId: string | null
  /** 分组名；未分组时为空串。与后端 `group_name` 对应。 */
  groupName: string
  audioMeta: AudioMeta
  createdAt: string
  formData: TaskFormData
}

/**
 * `GET /api/task_status/{task_id}` 的响应形状（已由 request 拦截器剥掉
 * `{code,msg,data}` 信封，但历史上有接口自己又套了一层 data，这里两种都兼容）。
 */
interface TaskStatusPayload {
  status?: TaskStatus
  result?: {
    markdown?: string
    transcript?: Transcript
    audio_meta?: AudioMeta
  }
  stage?: TaskStage | string | null
  stage_label?: string | null
  stageLabel?: string | null
  /** 后端在部分版本里把进度放在一个嵌套对象里，这里不建模，交给 normalize 处理。 */
  progress?: unknown
  progress_value?: number | null
  stage_progress?: number | null
  stageProgress?: number | null
  message?: string | null
  detail?: TaskDetail | null
  updated_at?: string | null
  updatedAt?: string | null
  data?: unknown
}

interface TaskStore {
  tasks: Task[]
  currentTaskId: string | null
  /**
   * 登记一条刚提交的任务。`groupName` / `groupId` 是本次批量落进的组
   * （单条提交 / 留空 = 未分组）：
   * 后端按组名建组，前端必须**同时**记住 groupId 与 groupName ——
   * NoteHistory 的切段逻辑要求两者都存在才归组，只写 groupName 会让
   * 刚提交的任务先显示成「未分组」，要等下一次 loadTasks 才跳回正确的组（spec 009 决策 4）。
   */
  addPendingTask: (
    taskId: string,
    platform: string,
    formData: Task['formData'],
    groupName?: string,
    groupId?: string | null
  ) => void
  updateTaskContent: (id: string, data: Partial<Omit<Task, 'id' | 'createdAt'>>) => void
  /**
   * 只更新进度字段（status / stage / progress …），不碰内容字段。
   * 轮询路径用它，避免每次 3 秒一次的心跳都把 markdown/transcript 重写一遍。
   */
  updateTaskStatus: (id: string, data: Partial<TaskProgress> & { status?: TaskStatus }) => void
  /**
   * 从后端把任务内容拉回内存。前端不再做任何持久化存储（用户决策 m04951），
   * 刷新页面后任务内容一律以服务端 `GET /api/task_status/{id}` 为准。
   */
  rehydrateTask: (id: string) => Promise<Task | null>
  /**
   * 从后端 `GET /api/task_list` 重建任务列表（刷新页面后调用）。
   * 只做「合并」不覆盖：列表接口不带 status，所以绝不会把内存里已经 SUCCESS 的
   * 任务降级；内存里已有的 markdown / transcript / audioMeta 一律保留。
   * 这个方法不抛异常（失败只 console.warn），调用方不需要 try/catch。
   */
  loadTasks: () => Promise<void>
  /**
   * 上一次 loadTasks 的失败原因（诊断用，不参与状态机）。
   *
   * 列表接口挂了以前只会 console.warn，界面看起来像"还没有历史记录" —— 把网络故障
   * 伪装成空态是最误导人的一种失败。这里只记一行文案给界面渲染错误态，成功即清空。
   */
  tasksLoadError: string | null
  removeTask: (id: string) => void
  /**
   * 批量删除（spec 010）：整批只打一次后端请求，返回后端逐条结果。
   * 整批请求本身失败（网络/500）时返回 null。
   */
  removeTasks: (ids: string[]) => Promise<BatchDeleteResult | null>
  clearTasks: () => void
  setCurrentTask: (taskId: string | null) => void
  getCurrentTask: () => Task | null
}

/**
 * 出队时任务的初始形态。内容字段一律留空 —— 它们由后端在成功时回填，
 * 前端只是这一份数据的缓存，不再是数据源。
 */
const emptyTask = (taskId: string, platform: string, formData: Task['formData']): Task => ({
  formData,
  id: taskId,
  status: 'PENDING',
  stage: 'queued',
  stageLabel: '等待处理',
  progress: 0,
  stageProgress: 0,
  markdown: '',
  platform,
  groupId: null,
  groupName: '',
  transcript: {
    full_text: '',
    language: '',
    raw: null,
    segments: [],
  },
  createdAt: new Date().toISOString(),
  audioMeta: {
    cover_url: '',
    duration: 0,
    file_path: '',
    platform: '',
    raw_info: null,
    title: '',
    video_id: '',
  },
})

/**
 * 后端 `created_at` 是 'YYYY-MM-DD HH:MM:SS'（不是 ISO）。`new Date('2026-10-04 12:07:30')`
 * 在 V8 里能解析、但这是实现相关的行为，所以显式把空格换成 'T' 再解析。
 * 解析不出来就返回 NaN，排序时保持插入顺序（不猜时间）。
 */
const parseServerTime = (value: string): number => {
  if (!value) return Number.NaN
  return new Date(value.trim().replace(' ', 'T')).getTime()
}

/**
 * 把「已在内存里的任务」和「服务端列表行」合并成一条。
 * - 服务端行没有 status，所以状态一律沿用内存里的（绝不凭空造一个状态，
 *   否则会把正在跑 / 已 SUCCESS 的任务打回 PENDING）。
 * - 内容字段（markdown / transcript / audioMeta）只在内存里为空时才用服务端信息补齐，
 *   已有内容不覆盖。
 * - groupId / groupName / platform / createdAt（以及标题）以服务端为准。
 */
const mergeServerRow = (task: Task, row: TaskListRow): Task => ({
  ...task,
  platform: row.platform || task.platform,
  groupId: row.group_id ?? null,
  groupName: row.group_name || '',
  createdAt: task.createdAt || row.created_at || '',
  audioMeta: {
    ...task.audioMeta,
    // 列表重载不重新引入封面：列表行只记元信息，封面留给单篇 rehydrateTask。
    cover_url: task.audioMeta.cover_url || '',
    title: task.audioMeta.title || row.title || '',
    video_id: task.audioMeta.video_id || row.video_id || '',
    platform: task.audioMeta.platform || row.platform || '',
  },
})

/**
 * 服务端有、内存里没有的行 —— 用 emptyTask 起一条 PENDING 记录。
 * 前端刷新后只有列表元信息可用，状态留给轮询 / rehydrateTask 去修正。
 */
const taskFromServerRow = (row: TaskListRow): Task => ({
  ...emptyTask(row.task_id, row.platform || '', {} as Task['formData']),
  groupId: row.group_id ?? null,
  groupName: row.group_name || '',
  createdAt: row.created_at || '',
  audioMeta: {
    cover_url: '',
    duration: 0,
    file_path: '',
    platform: row.platform || '',
    raw_info: null,
    title: row.title || '',
    video_id: row.video_id || '',
  },
})

export const useTaskStore = create<TaskStore>()((set, get) => ({
  tasks: [],
  tasksLoadError: null,
  currentTaskId: null,

  addPendingTask: (
    taskId: string,
    platform: string,
    formData: Task['formData'],
    groupName?,
    groupId?
  ) =>
    set(state => ({
      tasks: [
        // groupId / groupName 一起写：NoteHistory 要求两者同时存在才归组，
        // 只写组名会让刚提交的任务先落到「未分组」段（spec 009 决策 4）。
        // groupId 为 null（后端整批未建组）时保持 emptyTask 的 null，不造假的 id。
        {
          ...emptyTask(taskId, platform, formData),
          groupName: groupName || '',
          groupId: groupId || null,
        },
        ...state.tasks,
      ],
      currentTaskId: taskId, // 默认设置为当前任务
    })),

  updateTaskContent: (id, data) =>
    set(state => ({
      tasks: state.tasks.map(task => {
        if (task.id !== id) return task

        // 成功状态默认幂等；但如果这次带了 markdown，则允许把结果补写进去，
        // 避免“先写 SUCCESS、后写 markdown”被早退规则吞掉。
        if (task.status === 'SUCCESS' && data.status === 'SUCCESS' && !data.markdown) {
          return task
        }

        // markdown 直接覆盖（版本功能已删除，spec 008）
        return { ...task, ...data }
      }),
    })),

  updateTaskStatus: (id, data) =>
    set(state => ({
      tasks: state.tasks.map(task => {
        if (task.id !== id) return task
        // 已是终态就不再被迟到的进度帧覆盖回「进行中」。
        if (task.status === 'SUCCESS' && data.status !== 'SUCCESS') return task
        if (task.status === 'FAILED' && data.status === undefined) return task
        if (
          data.revision !== undefined &&
          task.revision !== undefined &&
          data.revision <= task.revision
        )
          return task
        return { ...task, ...data }
      }),
    })),

  rehydrateTask: async (id: string) => {
    try {
      const res = (await get_task_status(id)) as unknown as TaskStatusPayload | undefined
      const raw: TaskStatusPayload | undefined =
        res?.data && res?.status === undefined ? (res.data as TaskStatusPayload) : res
      if (!raw) return null

      const nested = raw.progress
      const progress: TaskProgress =
        nested && typeof nested === 'object' ? (nested as TaskProgress) : {}
      const result = raw.result ?? {}
      const progressValue =
        raw.progress_value ?? (typeof nested === 'number' ? nested : (progress.progress ?? null))

      const patch: Partial<Omit<Task, 'id' | 'createdAt'>> = {
        status: (raw.status || 'PENDING') as TaskStatus,
        stage: raw.stage ?? progress.stage ?? null,
        stageLabel: raw.stage_label ?? raw.stageLabel ?? progress.stageLabel ?? null,
        progress: progressValue,
        stageProgress: raw.stage_progress ?? raw.stageProgress ?? progress.stageProgress ?? null,
        message: raw.message ?? progress.message ?? null,
        detail: raw.detail ?? progress.detail ?? null,
        updatedAt: raw.updated_at ?? raw.updatedAt ?? progress.updatedAt ?? null,
      }
      if (result.markdown) patch.markdown = result.markdown
      if (result.transcript) patch.transcript = result.transcript
      if (result.audio_meta) patch.audioMeta = result.audio_meta

      // 本地没有这条任务（例如刷新页面后）就补一条，否则只做字段合并。
      if (!get().tasks.some(task => task.id === id)) {
        set(state => ({
          tasks: [
            {
              ...emptyTask(id, result.audio_meta?.platform || '', {} as Task['formData']),
              ...patch,
            } as Task,
            ...state.tasks,
          ],
        }))
      } else {
        get().updateTaskContent(id, patch)
      }
      return get().tasks.find(task => task.id === id) || null
    } catch (e) {
      console.warn(`任务 ${id} 内容回填失败`, e)
      return null
    }
  },

  getCurrentTask: () => {
    const currentTaskId = get().currentTaskId
    return get().tasks.find(task => task.id === currentTaskId) || null
  },

  loadTasks: async () => {
    try {
      const payload = (await listTasks()) as unknown as
        | { tasks?: TaskListRow[]; total?: number }
        | TaskListRow[]
        | undefined
      // 正常是 `{tasks, total}`；历史上有的接口会自己再套一层，这里两者都兼容。
      const rows: TaskListRow[] = Array.isArray(payload) ? payload : (payload?.tasks ?? [])
      // 请求成功但一行都没有，是真空态而不是失败态：先把上一次的错误清掉。
      set({ tasksLoadError: null })
      if (!Array.isArray(rows) || rows.length === 0) return

      set(state => {
        const inMemory = new Map(state.tasks.map(task => [task.id, task]))
        const merged = rows.map(row =>
          inMemory.has(row.task_id)
            ? mergeServerRow(inMemory.get(row.task_id) as Task, row)
            : taskFromServerRow(row)
        )

        // 内存里还有、但服务端列表里没有的任务：保留（可能刚提交、还没落库）。
        const serverIds = new Set(rows.map(row => row.task_id))
        const localOnly = state.tasks.filter(task => !serverIds.has(task.id))

        const ordered = [...merged, ...localOnly]
        if (ordered.every(task => Number.isFinite(parseServerTime(task.createdAt)))) {
          // 新的在前；时间相同（或都是空）时用插入顺序稳定兜底。
          ordered.sort((a, b) => parseServerTime(b.createdAt) - parseServerTime(a.createdAt))
        } else {
          console.warn('任务列表存在无法解析的 created_at，保持插入顺序')
        }

        return { tasks: ordered }
      })
    } catch (e) {
      console.warn('任务列表重载失败', e)
      set({ tasksLoadError: e instanceof Error ? e.message : String(e) })
    }
  },

  removeTask: async id => {
    // 乐观删除：先本地摘掉，再打后端。失败也不回滚 —— 下次 loadTasks 会把它带回来，
    // 而本地已经有了「服务端多出来的行」这条合并路径。
    set(state => ({
      tasks: state.tasks.filter(task => task.id !== id),
      currentTaskId: state.currentTaskId === id ? null : state.currentTaskId,
    }))

    // 按 task_id 删（后端会连这个任务的产物文件一起删）。
    // store 里不弹 toast：调用方（NoteHistory）自己决定要不要提示。
    try {
      await deleteTaskRecord(id)
    } catch (e) {
      console.warn(`任务 ${id} 删除失败`, e)
    }
  },

  removeTasks: async ids => {
    // 批量版 removeTask：同样乐观删除，但整批只打**一次**请求 —— 1000 条逐条请求
    // 会把浏览器连接池和 SQLite 写锁一起打满（spec 010）。
    const unique = Array.from(new Set(ids.filter(Boolean)))
    if (!unique.length) return null
    const doomed = new Set(unique)

    set(state => ({
      tasks: state.tasks.filter(task => !doomed.has(task.id)),
      currentTaskId:
        state.currentTaskId && doomed.has(state.currentTaskId) ? null : state.currentTaskId,
    }))

    try {
      const result = await deleteTaskRecords(unique)
      // 后端逐条隔离，没删掉的（多数是「任务仍在执行」）会在下一轮 loadTasks 被带回来。
      return result
    } catch (e) {
      console.warn('批量删除任务失败', e)
      return null
    }
  },

  clearTasks: () => set({ tasks: [], currentTaskId: null }),

  setCurrentTask: taskId => set({ currentTaskId: taskId }),
}))
