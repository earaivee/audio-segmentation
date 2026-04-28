import { defineComponent, ref, onMounted, onUnmounted } from 'vue'
import {
    NCard, NButton, NProgress, NSpace, NScrollbar, NTag,
    NSteps, NStep, useMessage,
} from 'naive-ui'
import { taskApi } from '../api'

type Stage = 'preparing' | 'segmenting' | 'transcribing' | 'inferring' | 'completed' | 'error'

const STAGE_LABELS: Record<Stage, string> = {
    preparing: '准备',
    segmenting: '切分音频',
    transcribing: '识别音频',
    inferring: '推理',
    completed: '完成',
    error: '错误',
}

const STAGE_CURRENT: Record<Stage, number> = {
    preparing: 1,
    segmenting: 2,
    transcribing: 3,
    inferring: 4,
    completed: 5,
    error: 5,
}

export default defineComponent({
    name: 'TaskPage',
    setup() {
        const message = useMessage()
        const status = ref('idle')
        const stage = ref<Stage>('preparing')
        const progress = ref(0)
        const statusMessage = ref('')
        const logs = ref<string[]>([])
        let ws: WebSocket | null = null
        let pollTimer: number | null = null

        const connectWs = () => {
            const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
            try {
                ws = new WebSocket(`${protocol}//${location.host}/ws/logs`)
            } catch {
                setTimeout(connectWs, 3000)
                return
            }

            ws.onopen = () => {
                console.log('[WS] 连接已建立')
            }

            ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data)
                    if (data.type === 'log') {
                        logs.value.push(data.message)
                        if (logs.value.length > 500) logs.value.shift()
                    } else if (data.type === 'history') {
                        if (data.logs && data.logs.length > 0) {
                            logs.value = [...data.logs]
                        }
                    } else if (data.type === 'progress') {
                        progress.value = Math.round(data.progress || 0)
                        statusMessage.value = data.message || ''
                        status.value = data.status || status.value
                        if (data.stage) stage.value = data.stage
                    }
                } catch {}
            }

            ws.onerror = () => {
                console.warn('[WS] 连接错误')
            }

            ws.onclose = () => {
                console.log('[WS] 连接关闭，3秒后重连')
                setTimeout(connectWs, 3000)
            }
        }

        const fetchStatus = async () => {
            try {
                const res = await taskApi.status()
                const newStatus = res.data.status
                const p = res.data.progress || 0
                status.value = newStatus
                progress.value = Math.round(p)
                statusMessage.value = res.data.message || ''
                if (res.data.stage) stage.value = res.data.stage

                // 任务运行中时缩短轮询间隔，否则恢复正常间隔
                adjustPolling(newStatus === 'running')
            } catch {}
        }

        const adjustPolling = (isRunning: boolean) => {
            const interval = isRunning ? 2000 : 5000
            if (pollTimer) clearInterval(pollTimer)
            pollTimer = window.setInterval(fetchStatus, interval)
        }

        const startTask = async () => {
            try {
                logs.value = []
                progress.value = 0
                stage.value = 'preparing'
                const res = await taskApi.run()
                if (res.data.error) {
                    message.warning(res.data.error)
                } else {
                    message.success('任务已启动')
                    status.value = 'running'
                }
            } catch (e: any) {
                message.error('启动失败: ' + (e.response?.data?.detail || e.message))
            }
        }

        const stopTask = async () => {
            try {
                await taskApi.stop()
                message.info('已发送停止信号')
            } catch (e: any) {
                message.error('停止失败')
            }
        }

        onMounted(() => {
            connectWs()
            fetchStatus()
            pollTimer = window.setInterval(fetchStatus, 5000)
        })

        onUnmounted(() => {
            if (ws) ws.close()
            if (pollTimer) clearInterval(pollTimer)
        })

        return () => (
            <div>
                <NSpace vertical size="large">
                    {/* 任务控制 */}
                    <NCard title="任务控制" size="small">
                        <NSpace vertical size="medium">
                            <NSpace align="center">
                                <span>状态：</span>
                                <NTag type={status.value === 'idle' ? 'default' : status.value === 'running' ? 'info' : status.value === 'completed' ? 'success' : 'error'}>
                                    {status.value === 'idle' ? '空闲' : status.value === 'running' ? '运行中' : status.value === 'completed' ? '已完成' : '出错'}
                                </NTag>
                                {statusMessage.value && (
                                    <span style="color: #666; font-size: 13px">{statusMessage.value}</span>
                                )}
                            </NSpace>

                            {/* 进度条 */}
                            <NProgress
                                type="line"
                                percentage={progress.value}
                                indicator-placement="inside"
                                processing={status.value === 'running'}
                                status={status.value === 'error' ? 'error' : status.value === 'completed' ? 'success' : 'default'}
                                style="margin: 4px 0"
                            />

                            {/* 步骤指示器 */}
                            <NSteps current={STAGE_CURRENT[stage.value]} size="small" style="margin: 8px 0">
                                <NStep title={STAGE_LABELS.preparing} description="等待启动" />
                                <NStep title={STAGE_LABELS.segmenting} description="分段处理" />
                                <NStep title={STAGE_LABELS.transcribing} description="ASR 识别" />
                                <NStep title={STAGE_LABELS.inferring} description="待实现" />
                            </NSteps>

                            <NSpace>
                                <NButton
                                    type="primary"
                                    onClick={startTask}
                                    disabled={status.value === 'running'}
                                    loading={status.value === 'running'}
                                >
                                    {status.value === 'running' ? '运行中...' : '一键运行'}
                                </NButton>
                                <NButton
                                    type="error"
                                    onClick={stopTask}
                                    disabled={status.value !== 'running'}
                                >
                                    停止任务
                                </NButton>
                            </NSpace>
                        </NSpace>
                    </NCard>

                    {/* 日志区域 */}
                    <NCard title="实时日志" size="small" style="flex: 1">
                        <NScrollbar style="max-height: calc(100vh - 420px); min-height: 300px">
                            <div style="font-family: monospace; font-size: 13px; line-height: 1.8; padding: 12px; background: #1e1e1e; color: #d4d4d4; border-radius: 4px; min-height: 300px">
                                {logs.value.length === 0 ? (
                                    <span style="color: #666">等待日志输出...</span>
                                ) : (
                                    logs.value.map((log, i) => (
                                        <div key={i}>{log}</div>
                                    ))
                                )}
                            </div>
                        </NScrollbar>
                    </NCard>
                </NSpace>
            </div>
        )
    },
})
