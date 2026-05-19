import React, { useRef, useState, useCallback, DragEvent, KeyboardEvent } from 'react';

const MAX_SIZE_GB = 3;
const MAX_BYTES = MAX_SIZE_GB * 1024 ** 3;

export interface PseudoFile {
  name: string;
  path?: string;
  size: number;
  _isPath?: boolean;
}

interface DropZoneProps {
  onFilesSelected: (files: (File | PseudoFile)[]) => void;
  t: Record<string, string>;
}

export default function DropZone({ onFilesSelected, t }: DropZoneProps) {
  const [dragging, setDragging] = useState(false);
  const [warning, setWarning]   = useState('');
  const inputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);

  const handleFiles = useCallback((files: (File | PseudoFile)[]) => {
    if (!files || files.length === 0) return;
    const tooLarge = files.some(f => f.size > MAX_BYTES);
    setWarning(tooLarge ? t.fileWarning3GB : '');
    onFilesSelected(files);
  }, [onFilesSelected, t]);

  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragging(false);
    const files = Array.from(e.dataTransfer.files);
    if (files.length > 0) handleFiles(files);
  };

  const onBrowse = () => {
    if (window.electron) {
      window.electron.file.openDialog().then(filePaths => {
        if (filePaths && filePaths.length > 0) {
          const pseudos = filePaths.map(filePath => ({
            name: filePath.split(/[\\/]/).pop() || filePath,
            path: filePath,
            size: 0,
            _isPath: true
          }));
          handleFiles(pseudos);
        }
      });
    } else {
      inputRef.current?.click();
    }
  };

  const onBrowseFolder = (e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    if (window.electron) {
      window.electron.file.openDirectoryDialog().then(filePaths => {
        if (filePaths && filePaths.length > 0) {
          const pseudos = filePaths.map(filePath => ({
            name: filePath.split(/[\\/]/).pop() || filePath,
            path: filePath,
            size: 0,
            _isPath: true
          }));
          handleFiles(pseudos);
        }
      });
    } else {
      folderInputRef.current?.click();
    }
  };

  return (
    <div className="dropzone-wrapper">
      <div
        className={`dropzone ${dragging ? 'dropzone--active' : ''}`}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={onBrowse}
        role="button"
        tabIndex={0}
        onKeyDown={(e: KeyboardEvent<HTMLDivElement>) => e.key === 'Enter' && onBrowse()}
        id="dropzone-area"
      >
        <input
          ref={inputRef}
          type="file"
          multiple
          accept="audio/*,video/*,.mp3,.wav,.flac,.m4a,.ogg,.aac,.mp4,.mov,.mkv,.avi"
          style={{ display: 'none' }}
          onChange={(e) => {
            if (e.target.files) {
              handleFiles(Array.from(e.target.files));
            }
          }}
          id="file-input-hidden"
          title="Select audio or video files"
        />

        <input
          ref={folderInputRef}
          type="file"
          {...({ webkitdirectory: "true", directory: "true" } as any)}
          multiple
          style={{ display: 'none' }}
          onChange={(e) => {
            if (e.target.files) {
              handleFiles(Array.from(e.target.files));
            }
          }}
          id="folder-input-hidden"
          title="Select folder containing audio or video files"
        />

        <div className="dropzone__icon">
          <svg className="dropzone__svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <polyline points="17 8 12 3 7 8" />
            <line x1="12" y1="3" x2="12" y2="15" />
          </svg>
        </div>
        <p className="dropzone__prompt">{t.dropzonePrompt}</p>
        <p className="dropzone__or">{t.dropzoneOr}</p>
        <div className="dropzone__actions" onClick={(e) => e.stopPropagation()}>
          <button
            type="button"
            className="btn btn-dropzone-action btn-browse-files"
            onClick={onBrowse}
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ marginRight: '4px' }}>
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
              <polyline points="14 2 14 8 20 8"></polyline>
            </svg>
            {t.browseFiles}
          </button>
          <button
            type="button"
            className="btn btn-dropzone-action btn-browse-folder"
            onClick={(e) => onBrowseFolder(e)}
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ marginRight: '4px' }}>
              <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path>
            </svg>
            {t.browseFolder}
          </button>
        </div>
      </div>

      {warning && <p className="dropzone__warning">{warning}</p>}
    </div>
  );
}
