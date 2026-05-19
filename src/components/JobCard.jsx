import React, { useState } from 'react';
import ProgressBar from './ProgressBar';

const getApiUrl = () => {
  const saved = localStorage.getItem('api_url');
  if (saved && saved.trim() !== '') {
    return saved.trim();
  }
  const hostname = window.location.hostname || '127.0.0.1';
  const protocol = window.location.protocol || 'http:';
  return `${protocol}//${hostname}:8000`;
};
const API = getApiUrl();

const STATUS_COLORS = {
  pending:       '#94a3b8',
  transcribing:  '#3b82f6',
  completed:     '#22c55e',
  failed:        '#ef4444',
  cancelled:     '#f59e0b',
  paused:        '#f59e0b',
};

const STATUS_ICONS = {
  pending:       '⏳',
  transcribing:  '🎙️',
  completed:     '✅',
  failed:        '❌',
  cancelled:     '🚫',
  paused:        '⏸️',
};

export default function JobCard({ job, t, onDeleted, onCancelled, onStatusChanged }) {
  const [exporting, setExporting] = useState(false);
  const [showEdit, setShowEdit] = useState(false);
  const [speakers, setSpeakers] = useState([]);
  const [editMap, setEditMap] = useState({});
  const [loadingSpeakers, setLoadingSpeakers] = useState(false);
  const [saving, setSaving] = useState(false);
  const [showMetadata, setShowMetadata] = useState(false);

  const handleOpenMedia = async () => {
    if (window.electron && job.file_path) {
      await window.electron.shell.open(job.file_path);
    } else {
      alert('再生できません / Cannot open file (Only supported in Electron app)');
    }
  };

  const handleOpenLocation = async () => {
    if (window.electron && job.file_path) {
      await window.electron.shell.showItem(job.file_path);
    } else {
      alert('フォルダを開けません / Cannot open containing folder (Only supported in Electron app)');
    }
  };

  const formatDuration = (sec) => {
    if (!sec) return '0m 0s';
    const m = Math.floor(sec / 60);
    const s = Math.round(sec % 60);
    return `${m}m ${s}s`;
  };

  const formatDate = (isoStr) => {
    if (!isoStr) return 'Unknown';
    try {
      const d = new Date(isoStr);
      return d.toLocaleString();
    } catch {
      return isoStr;
    }
  };

  const toggleEditSpeakers = async () => {
    if (showEdit) {
      setShowEdit(false);
      return;
    }
    
    setShowEdit(true);
    setLoadingSpeakers(true);
    try {
      const res = await fetch(`${API}/transcript/${job.id}`);
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      const unique = Array.from(new Set(data.segments.map(s => s.speaker || 'Unknown')));
      const validSpeakers = unique.filter(s => s);
      setSpeakers(validSpeakers);
      
      const initialMap = {};
      validSpeakers.forEach(s => {
        initialMap[s] = s;
      });
      setEditMap(initialMap);
    } catch (err) {
      alert(`${t.renameFailed || '話者名の読み込みに失敗しました'}: ${err.message}`);
      setShowEdit(false);
    } finally {
      setLoadingSpeakers(false);
    }
  };

  const handleSaveSpeakers = async () => {
    setSaving(true);
    try {
      const res = await fetch(`${API}/transcript/${job.id}/rename-speakers`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mapping: editMap }),
      });
      if (!res.ok) throw new Error(await res.text());
      alert(t.renameSuccess || '話者名を変更しました！');
      triggerRefresh();
      setShowEdit(false);
    } catch (err) {
      alert(`${t.renameFailed || '話者名の保存に失敗しました'}: ${err.message}`);
    } finally {
      setSaving(false);
    }
  };

  const handleExport = async (format) => {
    setExporting(true);
    try {
      const filename = `transcript_${job.id.substring(0, 8)}.${format}`;

      if (window.electron) {
        const buffer = await window.electron.api.exportTranscript(job.id, format);
        const savePath = await window.electron.file.saveDialog(filename, format);
        if (savePath) {
          await window.electron.file.write(savePath, buffer);
          const uiLang = localStorage.getItem('ui_lang') || 'ja';
          const msg = uiLang === 'ja'
            ? `ファイルを正常にエクスポートしました。\n保存先: ${savePath}\n\n保存したファイルを開きますか？`
            : `Transcript exported successfully.\nSaved to: ${savePath}\n\nWould you like to open the saved file?`;
          if (window.confirm(msg)) {
            await window.electron.shell.open(savePath);
          }
        }
      } else {
        const res = await fetch(`${API}/export/${job.id}?format=${format}`, { method: 'POST' });
        if (!res.ok) throw new Error(await res.text());
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        a.click();
        URL.revokeObjectURL(url);
      }
    } catch (err) {
      alert(`${t.errorExport}: ${err.message}`);
    } finally {
      setExporting(false);
    }
  };

  const handleCancel = async () => {
    try {
      if (window.electron) {
        await window.electron.api.cancelJob(job.id);
      } else {
        await fetch(`${API}/cancel/${job.id}`, { method: 'POST' });
      }
      onCancelled?.(job.id);
    } catch (err) {
      alert(`${t.errorCancel}: ${err.message}`);
    }
  };

  const triggerRefresh = () => {
    if (onStatusChanged) onStatusChanged(job.id);
    else if (onCancelled) onCancelled(job.id);
  };

  const handlePause = async () => {
    try {
      if (window.electron) {
        await window.electron.api.pauseJob(job.id);
      } else {
        const res = await fetch(`${API}/pause/${job.id}`, { method: 'POST' });
        if (!res.ok) throw new Error(await res.text());
      }
      triggerRefresh();
    } catch (err) {
      alert(`${t.errorPause}: ${err.message}`);
    }
  };

  const handleResume = async () => {
    try {
      if (window.electron) {
        await window.electron.api.resumeJob(job.id);
      } else {
        const res = await fetch(`${API}/resume/${job.id}`, { method: 'POST' });
        if (!res.ok) throw new Error(await res.text());
      }
      triggerRefresh();
    } catch (err) {
      alert(`${t.errorResume}: ${err.message}`);
    }
  };

  const handleDelete = async () => {
    try {
      if (window.electron) {
        await window.electron.api.deleteJob(job.id);
      } else {
        await fetch(`${API}/job/${job.id}`, { method: 'DELETE' });
      }
      onDeleted?.(job.id);
    } catch (err) {
      console.error(err);
    }
  };

  const isActive = job.status === 'transcribing' || job.status === 'pending' || job.status === 'paused';
  const isDone   = job.status === 'completed';

  const createdAt = job.created_at
    ? new Date(job.created_at).toLocaleString()
    : '';

  return (
    <div className={`job-card job-card--${job.status}`} id={`job-${job.id.substring(0, 8)}`}>
      {/* Header */}
      <div className="job-card__header">
        <div className="job-card__title">
          <span className="job-card__icon">{STATUS_ICONS[job.status] || '❓'}</span>
          <span className="job-card__filename" title={job.filename}>{job.filename}</span>
        </div>
        <span
          className="job-card__status-badge"
          style={{ background: STATUS_COLORS[job.status] || '#94a3b8' }}
        >
          {t[`status${job.status.charAt(0).toUpperCase() + job.status.slice(1)}`] || job.status}
        </span>
      </div>

      {/* Meta */}
      <div className="job-card__meta" style={{ display: 'flex', flexDirection: 'column', gap: '4px', alignItems: 'flex-start' }}>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
          <span>{createdAt}</span>
          {job.hardware_tier && (
            <span className="job-card__tier-badge">{job.hardware_tier}</span>
          )}
          {job.model_name && <span>· {job.model_name}</span>}
        </div>
        {/* Source File stats (Size, Duration, and filename) */}
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center', fontSize: '11px', color: 'var(--clr-text-muted)', marginTop: '2px', flexWrap: 'wrap' }}>
          {job.file_size_bytes > 0 && (
            <span>📦 {(job.file_size_bytes / 1024 / 1024).toFixed(1)} MB</span>
          )}
          {job.duration_seconds > 0 && (
            <span>⏱️ {formatDuration(job.duration_seconds)}</span>
          )}
          {job.file_path && (
            <span style={{ maxWidth: '350px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={job.file_path}>
              📁 {job.file_path.split('\\').pop().split('/').pop()}
            </span>
          )}
        </div>
      </div>

      {/* Stats */}
      {isDone && (
        <div className="job-card__stats">
          {job.segment_count != null && (
            <span className="stat-pill">📝 {job.segment_count} {t.segments}</span>
          )}
          {job.speaker_count != null && job.speaker_count > 0 && (
            <span className="stat-pill">🎤 {job.speaker_count} {t.speakers}</span>
          )}
        </div>
      )}

      {/* Progress */}
      {isActive && (
        <ProgressBar
          jobId={job.id}
          status={job.status}
          initialPct={job.progress_pct || 0}
          initialLabel={job.progress_label || ''}
          fileSize={job.file_size_bytes}
          duration={job.duration_seconds}
        />
      )}

      {/* Error */}
      {job.status === 'failed' && job.error_message && (
        <div className="job-card__error">{job.error_message}</div>
      )}

      {/* Speaker Editor Panel */}
      {isDone && showEdit && (
        <div className="job-card__speaker-editor">
          <h4>👥 {t.editSpeakers}</h4>
          {loadingSpeakers ? (
            <div className="speaker-editor-loading">Loading...</div>
          ) : (
            <>
              <div className="speaker-editor-fields">
                {speakers.map(spk => (
                  <div className="speaker-editor-row" key={spk}>
                    <span className="speaker-editor-label">{spk}</span>
                    <input
                      type="text"
                      className="speaker-editor-input"
                      value={editMap[spk] || ''}
                      onChange={(e) => setEditMap({ ...editMap, [spk]: e.target.value })}
                    />
                  </div>
                ))}
              </div>
              <div className="speaker-editor-actions">
                <button
                  className="btn btn-save-speakers"
                  onClick={handleSaveSpeakers}
                  disabled={saving}
                >
                  {saving ? t.saving : t.save}
                </button>
                <button
                  className="btn btn-cancel-speakers"
                  onClick={() => setShowEdit(false)}
                >
                  {t.cancelJob}
                </button>
              </div>
            </>
          )}
        </div>
      )}

      {/* Metadata Panel */}
      {showMetadata && (
        <div className="job-card__metadata-panel">
          <h4>ℹ {t.metadata} / Details</h4>
          <div className="metadata-grid">
            <div className="metadata-row">
              <span className="metadata-label">{t.createdAt}:</span>
              <span className="metadata-value">{formatDate(job.created_at)}</span>
            </div>
            <div className="metadata-row">
              <span className="metadata-label">{t.duration}:</span>
              <span className="metadata-value">{formatDuration(job.duration_seconds)}</span>
            </div>
            <div className="metadata-row">
              <span className="metadata-label">{t.sttModel}:</span>
              <span className="metadata-value">{job.model_name || 'auto'} ({job.hardware_tier || 'cpu'})</span>
            </div>
            <div className="metadata-row">
              <span className="metadata-label">{t.language}:</span>
              <span className="metadata-value">{job.language === 'ja' ? '日本語' : 'English'}</span>
            </div>
            <div className="metadata-row">
              <span className="metadata-label">📁 {t.browseFiles}:</span>
              <span className="metadata-value file-path-text" title={job.file_path}>
                {job.file_path || 'Unknown'}
              </span>
            </div>
          </div>

          {window.electron && job.file_path && (
            <div className="metadata-actions">
              <button
                type="button"
                className="btn btn-metadata-action btn-open-media"
                onClick={handleOpenMedia}
              >
                ▶ {t.openMedia}
              </button>
              <button
                type="button"
                className="btn btn-metadata-action btn-open-location"
                onClick={handleOpenLocation}
              >
                📁 {t.fileLocation}
              </button>
            </div>
          )}
        </div>
      )}

      {/* Actions */}
      <div className="job-card__actions">
        {(isDone || job.status === 'failed' || job.status === 'cancelled') && (
          <button
            id={`meta-${job.id.substring(0,8)}`}
            className={`btn btn-export btn-metadata ${showMetadata ? 'btn-metadata--active' : ''}`}
            onClick={() => setShowMetadata(!showMetadata)}
            disabled={exporting}
          >ℹ {t.metadata}</button>
        )}
        {isDone && (
          <>
            <button
              id={`edit-speakers-${job.id.substring(0,8)}`}
              className={`btn btn-export btn-edit-speakers ${showEdit ? 'btn-edit-speakers--active' : ''}`}
              onClick={toggleEditSpeakers}
              disabled={exporting}
            >👥 {t.editSpeakers}</button>
            <button
              id={`export-txt-${job.id.substring(0,8)}`}
              className="btn btn-export btn-txt"
              onClick={() => handleExport('txt')}
              disabled={exporting}
            >📄 {t.exportTxt}</button>
            <button
              id={`export-doc-${job.id.substring(0,8)}`}
              className="btn btn-export btn-doc"
              onClick={() => handleExport('doc')}
              disabled={exporting}
              style={{ background: 'rgba(59, 130, 246, 0.1)', color: '#60a5fa', border: '1px solid rgba(59, 130, 246, 0.15)' }}
            >📝 {t.exportDoc || 'DOC'}</button>
            <button
              id={`export-pdf-${job.id.substring(0,8)}`}
              className="btn btn-export btn-pdf"
              onClick={() => handleExport('pdf')}
              disabled={exporting}
            >📕 {t.exportPdf || 'PDF'}</button>
          </>
        )}
        {isActive && (
          <>
            {job.status === 'paused' ? (
              <button
                id={`resume-${job.id.substring(0,8)}`}
                className="btn btn-resume"
                onClick={handleResume}
              >▶ {t.resumeJob}</button>
            ) : (
              <button
                id={`pause-${job.id.substring(0,8)}`}
                className="btn btn-pause"
                onClick={handlePause}
              >⏸ {t.pauseJob}</button>
            )}
            <button
              id={`cancel-${job.id.substring(0,8)}`}
              className="btn btn-cancel"
              onClick={handleCancel}
            >{t.cancelJob}</button>
          </>
        )}
        <button
          id={`delete-${job.id.substring(0,8)}`}
          className="btn btn-delete"
          onClick={handleDelete}
        >{t.deleteJob}</button>
      </div>
    </div>
  );
}
