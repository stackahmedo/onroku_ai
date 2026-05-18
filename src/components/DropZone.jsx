import React, { useRef, useState, useCallback } from 'react';

const MAX_SIZE_GB = 3;
const MAX_BYTES = MAX_SIZE_GB * 1024 ** 3;

export default function DropZone({ onFilesSelected, t }) {
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
      </div>

      {warning && <p className="dropzone__warning">{warning}</p>}
    </div>
  );
}
