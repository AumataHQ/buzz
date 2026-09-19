//! Configured GhostHalo adapter contract. Deployment verifies the host process;
//! this catalog intentionally does not probe or authenticate any local adapter.
use super::*;

pub(super) fn remote_catalog() -> Vec<AcpRuntimeCatalogEntry> {
    let mut entries: Vec<_> = KNOWN_ACP_RUNTIMES
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
        .collect();

    entries.extend(
        presets::PRESET_HARNESSES
            .iter()
            .filter(|runtime| matches!(runtime.id, "gemini" | "grok"))
            .map(|runtime| {
                let mut entry = presets::preset_catalog_entry(runtime, |command| {
                    Some(std::path::PathBuf::from(command))
                });
                entry.binary_path = None;
                entry.underlying_cli_path = None;
                entry.can_auto_install = false;
                entry.node_required = false;
                entry.auth_status = AuthStatus::Unknown;
                entry.login_hint =
                    Some("Uses the account configured on GhostHalo.".to_string());
                entry.install_hint =
                    "Configured on GhostHalo; verified when deployed.".to_string();
                entry
            }),
    );

    entries
}

#[cfg(test)]
mod tests {
    use super::remote_catalog;

    #[test]
    fn remote_catalog_exposes_only_configured_ghosthalo_runtimes() {
        let entries = remote_catalog();
        let ids: Vec<_> = entries.iter().map(|entry| entry.id.as_str()).collect();
        assert_eq!(ids, ["claude", "codex", "gemini", "grok"]);

        let gemini = entries.iter().find(|entry| entry.id == "gemini").unwrap();
        assert_eq!(gemini.command.as_deref(), Some("gemini"));
        assert_eq!(gemini.default_args, ["--acp"]);

        let grok = entries.iter().find(|entry| entry.id == "grok").unwrap();
        assert_eq!(grok.command.as_deref(), Some("grok"));
        assert_eq!(
            grok.default_args,
            ["agent", "--always-approve", "stdio"]
        );
    }
}
