import React, { useState, useEffect, useCallback } from 'react';
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
              selectedFiles={selectedFiles}
              onFilesSelected={(files) => setSelectedFiles((prev) => [...prev, ...files])}
              onRemoveFile={(idx) => setSelectedFiles((prev) => prev.filter((_, i) => i !== idx))}
              t={t}
            />

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

        {/* ── Main jobs area ── */}
        <section className="jobs-area">
          <h2 className="section-title">{t.jobsTitle}</h2>

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
