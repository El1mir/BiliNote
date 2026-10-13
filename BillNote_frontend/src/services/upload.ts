import request from '@/utils/request' // 你项目里封装好的axios或者fetch

/** POST /upload 返回 R.success({"url": ...})，拦截器解包后 data 即 { url }。 */
export const uploadFile = async (formData: FormData): Promise<{ url: string }> => {
  const response = await request.post('/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  })
  return (response as { url: string }) ?? { url: '' }
}
