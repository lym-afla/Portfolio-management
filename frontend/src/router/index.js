import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import logger from '@/utils/logger'
import { routeChunkRecovery } from './chunkRecovery'
const OpenPositionsPage = () => import('../views/OpenPositionsPage.vue')
const LoginPage = () => import('../views/LoginPage.vue')
const RegisterPage = () => import('../views/RegisterPage.vue')
const ProfileLayout = () => import('../views/profile/ProfileLayout.vue')
const ProfilePage = () => import('../views/profile/ProfilePage.vue')
const ProfileEdit = () => import('../views/profile/ProfileEdit.vue')
const ProfileSettings = () => import('../views/profile/ProfileSettings.vue')
const ClosedPositionsPage = () => import('../views/ClosedPositionsPage.vue')
const TransactionsPage = () => import('../views/TransactionsPage.vue')
const DatabasePage = () => import('../views/DatabasePage.vue')
const PricesPage = () => import('../views/database/PricesPage.vue')
const AccountsPage = () => import('../views/database/AccountsPage.vue')
const SecuritiesPage = () => import('../views/database/SecuritiesPage.vue')
const DashboardPage = () => import('../views/DashboardPage.vue')
const FXPage = () => import('../views/database/FXPage.vue')
const SummaryPage = () => import('../views/SummaryPage.vue')
const SecurityDetailPage = () => import('../views/database/SecurityDetailPage.vue')
const BrokersPage = () => import('../views/database/BrokersPage.vue')

// Development-only debug components
const AuthDebugPanel =
  import.meta.env.DEV
    ? () => import('../components/AuthDebugPanel.vue')
    : null

// export const loading = ref(true)

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: LoginPage,
    meta: { requiresAuth: false },
  },
  {
    path: '/register',
    name: 'Register',
    component: RegisterPage,
    meta: { requiresAuth: false },
  },
  {
    path: '/dashboard',
    name: 'Dashboard',
    component: DashboardPage,
    meta: { requiresAuth: true },
  },
  {
    path: '/open-positions',
    name: 'OpenPositions',
    component: OpenPositionsPage,
    meta: { requiresAuth: true },
  },
  {
    path: '/closed-positions',
    name: 'ClosedPositions',
    component: ClosedPositionsPage,
    meta: { requiresAuth: true },
  },
  {
    path: '/transactions',
    name: 'Transactions',
    component: TransactionsPage,
    meta: { requiresAuth: true },
  },
  {
    path: '/profile',
    component: ProfileLayout,
    meta: { requiresAuth: true },
    children: [
      {
        path: '',
        name: 'Profile',
        component: ProfilePage,
      },
      {
        path: 'edit',
        name: 'ProfileEdit',
        component: ProfileEdit,
      },
      {
        path: 'settings',
        name: 'ProfileSettings',
        component: ProfileSettings,
      },
    ],
  },
  {
    path: '/database',
    name: 'Database',
    component: DatabasePage,
    meta: { requiresAuth: true },
    children: [
      {
        path: 'brokers',
        name: 'Brokers',
        component: BrokersPage,
      },
      {
        path: 'accounts',
        name: 'Accounts',
        component: AccountsPage,
      },
      {
        path: 'prices',
        name: 'Prices',
        component: PricesPage,
      },
      {
        path: 'securities',
        name: 'Securities',
        component: SecuritiesPage,
      },
      {
        path: 'fx',
        name: 'FX',
        component: FXPage,
      },
    ],
  },
  {
    path: '/database/securities/:id',
    name: 'SecurityDetail',
    component: SecurityDetailPage,
    meta: { requiresAuth: true },
  },
  {
    path: '/summary',
    name: 'Summary',
    component: SummaryPage,
    meta: { requiresAuth: true },
  },
  // Development-only debug route
  ...(import.meta.env.DEV && AuthDebugPanel
    ? [
        {
          path: '/debug-auth',
          name: 'DebugAuth',
          component: AuthDebugPanel,
          meta: { requiresAuth: true },
        },
      ]
    : []),
  {
    path: '/',
    redirect: '/dashboard',
  },
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
})

router.onError(error => routeChunkRecovery.capture(error))
router.afterEach((_to, _from, failure) => { if (!failure) routeChunkRecovery.clear() })

router.beforeEach(async (to, from, next) => {
  const guardId = Date.now()
  logger.log(
    'Router',
    `[${guardId}] Navigation from ${from.path} to ${to.path}`
  )

  const authStore = useAuthStore()

  // Check if user is going to auth pages
  const goingToAuthPage = to.name === 'Login' || to.name === 'Register'

  // Skip initialization completely for auth pages
  if (goingToAuthPage) {
    logger.log(
      'Router',
      `[${guardId}] Going to auth page, skipping initialization`
    )
    // But first check if already authenticated
    if (authStore.isAuthenticated) {
      logger.log(
        'Router',
        `[${guardId}] User is authenticated, redirecting to Profile`
      )
      next({ name: 'Profile' })
      return
    }
    next()
    return
  }

  // For non-auth pages, check initialization
  if (!authStore.isInitialized) {
    logger.log('Router', `[${guardId}] App not initialized, initializing...`)
    try {
      // Set a timeout to prevent infinite initialization
      const initPromise = authStore.initializeApp()
      const timeoutPromise = new Promise((_, reject) => {
        setTimeout(() => reject(new Error('Initialization timeout')), 3000)
      })

      await Promise.race([initPromise, timeoutPromise])
    } catch (error) {
      logger.error(
        'Router',
        `[${guardId}] Initialization failed or timed out:`,
        error
      )
      // Force initialization to complete to prevent infinite loops
      authStore.setInitialized(true)
    }
  }

  // After initialization (successful or not), check authentication
  const isAuthenticated = authStore.isAuthenticated

  // Check if the route requires authentication
  if (to.matched.some((record) => record.meta.requiresAuth)) {
    if (!isAuthenticated) {
      logger.log(
        'Router',
        `[${guardId}] Route requires auth but user is not authenticated, redirecting to login`
      )
      next({ name: 'Login' })
      return
    }
  }

  // Continue navigation
  next()
})

export default router
