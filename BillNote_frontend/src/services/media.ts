import request from '@/utils/request'

export interface RetentionSettings {
  screenshot_retention_days: number
  media_retention_days: number
}

export interface CleanupPreview {
  count: number
  bytes: number
  by_type: Record<string, { count: number; bytes: number }>
  expires_earliest: string | null
  expires_latest: string | null
}

export interface CleanupRun {
  resource_types: string[]
  expired_only: boolean
  deleted: number
  missing: number
  failed: number
  bytes_freed: number
  completed_at: string
}

export const getRetentionSettings = async (): Promise<RetentionSettings> =>
  (await request.get<RetentionSettings>('/media/settings')) as unknown as RetentionSettings
export const saveRetentionSettings = async (data: RetentionSettings): Promise<RetentionSettings> =>
  (await request.put<RetentionSettings>('/media/settings', data)) as unknown as RetentionSettings
export const getRecentCleanupRuns = async (): Promise<CleanupRun[]> =>
  (await request.get<CleanupRun[]>('/media/cleanup/recent')) as unknown as CleanupRun[]
export const previewMediaCleanup = async (
  resourceTypes: string[],
  expiredOnly: boolean
): Promise<CleanupPreview> =>
  (await request.get<CleanupPreview>('/media/cleanup/preview', {
    params: { resource_types: resourceTypes.join(','), expired_only: expiredOnly },
  })) as unknown as CleanupPreview
export interface CleanupResult {
  scheduled: boolean
  preview: CleanupPreview
  result: { deleted: number; missing: number; failed: number; bytes: number; requested: number }
}

export const runMediaCleanup = async (
  resource_types: string[],
  expired_only: boolean
): Promise<CleanupResult> =>
  (await request.post<CleanupResult>('/media/cleanup', {
    resource_types,
    expired_only,
  })) as unknown as CleanupResult
