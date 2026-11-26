interface ImportMetaEnv {
  /** API the build reads the catalog from (server side only), e.g. http://localhost:8000. */
  readonly SOBREPLANO_API_URL?: string;
  /** API the browser asks for a project's price history, e.g. http://localhost:8000. */
  readonly PUBLIC_API_URL?: string;
  /** "live" makes the build read the bank rate from datos.gov.co (SPEC 11d). */
  readonly REFERENCE_RATE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
