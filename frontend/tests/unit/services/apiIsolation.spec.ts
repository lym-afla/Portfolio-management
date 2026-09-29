import { describe, expect, it, vi } from 'vitest'

vi.mock('@/config/axiosConfig', () => { throw new Error('Typed module imported legacy Axios config') })
vi.mock('@/stores/auth', () => { throw new Error('Typed module imported auth store') })
vi.mock('@/stores/app', () => { throw new Error('Typed module imported app store') })
vi.mock('@/router', () => { throw new Error('Typed module imported router') })

describe('strict API leaf modules', () => {
  it('imports without constructing legacy auth, router, or stores', async () => {
    const [portfolio, context, database] = await Promise.all([
      import('@/services/api/portfolio'),
      import('@/services/api/context'),
      import('@/services/api/database'),
    ])
    expect(typeof portfolio.getOpenPositions).toBe('function')
    expect(typeof context.createPortfolioContextBackend).toBe('function')
    expect(typeof database.getFXData).toBe('function')
  })
})
