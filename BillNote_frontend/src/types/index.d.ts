export interface IProvider {
  id: string
  name: string
  logo: string
  type: string
  apiKey: string
  baseUrl: string
  enabled: number
  /** 同一时刻最多在途的请求数，默认 4 */
  maxConcurrency?: number
  /** 每分钟最多请求次数，默认 600 */
  maxRpm?: number
}
export interface IResponse<T> {
  code: number
  data: T
  msg: string
}
