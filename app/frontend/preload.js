/**
 * Electron Preload  –  V2
 * Exposes a safe IPC bridge via contextBridge.
 */
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electron', {
  api: {
    healthCheck:      ()               => ipcRenderer.invoke('api:health'),
    getHardware:      ()               => ipcRenderer.invoke('api:hardware'),
    upload:           (filePath, lang, model, speakerCount, chunkSeconds, diarizationMode, performanceMode, speakerRange) => ipcRenderer.invoke('api:upload', filePath, lang, model, speakerCount, chunkSeconds, diarizationMode, performanceMode, speakerRange),
    getJob:           (jobId)          => ipcRenderer.invoke('api:get-job', jobId),
    listJobs:         (skip, limit)    => ipcRenderer.invoke('api:list-jobs', skip, limit),
    exportTranscript: (jobId, format)  => ipcRenderer.invoke('api:export', jobId, format),
    cancelJob:        (jobId)          => ipcRenderer.invoke('api:cancel-job', jobId),
    pauseJob:         (jobId)          => ipcRenderer.invoke('api:pause-job', jobId),
    resumeJob:        (jobId)          => ipcRenderer.invoke('api:resume-job', jobId),
    deleteJob:        (jobId)          => ipcRenderer.invoke('api:delete-job', jobId),
  },
  file: {
    openDialog:  ()               => ipcRenderer.invoke('file:open-dialog'),
    openDirectoryDialog: ()       => ipcRenderer.invoke('file:open-directory-dialog'),
    selectDirectoryPath: ()       => ipcRenderer.invoke('file:select-directory-path'),
    saveDialog:  (filename)       => ipcRenderer.invoke('file:save-dialog', filename),
    write:       (path, data)     => ipcRenderer.invoke('file:write', path, data),
  },
  shell: {
    open: (path) => ipcRenderer.invoke('shell:open', path),
    showItem: (path) => ipcRenderer.invoke('shell:show-item', path),
  },
  win: {
    minimize: () => ipcRenderer.invoke('win:minimize'),
    maximize: () => ipcRenderer.invoke('win:maximize'),
    close:    () => ipcRenderer.invoke('win:close'),
    reload:   () => ipcRenderer.invoke('win:reload'),
    restart:  () => ipcRenderer.invoke('win:restart'),
  },
});
