/**
 * Transcript filtering, kept out of the component so hit counts can be
 * asserted without a DOM (this repo has no jsdom in devDependencies).
 */
export type TranscriptSegment = { start: number; text: string; end?: number }

/** Case-insensitive substring filter; an empty query returns everything. */
export function filterTranscript<T extends { text: string }>(segments: T[], query: string): T[] {
  const needle = query.trim().toLowerCase()
  if (!needle) return segments
  return segments.filter(segment => segment.text.toLowerCase().includes(needle))
}
