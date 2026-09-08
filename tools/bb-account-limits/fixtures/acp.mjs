import { createInterface } from "node:readline";
const write = message => process.stdout.write(JSON.stringify({ jsonrpc: "2.0", ...message }) + "\n");
let session = { sessionId: "fixture-session" };
createInterface({ input: process.stdin }).on("line", line => {
  const m = JSON.parse(line);
  const result = value => write({ id: m.id, result: value });
  switch (m.method) {
    case "initialize": result({ protocolVersion: 1, agentInfo: { name: "fixture", version: "1" }, agentCapabilities: { loadSession: true, sessionCapabilities: { fork: {} } }, authMethods: [] }); break;
    case "session/new": result(session); break;
    case "session/load": result({}); break;
    case "session/fork": session = { sessionId: "fixture-fork" }; result(session); break;
    case "session/prompt":
      write({ method: "session/update", params: { sessionId: session.sessionId, update: { sessionUpdate: "agent_message_chunk", content: { type: "text", text: "Fixture reply" } } } });
      result({ stopReason: "end_turn" }); break;
    case "session/cancel": break;
    default: if (m.id !== undefined) write({ id: m.id, error: { code: -32601, message: "Method not found" } });
  }
});
