export type AccountSelection =
  | Readonly<{ type: 'all'; id: null }>
  | Readonly<{ type: 'account' | 'broker' | 'group'; id: number }>

export interface PortfolioContext {
  readonly revision: number
  readonly accountSelection: AccountSelection
  readonly effectiveCurrentDate: string | null
  readonly currency: string | null
  readonly digits: number
}
