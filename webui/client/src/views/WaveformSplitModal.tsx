import { defineComponent, ref, watch, onBeforeUnmount, nextTick, h } from 'vue'
import {
    NModal, NButton, NSpace, NIcon, NTag, NInputNumber, NEmpty,
    NPopconfirm, useMessage, NCard,
} from 'naive-ui'
import {
    PlayCircleOutline, StopCircleOutline, AddOutline,
    TrashOutline, CutOutline, RemoveOutline,
} from '@vicons/ionicons5'
import WaveSurfer from 'wavesurfer.js'
import { audioApi } from '../api'

export default defineComponent({
    name: 'WaveformSplitModal',
    props: {
        show: { type: Boolean, required: true },
        filepath: { type: String, default: '' },
        filename: { type: String, default: '' },
        durationSec: { type: Number, default: 0 },
    },
    emits: ['update:show', 'split-done'],
    setup(props, { emit }) {
        const message = useMessage()
        const waveContainerRef = ref<HTMLDivElement | null>(null)
        let wavesurfer: WaveSurfer | null = null
        const isPlaying = ref(false)
        const currentTime = ref(0)
        const duration = ref(0)
        const markers = ref<number[]>([])
        const splitting = ref(false)
        const isReady = ref(false)
        const zoomLevel = ref(50)

        const formatTime = (sec: number) => {
            const m = Math.floor(sec / 60)
            const s = (sec % 60).toFixed(2)
            return m > 0 ? `${m}:${s.padStart(5, '0')}` : `${s}s`
        }

        const initWaveSurfer = async () => {
            await nextTick()
            if (!waveContainerRef.value || !props.filepath) return

            destroyWaveSurfer()
            isReady.value = false

            wavesurfer = WaveSurfer.create({
                container: waveContainerRef.value,
                waveColor: '#4a90d9',
                progressColor: '#1a56db',
                cursorColor: '#e53e3e',
                cursorWidth: 2,
                height: 180,
                barWidth: 2,
                barGap: 1,
                barRadius: 2,
                normalize: true,
                minPxPerSec: zoomLevel.value,
            })

            wavesurfer.on('ready', () => {
                duration.value = wavesurfer!.getDuration()
                isReady.value = true
            })

            wavesurfer.on('audioprocess', () => {
                currentTime.value = wavesurfer!.getCurrentTime()
            })

            wavesurfer.on('seeking', () => {
                currentTime.value = wavesurfer!.getCurrentTime()
            })

            wavesurfer.on('play', () => { isPlaying.value = true })
            wavesurfer.on('pause', () => { isPlaying.value = false })
            wavesurfer.on('finish', () => { isPlaying.value = false })

            wavesurfer.on('dblclick', () => {
                const time = wavesurfer!.getCurrentTime()
                addMarker(time)
            })

            wavesurfer.load(audioApi.playUrl(props.filepath))
        }

        const destroyWaveSurfer = () => {
            if (wavesurfer) {
                wavesurfer.destroy()
                wavesurfer = null
            }
            isPlaying.value = false
            isReady.value = false
            currentTime.value = 0
        }

        const togglePlay = () => {
            if (!wavesurfer || !isReady.value) return
            wavesurfer.playPause()
        }

        const addMarkerAtCurrent = () => {
            if (!wavesurfer || !isReady.value) return
            addMarker(wavesurfer.getCurrentTime())
        }

        const addMarker = (time: number) => {
            const rounded = Math.round(time * 100) / 100
            if (rounded <= 0 || rounded >= duration.value) return
            if (markers.value.some(m => Math.abs(m - rounded) < 0.05)) return
            markers.value.push(rounded)
            markers.value.sort((a, b) => a - b)
            renderMarkers()
        }

        const removeMarker = (index: number) => {
            markers.value.splice(index, 1)
            renderMarkers()
        }

        const updateMarkerTime = (index: number, newTime: number | null) => {
            if (newTime === null || newTime <= 0 || newTime >= duration.value) return
            markers.value[index] = Math.round(newTime * 100) / 100
            markers.value.sort((a, b) => a - b)
            renderMarkers()
        }

        const renderMarkers = () => {
            // Remove existing marker lines
            const container = waveContainerRef.value
            if (!container) return
            container.querySelectorAll('.wf-marker').forEach(el => el.remove())

            if (!wavesurfer || !isReady.value) return
            const wrapper = container.querySelector('div[data-testid="waveform"]') || container.children[0]
            if (!wrapper) return

            const totalWidth = (wrapper as HTMLElement).scrollWidth
            markers.value.forEach((time, i) => {
                const pct = time / duration.value
                const line = document.createElement('div')
                line.className = 'wf-marker'
                line.style.cssText = `
          position: absolute; top: 0; bottom: 0; width: 2px;
          background: #e53e3e; z-index: 5; pointer-events: none;
          left: ${pct * totalWidth}px;
        `
                const label = document.createElement('div')
                label.className = 'wf-marker'
                label.style.cssText = `
          position: absolute; top: -18px; z-index: 6;
          left: ${pct * totalWidth - 14}px;
          font-size: 10px; color: #e53e3e; font-weight: 600;
          background: rgba(255,255,255,0.9); padding: 0 3px; border-radius: 2px;
          pointer-events: none; white-space: nowrap;
        `
                label.textContent = `#${i + 1}`
                ;(wrapper as HTMLElement).style.position = 'relative'
                wrapper.appendChild(line)
                wrapper.appendChild(label)
            })
        }

        const handleZoom = (delta: number) => {
            zoomLevel.value = Math.max(10, Math.min(500, zoomLevel.value + delta))
            if (wavesurfer && isReady.value) {
                wavesurfer.zoom(zoomLevel.value)
                nextTick(() => renderMarkers())
            }
        }

        const confirmSplit = async () => {
            if (markers.value.length === 0) {
                message.warning('请至少添加一个分割点')
                return
            }
            splitting.value = true
            try {
                const res = await audioApi.splitAtTimes(props.filepath, markers.value)
                message.success(res.data.message || '切分完成')
                emit('split-done')
                closeModal()
            } catch (e: any) {
                message.error(e.response?.data?.detail || '切分失败')
            } finally {
                splitting.value = false
            }
        }

        const closeModal = () => {
            destroyWaveSurfer()
            markers.value = []
            emit('update:show', false)
        }

        // 弹窗打开时初始化
        watch(() => props.show, (val) => {
            if (val && props.filepath) {
                nextTick(() => initWaveSurfer())
            } else {
                destroyWaveSurfer()
                markers.value = []
            }
        })

        onBeforeUnmount(() => destroyWaveSurfer())

        // 计算切分后的片段预览
        const segmentPreview = () => {
            if (markers.value.length === 0) return null
            const bounds = [0, ...markers.value, duration.value]
            const segs = []
            for (let i = 0; i < bounds.length - 1; i++) {
                const dur = bounds[i + 1] - bounds[i]
                segs.push({ index: i + 1, start: bounds[i], end: bounds[i + 1], duration: dur })
            }
            return segs
        }

        return () => (
            <NModal
                show={props.show}
                onUpdateShow={(val: boolean) => { if (!val) closeModal() }}
                style="width: 90vw; max-width: 1200px"
                preset="card"
                title={`波形切分 - ${props.filename}`}
                closable
                maskClosable={false}
            >
                {/* 顶部信息和控制 */}
                <NSpace align="center" justify="space-between" style="margin-bottom: 12px">
                    <NSpace align="center">
                        <NButton
                            size="small" type={isPlaying.value ? 'error' : 'primary'}
                            onClick={togglePlay} disabled={!isReady.value}
                            v-slots={{ icon: () => <NIcon>{isPlaying.value ? <StopCircleOutline /> : <PlayCircleOutline />}</NIcon> }}
                        >
                            {isPlaying.value ? '暂停' : '播放'}
                        </NButton>
                        <NTag size="small">{formatTime(currentTime.value)} / {formatTime(duration.value)}</NTag>
                    </NSpace>
                    <NSpace align="center">
                        <NButton size="tiny" onClick={() => handleZoom(-20)}>
                            <NIcon><RemoveOutline /></NIcon>
                        </NButton>
                        <NTag size="small" type="info">缩放 {zoomLevel.value}px/s</NTag>
                        <NButton size="tiny" onClick={() => handleZoom(20)}>
                            <NIcon><AddOutline /></NIcon>
                        </NButton>
                    </NSpace>
                </NSpace>

                {/* 波形区域 */}
                <div
                    ref={waveContainerRef}
                    style="border: 1px solid #e0e0e6; border-radius: 6px; padding: 4px; margin-bottom: 12px; min-height: 190px; overflow-x: auto; position: relative; background: #fafafa"
                >
                    {!isReady.value && (
                        <div style="display: flex; align-items: center; justify-content: center; height: 180px; color: #999">
                            加载波形中...
                        </div>
                    )}
                </div>

                {/* 提示 */}
                <div style="color: #888; font-size: 12px; margin-bottom: 8px">
                    双击波形添加分割点，或点击下方按钮在当前播放位置添加
                </div>

                {/* 标记点管理 */}
                <NSpace align="center" style="margin-bottom: 12px">
                    <NButton size="small" type="primary" onClick={addMarkerAtCurrent}
                             disabled={!isReady.value}
                             v-slots={{ icon: () => <NIcon><AddOutline /></NIcon> }}>
                        在当前位置添加分割点
                    </NButton>
                    <NTag type={markers.value.length > 0 ? 'success' : 'default'} size="small">
                        {markers.value.length} 个分割点 → {markers.value.length + 1} 个片段
                    </NTag>
                </NSpace>

                {/* 标记列表 + 片段预览 */}
                {markers.value.length > 0 && (
                    <NCard size="small" style="margin-bottom: 12px; max-height: 200px; overflow-y: auto">
                        <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 8px">
                            {markers.value.map((time, i) => (
                                <div key={i} style="display: flex; align-items: center; gap: 6px; padding: 4px 8px; background: #f5f5f5; border-radius: 4px">
                                    <NTag size="tiny" type="error">#{i + 1}</NTag>
                                    <NInputNumber
                                        value={time}
                                        onUpdateValue={(v) => updateMarkerTime(i, v)}
                                        size="tiny" step={0.1} min={0.01}
                                        max={duration.value - 0.01}
                                        style="width: 110px"
                                        v-slots={{ suffix: () => 's' }}
                                    />
                                    <NButton size="tiny" quaternary type="error" onClick={() => removeMarker(i)}>
                                        <NIcon><TrashOutline /></NIcon>
                                    </NButton>
                                </div>
                            ))}
                        </div>
                        {/* 切分预览 */}
                        <div style="margin-top: 8px; font-size: 12px; color: #666">
                            片段预览：{segmentPreview()?.map((seg, i) => (
                            <NTag key={i} size="tiny" style="margin: 2px" type="info">
                                第{seg.index}段: {formatTime(seg.start)} ~ {formatTime(seg.end)} ({formatTime(seg.duration)})
                            </NTag>
                        ))}
                        </div>
                    </NCard>
                )}

                {/* 底部按钮 */}
                <NSpace justify="end">
                    <NButton onClick={closeModal}>取消</NButton>
                    <NPopconfirm onPositiveClick={confirmSplit}>
                        {{
                            trigger: () => (
                                <NButton type="warning" loading={splitting.value}
                                         disabled={markers.value.length === 0}
                                         v-slots={{ icon: () => <NIcon><CutOutline /></NIcon> }}>
                                    确认切分 ({markers.value.length + 1} 个片段)
                                </NButton>
                            ),
                            default: () => `将按 ${markers.value.length} 个分割点切分为 ${markers.value.length + 1} 个片段，确定？`,
                        }}
                    </NPopconfirm>
                </NSpace>
            </NModal>
        )
    },
})
