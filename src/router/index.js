import { createRouter, createWebHistory } from 'vue-router';

const routes = [
  {
    path: '/',
    name: 'map',
    component: () => import('../views/MapView.vue'),
  },
  {
    path: '/panel',
    name: 'panel',
    component: () => import('../views/Panel.vue'),
  }
];

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
});

export default router;