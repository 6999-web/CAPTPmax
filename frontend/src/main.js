import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'

import './style.css'
import App from './App.vue'
import Shooting from './components/Shooting.vue'
import Grappling from './components/Grappling.vue'
import Tactical from './components/Tactical.vue'
import Settings from './components/Settings.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/shooting' },
    { path: '/shooting', component: Shooting },
    { path: '/grappling', component: Grappling },
    { path: '/tactical', component: Tactical },
    { path: '/settings', component: Settings }
  ]
})

createApp(App).use(router).mount('#app')
