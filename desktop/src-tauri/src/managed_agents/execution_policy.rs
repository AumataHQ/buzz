//! Build-scoped execution policy for a desktop used only as a remote client.
use super::BackendKind;

pub(crate) fn remote_provider() -> Option<&'static str> {
    option_env!("BUZZ_DESKTOP_REMOTE_PROVIDER")
}

pub(crate) fn require_local_execution() -> Result<(), String> {
    require_local_with_policy(remote_provider())
}

fn require_local_with_policy(provider: Option<&str>) -> Result<(), String> {
    match provider {
        Some(id) => Err(format!(
            "Local agent execution is disabled in this desktop build. Run agents on {id}."
        )),
        None => Ok(()),
    }
}

pub(crate) fn creation_backend(backend: BackendKind) -> Result<BackendKind, String> {
    creation_backend_with_policy(backend, remote_provider())
}

fn creation_backend_with_policy(
    backend: BackendKind,
    required: Option<&str>,
) -> Result<BackendKind, String> {
    let Some(required) = required else {
        return Ok(backend);
    };
    match backend {
        BackendKind::Local => Ok(BackendKind::Provider {
            id: required.to_string(),
            config: serde_json::json!({}),
        }),
        BackendKind::Provider { ref id, .. } if id == required => Ok(backend),
        _ => Err(format!(
            "This desktop only deploys agents through {required}."
        )),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn remote_policy_refuses_local_and_other_providers() {
        assert!(require_local_with_policy(Some("ghosthalo-systemd")).is_err());
        assert!(require_local_with_policy(None).is_ok());
        let remote = creation_backend_with_policy(BackendKind::Local, Some("ghosthalo-systemd"))
            .expect("legacy local requests must resolve to the required provider");
        assert!(matches!(&remote, BackendKind::Provider { id, .. } if id == "ghosthalo-systemd"));
        assert!(creation_backend_with_policy(remote, Some("different-host")).is_err());
    }
}
