export interface ElectronAPI {
  api: {
    healthCheck: () => Promise<any>;
    getHardware: () => Promise<any>;
    upload: (
      filePath: string,
      lang: string,
      model: string,
      speakerCount: string,
      chunkSeconds: string,
      diarizationMode: string,
      performanceMode: string,
      speakerRange: string
    ) => Promise<any>;
    getJob: (jobId: string) => Promise<any>;
    listJobs: (skip: number, limit: number) => Promise<any>;
    exportTranscript: (jobId: string, format: string) => Promise<any>;
    cancelJob: (jobId: string) => Promise<any>;
    pauseJob: (jobId: string) => Promise<any>;
    resumeJob: (jobId: string) => Promise<any>;
    deleteJob: (jobId: string) => Promise<any>;
  };
  file: {
    openDialog: () => Promise<string[] | null>;
    openDirectoryDialog: () => Promise<string[] | null>;
    selectDirectoryPath: () => Promise<string | null>;
    saveDialog: (filename: string, format?: string) => Promise<string | null>;
    write: (path: string, data: any) => Promise<boolean>;
  };
  shell: {
    open: (path: string) => Promise<void>;
    showItem: (path: string) => Promise<void>;
  };
  win: {
    minimize: () => Promise<void>;
    maximize: () => Promise<void>;
    close: () => Promise<void>;
    reload: () => Promise<void>;
    restart: () => Promise<void>;
    confirm: (options: {
      title?: string;
      message: string;
      detail?: string;
      buttons?: string[];
    }) => Promise<boolean>;
  };
}

declare global {
  interface Window {
    electron: ElectronAPI;
  }
}

declare module '*.css' {
  const content: { [className: string]: string };
  export default content;
}

