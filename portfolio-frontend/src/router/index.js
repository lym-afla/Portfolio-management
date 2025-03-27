import { createRouter, createWebHistory } from 'vue-router'
// import { ref } from 'vue'
import store from '@/store'
import OpenPositionsPage from '../views/OpenPositionsPage.vue'
import LoginPage from '../views/LoginPage.vue'
import RegisterPage from '../views/RegisterPage.vue'
import ProfileLayout from '../views/profile/ProfileLayout.vue'
import ProfilePage from '../views/profile/ProfilePage.vue'
import ProfileEdit from '../views/profile/ProfileEdit.vue'
import ProfileSettings from '../views/profile/ProfileSettings.vue'
import ClosedPositionsPage from '../views/ClosedPositionsPage.vue'
import TransactionsPage from '../views/TransactionsPage.vue'
import DatabasePage from '../views/DatabasePage.vue'
import PricesPage from '../views/database/PricesPage.vue'
import AccountsPage from '../views/database/AccountsPage.vue'
import SecuritiesPage from '../views/database/SecuritiesPage.vue'
import DashboardPage from '../views/DashboardPage.vue'
import FXPage from '../views/database/FXPage.vue'
import SummaryPage from '../views/SummaryPage.vue'
import SecurityDetailPage from '../views/database/SecurityDetailPage.vue'
import BrokersPage from '../views/database/BrokersPage.vue'

// export const loading = ref(true)

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: LoginPage,
    meta: { requiresAuth: false, paddingTop: '0px' },
  },
  {
    path: '/register',
    name: 'Register',
    component: RegisterPage,
    meta: { requiresAuth: false, paddingTop: '0px' },
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
    meta: { requiresAuth: true, paddingTop: '50px' },
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
    meta: { requiresAuth: true, paddingTop: '70px' },
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
    meta: { requiresAuth: true, paddingTop: '70px' },
  },
  {
    path: '/summary',
    name: 'Summary',
    component: SummaryPage,
    meta: { requiresAuth: true, paddingTop: '70px' },
  },
  {
    path: '/',
    redirect: '/dashboard',
  },
]

const router = createRouter({
  history: createWebHistory(process.env.BASE_URL),
  routes,
})

router.beforeEach(async (to, from, next) => {
  const guardId = Date.now()
  console.log(`[Router][${guardId}] Navigation from ${from.path} to ${to.path}`)

  // Always ensure app is initialized
  if (!store.state.isInitialized) {
    console.log(`[Router][${guardId}] Initializing app...`)
    const result = await store.dispatch('initializeApp')
    console.log(`[Router][${guardId}] Initialization result:`, result)
  }

  const isAuthenticated = store.getters.isAuthenticated
  console.log(`[Router][${guardId}] Auth state:`, {
    isAuthenticated,
    hasToken: !!store.state.accessToken,
    hasUser: !!store.state.user,
    toPath: to.path,
    requiresAuth: to.matched.some((record) => record.meta.requiresAuth),
  })

  // Handle auth-required routes
  if (to.matched.some((record) => record.meta.requiresAuth)) {
    if (!isAuthenticated) {
      console.log(
        `[Router][${guardId}] Auth required but not authenticated, redirecting to login`
      )
      next({ name: 'Login' })
      return
    }
  }

  // Redirect authenticated users away from login/register
  if ((to.name === 'Login' || to.name === 'Register') && isAuthenticated) {
    console.log(
      `[Router][${guardId}] Already authenticated, redirecting to profile`
    )
    next({ name: 'Profile' })
    return
  }

  console.log(`[Router][${guardId}] Proceeding with navigation`)
  next()
})

export default router
