import request from '@/utils/request'

/** POST /upload 返回 R.success({"url": ...})，拦截器解包后 data 即 { url }。 */
export const uploadFile = async (formData: FormData): Promise<{ url: string }> => {
  const response = await request.post('/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  })
  // 拦截器已经把信封解开了，但 request 的静态类型仍是 axios 的响应对象，
  // 所以这里必须经过 unknown 中转 —— 直接断言会被 TS 判定为不重叠。
  return (response as unknown as { url?: string })?.url
    ? (response as unknown as { url: string })
    : { url: '' }
}
