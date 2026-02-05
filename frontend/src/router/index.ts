import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'Login',
      component: () => import('@/views/Login.vue'),
      meta: { requiresAuth: false },
    },
    {
      path: '/register',
      name: 'Register',
      component: () => import('@/views/Register.vue'),
      meta: { requiresAuth: false },
    },
    {
      path: '/',
      component: () => import('@/layouts/MainLayout.vue'),
      redirect: '/qa',
      meta: { requiresAuth: true },
      children: [
        {
          path: 'qa',
          name: 'QAPage',
          component: () => import('@/views/QAPage.vue'),
        },
        {
          path: 'job-listings',
          name: 'JobListings',
          component: () => import('@/views/JobListings.vue'),
        },
        {
          path: 'job-listings/:id',
          name: 'JobDetail',
          component: () => import('@/views/JobDetail.vue'),
        },
        {
          path: 'salary-distribution',
          name: 'SalaryDistribution',
          component: () => import('@/views/SalaryDistribution.vue'),
        },
        {
          path: 'location-distribution',
          name: 'LocationDistribution',
          component: () => import('@/views/LocationDistribution.vue'),
        },
        {
          path: 'wordcloud',
          name: 'WordCloud',
          component: () => import('@/views/WordCloud.vue'),
        },
      ],
    },
  ],
})

// 路由守卫
router.beforeEach((to, _from, next) => {
  const authStore = useAuthStore()
  
  if (to.meta.requiresAuth && !authStore.isAuthenticated) {
    next({ name: 'Login' })
  } else if ((to.name === 'Login' || to.name === 'Register') && authStore.isAuthenticated) {
    next({ name: 'QAPage' })
  } else {
    next()
  }
})

export default router

