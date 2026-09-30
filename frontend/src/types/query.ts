import type { PortfolioContext } from './portfolioContext'
import type { SortBy } from './portfolioTables'

export interface TableQueryParams {
  readonly context: PortfolioContext
  readonly dateFrom: string | null
  readonly dateTo: string | null
  readonly page: number
  readonly itemsPerPage: number
  readonly search: string
  readonly sortBy: Readonly<SortBy>
}

export function snapshotContext(context: PortfolioContext): PortfolioContext {
  return Object.freeze({ ...context, accountSelection: Object.freeze({ ...context.accountSelection }) })
}

export function snapshotTableQuery(params: TableQueryParams): TableQueryParams {
  return Object.freeze({
    ...params,
    context: snapshotContext(params.context),
    sortBy: Object.freeze({ ...params.sortBy }),
  })
}
