import assert from "node:assert/strict";
import { test } from "node:test";
import { agyProvider } from "./agy-provider.js";

test("AGY exposes only the permissions and quota capabilities its adapter supports", () => {
  assert.deepEqual(agyProvider.capabilities.permissionModes, ["full"]);
  assert.equal(agyProvider.maintenance?.usage, true);
  assert.equal(agyProvider.capabilities.supportsServiceTier, false);
});
