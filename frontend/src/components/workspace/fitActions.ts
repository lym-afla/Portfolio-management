export interface FitActionsInput {
  availableWidth: number
  /** Candidate action widths in presentation order (secondary, then overflow). */
  itemWidths: number[]
  /** Flex column gap between adjacent controls. */
  gap: number
  /** Width of the primary action, which always stays direct. */
  fixedWidth: number
  /** Width of the "More actions" activator, reserved while anything is hidden. */
  menuWidth: number
}

/**
 * Largest ordered prefix of candidate actions that fits beside the always-
 * direct primary action, reserving room for the overflow activator whenever
 * a suffix would remain hidden. Pure and deterministic so the responsive
 * rule is unit-testable without layout.
 */
export function fitVisibleActions(input: FitActionsInput): number {
  const { availableWidth, itemWidths, gap, fixedWidth, menuWidth } = input
  const rowWidth = (visibleCount: number, withMenu: boolean): number => {
    let width = fixedWidth
    for (let index = 0; index < visibleCount; index += 1) {
      width += gap + itemWidths[index]
    }
    if (withMenu) width += gap + menuWidth
    return width
  }
  for (let count = itemWidths.length; count >= 0; count -= 1) {
    const withMenu = count < itemWidths.length
    if (rowWidth(count, withMenu) <= availableWidth) return count
  }
  return 0
}
