import { defineComponent, ref, onMounted, h, watch } from 'vue'
import {
    NCard, NFormItem, NInputNumber, NSlider, NSwitch,
    NSelect, NInput, NButton, NSpace, NGrid, NGi,
    NModal, NIcon, NEmpty, NInputGroup, NTabs, NTabPane, NTag,
    useMessage,
} from 'naive-ui'
import {
    FolderOpenOutline, ArrowBackOutline, DesktopOutline,
    SaveOutline,
} from '@vicons/ionicons5'
import { configApi } from '../api'

export default defineComponent({
    name: 'ConfigPage',
    setup() {
        const message = useMessage()
        const config = ref<any>({
            input_dir: './resources/input',
            output_dir: './resources/output',
            supported_formats: ['.wav', '.mp3'],
            vad: { threshold: 0.5, min_silence_duration_ms: 720, min_speech_duration_ms: 600, speech_pad_ms: 200 },
            normalize: { enabled: true, method: 'rms', target_rms: 0.15, target_peak: 0.95, clipping_threshold: 0.99 },
            faster_whisper: { enabled: true, model_size: 'medium', model_path: './models/faster-whisper-medium', device: 'cpu', compute_type: 'int8', language: 'zh', beam_size: 5 },
            sovits: { enabled: true, format_type: 'gpt_sovits', speaker: 'output', language: 'ZH', output_path: './resources/output.list' },
        })
        const configLoaded = ref(false)
        const saving = ref(false)
        const saveStatus = ref<'idle' | 'saving' | 'saved'>('idle')

        // 目录浏览弹窗
        const browseModalVisible = ref(false)
        const browseCurrentPath = ref('')
        const browseParentPath = ref<string | null>(null)
        const browseDirs = ref<{ name: string; path: string }[]>([])
        const browseDrives = ref<{ name: string; path: string }[]>([])
        const browseField = ref('')

        const loadConfig = async () => {
            try {
                const res = await configApi.get()
                config.value = res.data
                configLoaded.value = true
            } catch (e) {
                message.error('加载配置失败')
            }
        }

        // 防抖自动保存
        let saveTimer: ReturnType<typeof setTimeout> | null = null
        const autoSave = () => {
            if (!configLoaded.value) return
            saveStatus.value = 'saving'
            if (saveTimer) clearTimeout(saveTimer)
            saveTimer = setTimeout(async () => {
                try {
                    await configApi.update(config.value)
                    saveStatus.value = 'saved'
                    setTimeout(() => { if (saveStatus.value === 'saved') saveStatus.value = 'idle' }, 2000)
                } catch (e) {
                    message.error('自动保存失败')
                    saveStatus.value = 'idle'
                }
            }, 800)
        }

        // 深度监听 config 变化自动保存
        watch(config, () => { autoSave() }, { deep: true })

        const openBrowse = (currentValue: string, field: string) => {
            browseField.value = field
            browseCurrentPath.value = currentValue || ''
            browseModalVisible.value = true
            loadBrowseDir(currentValue || '')
        }

        const loadBrowseDir = async (path: string) => {
            try {
                const res = await configApi.browseDirs(path)
                browseCurrentPath.value = res.data.current || ''
                browseParentPath.value = res.data.parent || null
                browseDirs.value = res.data.dirs || []
                browseDrives.value = res.data.drives || []
            } catch (e) {
                message.error('加载目录失败')
            }
        }

        const selectBrowsePath = () => {
            const path = browseCurrentPath.value
            switch (browseField.value) {
                case 'input_dir': config.value.input_dir = path; break
                case 'output_dir': config.value.output_dir = path; break
                case 'sovits_output_path': config.value.sovits.output_path = path; break
            }
            browseModalVisible.value = false
        }

        const DirInput = (props: { value: string; field: string; onUpdate: (v: string) => void }) => {
            return h(NInputGroup, {}, {
                default: () => [
                    h(NInput, {
                        value: props.value,
                        'onUpdate:value': props.onUpdate,
                        style: 'flex: 1',
                    }),
                    h(NButton, {
                        onClick: () => openBrowse(props.value, props.field),
                        type: 'primary',
                        ghost: true,
                    }, { icon: () => h(NIcon, null, { default: () => h(FolderOpenOutline) }) }),
                ],
            })
        }

        onMounted(loadConfig)

        return () => (
            <div>
                <NCard size="small" v-slots={{
                    header: () => (
                        <NSpace align="center" justify="space-between" style="width: 100%">
                            <span style="font-weight: 600; font-size: 16px">配置管理</span>
                            {saveStatus.value === 'saving' && <NTag size="small" type="warning" round>保存中...</NTag>}
                            {saveStatus.value === 'saved' && <NTag size="small" type="success" round>已保存</NTag>}
                        </NSpace>
                    ),
                }}>
                    <NTabs type="line">
                        {/* Tab 1: 基础配置 */}
                        <NTabPane name="basic" tab="基础配置">
                            <div style="padding: 16px 0">
                                <NGrid cols={2} xGap={16} yGap={4}>
                                    <NGi>
                                        <NFormItem label="输入目录">
                                            {DirInput({
                                                value: config.value.input_dir,
                                                field: 'input_dir',
                                                onUpdate: (v: string) => { config.value.input_dir = v },
                                            })}
                                        </NFormItem>
                                    </NGi>
                                    <NGi>
                                        <NFormItem label="输出目录">
                                            {DirInput({
                                                value: config.value.output_dir,
                                                field: 'output_dir',
                                                onUpdate: (v: string) => { config.value.output_dir = v },
                                            })}
                                        </NFormItem>
                                    </NGi>
                                    <NGi span={2}>
                                        <NFormItem label="支持的音频格式">
                                            <NSelect
                                                v-model:value={config.value.supported_formats}
                                                multiple
                                                options={[
                                                    { label: '.wav', value: '.wav' },
                                                    { label: '.mp3', value: '.mp3' },
                                                    { label: '.flac', value: '.flac' },
                                                    { label: '.ogg', value: '.ogg' },
                                                    { label: '.m4a', value: '.m4a' },
                                                ]}
                                            />
                                        </NFormItem>
                                    </NGi>
                                </NGrid>
                            </div>
                        </NTabPane>

                        {/* Tab 2: 音频处理 */}
                        <NTabPane name="processing" tab="音频处理">
                            <div style="padding: 16px 0">
                                <h4 style="margin: 0 0 12px; color: #333">VAD 语音检测</h4>
                                <NGrid cols={2} xGap={16} yGap={4}>
                                    <NGi>
                                        <NFormItem label="检测敏感度">
                                            <NSlider v-model:value={config.value.vad.threshold} min={0.1} max={0.95} step={0.05} />
                                        </NFormItem>
                                    </NGi>
                                    <NGi>
                                        <NFormItem label={`阈值: ${config.value.vad.threshold}`}>
                                            <NInputNumber v-model:value={config.value.vad.threshold} min={0.1} max={0.95} step={0.05} style="width: 100%" />
                                        </NFormItem>
                                    </NGi>
                                    <NGi>
                                        <NFormItem label="最小静音间隔 (ms)">
                                            <NInputNumber v-model:value={config.value.vad.min_silence_duration_ms} min={100} max={5000} step={10} style="width: 100%" />
                                        </NFormItem>
                                    </NGi>
                                    <NGi>
                                        <NFormItem label="最小语音时长 (ms)">
                                            <NInputNumber v-model:value={config.value.vad.min_speech_duration_ms} min={100} max={5000} step={10} style="width: 100%" />
                                        </NFormItem>
                                    </NGi>
                                    <NGi>
                                        <NFormItem label="语音边界填充 (ms)">
                                            <NInputNumber v-model:value={config.value.vad.speech_pad_ms} min={0} max={1000} step={10} style="width: 100%" />
                                        </NFormItem>
                                    </NGi>
                                </NGrid>

                                <h4 style="margin: 20px 0 12px; color: #333; display: flex; align-items: center; gap: 12px">
                                    音量归一化
                                    <NSwitch v-model:value={config.value.normalize.enabled} size="small" />
                                </h4>
                                <NGrid cols={2} xGap={16} yGap={4}>
                                    <NGi>
                                        <NFormItem label="归一化方法">
                                            <NSelect v-model:value={config.value.normalize.method} options={[
                                                { label: 'RMS (均方根)', value: 'rms' },
                                                { label: 'Peak (峰值)', value: 'peak' },
                                            ]} />
                                        </NFormItem>
                                    </NGi>
                                    <NGi>
                                        <NFormItem label="目标 RMS">
                                            <NInputNumber v-model:value={config.value.normalize.target_rms} min={0.01} max={0.99} step={0.01} style="width: 100%" />
                                        </NFormItem>
                                    </NGi>
                                    <NGi>
                                        <NFormItem label="目标峰值">
                                            <NInputNumber v-model:value={config.value.normalize.target_peak} min={0.01} max={1.0} step={0.01} style="width: 100%" />
                                        </NFormItem>
                                    </NGi>
                                    <NGi>
                                        <NFormItem label="削波阈值">
                                            <NInputNumber v-model:value={config.value.normalize.clipping_threshold} min={0.01} max={1.0} step={0.01} style="width: 100%" />
                                        </NFormItem>
                                    </NGi>
                                </NGrid>

                                {/* 音频切分配置已停用，由音频管理页筛选替代 */}
                            </div>
                        </NTabPane>

                        {/* Tab 3: 语音识别 */}
                        <NTabPane name="whisper" tab="语音识别">
                            <div style="padding: 16px 0">
                                <h4 style="margin: 0 0 12px; color: #333; display: flex; align-items: center; gap: 12px">
                                    faster-whisper
                                    <NSwitch v-model:value={config.value.faster_whisper.enabled} />
                                </h4>
                                <NGrid cols={2} xGap={16} yGap={4}>
                                    <NGi span={2}>
                                        <NFormItem label="模型路径 / 模型名">
                                            <NInput v-model:value={config.value.faster_whisper.model_path}
                                                    placeholder="留空使用 {model_size} 自动下载，或填本地模型路径" />
                                        </NFormItem>
                                    </NGi>
                                    <NGi>
                                        <NFormItem label="设备">
                                            <NSelect v-model:value={config.value.faster_whisper.device} options={[
                                                { label: 'CPU', value: 'cpu' },
                                                { label: 'CUDA (GPU)', value: 'cuda' },
                                            ]} />
                                        </NFormItem>
                                    </NGi>
                                    <NGi>
                                        <NFormItem label="计算精度">
                                            <NSelect v-model:value={config.value.faster_whisper.compute_type} options={[
                                                { label: 'int8', value: 'int8' },
                                                { label: 'int8_float16', value: 'int8_float16' },
                                                { label: 'int8_float32', value: 'int8_float32' },
                                                { label: 'float16', value: 'float16' },
                                                { label: 'float32', value: 'float32' },
                                            ]} />
                                        </NFormItem>
                                    </NGi>
                                    <NGi>
                                        <NFormItem label="语言">
                                            <NSelect v-model:value={config.value.faster_whisper.language} options={[
                                                { label: '中文', value: 'zh' },
                                                { label: '英文', value: 'en' },
                                                { label: '日文', value: 'ja' },
                                                { label: '韩文', value: 'ko' },
                                                { label: '自动检测', value: 'auto' },
                                            ]} />
                                        </NFormItem>
                                    </NGi>
                                    <NGi>
                                        <NFormItem label="Beam Size">
                                            <NInputNumber v-model:value={config.value.faster_whisper.beam_size} min={1} max={10} step={1} style="width: 100%" />
                                        </NFormItem>
                                    </NGi>
                                </NGrid>
                            </div>
                        </NTabPane>

                        {/* Tab 4: 推理文本*/}
                        <NTabPane name="sovits" tab="推理文本">
                            <div style="padding: 16px 0">
                                <NSpace align="center" style="margin-bottom: 16px">
                                    <span style="font-weight: 500">启用训练列表导出</span>
                                    <NSwitch v-model:value={config.value.sovits.enabled} />
                                </NSpace>
                                <NGrid cols={2} xGap={16} yGap={4}>
                                    <NGi span={2}>
                                        <NFormItem label="导出格式">
                                            <NSelect v-model:value={config.value.sovits.format_type} options={[
                                                { label: 'GPT-SoVITS (wav|speaker|lang|text)', value: 'gpt_sovits' },
                                                { label: 'VITS (wav|speaker|text)', value: 'vits' },
                                                { label: 'Bert-VITS2 (wav|speaker|lang|text)', value: 'bert_vits2' },
                                                { label: 'RVC (wav|text)', value: 'rvc' },
                                                { label: 'RVC 仅路径 (wav)', value: 'rvc_wav_only' },
                                                { label: 'IndexTTS (wav|text)', value: 'index_tts' },
                                                { label: 'Fish Speech (wav\\ttext)', value: 'fish_speech' },
                                            ]} />
                                        </NFormItem>
                                    </NGi>
                                    {(config.value.sovits.format_type === 'gpt_sovits'
                                      || config.value.sovits.format_type === 'vits'
                                      || config.value.sovits.format_type === 'bert_vits2') && (
                                        <NGi>
                                            <NFormItem label="说话人名称">
                                                <NInput v-model:value={config.value.sovits.speaker} />
                                            </NFormItem>
                                        </NGi>
                                    )}
                                    {(config.value.sovits.format_type === 'gpt_sovits'
                                      || config.value.sovits.format_type === 'bert_vits2') && (
                                        <NGi>
                                            <NFormItem label="语言标签">
                                                <NSelect v-model:value={config.value.sovits.language} options={[
                                                    { label: 'ZH (中文)', value: 'ZH' },
                                                    { label: 'EN (英文)', value: 'EN' },
                                                    { label: 'JA (日文)', value: 'JA' },
                                                ]} />
                                            </NFormItem>
                                        </NGi>
                                    )}
                                    <NGi span={2}>
                                        <NFormItem label="输出列表路径">
                                            {DirInput({
                                                value: config.value.sovits.output_path,
                                                field: 'sovits_output_path',
                                                onUpdate: (v: string) => { config.value.sovits.output_path = v },
                                            })}
                                        </NFormItem>
                                    </NGi>
                                </NGrid>
                            </div>
                        </NTabPane>
                    </NTabs>
                </NCard>

                {/* 目录浏览弹窗 */}
                <NModal show={browseModalVisible.value}
                        onUpdateShow={(val: boolean) => { browseModalVisible.value = val }}
                        preset="card" title="选择目录" style="width: 600px; max-height: 80vh">
                    {{
                        default: () => (
                            <NSpace vertical size="medium">
                                <NInputGroup>
                                    <NInput value={browseCurrentPath.value} readonly style="flex: 1" />
                                    <NButton type="primary" onClick={selectBrowsePath}>选择此目录</NButton>
                                </NInputGroup>

                                <NSpace>
                                    {browseParentPath.value && (
                                        <NButton size="small" onClick={() => loadBrowseDir(browseParentPath.value!)}
                                                 v-slots={{ icon: () => <NIcon><ArrowBackOutline /></NIcon> }}>
                                            上级目录
                                        </NButton>
                                    )}
                                    {browseDrives.value.map(d => (
                                        <NButton key={d.path} size="small" onClick={() => loadBrowseDir(d.path)}
                                                 v-slots={{ icon: () => <NIcon><DesktopOutline /></NIcon> }}>
                                            {d.name}
                                        </NButton>
                                    ))}
                                </NSpace>

                                <div style="max-height: 400px; overflow-y: auto; border: 1px solid #eee; border-radius: 4px">
                                    {browseDirs.value.length === 0 ? (
                                        <NEmpty description="空目录" size="small" style="padding: 20px" />
                                    ) : (
                                        browseDirs.value.map(d => (
                                            <div key={d.path}
                                                 style="display: flex; align-items: center; gap: 8px; padding: 8px 12px; cursor: pointer; border-bottom: 1px solid #f5f5f5; transition: background 0.2s"
                                                 onMouseenter={(e: MouseEvent) => (e.currentTarget as HTMLElement).style.background = '#f0f0f0'}
                                                 onMouseleave={(e: MouseEvent) => (e.currentTarget as HTMLElement).style.background = ''}
                                                 onDblclick={() => loadBrowseDir(d.path)}
                                                 onClick={() => { browseCurrentPath.value = d.path }}>
                                                <NIcon size={18} color="#f0a020"><FolderOpenOutline /></NIcon>
                                                <span style="font-size: 13px">{d.name}</span>
                                            </div>
                                        ))
                                    )}
                                </div>

                                <div style="font-size: 12px; color: #999">
                                    单击选中，双击进入目录
                                </div>
                            </NSpace>
                            ),
                        }}
                </NModal>
            </div>
        )
    },
})
