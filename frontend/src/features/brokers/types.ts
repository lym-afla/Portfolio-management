// D7 broker feature contracts. Display models are the ONLY shape that
// crosses into list components: an allowlist of rendered fields, never the
// raw wire records. Credential drafts live in the form for its open
// lifetime and cross to the API owner as typed intents.

export type BrokerProvider = 'tinkoff' | 'ib' | 'bybit' | 'okx'

export interface BrokerConnectionKey {
  provider: BrokerProvider
  tokenId: number
}

export interface BrokerStatusChip {
  readonly text: string
  readonly tone: 'warning' | 'error'
}

export interface BrokerConnectionDisplay {
  readonly provider: BrokerProvider
  readonly tokenId: number
  readonly label: string
  readonly statusIcon: 'mdi-check-circle' | 'mdi-close-circle'
  readonly statusLabel: string
  readonly statusTone: 'success' | 'error'
  readonly createdAtLabel: string
  readonly chips: readonly BrokerStatusChip[]
  readonly canTest: boolean
  readonly canRevoke: boolean
  readonly canDelete: boolean
  readonly busy: boolean
}

export const BROKER_PROVIDERS: readonly BrokerProvider[] = [
  'tinkoff',
  'ib',
  'bybit',
  'okx',
]

export function isBrokerProvider(value: unknown): value is BrokerProvider {
  return (
    value === 'tinkoff' || value === 'ib' || value === 'bybit' || value === 'okx'
  )
}

export function brokerKey(key: BrokerConnectionKey): string {
  return `${key.provider}:${key.tokenId}`
}

// Provider-specific credential drafts (form-owned, ephemeral). Field names
// mirror the incumbent payloads; the owner maps them onto the wire adapters.
export interface TinkoffTokenDraft {
  readonly provider: 'tinkoff'
  readonly brokerId: number
  readonly token: string
  readonly tokenType: 'read_only' | 'full_access'
  readonly sandboxMode: boolean
}

export interface InteractiveBrokersTokenDraft {
  readonly provider: 'ib'
  readonly brokerId: number
  readonly token: string
  readonly accountId: string
  readonly paperTrading: boolean
}

export interface BybitTokenDraft {
  readonly provider: 'bybit'
  readonly brokerId: number
  readonly apiKey: string
  readonly apiSecret: string
  readonly testnet: boolean
}

export interface OkxTokenDraft {
  readonly provider: 'okx'
  readonly brokerId: number
  readonly apiKey: string
  readonly apiSecret: string
  readonly passphrase: string
  readonly simulatedTrading: boolean
}

export type BrokerCredentialDraft =
  | TinkoffTokenDraft
  | InteractiveBrokersTokenDraft
  | BybitTokenDraft
  | OkxTokenDraft

export type BrokerSaveOutcome =
  | 'saved'
  | 'reactivated'
  | 'already-active'
  | 'rejected'

// The message dialog states the incumbent renders for the two Tinkoff
// long-running branches.
export interface BrokerMessageDialog {
  readonly title: string
  readonly text: string
}

export interface BrokerOption {
  readonly id: number
  readonly name: string
}

export interface BrokerOwnerEvents {
  error(message: string): void
  success(message: string): void
  info(message: string): void
}
