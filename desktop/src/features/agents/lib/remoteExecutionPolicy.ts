/** The packaging profile feeds this same value to the native build script. */
export const requiredRemoteProvider: string | undefined =
  import.meta.env?.VITE_BUZZ_REMOTE_PROVIDER || undefined;

export function defaultRemoteBackend() {
  return requiredRemoteProvider
    ? { type: "provider" as const, id: requiredRemoteProvider, config: {} }
    : undefined;
}
