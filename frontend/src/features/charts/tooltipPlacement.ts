// Viewport-aware placement for the NAV axis tooltip. ECharts' own `confine`
// stops at the chart container, which (a) can sit underneath the fixed
// workspace header — an overlay, not a clipping ancestor — and (b) clips its
// children with overflow:hidden. The tooltip therefore renders into
// document.body (appendTo) and the position callback pins it inside the
// UNOBSCURED viewport band: below the fixed header's measured bottom edge,
// inside the viewport on every side, horizontally within the chart. With
// appendTo, ECharts maps the callback's container-relative coordinates onto
// the body-attached element itself.

export interface TooltipPlacementInput {
  pointX: number
  pointY: number
  contentWidth: number
  contentHeight: number
  containerLeft: number
  containerTop: number
  /** Allowed viewport rect (the unobscured band). */
  bounds: { left: number; top: number; right: number; bottom: number }
}

/** Container-coordinate placement whose viewport result stays inside
    `bounds`: below the cursor when the box fits the band, above the cursor
    when below would overflow, clamped on every side, and pinned at the band
    top when the band is too short for the whole box (degenerate). */
export function clampTooltipPlacement(input: TooltipPlacementInput): { x: number; y: number } {
  const { pointX, pointY, contentWidth, contentHeight, containerLeft, containerTop, bounds } = input
  const minX = bounds.left - containerLeft + 2
  const maxX = Math.max(minX, bounds.right - containerLeft - contentWidth - 2)
  const minY = bounds.top - containerTop + 2
  const maxY = Math.max(minY, bounds.bottom - containerTop - contentHeight - 2)
  const bandBottom = bounds.bottom - containerTop
  const belowY = pointY + 18
  const aboveY = pointY - contentHeight - 14
  const candidateY = belowY + contentHeight <= bandBottom ? belowY : aboveY >= minY ? aboveY : belowY
  return {
    x: Math.round(Math.min(Math.max(pointX + 14, minX), maxX)),
    y: Math.round(Math.min(Math.max(candidateY, minY), maxY)),
  }
}

/** First viewport y (top to bottom) whose hit-test target is not part of a
    fixed/sticky overlay — the top of the unobscured content band, whatever
    elements compose the header. The tooltip being placed is hidden during
    sampling so its own box cannot shadow the measurement. */
export function firstUnobscuredViewportY(container: Element, hidden: { style: CSSStyleDeclaration } | null): number {
  const rect = container.getBoundingClientRect()
  const doc = container.ownerDocument
  const view = doc.defaultView
  if (!view) return Math.max(rect.top, 0)
  const centerX = rect.left + Math.min(rect.width / 2, view.innerWidth / 2)
  const isOverlay = (element: Element | null): boolean => {
    for (let node: Element | null = element; node && node !== doc.body; node = node.parentElement) {
      const position = view.getComputedStyle(node).position
      if (position === 'fixed' || position === 'sticky') return true
    }
    return false
  }
  const restore = hidden ? hidden.style.visibility : null
  if (hidden) hidden.style.visibility = 'hidden'
  try {
    const limit = Math.min(rect.bottom - 1, view.innerHeight - 1)
    for (let y = Math.max(rect.top, 0) + 2; y < limit; y += 2) {
      const hit = doc.elementFromPoint(centerX, y)
      if (hit && !isOverlay(hit)) return y
    }
    return Math.max(rect.top, 0)
  } finally {
    if (hidden) hidden.style.visibility = restore ?? ''
  }
}

type TooltipPoint = { x: number; y: number } | number[]

/** The allocation pies (C4) and the security histories reuse the same
    placement contract as the NAV pilot: body-attached tooltip pinned inside
    the unobscured viewport band. */
export const allocationTooltipPosition = navTooltipPosition
export const securityTooltipPosition = navTooltipPosition

/** The tooltip `position` callback: translate the unobscured viewport band
    into container coordinates and clamp the box into it. Falls back to the
    default below-cursor offset when the container is unreachable. */
export function navTooltipPosition(context: {
  point: TooltipPoint
  dom: { style: CSSStyleDeclaration } | null
  size: { contentSize: number[]; viewSize: number[] }
  resolveContainer?: () => HTMLElement | null
}): [number, number] {
  const pointX = Array.isArray(context.point) ? context.point[0] : context.point.x
  const pointY = Array.isArray(context.point) ? context.point[1] : context.point.y
  const fallback: [number, number] = [Math.round(pointX) + 14, Math.round(pointY) + 18]
  const dom = context.dom
  if (!dom) return fallback
  const container = context.resolveContainer?.() ?? null
  if (!container) return fallback
  const rect = container.getBoundingClientRect()
  if (rect.width === 0 || rect.height === 0) return fallback
  const view = container.ownerDocument.defaultView
  if (!view) return fallback
  const placement = clampTooltipPlacement({
    pointX,
    pointY,
    contentWidth: context.size.contentSize[0],
    contentHeight: context.size.contentSize[1],
    containerLeft: rect.left,
    containerTop: rect.top,
    bounds: {
      left: Math.max(0, rect.left),
      top: firstUnobscuredViewportY(container, dom),
      right: Math.min(view.innerWidth, rect.right),
      bottom: view.innerHeight,
    },
  })
  return [placement.x, placement.y]
}
