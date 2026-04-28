import axios from 'axios'

const api = axios.create({
    baseURL: '/api',
    timeout: 300000,
})

// 配置 API
export const configApi = {
    get: () => api.get('/config'),
    update: (data: any) => api.put('/config', data),
    updateSection: (section: string, data: any) => api.patch(`/config/${section}`, data),
    browseDirs: (path?: string) => api.get('/config/browse-dirs', { params: { path: path || '' } }),
}

// 任务 API
export const taskApi = {
    run: () => api.post('/task/run'),
    status: () => api.get('/task/status'),
    stop: () => api.post('/task/stop'),
}

// 音频 API
export const audioApi = {
    list: () => api.get('/audio/list'),
    tree: () => api.get('/audio/tree'),
    playUrl: (path: string) => `/api/audio/play?path=${encodeURIComponent(path)}`,
    delete: (filename: string, dir?: string) =>
        api.delete(`/audio/${encodeURIComponent(filename)}`, { params: { dir } }),
    merge: (filepaths: string[], output_filename?: string) =>
        api.post('/audio/merge', { filepaths, output_filename }),
    split: (filepath: string) => api.post('/audio/split', { filepath }),
    splitAtTimes: (filepath: string, times: number[]) =>
        api.post('/audio/split-at-times', { filepath, times }),
    transcribe: (filepath: string) => api.post('/audio/transcribe', { filepath }),
    updateText: (filepath: string, text: string) =>
        api.put('/audio/text', { filepath, text }),
    exportList: (items?: any[]) => api.post('/audio/export-list', { items: items || [] }),
    getOutputList: () => api.get('/audio/output-list'),
    rename: (filepath: string, newName: string) =>
        api.put('/audio/rename', { filepath, new_name: newName }),
    move: (filepath: string, targetFolder: string) =>
        api.put('/audio/move', { filepath, target_folder: targetFolder }),
    folders: () => api.get('/audio/folders'),
    sources: () => api.get('/audio/sources'),
    importSource: (files: File[], subfolder?: string) => {
        const formData = new FormData()
        files.forEach(f => formData.append('files', f))
        if (subfolder) formData.append('subfolder', subfolder)
        return api.post('/audio/import-source', formData, {
            headers: { 'Content-Type': 'multipart/form-data' },
            timeout: 600000,
        })
    },
    removeSource: (filepath: string) =>
        api.delete('/audio/remove-source', { params: { filepath } }),
    convertToWav: (filepath: string) => api.post('/audio/convert-to-wav', {}, { params: { filepath } }),
    convertAudio: (filepath: string, outputFormat: string) =>
        api.post('/audio/convert', { filepath, output_format: outputFormat }),
}

export default api
