import { defineComponent, ref, onMounted, onActivated, h, computed, reactive } from 'vue'
import {
    NCard, NDataTable, NButton, NSpace, NInput, NIcon, NEmpty,
    NPopconfirm, NModal, NAlert, NTag, NSelect, NTooltip, useMessage,
    NCollapse, NCollapseItem, NList, NListItem, NThing, NTree, NSlider,
    NUpload,
} from 'naive-ui'
import type { TreeOption, UploadFileInfo } from 'naive-ui'
import {
    PlayCircleOutline, StopCircleOutline, RefreshOutline,
    DownloadOutline, TrashOutline, GitMergeOutline, CutOutline, MicOutline,
    FolderOpenOutline, PencilOutline, SwapHorizontalOutline,
    VideocamOutline, DocumentTextOutline, FolderOutline, AlbumsOutline,
    CloudUploadOutline,
} from '@vicons/ionicons5'
import { audioApi } from '../api'
import WaveformSplitModal from './WaveformSplitModal'
import type { DataTableColumns, DataTableRowKey, SelectOption, PaginationProps } from 'naive-ui'

interface TreeNode {
    key: string
    folder?: string
    children_count?: number
    total_duration_sec?: number
    is_folder?: boolean
    children?: TreeNode[]
    seg_name?: string
    filename?: string
    filepath?: string
    duration_sec?: number
    text?: string
    parent_dir?: string
}

interface SourceFile {
    filename: string
    filepath: string
    size_mb: number
    ext: string
    folder: string
}

interface SourceGroup {
    folder: string
    folder_raw: string
    files: SourceFile[]
    count: number
    total_size_mb: number
}

export default defineComponent({
    name: 'AudioPage',
    setup() {
        const message = useMessage()
        const loading = ref(false)
        const treeData = ref<TreeNode[]>([])
        const editingTexts = ref<Record<string, string>>({})
        const checkedKeys = ref<DataTableRowKey[]>([])
        const expandedKeys = ref<DataTableRowKey[]>([])
        const currentAudio = ref<HTMLAudioElement | null>(null)
        const playingFile = ref('')
        const mergeModalVisible = ref(false)
        const transcribing = ref(false)
        const totalFiles = ref(0)
        const totalFolders = ref(0)

        // 原始源文件
        const sourceGroups = ref<SourceGroup[]>([])
        const sourceTotalFiles = ref(0)
        const sourceLoading = ref(false)
        const playingSource = ref('')
        const currentSourceAudio = ref<HTMLAudioElement | null>(null)
        const importing = ref(false)

        // 改名弹窗
        const renameModalVisible = ref(false)
        const renameTarget = ref<TreeNode | null>(null)
        const renameValue = ref('')
        // 移动弹窗
        const moveModalVisible = ref(false)
        const moveTarget = ref<TreeNode | null>(null)
        const moveTargetFolder = ref<string | null>(null)
        const folderOptions = ref<SelectOption[]>([])
        // 波形切分弹窗
        const splitModalVisible = ref(false)
        const splitTarget = ref<TreeNode | null>(null)
        // 查看推理文本弹窗
        const outputListModalVisible = ref(false)
        const outputListContent = ref('')
        const outputListPath = ref('')
        const outputListLoading = ref(false)

        // 获取所有文件节点（非文件夹），扁平化
        const allFileNodes = computed(() => {
            const files: TreeNode[] = []
            treeData.value.forEach(folder => {
                if (folder.children) files.push(...folder.children)
            })
            return files
        })

        // 左侧文件夹树：选中的文件夹 key
        const selectedFolderKey = ref<string | null>(null)

        // 文件夹树数据
        const folderTreeOptions = computed((): TreeOption[] => {
            const allNode: TreeOption = {
                key: '__all__',
                label: `全部 (${totalFiles.value})`,
                prefix: () => h(NIcon, { size: 16, color: '#2080f0' }, { default: () => h(AlbumsOutline) }),
            }
            const folderNodes: TreeOption[] = treeData.value.map(f => ({
                key: f.folder || f.key,
                label: `${f.folder} (${f.children_count})`,
                prefix: () => h(NIcon, { size: 16, color: '#f0a020' }, { default: () => h(FolderOutline) }),
            }))
            return [allNode, ...folderNodes]
        })

        // 时长筛选（双滑块）
        const durationRange = ref<[number, number]>([3, 10])
        const filterDuration = ref<[number, number]>([3, 10]) // 实际用于筛选的值
        let durationDebounceTimer: ReturnType<typeof setTimeout> | null = null

        // 根据选中文件夹 + 时长范围过滤文件
        const filteredFiles = computed(() => {
            let files = allFileNodes.value
            // 文件夹筛选
            if (selectedFolderKey.value && selectedFolderKey.value !== '__all__') {
                const folder = treeData.value.find(f => (f.folder || f.key) === selectedFolderKey.value)
                files = folder?.children || []
            }
            // 时长筛选（使用防抖后的值）
            const [minV, maxV] = filterDuration.value
            files = files.filter(f => {
                const d = f.duration_sec || 0
                return d >= minV && d <= maxV
            })
            return files
        })

        // 时长滑块最大值（根据数据动态计算）
        const durationSliderMax = computed(() => {
            const maxDur = Math.max(...allFileNodes.value.map(f => f.duration_sec || 0), 30)
            return Math.ceil(maxDur)
        })

        // --- 数据加载 ---
        const loadTree = async () => {
            loading.value = true
            try {
                const res = await audioApi.tree()
                treeData.value = res.data.tree || []
                totalFiles.value = res.data.total_files || 0
                totalFolders.value = res.data.total_folders || 0

                const texts: Record<string, string> = {}
                treeData.value.forEach(folder => {
                    folder.children?.forEach((f: TreeNode) => {
                        if (f.key) texts[f.key] = f.text || ''
                    })
                })
                editingTexts.value = texts
                expandedKeys.value = treeData.value.map(f => f.key)
            } catch (e) {
                message.error('加载文件列表失败')
            } finally {
                loading.value = false
            }
        }

        const loadSources = async () => {
            sourceLoading.value = true
            try {
                const res = await audioApi.sources()
                sourceGroups.value = res.data.groups || []
                sourceTotalFiles.value = res.data.total_files || 0
            } catch (e) { /* ignore */ } finally {
                sourceLoading.value = false
            }
        }

        const deleteSourceFile = async (filepath: string, filename: string) => {
            try {
                // 停止播放
                if (playingSource.value === filepath) {
                    if (currentSourceAudio.value) {
                        currentSourceAudio.value.pause()
                        currentSourceAudio.value = null
                    }
                    playingSource.value = ''
                }
                await audioApi.removeSource(filepath)
                message.success(`已删除: ${filename}`)
                await loadSources() // 刷新列表
            } catch (e: any) {
                message.error(e.response?.data?.detail || '删除失败')
            }
        }

        // --- 导入源音频 ---
        const importInputRef = ref<HTMLInputElement | null>(null)
        const triggerImport = () => {
            importInputRef.value?.click()
        }
        const handleImportFiles = async (e: Event) => {
            const input = e.target as HTMLInputElement
            const fileList = input.files
            if (!fileList || fileList.length === 0) return
            importing.value = true
            try {
                const files = Array.from(fileList)
                await audioApi.importSource(files)
                message.success(`已导入 ${files.length} 个文件`)
                await loadSources()
            } catch (err) {
                message.error('导入失败')
            } finally {
                importing.value = false
                input.value = ''  // 重置，允许重复选同文件
            }
        }

        // --- 播放 ---
        const playAudio = (filepath: string) => {
            if (currentAudio.value) {
                currentAudio.value.pause()
                currentAudio.value = null
            }
            if (playingFile.value === filepath) {
                playingFile.value = ''
                return
            }
            const audio = new Audio(audioApi.playUrl(filepath))
            audio.play()
            audio.onended = () => { playingFile.value = ''; currentAudio.value = null }
            currentAudio.value = audio
            playingFile.value = filepath
        }

        const playSource = (filepath: string) => {
            if (currentSourceAudio.value) {
                currentSourceAudio.value.pause()
                currentSourceAudio.value = null
            }
            if (playingSource.value === filepath) {
                playingSource.value = ''
                return
            }
            const audio = new Audio(audioApi.playUrl(filepath))
            audio.play()
            audio.onended = () => { playingSource.value = ''; currentSourceAudio.value = null }
            currentSourceAudio.value = audio
            playingSource.value = filepath
        }

        // --- 文本编辑（自动保存） ---
        const saveText = async (filepath: string) => {
            const text = editingTexts.value[filepath]
            try {
                await audioApi.updateText(filepath, text)
                for (const folder of treeData.value) {
                    const file = folder.children?.find(f => f.filepath === filepath)
                    if (file) { file.text = text; break }
                }
            } catch (e) {
                message.error('保存失败')
            }
        }

        // --- 导出推理文本 ---
        const exportList = async () => {
            const selected = getSelectedFiles()
            if (selected.length === 0) {
                message.warning('请先选择要导出的文件')
                return
            }
            try {
                const items = selected.map(f => ({
                    filepath: f.filepath,
                    text: editingTexts.value[f.key] || f.text,
                }))
                await audioApi.exportList(items)
                message.success(`已生成推理文本 (${items.length} 条)`)
            } catch (e) {
                message.error('生成失败')
            }
        }

        // --- 查看推理文本 ---
        const viewOutputList = async () => {
            outputListLoading.value = true
            outputListModalVisible.value = true
            try {
                const res = await audioApi.getOutputList()
                outputListContent.value = res.data.content
                outputListPath.value = res.data.path
                if (!res.data.exists) {
                    message.warning('推理文本文件尚未生成')
                }
            } catch (e) {
                message.error('读取失败')
            } finally {
                outputListLoading.value = false
            }
        }

        // --- 选中操作（仅文件节点） ---
        const getSelectedFiles = (): TreeNode[] => {
            return allFileNodes.value.filter(f => checkedKeys.value.includes(f.key))
        }

        const deleteSelected = async () => {
            const selected = getSelectedFiles()
            if (selected.length === 0) return
            try {
                for (const f of selected) {
                    await audioApi.delete(f.filename!, f.parent_dir)
                }
                message.success(`已删除 ${selected.length} 个文件`)
                checkedKeys.value = []
                await loadTree()
            } catch (e) {
                message.error('删除失败')
            }
        }

        const openMergeModal = () => {
            if (getSelectedFiles().length < 2) {
                message.warning('请至少选择 2 个文件进行合并')
                return
            }
            mergeModalVisible.value = true
        }

        // 合并预览名称
        const mergePreviewName = computed(() => {
            const files = getSelectedFiles()
            if (files.length < 2) return ''
            const s1 = (files[0].filename || '').replace(/\.[^/.]+$/, '')
            const s2 = (files[1].filename || '').replace(/\.[^/.]+$/, '')
            return `${s1}_${s2}_merge.wav`
        })

        const confirmMerge = async () => {
            try {
                await audioApi.merge(getSelectedFiles().map(f => f.filepath!))
                message.success('合并完成')
                mergeModalVisible.value = false
                checkedKeys.value = []
                await loadTree()
            } catch (e) {
                message.error('合并失败')
            }
        }

        const transcribeSelected = async () => {
            const selected = getSelectedFiles()
            if (selected.length === 0) {
                message.warning('请至少选择 1 个文件进行识别')
                return
            }
            transcribing.value = true
            let successCount = 0
            try {
                for (const f of selected) {
                    const res = await audioApi.transcribe(f.filepath!)
                    if (res.data.text) successCount++
                }
                message.success(`识别完成 (${successCount}/${selected.length})`)
                await loadTree()
            } catch (e) {
                message.error('识别失败')
            } finally {
                transcribing.value = false
            }
        }

        // --- 改名 ---
        const openRenameModal = (row: TreeNode) => {
            renameTarget.value = row
            renameValue.value = row.filename ? row.filename.replace(/\.[^/.]+$/, '') : ''
            renameModalVisible.value = true
        }

        const confirmRename = async () => {
            if (!renameTarget.value || !renameValue.value.trim()) return
            try {
                await audioApi.rename(renameTarget.value.filepath!, renameValue.value.trim())
                message.success('重命名成功')
                renameModalVisible.value = false
                await loadTree()
            } catch (e: any) {
                message.error(e.response?.data?.detail || '重命名失败')
            }
        }

        // --- 移动 ---
        const openMoveModal = async (row: TreeNode) => {
            moveTarget.value = row
            moveTargetFolder.value = null
            try {
                const res = await audioApi.folders()
                const opts: SelectOption[] = []
                // 添加"未分组"选项（根目录）
                if (row.parent_dir) {
                    opts.push({ label: '📁 未分组 (根目录)', value: '_root_' })
                }
                ;(res.data.folders || [])
                    .filter((f: string) => f !== row.parent_dir)
                    .forEach((f: string) => opts.push({ label: f, value: f }))
                folderOptions.value = opts
            } catch { /* ignore */ }
            moveModalVisible.value = true
        }

        const confirmMove = async () => {
            if (!moveTarget.value || !moveTargetFolder.value) return
            try {
                await audioApi.move(moveTarget.value.filepath!, moveTargetFolder.value)
                message.success('移动成功')
                moveModalVisible.value = false
                await loadTree()
            } catch (e: any) {
                message.error(e.response?.data?.detail || '移动失败')
            }
        }

        // --- 波形切分 ---
        const openSplitModal = (row: TreeNode) => {
            splitTarget.value = row
            splitModalVisible.value = true
        }

        const onSplitDone = async () => {
            await loadTree()
        }

        // --- 单文件删除 ---
        const deleteSingle = async (row: TreeNode) => {
            try {
                await audioApi.delete(row.filename!, row.parent_dir)
                message.success('已删除')
                await loadTree()
            } catch {
                message.error('删除失败')
            }
        }

        // --- 工具函数 ---
        const formatDuration = (seconds: number) => {
            if (!seconds && seconds !== 0) return '-'
            const m = Math.floor(seconds / 60)
            const s = (seconds % 60).toFixed(1)
            return m > 0 ? `${m}m ${s}s` : `${s}s`
        }

        // --- 表格列 ---
        const columns: DataTableColumns<TreeNode> = [
            { type: 'selection' },
            {
                title: '名称', key: 'name', width: 180,
                render(row) {
                    return h('span', { style: 'color: #333; font-size: 13px; text-align: left; display: block' }, row.seg_name || row.filename)
                },
            },
            {
                title: '时长', key: 'duration', width: 80,
                render(row) {
                    return formatDuration(row.duration_sec || 0)
                },
            },
            {
                title: '识别文本', key: 'text', minWidth: 200,
                render(row) {
                    return h(NInput, {
                        value: editingTexts.value[row.key] || '',
                        'onUpdate:value': (val: string) => { editingTexts.value[row.key] = val },
                        size: 'small', placeholder: '暂无识别文本',
                        style: 'width: 100%',
                        onBlur: () => saveText(row.filepath!),
                        onKeydown: (e: KeyboardEvent) => { if (e.key === 'Enter') saveText(row.filepath!) },
                    })
                },
            },
            {
                title: '操作', key: 'actions', width: 190, fixed: 'right',
                render(row) {
                    const isPlaying = playingFile.value === row.filepath
                    return h(NSpace, { size: 2, wrap: false }, { default: () => [
                            h(NTooltip, {}, {
                                trigger: () => h(NButton, { size: 'tiny', circle: true, quaternary: true,
                                    type: isPlaying ? 'error' : 'primary', onClick: () => playAudio(row.filepath!),
                                }, { icon: () => h(NIcon, { size: 16 }, { default: () => h(isPlaying ? StopCircleOutline : PlayCircleOutline) }) }),
                                default: () => isPlaying ? '停止' : '播放',
                            }),
                            h(NTooltip, {}, {
                                trigger: () => h(NButton, { size: 'tiny', circle: true, quaternary: true, type: 'warning',
                                    onClick: () => openSplitModal(row),
                                }, { icon: () => h(NIcon, { size: 16 }, { default: () => h(CutOutline) }) }),
                                default: () => '波形切分',
                            }),
                            h(NTooltip, {}, {
                                trigger: () => h(NButton, { size: 'tiny', circle: true, quaternary: true, type: 'info',
                                    onClick: () => openRenameModal(row),
                                }, { icon: () => h(NIcon, { size: 16 }, { default: () => h(PencilOutline) }) }),
                                default: () => '改名',
                            }),
                            h(NTooltip, {}, {
                                trigger: () => h(NButton, { size: 'tiny', circle: true, quaternary: true, type: 'info',
                                    onClick: () => openMoveModal(row),
                                }, { icon: () => h(NIcon, { size: 16 }, { default: () => h(SwapHorizontalOutline) }) }),
                                default: () => '移动',
                            }),
                            h(NPopconfirm, { onPositiveClick: () => deleteSingle(row) }, {
                                trigger: () => h(NButton, { size: 'tiny', circle: true, quaternary: true, type: 'error',
                                }, { icon: () => h(NIcon, { size: 16 }, { default: () => h(TrashOutline) }) }),
                                default: () => '确定删除？',
                            }),
                        ] })
                },
            },
        ]

        onMounted(() => {
            loadTree()
            loadSources()
        })

        // 每次激活组件时都刷新数据（配合 KeepAlive）
        onActivated(() => {
            loadTree()
            loadSources()
        })

        const selectedFileCount = computed(() => getSelectedFiles().length)

        // 分页配置
        const pagination = reactive({
            page: 1,
            pageSize: 10,
            showSizePicker: true,
            pageSizes: [10, 20, 50, 100, 1000],
            prefix: ({ itemCount }: { itemCount: number }) => `共 ${itemCount} 条`,
            onChange: (page: number) => { pagination.page = page },
            onUpdatePageSize: (pageSize: number) => { pagination.pageSize = pageSize; pagination.page = 1 },
        })

        // 当前选中文件夹名称
        const selectedFolderLabel = computed(() => {
            if (!selectedFolderKey.value || selectedFolderKey.value === '__all__') return '全部'
            return selectedFolderKey.value
        })

        return () => {
            const modals = [
                <NModal show={mergeModalVisible.value}
                        onUpdateShow={(val: boolean) => { mergeModalVisible.value = val }}
                        preset="dialog" title="合并音频" positiveText="确认合并" negativeText="取消"
                        onPositiveClick={confirmMerge}>
                    <NSpace vertical>
                        <p>将合并 {selectedFileCount.value} 个音频文件</p>
                        <NAlert type="info" showIcon={false}>输出文件: {mergePreviewName.value}</NAlert>
                        <NAlert type="warning" showIcon={false}>按选择顺序合并，保存在第一个文件所在目录</NAlert>
                    </NSpace>
                </NModal>,
                <NModal show={renameModalVisible.value}
                        onUpdateShow={(val: boolean) => { renameModalVisible.value = val }}
                        preset="dialog" title="重命名文件" positiveText="确认" negativeText="取消"
                        onPositiveClick={confirmRename}>
                    <NSpace vertical>
                        <p>当前文件: {renameTarget.value?.filename}</p>
                        <NInput v-model:value={renameValue.value} placeholder="输入新文件名（不含扩展名）" />
                    </NSpace>
                </NModal>,
                <NModal show={moveModalVisible.value}
                        onUpdateShow={(val: boolean) => { moveModalVisible.value = val }}
                        preset="dialog" title="移动文件" positiveText="确认移动" negativeText="取消"
                        onPositiveClick={confirmMove}>
                    <NSpace vertical>
                        <p>将 {moveTarget.value?.filename} 移动到：</p>
                        <NSelect value={moveTargetFolder.value}
                                 onUpdateValue={(v: string) => { moveTargetFolder.value = v }}
                                 options={folderOptions.value} placeholder="选择目标文件夹" />
                    </NSpace>
                </NModal>,
                <WaveformSplitModal
                    show={splitModalVisible.value}
                    {...{ 'onUpdate:show': (val: boolean) => { splitModalVisible.value = val }, 'onSplit-done': onSplitDone }}
                    filepath={splitTarget.value?.filepath || ''}
                    filename={splitTarget.value?.filename || ''}
                    durationSec={splitTarget.value?.duration_sec || 0}
                />,
                // 查看推理文本弹窗
                <NModal show={outputListModalVisible.value}
                        onUpdateShow={(val: boolean) => { outputListModalVisible.value = val }}
                        preset="card" title="推理文本 (output.list)" style="width: 1000px; height: 700px">
                    {{
                        default: () => (
                            <NSpace vertical size="medium" style="height: 100%">
                                <div style="font-size: 12px; color: #999">
                                    路径: {outputListPath.value}
                                </div>
                                {outputListLoading.value ? (
                                    <div style="text-align: center; padding: 40px">加载中...</div>
                                ) : outputListContent.value ? (
                                    <div style={{
                                        flex: 1,
                                        padding: '12px',
                                        background: '#fafafa',
                                        border: '1px solid #eee',
                                        borderRadius: '4px',
                                        overflowY: 'auto',
                                        fontFamily: 'monospace',
                                        fontSize: '13px',
                                        lineHeight: '1.8',
                                        whiteSpace: 'pre-wrap',
                                        wordBreak: 'break-all',
                                    }}>
                                        {outputListContent.value}
                                    </div>
                                ) : (
                                    <NEmpty description="文件不存在或为空" />
                                )}
                            </NSpace>
                        ),
                    }}
                </NModal>,
            ]

            return (
                <div style="display: flex; flex-direction: column; height: calc(100vh - 32px); gap: 12px;">
                    {/* 源音频 - 可折叠，固定最大高度 */}
                    <NCard title="源音频" size="small" style="flex-shrink: 0; max-height: 180px; overflow-y: auto;"
                           v-slots={{
                               'header-extra': () => (
                                   <NSpace align="center">
                                       <NTag type="info" size="small">{sourceTotalFiles.value} 个源文件</NTag>
                                       <NButton size="tiny" type="primary" loading={importing.value}
                                                onClick={triggerImport}
                                                v-slots={{ icon: () => <NIcon size={14}><CloudUploadOutline /></NIcon> }}>
                                           导入
                                       </NButton>
                                       <input
                                           ref={importInputRef}
                                           type="file" multiple
                                           accept=".wav,.mp3,.flac,.ogg,.mp4,.mkv,.avi,.webm,.m4a"
                                           style="display: none"
                                           onChange={handleImportFiles}
                                       />
                                       <NButton size="tiny" quaternary onClick={loadSources}
                                                v-slots={{ icon: () => <NIcon size={14}><RefreshOutline /></NIcon> }} />
                                   </NSpace>
                               ),
                           }}
                    >
                        {sourceGroups.value.length === 0 ? (
                            <NEmpty description="输入目录中暂无源文件" size="small" />
                        ) : (
                            <NCollapse defaultExpandedNames={sourceGroups.value.map((_, i) => String(i))}>
                                {sourceGroups.value.map((group, gi) => (
                                    <NCollapseItem
                                        key={gi}
                                        name={String(gi)}
                                        v-slots={{
                                            header: () => (
                                                <NSpace align="center" size="small">
                                                    <NIcon size={16} color="#f0a020"><FolderOpenOutline /></NIcon>
                                                    <span style="font-weight: 500">{group.folder}</span>
                                                    <NTag size="tiny" type="info" round>{group.count} 个</NTag>
                                                    <NTag size="tiny" round>{group.total_size_mb} MB</NTag>
                                                </NSpace>
                                            ),
                                        }}
                                    >
                                        <div style="display: flex; flex-wrap: wrap; gap: 8px">
                                            {group.files.map(sf => {
                                                const isPlaying = playingSource.value === sf.filepath
                                                const isVideo = ['.mp4', '.mkv', '.avi', '.webm'].includes(sf.ext)
                                                return (
                                                    <div key={sf.filepath} style="display: flex; align-items: center; gap: 8px; padding: 6px 10px; background: #fafafa; border-radius: 6px; border: 1px solid #eee; min-width: 280px; flex: 1; max-width: 480px">
                                                        <NIcon size={18} color={isVideo ? '#18a058' : '#2080f0'}>
                                                            {isVideo ? <VideocamOutline /> : <PlayCircleOutline />}
                                                        </NIcon>
                                                        <div style="flex: 1; min-width: 0">
                                                            <div style="font-size: 13px; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap" title={sf.filename}>
                                                                {sf.filename}
                                                            </div>
                                                            <div style="font-size: 12px; color: #999">{sf.size_mb} MB</div>
                                                        </div>
                                                        <NButton size="tiny" circle type={isPlaying ? 'error' : 'primary'} quaternary
                                                                 onClick={() => playSource(sf.filepath)}>
                                                            {{ icon: () => <NIcon size={16}>{isPlaying ? <StopCircleOutline /> : <PlayCircleOutline />}</NIcon> }}
                                                        </NButton>
                                                         <NPopconfirm 
                                                            onPositiveClick={() => deleteSourceFile(sf.filepath, sf.filename)}
                                                            positiveText="删除" 
                                                            negativeText="取消"
                                                        >
                                                            {{
                                                                trigger: () => (
                                                                    <NButton size="tiny" circle type="error" quaternary>
                                                                        {{ icon: () => <NIcon size={16}><TrashOutline /></NIcon> }}
                                                                    </NButton>
                                                                ),
                                                                default: () => `确定删除源文件 "${sf.filename}"？`,
                                                            }}
                                                        </NPopconfirm>
                                                    </div>
                                                )
                                            })}
                                        </div>
                                    </NCollapseItem>
                                ))}
                            </NCollapse>
                        )}
                    </NCard>

                    {/* 音频管理 - 填满剩余高度 */}
                    <NCard title="音频管理" size="small" style="flex: 1; min-height: 0; display: flex; flex-direction: column;"
                           contentStyle="flex: 1; min-height: 0; display: flex; flex-direction: column; padding: 12px;"
                           v-slots={{
                               'header-extra': () => (
                                   <NSpace align="center">
                                       <NTag type="info" size="small">
                                           {totalFolders.value} 个文件夹 / {totalFiles.value} 个文件
                                       </NTag>
                                       <NButton size="small" onClick={viewOutputList}
                                                v-slots={{ icon: () => <NIcon><DocumentTextOutline /></NIcon> }}>
                                           查看推理文本
                                       </NButton>
                                       <NButton size="small" onClick={loadTree} loading={loading.value}
                                                v-slots={{ icon: () => <NIcon><RefreshOutline /></NIcon> }}>
                                           刷新
                                       </NButton>
                                   </NSpace>
                               ),
                           }}
                    >
                        <div style="display: flex; gap: 12px; flex: 1; min-height: 0;">
                            {/* 左侧文件夹树 */}
                            <div style="width: 200px; flex-shrink: 0; border-right: 1px solid #efeff5; padding-right: 12px; overflow-y: auto;">
                                <NTree
                                    data={folderTreeOptions.value}
                                    blockLine
                                    selectable
                                    selectedKeys={selectedFolderKey.value ? [selectedFolderKey.value] : ['__all__']}
                                    onUpdateSelectedKeys={(keys: string[]) => {
                                        selectedFolderKey.value = keys[0] || null
                                        pagination.page = 1
                                        checkedKeys.value = []
                                    }}
                                    style="font-size: 13px;"
                                />
                            </div>

                            {/* 右侧内容区 */}
                            <div style="flex: 1; min-width: 0; display: flex; flex-direction: column; min-height: 0;">
                                {/* 时长筛选滑块 */}
                                <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px;">
                                    <span style="color: #666; font-size: 12px; white-space: nowrap;">时长</span>
                                    <span style="color: #2080f0; font-size: 12px; font-weight: 500; min-width: 20px; text-align: right;">{durationRange.value[0].toFixed(1)}s</span>
                                    <div style="flex: 1; min-width: 150px; max-width: 250px;">
                                        <NSlider
                                            value={durationRange.value}
                                            onUpdateValue={(v: any) => {
                                                durationRange.value = v
                                                // 防抖：3秒后才更新筛选条件
                                                if (durationDebounceTimer) clearTimeout(durationDebounceTimer)
                                                durationDebounceTimer = setTimeout(() => {
                                                    filterDuration.value = v
                                                    pagination.page = 1
                                                }, 1000)
                                            }}
                                            range min={0} max={durationSliderMax.value} step={0.1}
                                            tooltip={true}
                                            formatTooltip={(v: number) => `${v.toFixed(1)}s`}
                                        />
                                    </div>
                                    <span style="color: #2080f0; font-size: 12px; font-weight: 500; min-width: 28px;">{durationRange.value[1].toFixed(1)}s</span>
                                </div>
                                {/* 批量操作栏 */}
                                <NSpace style="margin-bottom: 8px" align="center" size="small" wrap>
                                    <NButton size="small" type="primary" onClick={openMergeModal}
                                             disabled={selectedFileCount.value < 2}
                                             v-slots={{ icon: () => <NIcon><GitMergeOutline /></NIcon> }}>
                                        合并 ({selectedFileCount.value})
                                    </NButton>
                                    <NButton size="small" type="success" onClick={transcribeSelected}
                                             disabled={selectedFileCount.value === 0} loading={transcribing.value}
                                             v-slots={{ icon: () => <NIcon><MicOutline /></NIcon> }}>
                                        识别 ({selectedFileCount.value})
                                    </NButton>
                                    <NPopconfirm onPositiveClick={deleteSelected}>
                                        {{
                                            trigger: () => (
                                                <NButton size="small" type="error"
                                                         disabled={selectedFileCount.value === 0}
                                                         v-slots={{ icon: () => <NIcon><TrashOutline /></NIcon> }}>
                                                    删除 ({selectedFileCount.value})
                                                </NButton>
                                            ),
                                            default: () => `确定删除 ${selectedFileCount.value} 个文件？`,
                                        }}
                                    </NPopconfirm>
                                    <NButton size="small" type="warning" onClick={exportList}
                                             disabled={selectedFileCount.value === 0}
                                             v-slots={{ icon: () => <NIcon><DocumentTextOutline /></NIcon> }}>
                                        推理文本 ({selectedFileCount.value})
                                    </NButton>
                                </NSpace>

                                {/* 数据表格 */}
                                <div style="flex: 1; min-height: 0;">
                                    {filteredFiles.value.length === 0 && !loading.value ? (
                                        <NEmpty description="暂无音频文件" />
                                    ) : (
                                        <NDataTable
                                            columns={columns} data={filteredFiles.value}
                                            loading={loading.value} size="small"
                                            flexHeight style="height: 100%"
                                            rowKey={(row: TreeNode) => row.key}
                                            checkedRowKeys={checkedKeys.value}
                                            onUpdateCheckedRowKeys={(keys: DataTableRowKey[]) => { checkedKeys.value = keys }}
                                            pagination={pagination as any}
                                        />
                                    )}
                                </div>
                            </div>
                        </div>
                    </NCard>
                    {modals}
                </div>
            )
        }
    },
})
