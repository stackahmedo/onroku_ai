import React, { useRef, useState, useCallback } from 'react';

const MAX_SIZE_GB = 3;
const MAX_BYTES = MAX_SIZE_GB * 1024 ** 3;

export default function DropZone({ selectedFiles = [], onFilesSelected, onRemoveFile, t }) {
  const [dragging, setDragging] = useState(false);
  const [warning, setWarning]   = useState('');
  const inputRef = useRef(null);
  const folderInputRef = useRef(null);

  const handleFiles = useCallback((files) => {
    if (!files || files.length === 0) return;
    const tooLarge = files.some(f => f.size > MAX_BYTES);
    setWarning(tooLarge ? t.fileWarning3GB : '');
    onFilesSelected(files);
  }, [onFilesSelected, t]);

  const onDrop = (e) => {
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
            name: filePath.split(/[\\/]/).pop(),
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

  const onBrowseFolder = (e) => {
    if (e) e.stopPropagation();
    if (window.electron) {
      window.electron.file.openDirectoryDialog().then(filePaths => {
        if (filePaths && filePaths.length > 0) {
          const pseudos = filePaths.map(filePath => ({
            name: filePath.split(/[\\/]/).pop(),
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

  const formatSize = (bytes) => {
    if (!bytes) return '';
    if (bytes > 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
    if (bytes > 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
    return `${(bytes / 1024).toFixed(0)} KB`;
  };

  const hasFiles = selectedFiles.length > 0;

  return (
    <div className="dropzone-wrapper">
      <div
        className={`dropzone ${dragging ? 'dropzone--active' : ''} ${hasFiles ? 'dropzone--has-file' : ''}`}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={onBrowse}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => e.key === 'Enter' && onBrowse()}
        id="dropzone-area"
      >
        <input
          ref={inputRef}
          type="file"
          multiple
          accept="audio/*,video/*,.mp3,.wav,.flac,.m4a,.ogg,.aac,.mp4,.mov,.mkv,.avi"
          style={{ display: 'none' }}
          onChange={(e) => handleFiles(Array.from(e.target.files))}
          id="file-input-hidden"
        />

        <input
          ref={folderInputRef}
          type="file"
          webkitdirectory="true"
          directory="true"
          multiple
          style={{ display: 'none' }}
          onChange={(e) => handleFiles(Array.from(e.target.files))}
          id="folder-input-hidden"
        />

        {hasFiles ? (
          <>
            <div className="dropzone__icon">🎵</div>
            <div className="dropzone__file-list" onClick={(e) => e.stopPropagation()}>
              {selectedFiles.map((file, idx) => (
                <div className="dropzone__file-item" key={idx}>
                  <span className="dropzone__file-icon">🎵</span>
                  <span className="dropzone__file-name" title={file.name}>{file.name}</span>
                  {file.size > 0 && (
                    <span className="dropzone__file-size">({formatSize(file.size)})</span>
                  )}
                  <button
                    type="button"
                    className="dropzone__file-remove"
                    onClick={() => onRemoveFile(idx)}
                    title="Remove file"
                  >✕</button>
                </div>
              ))}
            </div>
          </>
        ) : (
          <>
            <div className="dropzone__icon">📂</div>
            <p className="dropzone__prompt">{t.dropzonePrompt}</p>
            <p className="dropzone__or">{t.dropzoneOr}</p>
            <div className="dropzone__actions" onClick={(e) => e.stopPropagation()}>
              <button
                type="button"
                className="btn btn-dropzone-action btn-browse-files"
                onClick={onBrowse}
              >
                📄 {t.browseFiles}
              </button>
              <button
                type="button"
                className="btn btn-dropzone-action btn-browse-folder"
                onClick={onBrowseFolder}
              >
                📁 {t.browseFolder}
              </button>
            </div>
          </>
        )}
      </div>

      {warning && <p className="dropzone__warning">{warning}</p>}
    </div>
  );
}
