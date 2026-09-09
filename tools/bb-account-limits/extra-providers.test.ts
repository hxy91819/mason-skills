import assert from "node:assert/strict";
import { test } from "node:test";
import { extraProviders } from "./extra-providers.js";

test("optional ACP providers expose full access only", () => {
  for (const provider of extraProviders) {
    assert.deepEqual(provider.capabilities.permissionModes, ["full"]);
  }
});
