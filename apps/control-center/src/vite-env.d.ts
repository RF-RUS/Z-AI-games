/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Backend origin override, e.g. http://192.168.1.10 (default http://127.0.0.1). */
  readonly VITE_API_BASE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
