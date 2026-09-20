# GhostHalo remote launch provider

This provider uses Buzz's v1 `info` / `deploy` protocol. The Mac invokes
`buzz-backend-ghosthalo-systemd`; it sends the request on stdin over the existing
authenticated `ghosthalo` SSH connection to `/home/ghost/buzz/provider/host.py`.
SSH host-key verification and batch authentication are required. No local ACP
worker is started. Credentials are never placed in command arguments or local
staging files.

The host endpoint accepts only the configured GhostHalo relay and owner. It
supports the installed Claude, Codex, Gemini CLI, and Grok Build ACP runtimes,
using GhostHalo's existing provider authentication. Antigravity's `agy` CLI is
validated separately because it does not expose ACP; Gemini CLI supplies the
official Gemini ACP entrypoint. Other runtimes fail explicitly and need an
installed host adapter before support is added. The adapter executable is
resolved on GhostHalo; Mac paths are never executed remotely.

Each identity has a stable `buzz-managed-<pubkey>.service` and a private directory
under `/home/ghost/buzz/agents/managed/<pubkey>`. The directory and launch JSON
are protected with modes 0700 and 0600. A per-identity lock serializes deployment;
an identical already-active deployment returns the existing service. Changed
configuration restarts that identity's one service. `Restart=on-failure` means
intentional shutdown and the four-hour idle exit remain stopped. User lingering
allows services to outlive both SSH and the Mac. Work directories persist.

After deployment the desktop reads relay presence and uses relay shutdown
messages. `systemctl --user` and `journalctl --user` on GhostHalo remain the
operational recovery tools. Deployment confirmation means a surviving systemd
process; relay presence and a real reply are separate acceptance checks.

## Install and build

1. Install `host.py` at `/home/ghost/buzz/provider/host.py` (mode 0700). The
   host needs Python 3, `cryptography`, systemd user services, the Buzz ACP
   binary and the four runtimes referenced in the script. GhostHalo already has
   these dependencies. Preserve the existing relay and agent services.
2. Install the executable `buzz-backend-ghosthalo-systemd` in the Mac's
   `~/.local/bin`. Buzz searches that directory even when launched from Finder.
3. Activate Hermit and run `cd desktop && pnpm tauri:build:ghosthalo`. This
   packages `0.5.23-ghosthalo.2` with `VITE_BUZZ_REMOTE_PROVIDER=ghosthalo-systemd`.
   The same build input selects the frontend default and native execution
   refusal. The profile does not use Block's updater feed. Unprofiled upstream
   builds keep their original behavior; install the GhostHalo build on this Mac.

In this profile, GhostHalo is visible outside Advanced and the new-agent destination has no local choice. The native catalog offers the configured Claude, Codex, Gemini CLI, and Grok Build runtimes without probing Mac executables or treating local credentials as host authentication. Missing provider
discovery blocks creation. Legacy create requests resolve to GhostHalo, while
existing local records cannot launch, including through runtime-pair start and
automatic restore. Local ACP model-discovery subprocesses are also refused;
model configuration is applied on the remote adapter at launch.

## Validation

Run `python3 providers/ghosthalo/test_host.py` for identity validation, environment
authority, invalid destinations, private file permissions, and idempotent deploy.
Run the normal `just ci` gate, plus the native compiled-policy test:

```sh
VITE_BUZZ_REMOTE_PROVIDER=ghosthalo-systemd cargo test \
  --manifest-path desktop/src-tauri/Cargo.toml \
  remote_policy_blocks_actual_process_spawn -- --ignored
```

Then create an agent in the packaged desktop, request `hostname` and `pwd`,
verify `ghosthalo` and that identity's directory, and check no local `buzz-acp`
or adapter process exists. Quit and reopen the desktop; the remote PID should
remain unchanged. This live path is required in addition to fixture tests.
