// Stable categorical style mapping for the NAV pilot (C3). Colors come from
// the shared theme tokens and are assigned by a deterministic hash of the
// SERVER series id — never by label text or array position — so reordering
// or adding a category can never recolor surviving series. The two IRR lines
// keep fixed, visually distinct solid/dashed styles independent of any
// category entering the chart.
import { palette } from '@/theme'

const SERIES_PALETTE: readonly string[] = [
  palette.primary,
  palette.success,
  palette.warning,
  palette.info,
  '#7A4E2D',
  '#607D8B',
  '#8E4585',
  '#00838F',
  palette.secondary,
  '#6D4C41',
  '#9E9D24',
  palette.error,
]

// djb2: stable across sessions and insertions.
function hashId(id: string): number {
  let hash = 5381
  for (let index = 0; index < id.length; index += 1) {
    hash = ((hash << 5) + hash + id.charCodeAt(index)) | 0
  }
  return Math.abs(hash)
}

export function seriesColor(id: string): string {
  if (id === 'metric:irr_inception') return palette.error
  if (id === 'metric:irr_interval') return palette.success
  return SERIES_PALETTE[hashId(id) % SERIES_PALETTE.length]
}

export function irrLineStyle(id: string): { type: 'solid' | 'dashed'; width: number } {
  return id === 'metric:irr_interval' ? { type: 'dashed', width: 2 } : { type: 'solid', width: 2 }
}
