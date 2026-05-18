import React, { useState, useEffect, useCallback, useRef } from 'react';
import './App.css';
import DropZone from './components/DropZone';
import HardwareInfo from './components/HardwareInfo';
import LanguageSwitcher from './components/LanguageSwitcher';
import JobCard from './components/JobCard';
import en from './i18n/en';
import ja from './i18n/ja';

const API = 'http://127.0.0.1:8000';
const STRINGS = { en, ja };

export default function App() {
  const [uiLang, setUiLang]           = useState('ja');
  const [transcribeLang, setTranscribeLang] = useState('auto');
  const [transcribeModel, setTranscribeModel] = useState('auto');
  const [speakerCount, setSpeakerCount] = useState('auto');
  const [chunkSeconds, setChunkSeconds] = useState('auto');
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [jobs, setJobs]               = useState([]);
  const [loading, setLoading]         = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0); // 0-100 upload %
  const [uploadPhase, setUploadPhase] = useState(''); // 'uploading' | 'processing' | ''
  const [uploadNotice, setUploadNotice] = useState(''); // Live text for current sequential job
  const [toast, setToast]             = useState(null);
  const [backendOk, setBackendOk]     = useState(null);

  // New features state
  const [activeTab, setActiveTab] = useState('history');
  const [settingsExportDir, setSettingsExportDir] = useState('');
  const [logs, setLogs] = useState([]);
  const [autoScrollLogs, setAutoScrollLogs] = useState(true);
  const terminalBodyRef = useRef(null);

  const t = STRINGS[uiLang];

  // ── Backend health check ─────────────────────────────────
  useEffect(() => {
    const check = async () => {
      try {
        const res = await fetch(`${API}/health`);
        setBackendOk(res.ok);
      } catch {
        setBackendOk(false);
      }
    };
    check();
    const id = setInterval(check, 10000);
    return () => clearInterval(id);
  }, []);

  // ── Load Settings ──────────────────────────────────────────
  useEffect(() => {
    const fetchSettings = async () => {
      try {
        const res = await fetch(`${API}/settings`);
        if (res.ok) {
          const data = await res.json();
          setSettingsExportDir(data.transcript_export_dir || '');
        }
      } catch (err) {
        console.error('fetchSettings error:', err);
      }
    };
    fetchSettings();
  }, []);

  // ── Save Settings ──────────────────────────────────────────
  const handleSaveSettings = async () => {
    try {
      const res = await fetch(`${API}/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ transcript_export_dir: settingsExportDir }),
      });
      if (res.ok) {
        showToast(t.settingsSaveSuccess, 'success');
      } else {
        const errData = await res.json();
        showToast(`${t.settingsSaveFailed}: ${errData.detail || 'Error'}`, 'error');
      }
    } catch (err) {
      showToast(`${t.settingsSaveFailed}: ${err.message}`, 'error');
    }
  };

  // ── Native Folder Selection ─────────────────────────────────
  const handleBrowseSettingsFolder = async () => {
    if (window.electron && window.electron.file.selectDirectoryPath) {
      try {
        const selectedPath = await window.electron.file.selectDirectoryPath();
        if (selectedPath) {
          setSettingsExportDir(selectedPath);
        }
      } catch (err) {
        console.error('selectDirectoryPath error:', err);
      }
    }
  };

  // ── Fetch Backend Logs ──────────────────────────────────────
  const fetchLogs = useCallback(async () => {
    try {
      const res = await fetch(`${API}/logs?limit=150`);
      if (res.ok) {
        const data = await res.json();
        setLogs(data.logs || []);
      }
    } catch (err) {
      console.error('fetchLogs error:', err);
    }
  }, []);

  // Poll logs in the background when Settings tab is active
  useEffect(() => {
    if (activeTab !== 'settings') return;
    fetchLogs();
    const id = setInterval(fetchLogs, 2500);
    return () => clearInterval(id);
  }, [activeTab, fetchLogs]);

  // Auto-scroll logs terminal
  useEffect(() => {
    if (autoScrollLogs && terminalBodyRef.current) {
      terminalBodyRef.current.scrollTop = terminalBodyRef.current.scrollHeight;
    }
  }, [logs, autoScrollLogs, activeTab]);

  // ── Load jobs ─────────────────────────────────────────────
  const loadJobs = useCallback(async () => {
    try {
      let data;
      if (window.electron) {
        data = await window.electron.api.listJobs(0, 30);
      } else {
        const res = await fetch(`${API}/jobs?skip=0&limit=30`);
        data = await res.json();
      }
      setJobs(data.jobs || []);
    } catch (err) {
      console.error('loadJobs:', err);
    }
  }, []);

  useEffect(() => {
    loadJobs();
    const id = setInterval(loadJobs, 4000);
    return () => clearInterval(id);
  }, [loadJobs]);

  // ── Toast helper ──────────────────────────────────────────
  const showToast = (msg, type = 'info') => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 4000);
  };

  // ── Upload ────────────────────────────────────────────────
  const handleUpload = async () => {
    if (selectedFiles.length === 0) { showToast(t.errorSelectFile, 'error'); return; }
    setLoading(true);
    setUploadProgress(0);

    const filesToUpload = [...selectedFiles];
    setSelectedFiles([]); // clear queue immediately to prevent double submissions

    for (let i = 0; i < filesToUpload.length; i++) {
      const file = filesToUpload[i];
      setUploadPhase('uploading');
      setUploadProgress(0);
      const noticePrefix = `[${i + 1}/${filesToUpload.length}] `;
      setUploadNotice(`${noticePrefix}${uiLang === 'ja' ? 'アップロード中: ' : 'Uploading: '}${file.name}`);

      try {
        let response;

        if (window.electron && (file._isPath || file.path)) {
          // Electron path (both browsed and dropped files support IPC upload)
          setUploadProgress(50);
          response = await window.electron.api.upload(file.path, transcribeLang, transcribeModel, speakerCount, chunkSeconds);
          setUploadProgress(100);
        } else {
          // Browser / React dev fallback
          const formData = new FormData();
          formData.append('file', file);

          response = await new Promise((resolve, reject) => {
            const xhr = new XMLHttpRequest();
            const speakerParam = speakerCount && speakerCount !== 'auto' ? `&speaker_count=${speakerCount}` : '';
            const chunkParam = chunkSeconds && chunkSeconds !== 'auto' ? `&chunk_seconds=${chunkSeconds}` : '';
            xhr.open('POST', `${API}/upload?language=${transcribeLang}&model=${transcribeModel}${speakerParam}${chunkParam}`);

            xhr.upload.addEventListener('progress', (e) => {
              if (e.lengthComputable) {
                const pct = Math.round((e.loaded / e.total) * 100);
                setUploadProgress(pct);
              }
            });

            xhr.addEventListener('load', () => {
              if (xhr.status >= 200 && xhr.status < 300) {
                resolve(JSON.parse(xhr.responseText));
              } else {
                reject(new Error(`Upload failed: ${xhr.status} ${xhr.statusText}`));
              }
            });

            xhr.addEventListener('error', () => reject(new Error('Network error during upload')));
            xhr.addEventListener('abort', () => reject(new Error('Upload aborted')));
            xhr.send(formData);
          });
        }

        setUploadPhase('processing');
        setUploadNotice(`${noticePrefix}${uiLang === 'ja' ? 'サーバー処理開始中: ' : 'Starting server process: '}${file.name}`);
        showToast(`✅ Job started: ${file.name}`, 'success');
        await loadJobs();
      } catch (err) {
        showToast(`❌ ${t.errorUpload} (${file.name}): ${err.message}`, 'error');
      }
    }

    setUploadProgress(0);
    setUploadPhase('');
    setUploadNotice('');
    setLoading(false);
  };

  // ── Job events ────────────────────────────────────────────
  const handleDeleted  = (id) => setJobs((prev) => prev.filter((j) => j.id !== id));
  const handleCancelled = () => loadJobs();

  const activeJobs    = jobs.filter(j => j.status === 'transcribing' || j.status === 'pending' || j.status === 'paused');
  const completedJobs = jobs.filter(j => j.status === 'completed');
  const otherJobs     = jobs.filter(j => !['transcribing','pending','paused','completed'].includes(j.status));

  return (
    <div className="app">
      {/* ── Header ── */}
      <header className="app-header">
        <div className="app-header__left">
          <span className="app-logo">🎙️</span>
          <div>
            <h1 className="app-title">{t.appTitle}</h1>
            <p className="app-subtitle">{t.appSubtitle}</p>
          </div>
        </div>
        <div className="app-header__right">
          {/* Backend status dot */}
          <span
            className={`backend-dot ${backendOk === true ? 'backend-dot--ok' : backendOk === false ? 'backend-dot--err' : 'backend-dot--unknown'}`}
            title={backendOk ? 'Backend connected' : 'Backend offline'}
          />
          <LanguageSwitcher uiLang={uiLang} onToggle={() => setUiLang(u => u === 'en' ? 'ja' : 'en')} />
        </div>
      </header>

      <main className="app-main">
        {/* ── Left panel ── */}
        <aside className="sidebar">
          <HardwareInfo t={t} />

          <section className="upload-panel glass-panel">
            <DropZone
              onFilesSelected={(files) => setSelectedFiles((prev) => [...prev, ...files])}
              t={t}
            />

            {/* Selected File Queue List - Unlimited Files displayed clearly on Left sidebar */}
            {selectedFiles.length > 0 && (
              <div className="selected-files-card">
                <div className="selected-files-header">
                  <span className="selected-files-title">{t.selectedFile}</span>
                  <span className="selected-files-count" id="sidebar-queue-count">{selectedFiles.length}</span>
                </div>
                <div className="selected-file-list" id="sidebar-file-queue">
                  {selectedFiles.map((file, idx) => (
                    <div className="selected-file-item" key={idx}>
                      <span className="selected-file-icon">🎵</span>
                      <span className="selected-file-name" title={file.name}>{file.name}</span>
                      {file.size > 0 && (
                        <span className="selected-file-size">({(file.size / 1024 / 1024).toFixed(1)} MB)</span>
                      )}
                      <button
                        type="button"
                        className="selected-file-remove"
                        onClick={() => setSelectedFiles(prev => prev.filter((_, i) => i !== idx))}
                        title="Remove file"
                      >✕</button>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Transcription language selector */}
            <div className="lang-select-row">
              <label htmlFor="transcribe-lang-select" className="lang-select-label">
                {t.language}
              </label>
              <select
                id="transcribe-lang-select"
                className="lang-select"
                value={transcribeLang}
                onChange={e => setTranscribeLang(e.target.value)}
              >
                <option value="auto">{uiLang === 'ja' ? '自動検出 / Auto' : 'Auto Detect'}</option>
                <option value="ja">{t.languageJa}</option>
                <option value="en">{t.languageEn}</option>
                <option value="zh">中文</option>
                <option value="ko">한국어</option>
                <option value="es">Español</option>
                <option value="fr">Français</option>
                <option value="de">Deutsch</option>
              </select>
            </div>

            {/* Transcription model selector */}
            <div className="lang-select-row">
              <label htmlFor="transcribe-model-select" className="lang-select-label">
                {t.model || 'Model'}
              </label>
              <select
                id="transcribe-model-select"
                className="lang-select"
                value={transcribeModel}
                onChange={e => setTranscribeModel(e.target.value)}
              >
                <option value="auto">Auto</option>
                <option value="large-v3">large-v3</option>
                <option value="medium">medium</option>
                <option value="small">small</option>
                <option value="base">base</option>
                <option value="tiny">tiny</option>
              </select>
            </div>

            {/* Speaker count selector */}
            <div className="lang-select-row">
              <label htmlFor="speaker-count-select" className="lang-select-label">
                👥 {t.speakers || '話者数'}
              </label>
              <select
                id="speaker-count-select"
                className="lang-select"
                value={speakerCount}
                onChange={e => setSpeakerCount(e.target.value)}
              >
                <option value="auto">{uiLang === 'ja' ? '自動検出 / Auto' : 'Auto Detect'}</option>
                <option value="1">1</option>
                <option value="2">2 (推奨 / Recommended)</option>
                <option value="3">3</option>
                <option value="4">4</option>
                <option value="5">5</option>
                <option value="6">6</option>
              </select>
            </div>

            {/* Chunk seconds selector */}
            <div className="lang-select-row">
              <label htmlFor="chunk-seconds-select" className="lang-select-label">
                ⏱️ {uiLang === 'ja' ? '分割時間 / Chunk' : 'Chunk Size'}
              </label>
              <select
                id="chunk-seconds-select"
                className="lang-select"
                value={chunkSeconds}
                onChange={e => setChunkSeconds(e.target.value)}
              >
                <option value="auto">{uiLang === 'ja' ? '自動 (推奨) / Auto' : 'Auto Profile'}</option>
                <option value="60">1分 / 1 min (高速 / Fast progress)</option>
                <option value="180">3分 / 3 mins</option>
                <option value="300">5分 / 5 mins (高精度 / Balanced)</option>
                <option value="600">10分 / 10 mins</option>
                <option value="0">{uiLang === 'ja' ? '無制限 / No Chunking (最高精度)' : 'Full File (Max Coherence)'}</option>
              </select>
            </div>

            <button
              id="upload-btn"
              className={`btn btn-primary btn-upload ${loading ? 'btn--loading' : ''}`}
              onClick={handleUpload}
              disabled={selectedFiles.length === 0 || loading}
            >
              {loading && uploadPhase === 'uploading' ? t.uploading
                : loading && uploadPhase === 'processing' ? t.processing
                : t.uploadBtn}
            </button>

            {/* Upload progress bar */}
            {loading && (
              <div className="upload-progress-wrap">
                <div className="upload-progress-track">
                  <div
                    className={`upload-progress-fill ${uploadPhase === 'processing' ? 'upload-progress-fill--pulse' : ''}`}
                    style={{ width: `${uploadPhase === 'processing' ? 100 : uploadProgress}%` }}
                  />
                </div>
                <div className="upload-progress-meta">
                  <span className="upload-progress-label">
                    {uploadNotice || (uploadPhase === 'uploading'
                      ? `⬆ ${uploadProgress}%`
                      : uploadPhase === 'processing'
                      ? '⚙ ' + (uiLang === 'ja' ? 'サーバー処理中...' : 'Server processing...')
                      : '')}
                  </span>
                </div>
              </div>
            )}
          </section>
        </aside>

        {/* ── Main content area with Tabs ── */}
        <section className="jobs-area">
          <div className="tabs-nav-wrapper">
            <div className="tabs-nav">
              <button
                className={`tab-btn ${activeTab === 'history' ? 'tab-btn--active' : ''}`}
                onClick={() => setActiveTab('history')}
                id="tab-btn-history"
              >
                📖 {t.tabHistory}
              </button>
              <button
                className={`tab-btn ${activeTab === 'settings' ? 'tab-btn--active' : ''}`}
                onClick={() => setActiveTab('settings')}
                id="tab-btn-settings"
              >
                ⚙️ {t.tabSettings}
              </button>
            </div>
          </div>

          {activeTab === 'history' ? (
            <>
              {jobs.length === 0 && (
                <div className="empty-state">
                  <span className="empty-icon">🎤</span>
                  <p>{t.noJobs}</p>
                </div>
              )}

              {/* Active */}
              {activeJobs.map(job => (
                <JobCard key={job.id} job={job} t={t} onDeleted={handleDeleted} onCancelled={handleCancelled} />
              ))}

              {/* Completed */}
              {completedJobs.map(job => (
                <JobCard key={job.id} job={job} t={t} onDeleted={handleDeleted} onCancelled={handleCancelled} />
              ))}

              {/* Others (failed / cancelled) */}
              {otherJobs.map(job => (
                <JobCard key={job.id} job={job} t={t} onDeleted={handleDeleted} onCancelled={handleCancelled} />
              ))}
            </>
          ) : (
            <div className="settings-section glass-panel" style={{ padding: '24px', borderRadius: 'var(--radius-lg)' }}>
              <div className="settings-group">
                <label className="settings-label" htmlFor="settings-export-path-input">{t.settingsExportPath}</label>
                <p className="app-subtitle" style={{ fontSize: '12px', margin: '-4px 0 8px 0', color: 'var(--clr-text-muted)', textAlign: 'left' }}>
                  {t.settingsExportPathDesc}
                </p>
                <div className="settings-path-row">
                  <input
                    type="text"
                    className="settings-input-path"
                    value={settingsExportDir}
                    onChange={(e) => setSettingsExportDir(e.target.value)}
                    placeholder="e.g. C:\Transcripts"
                    id="settings-export-path-input"
                  />
                  {window.electron && (
                    <button
                      type="button"
                      className="btn btn-secondary"
                      onClick={handleBrowseSettingsFolder}
                      id="settings-browse-btn"
                    >
                      📁 {t.browseFolder}
                    </button>
                  )}
                </div>
                <button
                  type="button"
                  className="btn btn-primary btn-settings-save"
                  onClick={handleSaveSettings}
                  id="settings-save-btn"
                  style={{ marginTop: '8px' }}
                >
                  💾 {t.save}
                </button>
              </div>

              {/* Developer Logs Terminal */}
              <div className="settings-group" style={{ marginTop: '16px' }}>
                <label className="settings-label">{t.devLogsTitle}</label>
                <div className="dev-terminal">
                  <div className="terminal-header">
                    <span className="terminal-title">🟢 uvicorn@127.0.0.1:8000 (~/app/storage/logs/backend.log)</span>
                    <div className="terminal-controls">
                      <button
                        type="button"
                        className={`btn-terminal ${autoScrollLogs ? 'tab-btn--active' : ''}`}
                        onClick={() => setAutoScrollLogs(!autoScrollLogs)}
                        style={{ border: '1px solid rgba(255,255,255,0.08)', borderRadius: '4px', fontSize: '10px' }}
                      >
                        🔄 {t.btnScrollToggle}
                      </button>
                      <button
                        type="button"
                        className="btn-terminal"
                        onClick={fetchLogs}
                        style={{ border: '1px solid rgba(255,255,255,0.08)', borderRadius: '4px', fontSize: '10px' }}
                      >
                        ↻ {t.btnRefreshLogs}
                      </button>
                    </div>
                  </div>
                  <div className="terminal-body" ref={terminalBodyRef}>
                    {logs.length === 0 ? (
                      <div className="log-line" style={{ color: 'var(--clr-text-muted)', fontStyle: 'italic' }}>
                        Waiting for backend logs...
                      </div>
                    ) : (
                      logs.map((line, idx) => {
                        let lineClass = "log-line--info";
                        if (line.includes("[WARNING]")) lineClass = "log-line--warn";
                        else if (line.includes("[ERROR]") || line.toLowerCase().includes("exception") || line.includes("[CRITICAL]")) lineClass = "log-line--error";

                        return (
                          <div key={idx} className={`log-line ${lineClass}`}>
                            {line}
                          </div>
                        );
                      })
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}
        </section>
      </main>

      {/* ── Toast ── */}
      {toast && (
        <div className={`toast toast--${toast.type}`} role="alert">
          {toast.msg}
        </div>
      )}
    </div>
  );
}
