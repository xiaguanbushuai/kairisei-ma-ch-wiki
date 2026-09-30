import { createRouter, createWebHashHistory } from 'vue-router'

const routes = [
  { path: '/', name: 'home', component: () => import('./views/Home.vue') },
  { path: '/cards', name: 'cards', component: () => import('./views/CardList.vue') },
  { path: '/card/:id', name: 'card', component: () => import('./views/CardDetail.vue') },
  { path: '/skills', name: 'skills', component: () => import('./views/SkillList.vue') },
  { path: '/bosses', name: 'bosses', component: () => import('./views/BossList.vue') },
  { path: '/boss/:id', name: 'boss', component: () => import('./views/BossDetail.vue') },
  { path: '/items', name: 'items', component: () => import('./views/ItemList.vue') },
]

export default createRouter({
  history: createWebHashHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})
