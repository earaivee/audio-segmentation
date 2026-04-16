import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'
import naive from 'naive-ui'
import App from './App'
import ConfigPage from './views/ConfigPage'
import TaskPage from './views/TaskPage'
import AudioPage from './views/AudioPage'

const router = createRouter({
    history: createWebHistory(),
    routes: [
        { path: '/', redirect: '/task' },
        { path: '/config', component: ConfigPage, meta: { title: '配置管理' } },
        { path: '/task', component: TaskPage, meta: { title: '任务执行' } },
        { path: '/audio', component: AudioPage, meta: { title: '音频管理' } },
    ],
})

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.use(naive)
app.mount('#app')
