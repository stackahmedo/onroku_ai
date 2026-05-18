import React, { useEffect, useState } from 'react';

const API = 'http://127.0.0.1:8000';

const TIER_ICONS  = { light: '🔴', medium: '🟡', heavy: '🟢' };
const TIER_LABELS = { light: 'Light', medium: 'Medium', heavy: 'Heavy' };

export default function HardwareInfo({ t }) {
  const [hw, setHw] = useState(null);

  useEffect(() => {
    const load = async () => {
      try {
        let data;
        if (window.electron) {
          data = await window.electron.api.getHardware();
        } else {
          const res = await fetch(`${API}/hardware`);
          data = await res.json();
        }
        setHw(data);
      } catch (err) {
        console.warn('Hardware info unavailable:', err);
      }
    };
    load();
  }, []);

  if (!hw) return (
    <div className="hw-panel hw-panel--loading">
      <span className="hw-dot" />
      <span>Detecting hardware...</span>
    </div>
  );

  const tier = hw.tier || 'light';
  const chunkMin = Math.round((hw.chunk_seconds || 600) / 60);

  return (
    <div className={`hw-panel hw-panel--${tier}`} id="hardware-info">
      <div className="hw-tier-badge">
        <span className="hw-tier-icon">{TIER_ICONS[tier]}</span>
        <span className="hw-tier-label">{t[`tier${tier.charAt(0).toUpperCase() + tier.slice(1)}`]}</span>
      </div>

      <div className="hw-details">
        <div className="hw-item">
          <span className="hw-key">{t.model}</span>
          <span className="hw-val">{hw.model_name}</span>
        </div>
        <div className="hw-item">
          <span className="hw-key">{t.device}</span>
          <span className="hw-val">{hw.device?.toUpperCase()}</span>
        </div>
        <div className="hw-item">
          <span className="hw-key">{t.ram}</span>
          <span className="hw-val">{hw.ram_gb} GB</span>
        </div>
        <div className="hw-item">
          <span className="hw-key">{t.chunkSize}</span>
          <span className="hw-val">{chunkMin} {t.minutes}</span>
        </div>
        {hw.gpu_available && hw.gpu_name && (
          <div className="hw-item">
            <span className="hw-key">{t.gpu}</span>
            <span className="hw-val hw-val--gpu">{hw.gpu_name} ({hw.gpu_vram_gb} GB)</span>
          </div>
        )}
      </div>
    </div>
  );
}
