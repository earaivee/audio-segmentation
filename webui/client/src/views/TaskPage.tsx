import { defineComponent, ref, onMounted, onUnmounted } from 'vue'
import {
    NCard, NButton, NProgress, NSpace, NScrollbar, NTag, NAlert,
    NSteps, NStep, NIcon, useMessage,
} from 'naive-ui'
import {
    CheckmarkCircleOutline, EllipseOutline, AlertCircleOutline,
} from '@vicons/ionicons5'
import { taskApi } from '../api'

export default defineComponent({
    name: 'TaskPage',
    setup() {
        const message = useMessage()
        const status = ref('idle')
        const progress = ref(0)
        const statusMessage = ref('')
        const logs = ref<string[]>([])
        const currentStep = ref(0)
        let ws: WebSocket | null = null
        let pollTimer: number | null = null

        const statusColorMap: Record<string, string> = {
            idle: 'default',
            running: 'info',
            completed: 'success',
            error: 'error',
        }

        const statusTextMap: Record<string, string> = {
            idle: '空闲',
            running: '运行中',
            completed: '已完成',
            error: '出错',
        }

        // 根据进度计算当前步骤
        const updateStep = (p: number) => {
            if (p <= 0) currentStep.value = 0
            else if (p < 0.05) currentStep.value = 1  // 加载模型
            else if (p < 0.7) currentStep.value = 2   // 音频切分
            else if (p < 0.95) currentStep.value = 3  // 语音识别
            else if (p < 1.0) currentStep.value = 4   // 生成列表
            else currentStep.value = 5                  // 完成
        }

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
                        progress.value = Math.round((data.progress || 0) * 100)
                        statusMessage.value = data.message || ''
                        status.value = data.status || status.value
                        updateStep(data.progress || 0)
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
                progress.value = Math.round(p * 100)
                statusMessage.value = res.data.message || ''
                updateStep(p)

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
                currentStep.value = 0
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

        const stepStatus = (step: number): 'process' | 'finish' | 'wait' | 'error' => {
            if (status.value === 'error' && currentStep.value === step) return 'error'
            if (step < currentStep.value) return 'finish'
            if (step === currentStep.value && status.value === 'running') return 'process'
            return 'wait'
        }

        return () => (
            <div>
                <NSpace vertical size="large">
                    {/* 任务控制 */}
                    <NCard title="任务控制" size="small">
                        <NSpace vertical size="medium">
                            <NSpace align="center">
                                <span>状态：</span>
                                <NTag type={statusColorMap[status.value] as any}>
                                    {statusTextMap[status.value] || status.value}
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
                            <NSteps current={currentStep.value} size="small" style="margin: 8px 0">
                                <NStep title="准备" description="等待启动" />
                                <NStep title="加载模型" description="前置处理" />
                                <NStep title="音频切分" description="分段处理" />
                                <NStep title="语音识别" description="ASR 识别" />
                                <NStep title="生成列表" description="训练数据" />
                                <NStep title="完成" description="" />
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
