import { createRouter, createWebHistory } from 'vue-router'
import { ref } from 'vue'
import DashboardPage from '../views/DashboardPage.vue'
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
import BrokersPage from '../views/database/BrokersPage.vue'
import SecuritiesPage from '../views/database/SecuritiesPage.vue'

export const loading = ref(true)

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: LoginPage,
    meta: { requiresAuth: false }
  },
  {
    path: '/register',
    name: 'Register',
    component: RegisterPage,
    meta: { requiresAuth: false }
  },
  {
    path: '/dashboard',
    name: 'Dashboard',
    component: DashboardPage,
    meta: { requiresAuth: true }
  },
  {
    path: '/open-positions',
    name: 'OpenPositions',
    component: OpenPositionsPage,
    meta: { requiresAuth: true }
  },
  {
    path: '/closed-positions',
    name: 'ClosedPositions',
    component: ClosedPositionsPage,
    meta: { requiresAuth: true }
  },
  {
    path: '/transactions',
    name: 'Transactions',
    component: TransactionsPage,
    meta: { requiresAuth: true }
  },
  {
    path: '/profile',
    component: ProfileLayout,
    meta: { requiresAuth: true },
    children: [
      {
        path: '',
        name: 'Profile',
        component: ProfilePage
      },
      {
        path: 'edit',
        name: 'ProfileEdit',
        component: ProfileEdit
      },
      {
        path: 'settings',
        name: 'ProfileSettings',
        component: ProfileSettings
      }
    ]
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
        path: 'prices',
        name: 'Prices',
        component: PricesPage,
      },
      {
        path: 'securities',
        name: 'Securities',
        component: SecuritiesPage,
      },
    ]
  },
  {
    path: '/',
    redirect: '/dashboard'
  }
]

const router = createRouter({
  history: createWebHistory(process.env.BASE_URL),
  routes
})

router.beforeEach((to, from, next) => {
  loading.value = true
  next()
})

export default router