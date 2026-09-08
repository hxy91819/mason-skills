import { experimental_captureBridgeJsonRpcOutput, experimental_runBridgeConformance } from "@get-bb/plugin-sdk/provider-bridge/testing";
import { experimental_providerBridge as bridge } from "../host.ts";
import { fileURLToPath } from "node:url";

const capture = experimental_captureBridgeJsonRpcOutput();
try {
  const report = await experimental_runBridgeConformance({
    providerId: "acp-codexl",
    timeoutMs: 2000,
    transport: { send: line => bridge.handleLine(line), takeMessages: () => capture.takeMessages() },
    session: {
      cwd: process.cwd(), promptInput: [{ type: "text", text: "fixture" }],
      options: {
        permissionMode: "full", permissionScope: "full", approvalReviewer: null, permissionEscalation: null,
        providerOptions: { acpDialect: "generic", acpLaunchSpec: { displayName: "Fixture", command: process.execPath, args: [fileURLToPath(new URL("./acp.mjs", import.meta.url))], env: {} } },
      },
    },
  });
  capture.restore();
  console.log(JSON.stringify(report));
} finally {
  capture.restore();
  bridge.onClose?.();
}
