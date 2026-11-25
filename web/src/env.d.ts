interface ImportMetaEnv {
  /** API the build reads the catalog from (server side only), e.g. http://localhost:8000. */
  readonly SOBREPLANO_API_URL?: string;
  /** API the browser asks for a project's price history, e.g. http://localhost:8000. */
  readonly PUBLIC_API_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
