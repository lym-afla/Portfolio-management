import { expect, it, vi } from 'vitest'
import { shallowMount } from '@vue/test-utils'
import { generateVuetifyStubs } from '../test-utils'
import ProfileLayout from '@/views/profile/ProfileLayout.vue'
const { logout } = vi.hoisted(() => ({
  logout: vi.fn().mockResolvedValue(undefined),
}))
vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ logout, clearTokens: vi.fn() }),
}))
vi.mock('@/services/api', () => ({
  logout: vi.fn().mockResolvedValue(undefined),
  deleteUserAccount: vi.fn(),
}))
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useRoute: () => ({ path: '/profile' }),
}))
it('routes profile logout through the same immediate auth epoch invalidation', async () => {
  const wrapper = shallowMount(ProfileLayout, {
    global: {
      stubs: {
        ...generateVuetifyStubs(),
        VContainer: { template: '<div><slot /></div>' },
        VRow: true,
        VDialog: true,
      },
    },
  })
  await wrapper.vm.handleLogout()
  expect(logout).toHaveBeenCalledOnce()
  wrapper.unmount()
})
