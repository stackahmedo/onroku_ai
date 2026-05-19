import React, { useEffect, useState } from 'react';

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

const TIER_ICONS: Record<string, string> = { light: '🔴', medium: '🟡', heavy: '🟢' };

interface HardwareData {
  tier?: 'light' | 'medium' | 'heavy';
  chunk_seconds?: number;
  model_name?: string;
  cpu_name?: string;
  gpu_available?: boolean;
  gpu_name?: string;
  gpu_vram_gb?: number;
  ram_gb?: number;
  device?: string;
}

interface HardwareInfoProps {
  t: Record<string, string>;
}

export default function HardwareInfo({ t }: HardwareInfoProps) {
  const [hw, setHw] = useState<HardwareData | null>(null);

  useEffect(() => {
    let active = true;
    let timer: NodeJS.Timeout;

    const load = async () => {
      try {
        let data: HardwareData;
        if (window.electron) {
          data = await window.electron.api.getHardware();
        } else {
          const res = await fetch(`${API}/hardware`);
          data = await res.json();
        }
        if (active && data) {
          setHw(data);
        }
      } catch (err) {
        console.warn('Hardware info unavailable, retrying in 3s:', err);
        if (active) {
          timer = setTimeout(load, 3000);
        }
      }
    };
    load();

    return () => {
      active = false;
      clearTimeout(timer);
    };
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
          <span className="hw-key">{t.cpu || 'CPU'}</span>
          <span className="hw-val" title={hw.cpu_name}>{hw.cpu_name}</span>
        </div>
        <div className="hw-item">
          <span className="hw-key">{t.gpu || 'GPU'}</span>
          <span className={`hw-val ${hw.gpu_available ? 'hw-val--gpu' : ''}`}>
            {hw.gpu_name
              ? `${hw.gpu_name}${hw.gpu_vram_gb ? ` (${hw.gpu_vram_gb} GB)` : ''}`
              : 'None / Not Detected'}
          </span>
        </div>
        <div className="hw-item">
          <span className="hw-key">{t.ram}</span>
          <span className="hw-val">{hw.ram_gb} GB</span>
        </div>
        <div className="hw-item">
          <span className="hw-key">{t.device}</span>
          <span className="hw-val">{hw.device?.toUpperCase()}</span>
        </div>
        <div className="hw-item">
          <span className="hw-key">{t.chunkSize}</span>
          <span className="hw-val">{chunkMin} {t.minutes}</span>
        </div>
      </div>
    </div>
  );
}
