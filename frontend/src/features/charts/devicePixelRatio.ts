// Phase C Task 6: sharp charts at native zoom. zrender's canvas painter fixes
// the backing-store devicePixelRatio at echarts.init and Painter.resize()
// never re-reads it, so a DPR change (browser native zoom, monitor switch)
// leaves the stale low-resolution bitmap CSS-scaled. The only public-API fix
// is re-initialization. This watcher arms a self-re-arming matchMedia
// resolution query for the CURRENT dpr; when it stops matching, the dpr has
// changed, so the caller re-initializes its chart and the query re-arms for
// the new value. Chart wrappers bump a :key on their VChart — interaction
// state lives outside the chart and survives the fresh painter.
import { onMounted, onUnmounted } from 'vue'

export function watchDevicePixelRatio(onChange: (dpr: number) => void): void {
  let query: MediaQueryList | null = null
  let handler: (() => void) | null = null
  let active = true

  const arm = (dpr: number): void => {
    if (!active || typeof window.matchMedia !== 'function') return
    query = window.matchMedia(`(resolution: ${dpr}dppx)`)
    handler = () => {
      if (!active) return
      const next = window.devicePixelRatio || 1
      // Re-arm FIRST: a fast multi-step zoom fires one change per step and
      // the final value must always have a live query.
      arm(next)
      onChange(next)
    }
    query.addEventListener('change', handler, { once: true })
  }

  onMounted(() => arm(window.devicePixelRatio || 1))
  onUnmounted(() => {
    active = false
    if (query && handler) query.removeEventListener('change', handler)
    query = null
    handler = null
  })
}
