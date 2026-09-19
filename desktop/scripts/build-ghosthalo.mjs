import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

// One value compiles the frontend default and native refusal together. Updating
// from Block's release feed must not replace this policy with a stock desktop.
const env = { ...process.env, VITE_BUZZ_REMOTE_PROVIDER: "ghosthalo-systemd" };
delete env.BUZZ_UPDATER_ENDPOINT;
delete env.BUZZ_UPDATER_PUBLIC_KEY;
const result = spawnSync(
  process.execPath,
  [
    "scripts/tauri-command.mjs",
    "build",
    "--bundles",
    "app",
    "--config",
    JSON.stringify({
      version: "0.5.23-ghosthalo.2",
      plugins: { updater: { endpoints: [] } },
    }),
    ...process.argv.slice(2),
  ],
  {
    cwd: fileURLToPath(new URL("../", import.meta.url)),
    env,
    stdio: "inherit",
  },
);
if (result.error) throw result.error;
process.exitCode = result.status ?? 1;
