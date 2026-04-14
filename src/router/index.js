import { createRouter, createWebHistory } from 'vue-router';

const routes = [
  {
    path: '/',
    name: 'map',
    component: () => import('../views/MapView.vue'),
  },
  {
    path: '/helmet',
    name: 'helmet',
    component: () => import('../views/Helmet.vue'),
  },
  {
    path: '/me',
    name: 'me',
    component: () => import('../views/Me.vue'),
  },
  {
    path: '/config',
    name: 'config',
    component: () => import('../views/Config.vue'),
  },
  {
    path: '/log',
    name: 'log',
    component: () => import('../views/Log.vue'),
  }
];

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
});

export default router;