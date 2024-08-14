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
  // {
  //   path: '/database',
  //   name: 'Database',
  //   component: () => import('../views/DatabasePage.vue'),
  //   meta: { requiresAuth: true },
  //   children: [
  //     {
  //       path: 'brokers',
  //       name: 'Brokers',
  //       component: () => import('../views/database/BrokersPage.vue'),
  //     },
  //     {
  //       path: 'securities',
  //       name: 'Securities',
  //       component: () => import('../views/database/SecuritiesPage.vue'),
  //     },
  //     {
  //       path: 'prices',
  //       name: 'Prices',
  //       component: () => import('../views/database/PricesPage.vue'),
  //     },
  //   ]
  // },
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