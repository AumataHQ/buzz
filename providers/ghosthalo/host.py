#!/usr/bin/env python3
"""GhostHalo deploy endpoint and systemd runner; invoked only through authenticated SSH."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

ROOT = Path("/home/ghost/buzz/agents/managed")
HOST_SCRIPT = "/home/ghost/buzz/provider/host.py"
RELAY = "wss://ghosthalo.tailed205b.ts.net:10443"
OWNER = "5b80a0f34dd9f0b6fdee57c1c25d1d768e60428df664d986dc77f295392bbfcf"
PATH = "/home/ghost/buzz/bin:/home/ghost/buzz/adapters/node_modules/.bin:/home/ghost/.local/bin:/usr/local/bin:/usr/bin:/bin"
COMMANDS = {
    "codex-acp": "/home/ghost/buzz/adapters/node_modules/.bin/codex-acp",
    "claude-agent-acp": "/home/ghost/buzz/adapters/node_modules/.bin/claude-agent-acp",
    "gemini": "/home/ghost/.local/bin/gemini",
    "grok": "/home/ghost/.local/bin/grok",
}
MAX_REQUEST = 1024 * 1024


def public_key(nsec):
    """Validate Bech32 nsec checksum and derive its x-only public key."""
    from cryptography.hazmat.primitives.asymmetric import ec
    alphabet = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
    if not isinstance(nsec, str) or not nsec.startswith("nsec1") or len(nsec) != 63:
        raise ValueError("A valid agent nsec is required")
    try:
        data = [alphabet.index(c) for c in nsec[5:]]
    except ValueError as error:
        raise ValueError("Invalid agent identity") from error
    checksum = 1
    values = [ord(c) >> 5 for c in "nsec"] + [0] + [ord(c) & 31 for c in "nsec"] + data
    for value in values:
        top = checksum >> 25
        checksum = ((checksum & 0x1ffffff) << 5) ^ value
        for index, generator in enumerate((0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3)):
            if (top >> index) & 1:
                checksum ^= generator
    if checksum != 1:
        raise ValueError("Invalid agent identity checksum")
    accumulator = bits = 0
    secret = bytearray()
    for value in data[:-6]:
        accumulator = (accumulator << 5) | value
        bits += 5
        while bits >= 8:
            bits -= 8
            secret.append((accumulator >> bits) & 255)
    if len(secret) != 32 or (accumulator & ((1 << bits) - 1)):
        raise ValueError("Invalid agent identity payload")
    key = ec.derive_private_key(int.from_bytes(secret, "big"), ec.SECP256K1())
    return f"{key.public_key().public_numbers().x:064x}"


def prepare(request):
    if request.get("op") != "deploy" or request.get("provider_config", {}) != {}:
        raise ValueError("Unsupported deployment request")
    agent = request["agent"]
    launch = agent["launch"]
    if agent.get("relay_url", "").rstrip("/") != RELAY or launch.get("owner_pubkey") != OWNER:
        raise ValueError("This provider only accepts the configured GhostHalo community and owner")
    pubkey = public_key(agent.get("private_key_nsec"))
    # Only known installed adapters are supported. Never execute arbitrary Mac paths,
    # shell snippets, or a command supplied through environment overrides.
    command = COMMANDS.get(Path(launch.get("command", "")).name)
    if command is None:
        raise ValueError(
            "GhostHalo currently supports the Claude, Codex, Gemini, and Grok ACP runtimes"
        )
    args = launch.get("args", [])
    if not isinstance(args, list) or any(not isinstance(a, str) or "," in a or "\x00" in a for a in args):
        raise ValueError("Invalid ACP arguments")
    env = {}
    for layer in (launch.get("policy_env", {}), launch.get("env", {})):
        if not isinstance(layer, dict):
            raise ValueError("Invalid launch environment")
        for key, value in layer.items():
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) or not isinstance(value, str) or "\x00" in value or len(value.encode()) > 65536:
                raise ValueError("Invalid launch environment")
            env[key] = value
    if "BUZZ_ACP_NO_PRESENCE" in env:
        raise ValueError("Remote presence cannot be disabled")
    # Identity, executable and lifecycle settings are owned by this endpoint.
    for key in list(env):
        if key in {"NOSTR_PRIVATE_KEY", "BUZZ_AUTH_TAG", "BUZZ_ACP_SYSTEM_PROMPT_FILE",
                   "BUZZ_ACP_RESPOND_TO_ALLOWLIST", "LD_PRELOAD", "DYLD_INSERT_LIBRARIES", "NODE_OPTIONS"}:
            del env[key]
    mode = agent.get("respond_to", "owner-only")
    if mode not in {"owner-only", "allowlist", "anyone", "nobody"}:
        raise ValueError("Invalid audience policy")
    allowed = agent.get("respond_to_allowlist") or []
    if mode == "allowlist" and (not allowed or any(not re.fullmatch(r"[0-9a-f]{64}", p) for p in allowed)):
        raise ValueError("Invalid audience allowlist")
    auth = agent.get("auth_tag")
    if not isinstance(auth, str) or not auth:
        raise ValueError("Desktop ownership attestation is required")
    tag = json.loads(auth)
    if not isinstance(tag, list) or len(tag) != 4 or tag[:2] != ["auth", OWNER]:
        raise ValueError("Invalid ownership attestation")
    env.update({"HOME": "/home/ghost", "PATH": PATH,
                "BUZZ_RELAY_URL": RELAY, "BUZZ_PRIVATE_KEY": agent["private_key_nsec"],
                "BUZZ_AUTH_TAG": auth, "BUZZ_ACP_AGENT_OWNER": OWNER,
                "BUZZ_ACP_AGENT_COMMAND": command, "BUZZ_ACP_AGENT_ARGS": ",".join(args),
                "BUZZ_ACP_MCP_COMMAND": "", "BUZZ_ACP_RESPOND_TO": mode,
                "BUZZ_ACP_ALLOWED_RESPOND_TO": mode,
                "BUZZ_ACP_EXIT_AFTER_INACTIVITY": "14400", "BUZZ_ACP_HEARTBEAT_INTERVAL": "0"})
    if mode == "allowlist":
        env["BUZZ_ACP_RESPOND_TO_ALLOWLIST"] = ",".join(allowed)
    return pubkey, {"env": env, "name": agent.get("name", "Buzz agent")}


def write_private(path, data):
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".launch-")
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def systemctl(*args):
    return subprocess.run(["/usr/bin/systemctl", "--user", *args], capture_output=True, timeout=35, check=False)


def deploy(request):
    pubkey, launch = prepare(request)
    os.umask(0o077)
    ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory = ROOT / pubkey
    if directory.is_symlink():
        raise ValueError("Agent directory cannot be a symlink")
    directory.mkdir(mode=0o700, exist_ok=True)
    service = "buzz-managed-" + pubkey + ".service"
    serialized = json.dumps(launch, sort_keys=True)
    fingerprint = hashlib.sha256(serialized.encode()).hexdigest()
    with (directory / "deploy.lock").open("a") as lock:
        deadline = time.monotonic() + 30
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise RuntimeError("Another deployment is still in progress")
                time.sleep(0.1)
        stamp = directory / "fingerprint"
        unchanged = stamp.exists() and stamp.read_text() == fingerprint
        if unchanged and systemctl("is-active", "--quiet", service).returncode == 0:
            return {"ok": True, "agent_id": "systemd:ghosthalo:" + service}
        unit = Path("/home/ghost/.config/systemd/user") / service
        text = ("[Unit]\nDescription=Buzz remote agent\nAfter=network-online.target\n"
                "StartLimitIntervalSec=300\nStartLimitBurst=3\n[Service]\nType=simple\n"
                f"WorkingDirectory={directory}\nExecStart=/usr/bin/python3 {HOST_SCRIPT} --run {pubkey}\n"
                "Restart=on-failure\nRestartSec=10\nTimeoutStopSec=30\nKillMode=control-group\nUMask=0077\n"
                "[Install]\nWantedBy=default.target\n")
        write_private(directory / "launch.json", serialized)
        write_private(unit, text)
        for args in (("daemon-reload",), ("enable", service), ("restart", service)):
            if systemctl(*args).returncode:
                raise RuntimeError("Could not activate GhostHalo agent service")
        # Require a surviving main process, not merely a successful systemctl call.
        time.sleep(2)
        if systemctl("is-active", "--quiet", service).returncode:
            raise RuntimeError("GhostHalo agent exited during startup")
        write_private(stamp, fingerprint)
    return {"ok": True, "agent_id": "systemd:ghosthalo:" + service}


def run_agent(pubkey):
    if not re.fullmatch(r"[0-9a-f]{64}", pubkey):
        raise ValueError("Invalid agent identifier")
    directory = ROOT / pubkey
    launch = json.loads((directory / "launch.json").read_text())
    os.chdir(directory)
    # No ambient SSH/session environment or Mac credentials are inherited.
    os.execve("/home/ghost/buzz/bin/buzz-acp", ["buzz-acp"], launch["env"])


if __name__ == "__main__":
    try:
        if len(sys.argv) == 3 and sys.argv[1] == "--run":
            run_agent(sys.argv[2])
        else:
            raw = sys.stdin.buffer.read(MAX_REQUEST + 1)
            if len(raw) > MAX_REQUEST:
                raise ValueError("Oversized provider request")
            print(json.dumps(deploy(json.loads(raw))))
    except Exception:
        # Never echo secrets, provider data, tracebacks, or child stderr.
        print(json.dumps({"ok": False, "error": "GhostHalo launch refused or failed"}))
        sys.exit(1)
