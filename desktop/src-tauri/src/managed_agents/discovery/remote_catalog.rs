//! Configured GhostHalo adapter contract. Deployment verifies the host process;
//! this catalog intentionally does not probe or authenticate any local adapter.
use super::*;

pub(super) fn remote_catalog() -> Vec<AcpRuntimeCatalogEntry> {
    KNOWN_ACP_RUNTIMES
        .iter()
        .filter(|runtime| matches!(runtime.id, "claude" | "codex"))
        .map(|runtime| {
            let mut entry = discover_acp_runtime_phase1(runtime, false).entry;
            entry.availability = AcpAvailabilityStatus::Available;
            entry.command = runtime
                .commands
                .first()
                .map(|command| (*command).to_string());
            entry.binary_path = None;
            entry.underlying_cli_path = None;
            entry.can_auto_install = false;
            entry.node_required = false;
            entry.auth_status = AuthStatus::Unknown;
            entry.login_hint = Some("Uses the account configured on GhostHalo.".to_string());
            entry.install_hint = "Configured on GhostHalo; verified when deployed.".to_string();
            entry
        })
        .collect()
}
