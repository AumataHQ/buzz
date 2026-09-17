"""No real services or secrets: validate the production deploy planner and reconciler."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("host", Path(__file__).with_name("host.py"))
host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)


def request():
    fixture = Path(__file__).parents[2] / "crates/buzz-backend-kubernetes/tests/fixtures/provider-wire/deploy-full-launch.request.json"
    data = json.loads(fixture.read_text())
    data["provider_config"] = {}
    agent = data["agent"]
    agent["relay_url"] = host.RELAY
    agent["respond_to"] = "owner-only"
    agent["auth_tag"] = json.dumps(["auth", host.OWNER, "", "0" * 128])
    agent["launch"].update(command="codex-acp", args=[], owner_pubkey=host.OWNER)
    return data


class ProviderTests(unittest.TestCase):
    def test_identity_and_host_authority_override_user_environment(self):
        data = request()
        data["agent"]["launch"]["env"].update(HOME="/tmp/wrong", BUZZ_PRIVATE_KEY="wrong", BUZZ_ACP_AGENT_COMMAND="sh")
        pubkey, launch = host.prepare(data)
        self.assertRegex(pubkey, r"^[0-9a-f]{64}$")
        self.assertEqual(launch["env"]["BUZZ_PRIVATE_KEY"], data["agent"]["private_key_nsec"])
        self.assertEqual(launch["env"]["HOME"], "/home/ghost")
        self.assertEqual(launch["env"]["BUZZ_ACP_AGENT_COMMAND"], host.COMMANDS["codex-acp"])
        self.assertEqual(launch["env"]["BUZZ_ACP_MODEL"], "gpt-5")

    def test_bad_identity_foreign_owner_relay_and_commands_are_refused(self):
        for mutate in [
            lambda a: a.update(private_key_nsec="missing"),
            lambda a: a.update(private_key_nsec=a["private_key_nsec"][:-1] + "q"),
            lambda a: a.update(relay_url="wss://other.example"),
            lambda a: a["launch"].update(owner_pubkey="b" * 64),
            lambda a: a["launch"].update(command="/bin/sh"),
            lambda a: a["launch"]["env"].update(BUZZ_ACP_NO_PRESENCE="true"),
            lambda a: a.update(respond_to="allowlist", respond_to_allowlist=[]),
        ]:
            with self.subTest(mutate=mutate):
                data = request()
                mutate(data["agent"])
                with self.assertRaises(ValueError):
                    host.prepare(data)

    def test_identical_running_deploy_is_idempotent(self):
        pubkey, launch = host.prepare(request())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root / pubkey
            directory.mkdir()
            import hashlib
            fingerprint = hashlib.sha256(json.dumps(launch, sort_keys=True).encode()).hexdigest()
            (directory / "fingerprint").write_text(fingerprint)
            with patch.object(host, "ROOT", root), patch.object(host, "systemctl", return_value=subprocess.CompletedProcess([], 0)) as ctl:
                result = host.deploy(request())
                self.assertTrue(result["ok"])
                self.assertEqual(ctl.call_count, 1)
                self.assertEqual(ctl.call_args.args[0], "is-active")

    def test_private_write_replaces_without_exposing_contents_or_permissions(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "launch.json"
            host.write_private(path, "test-data")
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            host.write_private(path, "replacement")
            self.assertEqual(path.read_text(), "replacement")


if __name__ == "__main__":
    unittest.main()
