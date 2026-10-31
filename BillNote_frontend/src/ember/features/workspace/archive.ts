/**
 * Browser-side archive helpers. The backend names the top-level folder inside the
 * zip after the group, so only the outer file name needs cleaning here.
 */

/** Strip the characters Windows/macOS reject in a file name, then collapse runs of space. */
export const sanitizeFileName = (name: string): string => {
  const cleaned = name
    .replace(/[\\/:*?"<>|]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
  return cleaned || 'notes'
}

/**
 * Hand a Blob to the browser's download machinery. Chromium may start handling the
 * download asynchronously, so the object URL is revoked on a later task — revoking in
 * the same task can leave the user with a success toast and no file.
 */
export const saveBlob = (blob: Blob, fileName: string) => {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = fileName
  link.style.display = 'none'
  document.body.appendChild(link)
  link.click()
  window.setTimeout(() => {
    URL.revokeObjectURL(url)
    link.remove()
  }, 1000)
}
