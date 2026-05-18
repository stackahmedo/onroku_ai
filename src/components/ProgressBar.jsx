import React, { useEffect, useRef, useState } from 'react';

const API = 'http://127.0.0.1:8000';

export default function ProgressBar({ jobId, status, initialPct = 0, initialLabel = '' }) {
  const [pct, setPct]           = useState(initialPct);
  const [label, setLabel]       = useState(initialLabel);
  const [elapsed, setElapsed]   = useState(0);
  const [duration, setDuration] = useState(null);
  const esRef = useRef(null);

  useEffect(() => {
    if (!jobId) return;
    if (status === 'completed' || status === 'failed' || status === 'cancelled') {
      setPct(status === 'completed' ? 100 : initialPct);
      return;
    }

    // Open SSE stream
    const es = new EventSource(`${API}/progress/${jobId}`);
    esRef.current = es;

    es.addEventListener('progress', (e) => {
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
      } catch {}
    });

    es.addEventListener('done', (e) => {
      try {
        const data = JSON.parse(e.data);
        setPct(data.pct ?? 100);
        setLabel(data.label ?? '');
      } catch {}
      es.close();
    });

    es.onerror = () => es.close();

    return () => { es.close(); };
  }, [jobId, status]);

  // Local clock ticker for smooth second increment during transcription
  useEffect(() => {
    if (status !== 'transcribing' && status !== 'pending') return;
    if (pct >= 100) return;

    const interval = setInterval(() => {
      setElapsed((prev) => prev + 1);
    }, 1000);

    return () => clearInterval(interval);
  }, [status, pct]);

  const formatTime = (secs) => {
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
          {isActive && (
            <span className="progress-timer">
              ⏱️ {formatTime(elapsed)}
              {remaining !== null && (
                <span className="progress-eta">
                  {' · '}Remaining: ~{formatTime(remaining)}
                </span>
              )}
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
