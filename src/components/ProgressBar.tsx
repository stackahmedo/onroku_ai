import React, { useEffect, useRef, useState } from 'react';

const getApiUrl = (): string => {
  const saved = localStorage.getItem('api_url');
  if (saved && saved.trim() !== '') {
    return saved.trim();
  }
  const hostname = window.location.hostname || '127.0.0.1';
  const protocol = window.location.protocol === 'file:' ? 'http:' : (window.location.protocol || 'http:');
  return `${protocol}//${hostname}:8000`;
};
const API = getApiUrl();

interface ProgressBarProps {
  jobId: string;
  status: string;
  initialPct?: number;
  initialLabel?: string;
  fileSize?: number;
  duration?: number | null;
}

export default function ProgressBar({
  jobId,
  status,
  initialPct = 0,
  initialLabel = '',
  fileSize: initialFileSize = 0,
  duration: initialDuration = null,
}: ProgressBarProps) {
  const [pct, setPct]           = useState<number>(initialPct);
  const [label, setLabel]       = useState<string>(initialLabel);
  const [elapsed, setElapsed]   = useState<number>(0);
  const [duration, setDuration] = useState<number | null>(initialDuration);
  const [fileSize, setFileSize] = useState<number>(initialFileSize);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!jobId) return;
    if (status === 'completed' || status === 'failed' || status === 'cancelled') {
      setPct(status === 'completed' ? 100 : initialPct);
      return;
    }

    // Open SSE stream
    const es = new EventSource(`${API}/progress/${jobId}`);
    esRef.current = es;

    es.addEventListener('progress', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        setPct(data.pct ?? 0);
        setLabel(data.label ?? '');
        if (data.elapsed_seconds !== undefined && data.elapsed_seconds !== null) {
          setElapsed(data.elapsed_seconds);
        }
        if (data.duration_seconds !== undefined && data.duration_seconds !== null) {
          setDuration(data.duration_seconds);
        }
        if (data.file_size_bytes !== undefined && data.file_size_bytes !== null) {
          setFileSize(data.file_size_bytes);
        }
      } catch {}
    });

    es.addEventListener('done', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        setPct(data.pct ?? 100);
        setLabel(data.label ?? '');
      } catch {}
      es.close();
    });

    es.onerror = () => es.close();

    return () => {
      es.close();
    };
  }, [jobId, status, initialPct]);

  // Local clock ticker for smooth second increment during transcription
  useEffect(() => {
    if (status !== 'transcribing' && status !== 'pending') return;
    if (pct >= 100) return;

    const interval = setInterval(() => {
      setElapsed((prev) => prev + 1);
    }, 1000);

    return () => clearInterval(interval);
  }, [status, pct]);

  const formatTime = (secs: number) => {
    if (isNaN(secs) || secs < 0) return '00:00';
    const m = Math.floor(secs / 60);
    const s = Math.floor(secs % 60);
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  };

  const barColor = pct === 100
    ? 'var(--clr-success)'
    : 'linear-gradient(90deg, var(--clr-accent), var(--clr-accent2))';

  // Calculate ETA dynamically based on elapsed time and progress
  // We only estimate when progress is >= 10% to avoid early stage/model loading noise
  const remaining = (pct >= 10 && pct < 100)
    ? Math.round((elapsed / pct) * (100 - pct))
    : null;

  const isActive = status === 'transcribing' || status === 'pending' || status === 'paused';

  return (
    <div className="progress-wrap">
      <div className="progress-track">
        <div
          className="progress-fill"
          style={{
            width: `${pct}%`,
            background: barColor,
            transition: 'width 0.5s ease',
          }}
        />
      </div>
      <div className="progress-meta">
        <div className="progress-left-side">
          <span className="progress-pct">{pct}%</span>
          {fileSize > 0 && (
            <span className="progress-size" style={{ fontSize: '11px', color: 'var(--clr-text-muted)', marginLeft: '8px' }}>
              📦 {(fileSize / 1024 / 1024).toFixed(1)} MB
            </span>
          )}
          {duration !== null && duration > 0 && (
            <span className="progress-dur" style={{ fontSize: '11px', color: 'var(--clr-text-muted)', marginLeft: '8px' }}>
              ⏱️ {formatTime(duration)}
            </span>
          )}
          {isActive && (
            <span className="progress-timer" style={{ marginLeft: '8px' }}>
              ({formatTime(elapsed)}
              {remaining !== null && (
                <span className="progress-eta">
                  {' · '}~{formatTime(remaining)}
                </span>
              )}
              )
            </span>
          )}
        </div>
        {label && (
          <span className="progress-label">
            {isActive && <span className="pulsing-dot" />}
            {label}
          </span>
        )}
      </div>
    </div>
  );
}
