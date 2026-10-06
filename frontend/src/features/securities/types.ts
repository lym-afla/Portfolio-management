// D7 security feature contracts. Sections receive display-only views built
// from accepted server responses; every value stays the server-issued
// display string (commas, precision, missing-value markers) and is never
// converted through Number.

export interface DetailField {
  label: string
  value: string
  explanation?: string
}

export interface SecurityOverviewView {
  securityId: number
  name: string
  identifier: string
  instrumentType: string
  currency: string
  fields: readonly DetailField[]
}

export interface BondMetadataView {
  primary: readonly DetailField[]
  coupon: readonly DetailField[]
}

export interface CryptoRewardsView {
  nativeQuantity: string
  fiatValue: string
}

export interface SecurityActivityTransaction {
  readonly id: number | string
  readonly [field: string]: unknown
}

export interface SecurityActivityView {
  transactions: readonly SecurityActivityTransaction[]
  totalItems: number
  page: number
  itemsPerPage: number
  pageCount: number
}
