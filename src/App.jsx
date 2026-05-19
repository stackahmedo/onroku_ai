import React, { useState, useEffect, useCallback, useRef } from 'react';
import './App.css';
import DropZone from './components/DropZone';
import HardwareInfo from './components/HardwareInfo';
import LanguageSwitcher from './components/LanguageSwitcher';
import JobCard from './components/JobCard';
import en from './i18n/en';
import ja from './i18n/ja';

const getApiUrl = () => {
  const saved = localStorage.getItem('api_url');
  if (saved && saved.trim() !== '') {
    return saved.trim();
  }
  const hostname = window.location.hostname || '127.0.0.1';
  const protocol = window.location.protocol === 'file:' ? 'http:' : (window.location.protocol || 'http:');
  return `${protocol}//${hostname}:8000`;
};
const API = getApiUrl();
const STRINGS = { en, ja };

export default function App() {
  const [uiLang, setUiLang]           = useState('ja');
  const [transcribeLang, setTranscribeLang] = useState('auto');
  const [transcribeModel, setTranscribeModel] = useState('auto');
  const [speakerCount, setSpeakerCount] = useState('auto');
  const [chunkSeconds, setChunkSeconds] = useState('auto');
  const [diarizationMode, setDiarizationMode] = useState('accurate');
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [jobs, setJobs]               = useState([]);
  const [loading, setLoading]         = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0); // 0-100 upload %
  const [uploadPhase, setUploadPhase] = useState(''); // 'uploading' | 'processing' | ''
  const [uploadNotice, setUploadNotice] = useState(''); // Live text for current sequential job
  const [toast, setToast]             = useState(null);
  const [backendOk, setBackendOk]     = useState(null);

  const [performanceMode, setPerformanceMode] = useState('auto');
  const speakerRange = 'normal';
  const [hwProfile, setHwProfile] = useState(null);

  // New features state
  const [activeTab, setActiveTab] = useState('completed');
  const [settingsExportDir, setSettingsExportDir] = useState('');
  const [pdfMaxChars, setPdfMaxChars] = useState(1000);
  const [pdfTemplate, setPdfTemplate] = useState('corporate');
  const [settingsApiUrl, setSettingsApiUrl] = useState(() => localStorage.getItem('api_url') || '');
  
  // Converter States
  const [txtInputText, setTxtInputText] = useState('');
  const [txtPdfTemplate, setTxtPdfTemplate] = useState('compact_terminal');
  const [txtMaxChars, setTxtMaxChars] = useState(1000);
  const [txtFilename, setTxtFilename] = useState('');
  const [txtDuration, setTxtDuration] = useState('');
  const [txtFontSize, setTxtFontSize] = useState('');
  const [txtRowPadding, setTxtRowPadding] = useState('');
  const [txtOutputFormat, setTxtOutputFormat] = useState('pdf');
  const [txtHeader, setTxtHeader] = useState('');
  const [txtFooter, setTxtFooter] = useState('');
  const [txtWatermark, setTxtWatermark] = useState('');
  const [txtVerticalJapanese, setTxtVerticalJapanese] = useState(false);
  const [txtPageLayout, setTxtPageLayout] = useState('table');
  const [txtAutoPageNumbers, setTxtAutoPageNumbers] = useState(true);
  const [txtSmartSpeakerStyling, setTxtSmartSpeakerStyling] = useState(true);
  const [txtSpeakerFilter, setTxtSpeakerFilter] = useState('');
  const [txtSpeakerRenames, setTxtSpeakerRenames] = useState('');
  const [txtSpeakerColors, setTxtSpeakerColors] = useState('');
  const [txtCustomFontName, setTxtCustomFontName] = useState('');
  const [txtCustomFontFile, setTxtCustomFontFile] = useState(null);
  const [txtSilenceDetection, setTxtSilenceDetection] = useState(false);
  const [txtSilenceThreshold, setTxtSilenceThreshold] = useState(4);
  const [isConvertingTxt, setIsConvertingTxt] = useState(false);
  const [pdfPreviewUrl, setPdfPreviewUrl] = useState(null);

  // Revoke object URL on unmount or URL replacement
  useEffect(() => {
    return () => {
      if (pdfPreviewUrl) {
        window.URL.revokeObjectURL(pdfPreviewUrl);
      }
    };
  }, [pdfPreviewUrl]);
  useEffect(() => {
    if (txtOutputFormat !== 'pdf' && pdfPreviewUrl) {
      window.URL.revokeObjectURL(pdfPreviewUrl);
      setPdfPreviewUrl(null);
    }
  }, [txtOutputFormat, pdfPreviewUrl]);
  const [isSearchingAPI, setIsSearchingAPI] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [isClearingCache, setIsClearingCache] = useState(false);
  const [logs, setLogs] = useState([]);
  const [autoScrollLogs, setAutoScrollLogs] = useState(true);
  const [theme, setTheme] = useState(() => localStorage.getItem('theme') || 'dark');
  const [exportedFiles, setExportedFiles] = useState([]);
  const [exportsDir, setExportsDir] = useState('');
  const [isLoadingExports, setIsLoadingExports] = useState(false);
  const terminalBodyRef = useRef(null);

  // Sync theme changes to localStorage
  useEffect(() => {
    localStorage.setItem('theme', theme);
  }, [theme]);

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
          setPdfMaxChars(data.pdf_max_chars_per_page || 1000);
          setPdfTemplate(data.pdf_template || 'corporate');
        }
      } catch (err) {
        console.error('fetchSettings error:', err);
      }
    };
    fetchSettings();
  }, []);

  // ── Fetch Hardware Profile at Startup ────────────────────────
  useEffect(() => {
    const fetchHw = async () => {
      try {
        let data;
        if (window.electron) {
          data = await window.electron.api.getHardware();
        } else {
          const res = await fetch(`${API}/hardware`);
          data = await res.json();
        }
        setHwProfile(data);
      } catch (err) {
        console.warn('Failed to load hardware profile:', err);
      }
    };
    fetchHw();
  }, []);

  const getAutoRecommendationText = () => {
    if (!hwProfile) return uiLang === 'ja' ? 'ハードウェア検出中...' : 'Detecting hardware...';
    const gpuType = hwProfile.gpu_type || 'none';
    const gpuVram = hwProfile.gpu_vram_gb || 0;
    const ram = hwProfile.ram_gb || 8;
    
    let asr = 'faster-whisper CPU (int8)';
    let spk = 'pyannote CPU';
    let model = ram >= 16 ? 'base' : 'small';
    
    if (gpuType === 'nvidia' && gpuVram >= 4) {
      asr = 'faster-whisper CUDA';
      spk = 'pyannote CUDA';
      model = gpuVram < 8 ? 'medium' : 'large-v3';
    } else if (gpuType === 'apple_silicon') {
      asr = 'whisper.cpp Metal';
      spk = 'pyannote CPU';
      model = 'small';
    } else if (gpuType === 'amd_intel') {
      asr = 'whisper.cpp Vulkan';
      spk = 'pyannote CPU';
      model = ram >= 16 ? 'medium-q5_0' : 'small-q5_0';
    }
    
    if (uiLang === 'ja') {
      return `自動推奨: ASR: ${asr} | モデル: ${model} | 話者検出: ${spk}`;
    } else {
      return `Recommended: ASR: ${asr} | Model: ${model} | Speaker: ${spk}`;
    }
  };

  // ── Save Settings ──────────────────────────────────────────
  const handleSaveSettings = async () => {
    try {
      const res = await fetch(`${API}/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          transcript_export_dir: settingsExportDir,
          pdf_max_chars_per_page: pdfMaxChars,
          pdf_template: pdfTemplate,
        }),
      });
      if (res.ok) {
        const prevApiUrl = localStorage.getItem('api_url') || '';
        const newApiUrl = settingsApiUrl.trim();
        localStorage.setItem('api_url', newApiUrl);

        if (newApiUrl !== prevApiUrl) {
          showToast(uiLang === 'ja' ? '接続先API URLを変更しました。再読み込み中...' : 'Connection API URL updated. Reconnecting...', 'success');
          setTimeout(() => {
            window.location.reload();
          }, 1500);
        } else {
          showToast(t.settingsSaveSuccess, 'success');
        }
      } else {
        const errData = await res.json();
        showToast(`${t.settingsSaveFailed}: ${errData.detail || 'Error'}`, 'error');
      }
    } catch (err) {
      const prevApiUrl = localStorage.getItem('api_url') || '';
      const newApiUrl = settingsApiUrl.trim();
      localStorage.setItem('api_url', newApiUrl);

      if (newApiUrl !== prevApiUrl) {
        showToast(uiLang === 'ja' ? '接続先API URLを変更しました。再読み込み中...' : 'Connection API URL updated. Reconnecting...', 'success');
        setTimeout(() => {
          window.location.reload();
        }, 1500);
      } else {
        showToast(`${t.settingsSaveFailed}: ${err.message}`, 'error');
      }
    }
  };

  // ── Auto Searching & Connection Testing ──────────────────────────
  const handleAutoSearchAPI = async () => {
    setIsSearchingAPI(true);
    setTestResult(null);
    showToast(uiLang === 'ja' ? 'バックエンドサーバーを自動検索中...' : 'Searching for backend servers...', 'info');

    const currentHost = window.location.hostname || 'localhost';
    const protocol = window.location.protocol === 'file:' ? 'http:' : (window.location.protocol || 'http:');
    
    const candidates = [
      `${protocol}//${currentHost}:8000`,
      `http://localhost:8000`,
      `http://127.0.0.1:8000`
    ];
    
    const uniqueCandidates = [...new Set(candidates)];
    
    let found = null;
    for (const url of uniqueCandidates) {
      try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 1200);
        
        const res = await fetch(`${url}/health`, { signal: controller.signal });
        clearTimeout(timeoutId);
        if (res.ok) {
          found = url;
          break;
        }
      } catch (err) {}
    }
    
    setIsSearchingAPI(false);
    if (found) {
      setSettingsApiUrl(found);
      setTestResult({ success: true, message: uiLang === 'ja' ? `接続可能なサーバーを発見しました: ${found}` : `Active server found: ${found}` });
      showToast(uiLang === 'ja' ? '接続可能なサーバーが見つかりました！' : 'Active backend server discovered!', 'success');
    } else {
      setTestResult({ success: false, message: uiLang === 'ja' ? '接続可能なサーバーが見つかりませんでした。起動しているか確認してください。' : 'No active backend server found. Please ensure your server is running.' });
      showToast(uiLang === 'ja' ? 'サーバーが見つかりませんでした。' : 'No server discovered.', 'error');
    }
  };

  const handleTestConnection = async () => {
    const url = settingsApiUrl.trim();
    if (!url) {
      setTestResult({ success: false, message: uiLang === 'ja' ? 'URLを入力してください。' : 'Please enter a URL first.' });
      return;
    }
    
    setTestResult(null);
    showToast(uiLang === 'ja' ? '接続確認中...' : 'Testing connection...', 'info');
    
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 2000);
      
      const res = await fetch(`${url}/health`, { signal: controller.signal });
      clearTimeout(timeoutId);
      
      if (res.ok) {
        setTestResult({ success: true, message: uiLang === 'ja' ? `接続成功! サーバーは正常に稼働しています (${url})` : `Connection success! Server is online (${url})` });
        showToast(uiLang === 'ja' ? '接続テスト成功！正常に通信できます。' : 'Connection test successful!', 'success');
      } else {
        setTestResult({ success: false, message: uiLang === 'ja' ? `ステータスエラー: ${res.status}` : `Server returned status code: ${res.status}` });
        showToast(uiLang === 'ja' ? '接続失敗: ステータス異常' : 'Connection failed: abnormal status', 'error');
      }
    } catch (err) {
      setTestResult({ success: false, message: uiLang === 'ja' ? '接続できませんでした。URLまたはサーバー状態を確認してください。' : 'Unable to connect. Please verify the URL or server status.' });
      showToast(uiLang === 'ja' ? '接続失敗' : 'Connection failed', 'error');
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

  // ── Clear Cache ─────────────────────────────────────────────
  const handleClearCache = async () => {
    setIsClearingCache(true);
    try {
      const res = await fetch(`${API}/clear-cache`, { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        showToast(`${t.settingsClearCacheSuccess}${data.mb_cleared} MB!`, 'success');
      } else {
        showToast(uiLang === 'ja' ? 'キャッシュのクリアに失敗しました' : 'Failed to clear cache', 'error');
      }
    } catch (err) {
      showToast(uiLang === 'ja' ? 'エラーが発生しました' : 'Error connecting to server', 'error');
    } finally {
      setIsClearingCache(false);
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

  // ── Load Exported Files ──────────────────────────────────
  const loadExportedFiles = useCallback(async () => {
    setIsLoadingExports(true);
    try {
      const res = await fetch(`${API}/exports`);
      if (res.ok) {
        const data = await res.json();
        setExportedFiles(data.files || []);
        setExportsDir(data.export_dir || '');
      }
    } catch (err) {
      console.error('loadExportedFiles error:', err);
    } finally {
      setIsLoadingExports(false);
    }
  }, []);

  useEffect(() => {
    if (activeTab === 'exports') {
      loadExportedFiles();
    }
  }, [activeTab, loadExportedFiles]);

  const handleDeleteExportFile = async (fileName) => {
    let proceed = false;
    if (window.electron && window.electron.win && window.electron.win.confirm) {
      proceed = await window.electron.win.confirm({
        title: uiLang === 'ja' ? 'ファイルを削除' : 'Delete File',
        message: t.exportsConfirmDelete || (uiLang === 'ja' ? 'このファイルを削除してもよろしいですか？' : 'Are you sure you want to delete this file?'),
        buttons: uiLang === 'ja' ? ['削除', 'キャンセル'] : ['Delete', 'Cancel']
      });
    } else {
      proceed = window.confirm(t.exportsConfirmDelete || 'Are you sure?');
    }
    if (!proceed) return;
    try {
      const res = await fetch(`${API}/exports/${encodeURIComponent(fileName)}`, {
        method: 'DELETE',
      });
      if (res.ok) {
        showToast(uiLang === 'ja' ? 'ファイルを削除しました！' : 'File deleted successfully!', 'success');
        loadExportedFiles();
      } else {
        showToast(uiLang === 'ja' ? 'ファイルの削除に失敗しました' : 'Failed to delete file', 'error');
      }
    } catch (err) {
      showToast(`Error: ${err.message}`, 'error');
    }
  };

  const handleOpenExportsFolder = async () => {
    if (window.electron && exportsDir) {
      await window.electron.shell.open(exportsDir);
    } else {
      alert('フォルダを開けません / Cannot open folder (Only supported in Electron app)');
    }
  };

  const handleOpenExportFile = async (file) => {
    if (window.electron && file.absolute_path) {
      await window.electron.shell.open(file.absolute_path);
    } else {
      const a = document.createElement('a');
      a.href = `${API}/exports/${encodeURIComponent(file.name)}/download`;
      a.download = file.name;
      a.click();
    }
  };

  const handleShowExportInFolder = async (file) => {
    if (window.electron && file.absolute_path) {
      await window.electron.shell.showItem(file.absolute_path);
    }
  };

  // ── Toast helper ──────────────────────────────────────────
  const showToast = (msg, type = 'info') => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 4000);
  };

  // ── Converter Handlers ─────────────────────────────────────
  const handleTxtFileChange = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (event) => {
      setTxtInputText(event.target.result);
      showToast(uiLang === 'ja' ? 'ファイルを読み込みました！' : 'TXT file loaded successfully!', 'success');
    };
    reader.readAsText(file);
  };

  const loadExampleTxt = () => {
    setTxtInputText(
      "00:00:12 | 話者6 | このまま1-9-3まるまつばらが 工事です\n" +
      "00:00:15 | 話者9 | おり青いです\n" +
      "00:00:16 | 話者6 | さてトランプ大統領は 米中階段を終えて\n" +
      "00:00:19 | 話者6 | ペキンを後にしました\n" +
      "00:00:21 | 話者6 | 今日いくつかの防疫協定を 結んだと語りました\n" +
      "00:00:25 | 話者6 | 米中どちらが 少者と言えるんでしょうか\n" +
      "00:00:28 | 話者6 | また少年となっていた タイア問題といらん問題は\n" +
      "00:00:31 | 話者6 | 階段によって今後 どんなふうに変わって 可能性がある\n" +
      "00:00:36 | 話者6 | さらに 高知総理が 帰国のとについたトランプしと\n" +
      "00:00:39 | 話者9 | 電話階段を こんなを見てほしいです\n" +
      "00:00:41 | 話者6 | 今日は米中階段の 本質を読み取りたいと\n" +
      "00:00:44 | 話者6 | 読むように思っております\n" +
      "00:00:46 | 話者9 | 今夜のゲストを紹介します"
    );
    showToast(uiLang === 'ja' ? 'サンプルデータを読み込みました！' : 'Sample grid data loaded!', 'info');
  };

  const renderPdfCustomizerForm = () => {
    const pdfMakerFieldStyle = { width: '100%', padding: '6px 8px', fontSize: '12px', background: 'rgba(0,0,0,0.3)', border: '1px solid var(--clr-border)', color: '#fff', borderRadius: 'var(--radius-sm)' };
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
        <div>
          <label className="settings-label" style={{ fontSize: '12px', display: 'block', marginBottom: '6px' }}>
            Output format
          </label>
          <select value={txtOutputFormat} onChange={(e) => setTxtOutputFormat(e.target.value)} style={pdfMakerFieldStyle}>
            <option value="pdf">PDF</option>
            <option value="doc">DOC</option>
            <option value="xlsx">XLSX</option>
            <option value="csv">CSV</option>
            <option value="html">HTML</option>
            <option value="json">JSON</option>
            <option value="txt">TXT</option>
          </select>
        </div>
        
        {/* Template Select */}
        <div>
          <label className="settings-label" style={{ fontSize: '12px', display: 'block', marginBottom: '6px' }}>
            🎨 {uiLang === 'ja' ? 'PDFデザインテンプレート' : 'PDF Design Template'}
          </label>
          <select
            value={txtPdfTemplate}
            onChange={(e) => setTxtPdfTemplate(e.target.value)}
            className="settings-select"
            style={{ width: '100%', padding: '6px 8px', fontSize: '12px', background: 'rgba(0,0,0,0.3)', border: '1px solid var(--clr-border)', color: '#fff', borderRadius: 'var(--radius-sm)' }}
          >
            <option value="corporate">💼 Corporate Slate</option>
            <option value="eco">🌱 Eco-Friendly Minimalist</option>
            <option value="cyberpunk">⚡ Cyberpunk Obsidian</option>
            <option value="emerald">💚 Royal Emerald</option>
            <option value="amber">🍊 Warm Amber Editorial</option>
            <option value="serif_court">📜 Formal Court Serif</option>
            <option value="cherry_blossom">🌸 Cherry Blossom Sakura</option>
            <option value="crimson">🔴 Executive Crimson</option>
            <option value="indigo">💜 Modern Indigo</option>
            <option value="accessibility">♿ High-Contrast Accessible</option>
            <option value="compact_terminal">💻 Compact Terminal Grid</option>
          </select>
        </div>

        {/* Custom Filename */}
        <div>
          <label className="settings-label" style={{ fontSize: '12px', display: 'block', marginBottom: '6px' }}>
            📝 {uiLang === 'ja' ? 'カスタムファイル名 (フッター表示)' : 'Custom File Name (Footer)'}
          </label>
          <input
            type="text"
            value={txtFilename}
            onChange={(e) => setTxtFilename(e.target.value)}
            placeholder={uiLang === 'ja' ? '例: 会議議事録' : 'e.g. Meeting Minutes'}
            style={{ width: '100%', padding: '6px 8px', fontSize: '12px', background: 'rgba(0,0,0,0.3)', border: '1px solid var(--clr-border)', color: '#fff', borderRadius: 'var(--radius-sm)' }}
          />
        </div>

        {/* Custom Duration */}
        <div>
          <label className="settings-label" style={{ fontSize: '12px', display: 'block', marginBottom: '6px' }}>
            ⏱️ {uiLang === 'ja' ? '録音時間 / 表示用 (例: 45:10)' : 'Recording Duration (e.g. 45:10)'}
          </label>
          <input
            type="text"
            value={txtDuration}
            onChange={(e) => setTxtDuration(e.target.value)}
            placeholder="00:00"
            style={{ width: '100%', padding: '6px 8px', fontSize: '12px', background: 'rgba(0,0,0,0.3)', border: '1px solid var(--clr-border)', color: '#fff', borderRadius: 'var(--radius-sm)' }}
          />
        </div>

        {/* Custom Font Size & Row Padding */}
        <div style={{ display: 'flex', gap: '10px' }}>
          <div style={{ flex: 1 }}>
            <label className="settings-label" style={{ fontSize: '12px', display: 'block', marginBottom: '6px' }}>
              🔤 {uiLang === 'ja' ? '文字サイズ (pt)' : 'Font Size (pt)'}
            </label>
            <input
              type="number"
              min="6"
              max="16"
              step="0.5"
              value={txtFontSize}
              onChange={(e) => setTxtFontSize(e.target.value)}
              placeholder="8"
              style={{ width: '100%', padding: '6px 8px', fontSize: '12px', background: 'rgba(0,0,0,0.3)', border: '1px solid var(--clr-border)', color: '#fff', borderRadius: 'var(--radius-sm)', textAlign: 'center' }}
            />
          </div>

          <div style={{ flex: 1 }}>
            <label className="settings-label" style={{ fontSize: '12px', display: 'block', marginBottom: '6px' }}>
              ↕️ {uiLang === 'ja' ? '行間余白 (pt)' : 'Row Padding (pt)'}
            </label>
            <input
              type="number"
              min="0.5"
              max="12"
              step="0.5"
              value={txtRowPadding}
              onChange={(e) => setTxtRowPadding(e.target.value)}
              placeholder="3"
              style={{ width: '100%', padding: '6px 8px', fontSize: '12px', background: 'rgba(0,0,0,0.3)', border: '1px solid var(--clr-border)', color: '#fff', borderRadius: 'var(--radius-sm)', textAlign: 'center' }}
            />
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
          <div>
            <label className="settings-label" style={{ fontSize: '12px', display: 'block', marginBottom: '6px' }}>Header</label>
            <input type="text" value={txtHeader} onChange={(e) => setTxtHeader(e.target.value)} placeholder="Project / meeting title" style={pdfMakerFieldStyle} />
          </div>
          <div>
            <label className="settings-label" style={{ fontSize: '12px', display: 'block', marginBottom: '6px' }}>Footer</label>
            <input type="text" value={txtFooter} onChange={(e) => setTxtFooter(e.target.value)} placeholder="Confidential / notes" style={pdfMakerFieldStyle} />
          </div>
          <div>
            <label className="settings-label" style={{ fontSize: '12px', display: 'block', marginBottom: '6px' }}>Watermark</label>
            <input type="text" value={txtWatermark} onChange={(e) => setTxtWatermark(e.target.value)} placeholder="DRAFT" style={pdfMakerFieldStyle} />
          </div>
          <div>
            <label className="settings-label" style={{ fontSize: '12px', display: 'block', marginBottom: '6px' }}>Page Layout</label>
            <select value={txtPageLayout} onChange={(e) => setTxtPageLayout(e.target.value)} style={pdfMakerFieldStyle}>
              <option value="table">Standard table</option>
              <option value="wide">Wide transcript</option>
              <option value="compact">Compact pages</option>
            </select>
          </div>
        </div>

        <div>
          <label className="settings-label" style={{ fontSize: '12px', display: 'block', marginBottom: '6px' }}>Speaker rename, color, and filter</label>
          <textarea value={txtSpeakerRenames} onChange={(e) => setTxtSpeakerRenames(e.target.value)} placeholder={'Speaker 1=Host\nSpeaker 2=Guest'} style={{ ...pdfMakerFieldStyle, height: '52px', resize: 'vertical', fontFamily: 'Consolas, Monaco, monospace' }} />
          <textarea value={txtSpeakerColors} onChange={(e) => setTxtSpeakerColors(e.target.value)} placeholder={'Host=#2563eb\nGuest=#16a34a'} style={{ ...pdfMakerFieldStyle, height: '52px', resize: 'vertical', fontFamily: 'Consolas, Monaco, monospace', marginTop: '8px' }} />
          <input type="text" value={txtSpeakerFilter} onChange={(e) => setTxtSpeakerFilter(e.target.value)} placeholder="Speaker filter: Host, Guest" style={{ ...pdfMakerFieldStyle, marginTop: '8px' }} />
        </div>

        <div>
          <label className="settings-label" style={{ fontSize: '12px', display: 'block', marginBottom: '6px' }}>Custom Font Upload</label>
          <input
            type="file"
            accept=".ttf,.ttc,.otf"
            onChange={(e) => {
              const file = e.target.files?.[0] || null;
              setTxtCustomFontFile(file);
              setTxtCustomFontName(file?.name || '');
            }}
            style={pdfMakerFieldStyle}
          />
          {txtCustomFontName && <span style={{ fontSize: '11px', color: 'var(--clr-text-muted)' }}>Selected: {txtCustomFontName}</span>}
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', fontSize: '12px', color: 'var(--clr-text)' }}>
          <label><input type="checkbox" checked={txtSmartSpeakerStyling} onChange={(e) => setTxtSmartSpeakerStyling(e.target.checked)} /> Smart speaker styling</label>
          <label><input type="checkbox" checked={txtAutoPageNumbers} onChange={(e) => setTxtAutoPageNumbers(e.target.checked)} /> Auto page numbering</label>
          <label><input type="checkbox" checked={txtVerticalJapanese} onChange={(e) => setTxtVerticalJapanese(e.target.checked)} /> Vertical Japanese PDF</label>
          <label><input type="checkbox" checked={txtSilenceDetection} onChange={(e) => setTxtSilenceDetection(e.target.checked)} /> Silence detection</label>
        </div>
        {txtSilenceDetection && (
          <div>
            <label className="settings-label" style={{ fontSize: '12px', display: 'block', marginBottom: '6px' }}>Silence Threshold Seconds</label>
            <input type="number" min="1" max="60" step="0.5" value={txtSilenceThreshold} onChange={(e) => setTxtSilenceThreshold(e.target.value)} style={pdfMakerFieldStyle} />
          </div>
        )}
      </div>
    );
  };

  const parsePdfMakerMap = (value) => {
    return value
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean)
      .reduce((acc, line) => {
        const [key, ...rest] = line.split('=');
        if (key && rest.length) acc[key.trim()] = rest.join('=').trim();
        return acc;
      }, {});
  };

  const readFileAsBase64 = (file) => new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = typeof reader.result === 'string' ? reader.result : '';
      const marker = 'base64,';
      const index = result.indexOf(marker);
      resolve(index >= 0 ? result.slice(index + marker.length) : result);
    };
    reader.onerror = () => reject(reader.error || new Error('Failed to read file'));
    reader.readAsDataURL(file);
  });

  const getDownloadFilename = (res, fallbackExtension) => {
    const disposition = res.headers.get('content-disposition') || '';
    const utf8Match = disposition.match(/filename\*=UTF-8''([^;]+)/i);
    if (utf8Match) {
      return decodeURIComponent(utf8Match[1]);
    }
    const plainMatch = disposition.match(/filename="?([^";]+)"?/i);
    if (plainMatch) {
      return plainMatch[1];
    }
    return `converted_transcript.${fallbackExtension}`;
  };

  const handleConvertTxtToPdf = async (shouldDownload = false) => {
    const trimmed = txtInputText.trim();
    if (!trimmed) {
      showToast(uiLang === 'ja' ? 'テキストを入力するか、ファイルをアップロードしてください。' : 'Please paste text or load a file first.', 'error');
      return;
    }
    
    setIsConvertingTxt(true);
    showToast(uiLang === 'ja' ? 'PDFを生成中...' : 'Generating PDF...', 'info');
    
    try {
      const customFontBase64 = txtCustomFontFile ? await readFileAsBase64(txtCustomFontFile) : undefined;
      const res = await fetch(`${API}/convert-txt-to-pdf`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: trimmed,
          output_format: txtOutputFormat,
          pdf_template: txtPdfTemplate,
          max_chars: txtMaxChars,
          custom_filename: txtFilename || undefined,
          custom_duration: txtDuration || undefined,
          font_size: txtFontSize ? parseFloat(txtFontSize) : undefined,
          row_padding: txtRowPadding ? parseFloat(txtRowPadding) : undefined,
          custom_header: txtHeader || undefined,
          custom_footer: txtFooter || undefined,
          watermark: txtWatermark || undefined,
          vertical_japanese: txtVerticalJapanese,
          page_layout: txtPageLayout,
          auto_page_numbers: txtAutoPageNumbers,
          smart_speaker_styling: txtSmartSpeakerStyling,
          speaker_filter: txtSpeakerFilter.split(',').map((item) => item.trim()).filter(Boolean),
          speaker_renames: parsePdfMakerMap(txtSpeakerRenames),
          speaker_colors: parsePdfMakerMap(txtSpeakerColors),
          silence_detection: txtSilenceDetection,
          silence_threshold: parseFloat(txtSilenceThreshold) || 4,
          custom_font_name: txtCustomFontFile ? txtCustomFontFile.name : undefined,
          custom_font_base64: customFontBase64,
        }),
      });
      
      if (res.ok) {
        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const isPdfOutput = txtOutputFormat === 'pdf';
        const downloadName = getDownloadFilename(res, txtOutputFormat);
        
        // Revoke old preview URL if exists
        if (pdfPreviewUrl) {
          window.URL.revokeObjectURL(pdfPreviewUrl);
        }
        
        if (isPdfOutput) {
          setPdfPreviewUrl(url);
        } else {
          setPdfPreviewUrl(null);
        }
        showToast(uiLang === 'ja' ? 'PDFプレビューを更新しました！' : 'PDF preview updated successfully!', 'success');
        
        if (shouldDownload) {
          const a = document.createElement('a');
          a.href = url;
          a.download = downloadName;
          document.body.appendChild(a);
          a.click();
          a.remove();
        }
        if (!isPdfOutput) {
          if (!shouldDownload) {
            const a = document.createElement('a');
            a.href = url;
            a.download = downloadName;
            document.body.appendChild(a);
            a.click();
            a.remove();
          }
          setTimeout(() => window.URL.revokeObjectURL(url), 0);
          showToast(uiLang === 'ja' ? 'ファイルを書き出しました。' : 'File exported successfully.', 'success');
        }
      } else {
        const err = await res.json();
        showToast(`${t.txtConvError}: ${err.detail || 'Error'}`, 'error');
      }
    } catch (err) {
      showToast(`${t.txtConvError}: ${err.message}`, 'error');
    } finally {
      setIsConvertingTxt(false);
    }
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
        if (window.electron && (file._isPath || file.path)) {
          // Electron path (both browsed and dropped files support IPC upload)
          setUploadProgress(50);
          await window.electron.api.upload(file.path, transcribeLang, transcribeModel, speakerCount, chunkSeconds, diarizationMode, performanceMode, speakerRange);
          setUploadProgress(100);
        } else {
          // Browser / React dev fallback
          const formData = new FormData();
          formData.append('file', file);

          await new Promise((resolve, reject) => {
            const xhr = new XMLHttpRequest();
            const speakerParam = speakerCount && speakerCount !== 'auto' ? `&speaker_count=${speakerCount}` : '';
            const chunkParam = chunkSeconds && chunkSeconds !== 'auto' ? `&chunk_seconds=${chunkSeconds}` : '';
            xhr.open('POST', `${API}/upload?language=${transcribeLang}&model=${transcribeModel}${speakerParam}${chunkParam}&diarization_mode=${diarizationMode}&performance_mode=${performanceMode}&speaker_range=${speakerRange}`);

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
        setActiveTab('processing');
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
    <div className="app" data-theme={theme}>
      {/* ── Header ── */}
      <header className="app-header">
        <div className="app-header__left">
          <img
            src="./logo.png"
            alt="Onroku AI Logo"
            className="app-logo-img"
            style={{
              height: '42px',
              width: 'auto',
              filter: 'drop-shadow(0 0 10px rgba(96, 165, 250, 0.35))',
              borderRadius: '6px',
              marginRight: '6px'
            }}
          />
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
          
          {/* Theme switcher toggle */}
          <button
            type="button"
            className="theme-toggle"
            onClick={() => setTheme(t => t === 'dark' ? 'light' : 'dark')}
            title={theme === 'dark' ? 'Switch to Light Mode' : 'Switch to Dark Mode'}
            id="theme-toggle-btn"
          >
            <span className="theme-toggle__icon">{theme === 'dark' ? '☀️' : '🌙'}</span>
          </button>

          {/* Electron window controls & utilities */}
          {window.electron && (
            <div className="electron-controls" style={{ display: 'flex', alignItems: 'center', gap: '8px', marginLeft: '12px' }}>
              <button
                type="button"
                className="header-util-btn"
                onClick={() => window.electron.win.reload()}
                title={uiLang === 'ja' ? '画面を更新 / Refresh' : 'Refresh Page'}
                id="win-reload-btn"
              >
                🔄
              </button>
              
              <div className="win-control-divider" style={{ width: '1px', height: '18px', background: 'var(--clr-border)', margin: '0 4px' }} />

              <button
                type="button"
                className="win-ctrl-btn win-ctrl-btn--min"
                onClick={() => window.electron.win.minimize()}
                title={uiLang === 'ja' ? '最小化 / Minimize' : 'Minimize'}
              >
                —
              </button>
              <button
                type="button"
                className="win-ctrl-btn win-ctrl-btn--max"
                onClick={() => window.electron.win.maximize()}
                title={uiLang === 'ja' ? '最大化・元に戻す / Maximize' : 'Maximize / Restore'}
              >
                ⬜
              </button>
              <button
                type="button"
                className="win-ctrl-btn win-ctrl-btn--close"
                onClick={() => window.electron.win.close()}
                title={uiLang === 'ja' ? '閉じる / Close' : 'Close'}
              >
                ✕
              </button>
            </div>
          )}
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
                <option value="auto">Auto (Whisper)</option>
                <option value="large-v3">Whisper large-v3</option>
                <option value="medium">Whisper medium</option>
                <option value="small">Whisper small</option>
                <option value="base">Whisper base</option>
                <option value="tiny">Whisper tiny</option>
                <option value="qwen3-asr-0.6b">{t.modelQwen3Asr06b || "Qwen3-ASR 0.6B"}</option>
                <option value="qwen3-asr-1.7b">{t.modelQwen3Asr17b || "Qwen3-ASR 1.7B"}</option>
              </select>
            </div>

            {/* Performance Mode Selector */}
            <div className="lang-select-row">
              <label htmlFor="performance-mode-select" className="lang-select-label">
                ⚡ {t.performanceModeTitle || 'Performance Mode'}
              </label>
              <select
                id="performance-mode-select"
                className="lang-select"
                value={performanceMode}
                onChange={e => setPerformanceMode(e.target.value)}
              >
                <option value="auto">⚡ {t.performanceModeAuto || 'Recommended (Auto)'}</option>
                <option value="eco">🍃 {t.performanceModeEco || 'Eco (Low VRAM/Threads)'}</option>
                <option value="balanced">⚖️ {t.performanceModeBalanced || 'Balanced (Standard)'}</option>
                <option value="accurate">🎯 {t.performanceModeAccurate || 'Accurate (Max Precision)'}</option>
              </select>
            </div>

            {/* Unified 2-Option Speakers Control (Enable / Disable) */}
            <div className="lang-select-row">
              <label htmlFor="diarization-mode-select" className="lang-select-label">
                👥 {uiLang === 'ja' ? '話者検出 / Speakers' : 'Speakers'}
              </label>
              <select
                id="diarization-mode-select"
                className="lang-select"
                value={diarizationMode}
                onChange={e => {
                  const val = e.target.value;
                  setDiarizationMode(val);
                  setSpeakerCount(val === 'accurate' ? 'auto' : '1');
                }}
              >
                <option value="accurate">{t.diarizationModeEnabled || '有効 (話者検出あり) / Enabled'}</option>
                <option value="off">{t.diarizationModeDisabled || '無効 (話者検出なし) / Disabled'}</option>
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

            {/* Dynamic Auto Recommendation Badge */}
            <div
              className="recommendation-badge"
              style={{
                margin: '12px 0 6px 0',
                padding: '10px 14px',
                borderRadius: '8px',
                background: 'rgba(255, 255, 255, 0.05)',
                borderLeft: '3px solid var(--accent, #6366f1)',
                fontSize: '0.82rem',
                color: '#cbd5e1',
                lineHeight: '1.4'
              }}
            >
              {getAutoRecommendationText()}
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
                className={`tab-btn ${activeTab === 'processing' ? 'tab-btn--active' : ''}`}
                onClick={() => setActiveTab('processing')}
                id="tab-btn-processing"
              >
                ⚡ {t.tabProcessing || '処理中 / Processing'}
                {activeJobs.length > 0 && (
                  <span style={{
                    background: 'var(--clr-accent, #3b82f6)',
                    color: '#fff',
                    borderRadius: '10px',
                    padding: '2px 6px',
                    fontSize: '10px',
                    marginLeft: '6px',
                    fontWeight: '700'
                  }}>
                    {activeJobs.length}
                  </span>
                )}
              </button>
              <button
                className={`tab-btn ${activeTab === 'completed' ? 'tab-btn--active' : ''}`}
                onClick={() => setActiveTab('completed')}
                id="tab-btn-completed"
              >
                ✅ {t.tabCompleted || '完了済み / Completed'}
              </button>
              <button
                className={`tab-btn ${activeTab === 'txt_converter' ? 'tab-btn--active' : ''}`}
                onClick={() => setActiveTab('txt_converter')}
                id="tab-btn-txt-converter"
              >
                📕 {t.tabTxtConverter}
              </button>
              <button
                className={`tab-btn ${activeTab === 'exports' ? 'tab-btn--active' : ''}`}
                onClick={() => setActiveTab('exports')}
                id="tab-btn-exports"
              >
                📂 {t.tabExports || '出力ファイル'}
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

          {activeTab === 'processing' ? (
            <>
              {activeJobs.length === 0 ? (
                <div className="empty-state">
                  <span className="empty-icon">⚡</span>
                  <p>{t.noActiveJobs || '現在、処理中のファイルはありません。'}</p>
                </div>
              ) : (
                activeJobs.map(job => (
                  <JobCard key={job.id} job={job} t={t} onDeleted={handleDeleted} onCancelled={handleCancelled} />
                ))
              )}
            </>
          ) : activeTab === 'completed' ? (
            <>
              {completedJobs.length === 0 && otherJobs.length === 0 ? (
                <div className="empty-state">
                  <span className="empty-icon">✅</span>
                  <p>{t.noCompletedJobs || '完了した文字起こし履歴はまだありません。'}</p>
                </div>
              ) : (
                <>
                  {completedJobs.map(job => (
                    <JobCard key={job.id} job={job} t={t} onDeleted={handleDeleted} onCancelled={handleCancelled} />
                  ))}
                  {otherJobs.length > 0 && (
                    <>
                      <div style={{
                        textAlign: 'left',
                        margin: '24px 0 12px 0',
                        fontSize: '14px',
                        fontWeight: '600',
                        color: 'var(--clr-text-muted)',
                        borderBottom: '1px solid rgba(255, 255, 255, 0.05)',
                        paddingBottom: '6px'
                      }}>
                        {uiLang === 'ja' ? 'その他 (エラー / キャンセル)' : 'Others (Failed / Cancelled)'}
                      </div>
                      {otherJobs.map(job => (
                        <JobCard key={job.id} job={job} t={t} onDeleted={handleDeleted} onCancelled={handleCancelled} />
                      ))}
                    </>
                  )}
                </>
              )}
            </>
          ) : activeTab === 'txt_converter' ? (
            <div className="txt-converter-section glass-panel" style={{ padding: '24px', borderRadius: 'var(--radius-lg)', color: 'var(--clr-text-primary)' }}>
              <div style={{ textAlign: 'left', marginBottom: '20px' }}>
                <h2 style={{ fontSize: '20px', fontWeight: '700', marginBottom: '6px', color: 'var(--clr-primary, #6366f1)' }}>
                  {t.txtConvTitle}
                </h2>
                <p className="app-subtitle" style={{ fontSize: '13px', color: 'var(--clr-text-muted)', margin: 0 }}>
                  {t.txtConvSubtitle}
                </p>
              </div>

              {/* Main Content Area: Flex / Grid split depending on preview state */}
              <div style={{ display: 'grid', gridTemplateColumns: pdfPreviewUrl ? '1fr 1fr' : '1fr 340px', gap: '20px', textAlign: 'left' }}>
                
                {/* Left Side: Paste text / Load file & Settings */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <label className="settings-label" style={{ margin: 0 }}>{t.txtConvLabelPaste}</label>
                    <button 
                      type="button" 
                      className="btn btn-secondary" 
                      onClick={loadExampleTxt}
                      style={{ fontSize: '11px', padding: '4px 10px', height: 'auto' }}
                    >
                      💡 {uiLang === 'ja' ? 'サンプルロード' : 'Load Example'}
                    </button>
                  </div>
                  
                  <textarea
                    style={{
                      width: '100%',
                      height: pdfPreviewUrl ? '360px' : '280px',
                      background: 'rgba(0, 0, 0, 0.2)',
                      color: '#e2e8f0',
                      border: '1px solid var(--clr-border)',
                      borderRadius: 'var(--radius-md)',
                      padding: '12px',
                      fontSize: '13px',
                      fontFamily: 'Consolas, Monaco, monospace',
                      resize: 'none',
                      outline: 'none',
                      lineHeight: '1.5',
                      transition: 'height 0.2s ease'
                    }}
                    value={txtInputText}
                    onChange={(e) => setTxtInputText(e.target.value)}
                    placeholder={t.txtConvPlaceholder}
                  />

                  <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
                    <div style={{ flex: 1 }}>
                      <label className="settings-label" style={{ display: 'block', marginBottom: '6px' }}>{t.txtConvLabelSelectFile}</label>
                      <input
                        type="file"
                        accept=".txt"
                        onChange={handleTxtFileChange}
                        style={{
                          fontSize: '12px',
                          color: 'var(--clr-text-muted)',
                          background: 'rgba(255,255,255,0.02)',
                          border: '1px dashed var(--clr-border)',
                          padding: '10px',
                          borderRadius: 'var(--radius-md)',
                          width: '100%',
                          cursor: 'pointer'
                        }}
                      />
                    </div>

                    {/* Settings grid when preview is active */}
                    {pdfPreviewUrl && (
                      <div style={{ background: 'rgba(255,255,255,0.01)', border: '1px solid rgba(255,255,255,0.05)', padding: '12px', borderRadius: 'var(--radius-md)', display: 'flex', flexDirection: 'column', gap: '10px', marginTop: '10px', flex: 1 }}>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                          <div>
                            <label className="settings-label" style={{ fontSize: '11px', display: 'block', marginBottom: '4px' }}>
                              📄 {t.txtConvLabelMinChars}
                            </label>
                            <input
                              type="number"
                              min="50"
                              value={txtMaxChars}
                              onChange={(e) => setTxtMaxChars(Math.max(50, parseInt(e.target.value) || 1000))}
                              style={{ width: '100%', padding: '4px 6px', fontSize: '11px', background: 'rgba(0,0,0,0.3)', border: '1px solid var(--clr-border)', color: '#fff', borderRadius: 'var(--radius-sm)' }}
                            />
                          </div>
                          <div>
                            <label className="settings-label" style={{ fontSize: '11px', display: 'block', marginBottom: '4px' }}>
                              🎨 {uiLang === 'ja' ? 'テンプレート' : 'Template'}
                            </label>
                            <select
                              value={txtPdfTemplate}
                              onChange={(e) => setTxtPdfTemplate(e.target.value)}
                              style={{ width: '100%', padding: '4px 6px', fontSize: '11px', background: 'rgba(0,0,0,0.3)', border: '1px solid var(--clr-border)', color: '#fff', borderRadius: 'var(--radius-sm)' }}
                            >
                              <option value="corporate">💼 Corporate</option>
                              <option value="eco">🌱 Eco-Friendly</option>
                              <option value="cyberpunk">⚡ Cyberpunk</option>
                              <option value="emerald">💚 Emerald</option>
                              <option value="amber">🍊 Amber</option>
                              <option value="serif_court">📜 Serif Court</option>
                              <option value="cherry_blossom">🌸 Sakura</option>
                              <option value="crimson">🔴 Crimson</option>
                              <option value="indigo">💜 Indigo</option>
                              <option value="accessibility">♿ Accessible</option>
                              <option value="compact_terminal">💻 Compact Terminal</option>
                            </select>
                          </div>
                        </div>

                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                          <div>
                            <label className="settings-label" style={{ fontSize: '11px', display: 'block', marginBottom: '4px' }}>
                              📝 {uiLang === 'ja' ? 'ファイル名' : 'File Name'}
                            </label>
                            <input
                              type="text"
                              value={txtFilename}
                              onChange={(e) => setTxtFilename(e.target.value)}
                              placeholder={uiLang === 'ja' ? '会議議事録' : 'e.g. Minutes'}
                              style={{ width: '100%', padding: '4px 6px', fontSize: '11px', background: 'rgba(0,0,0,0.3)', border: '1px solid var(--clr-border)', color: '#fff', borderRadius: 'var(--radius-sm)' }}
                            />
                          </div>
                          <div>
                            <label className="settings-label" style={{ fontSize: '11px', display: 'block', marginBottom: '4px' }}>
                              ⏱️ {uiLang === 'ja' ? '録音時間' : 'Duration'}
                            </label>
                            <input
                              type="text"
                              value={txtDuration}
                              onChange={(e) => setTxtDuration(e.target.value)}
                              placeholder="00:00"
                              style={{ width: '100%', padding: '4px 6px', fontSize: '11px', background: 'rgba(0,0,0,0.3)', border: '1px solid var(--clr-border)', color: '#fff', borderRadius: 'var(--radius-sm)' }}
                            />
                          </div>
                        </div>

                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                          <div>
                            <label className="settings-label" style={{ fontSize: '11px', display: 'block', marginBottom: '4px' }}>
                              🔤 {uiLang === 'ja' ? '文字サイズ' : 'Font Size'}
                            </label>
                            <input
                              type="number"
                              min="6"
                              max="16"
                              step="0.5"
                              value={txtFontSize}
                              onChange={(e) => setTxtFontSize(e.target.value)}
                              placeholder="8"
                              style={{ width: '100%', padding: '4px 6px', fontSize: '11px', background: 'rgba(0,0,0,0.3)', border: '1px solid var(--clr-border)', color: '#fff', borderRadius: 'var(--radius-sm)', textAlign: 'center' }}
                            />
                          </div>
                          <div>
                            <label className="settings-label" style={{ fontSize: '11px', display: 'block', marginBottom: '4px' }}>
                              ↕️ {uiLang === 'ja' ? '行余白' : 'Padding'}
                            </label>
                            <input
                              type="number"
                              min="0.5"
                              max="12"
                              step="0.5"
                              value={txtRowPadding}
                              onChange={(e) => setTxtRowPadding(e.target.value)}
                              placeholder="3"
                              style={{ width: '100%', padding: '4px 6px', fontSize: '11px', background: 'rgba(0,0,0,0.3)', border: '1px solid var(--clr-border)', color: '#fff', borderRadius: 'var(--radius-sm)', textAlign: 'center' }}
                            />
                          </div>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Actions when preview is active */}
                  {pdfPreviewUrl && (
                    <div style={{ display: 'flex', gap: '12px', marginTop: '12px' }}>
                      <button
                        type="button"
                        className="btn btn-secondary"
                        onClick={() => handleConvertTxtToPdf(false)}
                        disabled={isConvertingTxt}
                        style={{ flex: 1, padding: '10px', fontSize: '13px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px' }}
                      >
                        🔄 {isConvertingTxt ? (uiLang === 'ja' ? '更新中...' : 'Updating...') : (uiLang === 'ja' ? 'プレビュー更新' : 'Update Preview')}
                      </button>
                      <button
                        type="button"
                        className="btn btn-primary"
                        onClick={() => handleConvertTxtToPdf(true)}
                        style={{ flex: 1, padding: '10px', fontSize: '13px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px' }}
                      >
                        💾 {uiLang === 'ja' ? 'PDFを保存' : 'Download PDF'}
                      </button>
                    </div>
                  )}
                </div>

                {/* Right Side: Options when NO preview, or the Live PDF Preview frame when preview is active */}
                {!pdfPreviewUrl ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', background: 'rgba(255, 255, 255, 0.02)', padding: '16px', borderRadius: 'var(--radius-md)', border: '1px solid rgba(255, 255, 255, 0.05)' }}>
                    
                    {/* Compaction Slider / Number */}
                    <div>
                      <label className="settings-label" style={{ fontSize: '12px', display: 'block', marginBottom: '6px' }}>
                        📄 {t.txtConvLabelMinChars}
                      </label>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <input
                          type="range"
                          min="100"
                          max="5000"
                          step="100"
                          value={txtMaxChars}
                          onChange={(e) => setTxtMaxChars(parseInt(e.target.value))}
                          style={{ flex: 1, cursor: 'pointer' }}
                        />
                        <input
                          type="number"
                          min="50"
                          value={txtMaxChars}
                          onChange={(e) => setTxtMaxChars(Math.max(50, parseInt(e.target.value) || 1000))}
                          style={{
                            width: '75px',
                            background: 'rgba(0, 0, 0, 0.2)',
                            color: '#fff',
                            border: '1px solid var(--clr-border)',
                            borderRadius: 'var(--radius-sm)',
                            padding: '4px 6px',
                            fontSize: '12px',
                            textAlign: 'center'
                          }}
                        />
                      </div>
                      <span style={{ fontSize: '11px', color: 'var(--clr-text-muted)', display: 'block', marginTop: '4px' }}>
                        {uiLang === 'ja' ? '※多いほどページ数が凝縮されます' : '* Higher value yields fewer total pages'}
                      </span>
                    </div>

                    {renderPdfCustomizerForm()}

                    <div style={{ marginTop: 'auto', paddingTop: '10px' }}>
                      <button
                        type="button"
                        className="btn btn-primary"
                        onClick={() => handleConvertTxtToPdf(false)}
                        disabled={isConvertingTxt}
                        style={{
                          width: '100%',
                          padding: '12px',
                          fontSize: '14px',
                          fontWeight: '600',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          gap: '8px',
                          borderRadius: 'var(--radius-md)'
                        }}
                      >
                        🔍 {isConvertingTxt ? (uiLang === 'ja' ? '生成中...' : 'Generating...') : (uiLang === 'ja' ? 'PDFプレビューを生成' : 'Generate PDF Preview')}
                      </button>
                    </div>

                  </div>
                ) : (
                  /* PDF Live Preview Pane */
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', height: '100%' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ fontSize: '12px', fontWeight: '600', color: 'var(--clr-primary)' }}>
                        🖥️ {uiLang === 'ja' ? 'リアルタイムPDFプレビュー' : 'Live PDF Preview'}
                      </span>
                      <button
                        type="button"
                        onClick={() => setPdfPreviewUrl(null)}
                        style={{
                          background: 'none',
                          border: 'none',
                          color: 'var(--clr-text-muted)',
                          fontSize: '11px',
                          cursor: 'pointer',
                          textDecoration: 'underline'
                        }}
                      >
                        ❌ {uiLang === 'ja' ? 'プレビューを閉じる' : 'Close Preview'}
                      </button>
                    </div>

                    <iframe
                      src={pdfPreviewUrl}
                      style={{
                        width: '100%',
                        height: '460px',
                        background: '#333',
                        border: '1px solid var(--clr-border)',
                        borderRadius: 'var(--radius-md)'
                      }}
                      title="PDF Preview"
                    />
                  </div>
                )}

              </div>
            </div>
          ) : activeTab === 'exports' ? (
            <div className="exports-section glass-panel" style={{ padding: '24px', borderRadius: 'var(--radius-lg)', color: 'var(--clr-text-primary)' }}>
              {/* Header with Title and native action triggers */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px', flexWrap: 'wrap', gap: '12px' }}>
                <div style={{ textAlign: 'left' }}>
                  <h2 style={{ fontSize: '20px', fontWeight: '700', marginBottom: '6px', color: 'var(--clr-primary, #6366f1)', margin: 0 }}>
                    📂 {t.exportsTitle || '出力ファイル管理'}
                  </h2>
                  <p className="app-subtitle" style={{ fontSize: '13px', color: 'var(--clr-text-muted)', margin: 0 }}>
                    {t.exportsSubtitle || 'これまでにエクスポートされたドキュメントの一覧を表示・管理します。'}
                  </p>
                </div>
                <div style={{ display: 'flex', gap: '10px' }}>
                  {window.electron && (
                    <button
                      type="button"
                      className="btn btn-secondary"
                      onClick={handleOpenExportsFolder}
                      style={{ padding: '8px 14px', fontSize: '12px' }}
                    >
                      📂 {t.exportsShowFolder || 'フォルダを開く'}
                    </button>
                  )}
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={loadExportedFiles}
                    disabled={isLoadingExports}
                    style={{ padding: '8px 14px', fontSize: '12px' }}
                  >
                    🔄 {isLoadingExports ? '...' : (uiLang === 'ja' ? '更新' : 'Refresh')}
                  </button>
                </div>
              </div>

              {/* Exports Folder Path Display */}
              {exportsDir && (
                <div style={{
                  background: 'rgba(255, 255, 255, 0.02)',
                  border: '1px solid rgba(255, 255, 255, 0.05)',
                  borderRadius: 'var(--radius-md)',
                  padding: '8px 12px',
                  fontSize: '12px',
                  color: 'var(--clr-text-muted)',
                  textAlign: 'left',
                  marginBottom: '20px',
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis'
                }} title={exportsDir}>
                  <strong>📁 {uiLang === 'ja' ? '現在の保存先: ' : 'Active Directory: '}</strong> {exportsDir}
                </div>
              )}

              {/* Files list or empty state */}
              {isLoadingExports ? (
                <div className="empty-state" style={{ padding: '60px 0' }}>
                  <span className="empty-icon" style={{ animation: 'spin 2s linear infinite' }}>🔄</span>
                  <p>{uiLang === 'ja' ? '読み込み中...' : 'Loading files...'}</p>
                </div>
              ) : exportedFiles.length === 0 ? (
                <div className="empty-state" style={{ padding: '60px 0' }}>
                  <span className="empty-icon">📁</span>
                  <p>{t.exportsEmpty || '出力ファイルがありません。'}</p>
                </div>
              ) : (
                <div className="exports-table-wrapper" style={{ overflowX: 'auto', background: 'rgba(0,0,0,0.1)', borderRadius: 'var(--radius-md)', border: '1px solid var(--clr-border)' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '13px' }}>
                    <thead>
                      <tr style={{ background: 'rgba(255, 255, 255, 0.03)', borderBottom: '1px solid var(--clr-border)' }}>
                        <th style={{ padding: '12px 16px', fontWeight: '600', color: 'var(--clr-text-muted)' }}>{uiLang === 'ja' ? '種類' : 'Type'}</th>
                        <th style={{ padding: '12px 16px', fontWeight: '600', color: 'var(--clr-text-muted)' }}>{uiLang === 'ja' ? 'ファイル名' : 'Name'}</th>
                        <th style={{ padding: '12px 16px', fontWeight: '600', color: 'var(--clr-text-muted)' }}>{uiLang === 'ja' ? 'サイズ' : 'Size'}</th>
                        <th style={{ padding: '12px 16px', fontWeight: '600', color: 'var(--clr-text-muted)' }}>{uiLang === 'ja' ? '生成日時' : 'Date Created'}</th>
                        <th style={{ padding: '12px 16px', fontWeight: '600', color: 'var(--clr-text-muted)', textAlign: 'right' }}>{uiLang === 'ja' ? 'アクション' : 'Actions'}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {exportedFiles.map((file, idx) => {
                        // Custom format colors and icons
                        const formatConfig = {
                          doc:  { icon: '📝', color: '#3b82f6', label: 'Word' },
                          pdf:  { icon: '📕', color: '#ef4444', label: 'PDF' },
                          txt:  { icon: '📄', color: '#94a3b8', label: 'TXT' }
                        }[file.format] || { icon: '📄', color: 'var(--clr-text-muted)', label: file.format.toUpperCase() };

                        const formattedSize = file.size_bytes > 1024 * 1024
                          ? `${(file.size_bytes / 1024 / 1024).toFixed(1)} MB`
                          : `${(file.size_bytes / 1024).toFixed(1)} KB`;

                        const formattedDate = new Date(file.created_at).toLocaleString();

                        return (
                          <tr key={idx} style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.04)', transition: 'background 0.2s', cursor: 'pointer' }} className="exports-row">
                            <td style={{ padding: '12px 16px' }}>
                              <span style={{
                                background: `${formatConfig.color}15`,
                                color: formatConfig.color,
                                padding: '4px 8px',
                                borderRadius: '4px',
                                fontSize: '11px',
                                fontWeight: '700',
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: '4px'
                              }}>
                                {formatConfig.icon} {formatConfig.label}
                              </span>
                            </td>
                            <td 
                              style={{ padding: '12px 16px', fontWeight: '600', wordBreak: 'break-all' }}
                              onClick={() => handleOpenExportFile(file)}
                              className="export-file-title"
                            >
                              {file.name}
                            </td>
                            <td style={{ padding: '12px 16px', color: 'var(--clr-text-muted)' }}>
                              {formattedSize}
                            </td>
                            <td style={{ padding: '12px 16px', color: 'var(--clr-text-muted)' }}>
                              {formattedDate}
                            </td>
                            <td style={{ padding: '12px 16px', textAlign: 'right' }}>
                              <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
                                <button
                                  type="button"
                                  className="btn btn-secondary"
                                  onClick={() => handleOpenExportFile(file)}
                                  style={{ padding: '4px 10px', fontSize: '11px', height: 'auto' }}
                                >
                                  ▶ {t.exportsOpen || '開く'}
                                </button>
                                {window.electron && (
                                  <button
                                    type="button"
                                    className="btn btn-secondary"
                                    onClick={() => handleShowExportInFolder(file)}
                                    style={{ padding: '4px 10px', fontSize: '11px', height: 'auto' }}
                                    title="エクスプローラーで選択"
                                  >
                                    📁
                                  </button>
                                )}
                                <button
                                  type="button"
                                  className="btn btn-delete"
                                  onClick={() => handleDeleteExportFile(file.name)}
                                  style={{ padding: '4px 10px', fontSize: '11px', height: 'auto', background: 'rgba(239, 68, 68, 0.1)', color: '#f87171', border: '1px solid rgba(239, 68, 68, 0.15)' }}
                                >
                                  🗑️ {t.exportsDelete || '削除'}
                                </button>
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
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
              </div>

              {/* Cache Data Remover Section */}
              <div className="settings-group" style={{ marginTop: '24px', borderTop: '1px solid rgba(255, 255, 255, 0.05)', paddingTop: '20px' }}>
                <label className="settings-label">{t.settingsClearCache}</label>
                <p className="app-subtitle" style={{ fontSize: '12px', margin: '-4px 0 12px 0', color: 'var(--clr-text-muted)', textAlign: 'left' }}>
                  {t.settingsClearCacheDesc}
                </p>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={handleClearCache}
                  disabled={isClearingCache}
                  id="settings-clear-cache-btn"
                  style={{
                    background: 'rgba(239, 68, 68, 0.1)',
                    color: '#f87171',
                    border: '1px solid rgba(239, 68, 68, 0.2)',
                    fontWeight: '600',
                    padding: '10px 16px',
                    transition: 'all 0.2s ease',
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.background = 'rgba(239, 68, 68, 0.2)';
                    e.currentTarget.style.boxShadow = '0 0 12px rgba(239, 68, 68, 0.3)';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.background = 'rgba(239, 68, 68, 0.1)';
                    e.currentTarget.style.boxShadow = 'none';
                  }}
                >
                  {isClearingCache ? (uiLang === 'ja' ? 'クリア中...' : 'Clearing...') : t.settingsClearCacheBtn}
                </button>
              </div>

              <button
                type="button"
                className="btn btn-primary btn-settings-save"
                onClick={handleSaveSettings}
                id="settings-save-btn"
                style={{ marginTop: '20px', display: 'block', width: '100%', maxWidth: '200px' }}
              >
                💾 {t.save}
              </button>

              {/* Developer Logs Terminal */}
              <div className="settings-group" style={{ marginTop: '16px' }}>
                <label className="settings-label">{t.devLogsTitle}</label>
                <div className="dev-terminal">
                  <div className="terminal-header">
                    <span className="terminal-title">🟢 uvicorn@{API.replace('http://', '').replace('https://', '')} (~/app/storage/logs/backend.log)</span>
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
