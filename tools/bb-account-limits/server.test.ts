import assert from "node:assert/strict";
import { test } from "node:test";
import { providers } from "./server.js";

function acpLaunchEnv(provider: typeof providers[number]) {
  const options = provider.experimental_bridgeOptions as {
    acpLaunchSpec?: { env?: Record<string, string> };
  } | null;
  return options?.acpLaunchSpec?.env;
}

test("plugin ACP providers expose full access only", () => {
  for (const provider of providers) {
    assert.deepEqual(provider.capabilities.permissionModes, ["full"]);
  }
});

test("Cliproxy quota sources do not register as executable providers", () => {
  assert.ok(providers.every(provider => !provider.id.startsWith("cliproxy-")));
});

test("Codex ACP providers start with Codex full access", () => {
  const codexProviders = providers.filter(provider => provider.id.startsWith("acp-codex"));
  assert.ok(codexProviders.length > 0);

  for (const provider of codexProviders) {
    assert.equal(acpLaunchEnv(provider)?.INITIAL_AGENT_MODE, "agent-full-access");
  }
});
