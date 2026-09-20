import assert from "node:assert/strict";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { createServer } from "vite";

test("GhostHalo profile defaults creation and catalog starts to remote, refusing local form state", async () => {
  const server = await createServer({
    configFile: false,
    optimizeDeps: { noDiscovery: true, entries: [] },
    root: fileURLToPath(new URL("../", import.meta.url)),
    server: { middlewareMode: true, watch: null },
    resolve: {
      alias: { "@": fileURLToPath(new URL("../src", import.meta.url)) },
    },
    define: {
      "import.meta.env.VITE_BUZZ_REMOTE_PROVIDER":
        JSON.stringify("ghosthalo-systemd"),
    },
  });
  try {
    const intent = await server.ssrLoadModule(
      "/src/features/agents/ui/whereToRunIntent.ts",
    );
    const mapping = await server.ssrLoadModule(
      "/src/features/agents/lib/instanceInputForDefinition.ts",
    );
    const draft = intent.emptyWhereToRunDraft;
    assert.equal(draft.runOn, "ghosthalo-systemd");
    assert.equal(intent.canSubmitWhereToRun(draft), false);
    assert.equal(
      intent.canSubmitWhereToRun({ ...draft, runOn: "local" }),
      false,
    );
    assert.equal(
      intent.canSubmitWhereToRun({ ...draft, runOn: "another-provider" }),
      false,
    );
    const ready = {
      ...draft,
      probedProvider: { ok: true, config_schema: { properties: {} } },
    };
    assert.equal(intent.canSubmitWhereToRun(ready), true);
    const expected = { type: "provider", id: "ghosthalo-systemd", config: {} };
    assert.deepEqual(intent.resolveBackendIntent(ready), expected);
    const input = await mapping.buildInstanceInputForDefinition(
      { id: "test", displayName: "Test", systemPrompt: "", avatarUrl: null },
      { id: "codex", command: "codex-acp" },
    );
    assert.deepEqual(input.backend, expected);
    assert.equal(input.startOnAppLaunch, false);
  } finally {
    await server.close();
  }
});
