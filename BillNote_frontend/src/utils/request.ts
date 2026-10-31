import axios, { AxiosInstance, AxiosResponse } from 'axios'
import toast from 'react-hot-toast'
import { translate } from '@/ember/i18n/locale'
import type { MessageKey } from '@/ember/i18n/strings'

// 统一响应类型
export interface IResponse<T = unknown> {
  code: number
  msg: string
  data: T
}

// 允许调用方在 axios 配置里带 suppressToast: true，让拦截器对【预期内的失败】
// 不弹全局红 toast（例如 onboarding 撞名重试、轮询健康检查）。业务代码自己 catch 处理。
declare module 'axios' {
  export interface AxiosRequestConfig {
    suppressToast?: boolean
  }
}

/**
 * 后端错误 → 用户语言。
 *
 * 后端返回的 msg 是中文的（例如「该视频正在生成中，请稍候」），直接弹出来会让英文界面
 * 里蹦出中文。后端在结构化错误里已经带了稳定的 data.reason，这里按 reason 查文案，
 * 查不到才回退到后端原文 —— 回退原文总比吞掉错误强。
 */
const REASON_KEYS: Record<string, MessageKey> = {
  task_in_progress: 'serverError.taskInProgress',
  insufficient_disk_space: 'serverError.insufficientDiskSpace',
  transcriber_model_not_ready: 'serverError.transcriberNotReady',
  already_generated: 'serverError.alreadyGenerated',
  group_create_failed: 'serverError.groupCreateFailed',
  provider_name_exists: 'serverError.providerNameExists',
  model_name_exists: 'serverError.modelNameExists',
}

export function localizedError(res: IResponse | undefined, fallbackKey: MessageKey): string {
  const reason = (res?.data as { reason?: string } | null | undefined)?.reason
  const key = reason ? REASON_KEYS[reason] : undefined
  if (key) return translate(key)
  return res?.msg || translate(fallbackKey)
}
// 模拟一个消息提示函数 (实际项目中会使用UI库的组件，如 Ant Design 的 message 或 Element UI 的 ElMessage)
// This function simulates a message display (in real projects, you'd use a UI library's component)

const baseURL = import.meta.env.VITE_API_BASE_URL

// 创建实例
const request: AxiosInstance = axios.create({
  baseURL: baseURL || '/api',
  // 30s：抽帧/转写时后端 CPU 打满，状态轮询偶发超过 10s 会被 axios 掐断，
  // 前端就会误判成网络错误（历史上导致任务被误标失败 + 重复提交）。
  timeout: 30000,
})

// 响应拦截器
request.interceptors.response.use(
  (response: AxiosResponse<IResponse>) => {
    const res = response.data
    if (res.code === 0) {
      // 业务成功，可以根据需要显示成功消息，或者不显示（如果操作本身就是可见的）
      // showMessage('success', res.msg || '操作成功'); // 如果需要显示成功消息
      // 返回 data 部分，简化后续业务代码。
      //
      // 这里的断言是刻意保留的：拦截器的语义就是「把信封拆掉」，而 axios 的
      // AxiosInterceptorFulfilled 类型要求回调返回 AxiosResponse。两者不可能同时
      // 满足，所以类型层必须在这里断一次。真正的解法是给 55 个调用点换成
      // 「返回解包数据」的客户端门面，那是一次独立的 HTTP 层重构，不该混进本次改版。
      return res.data as unknown as AxiosResponse
    } else {
      // 业务错误，统一显示后端返回的错误消息（除非调用方显式 suppressToast）
      if (!response.config?.suppressToast) {
        toast.error(localizedError(res, 'serverError.generic'))
      }
      return Promise.reject(res) // 拒绝Promise，让业务代码可以捕获并处理
    }
  },
  error => {
    const suppress = error?.config?.suppressToast === true
    // 网络/服务器错误
    const res = error?.response?.data as IResponse | undefined
    if (res) {
      // 如果后端有返回错误信息，则显示后端信息
      if (!suppress) toast.error(localizedError(res, 'serverError.server'))
      return Promise.reject(res)
    } else {
      // 没有响应数据（如网络中断），显示通用网络错误
      if (!suppress) toast.error(translate('serverError.network'))
      return Promise.reject({
        code: -1,
        msg: '请求失败，请检查网络连接',
        data: null,
      } as IResponse)
    }
  }
)

export default request
