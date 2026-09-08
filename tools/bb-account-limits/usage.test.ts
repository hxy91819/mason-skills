import assert from "node:assert/strict";
import { test } from "node:test";
import { mkdtemp, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { normalizeAgyUsage, readAgyUsage, normalizeCodexLimits, normalizeKiroUsage, readCodexUsage, readKiroUsage } from "./usage.js";

const agy = "Gemini Models\tWeekly Limit Remaining\t94%\t2026-09-11T02:49:57Z\nClaude and GPT models\tFive Hour Limit Remaining\t99.5%\t2026-09-07T08:07:15Z\n";

test("AGY converts remaining quota into used quota and preserves group reset times", () => {
  const result = normalizeAgyUsage(agy);
  assert.ok(result.supported && result.usage.status === "ok");
  assert.deepEqual(result.usage.windows, [
    { label: "Gemini Models: Weekly limit", usedPercent: 6, resetsAt: "2026-09-11T02:49:57.000Z" },
    { label: "Claude and GPT models: 5-hour limit", usedPercent: 0.5, resetsAt: "2026-09-07T08:07:15.000Z" },
  ]);
  for (const [remaining, used] of [["0%", 100], ["100%", 0]] as const) {
    const edge = normalizeAgyUsage(agy.replace("94%", remaining));
    assert.ok(edge.supported && edge.usage.status === "ok");
    assert.equal(edge.usage.windows[0].usedPercent, used);
  }
});

test("AGY rejects unknown, partial and invalid quota output", () => {
  for (const raw of ["", "No usage data available.", agy + "unexpected", agy.replace("94%", "101%"), agy.replace("94%", "NaN%"), agy.replace("2026-09-11", "2026-02-30")]) {
    const result = normalizeAgyUsage(raw);
    assert.ok(result.supported && result.usage.status === "error");
  }
});

test("AGY query uses the usage command, ignores startup diagnostics and rejects unsuccessful exits", async () => {
  await executable(`
    if (JSON.stringify(process.argv.slice(2)) !== JSON.stringify(['--print','/usage'])) process.exit(2);
    console.error('You are not logged into Antigravity.');
    console.log(${JSON.stringify(agy)});`, async path => {
    assert.deepEqual(await readAgyUsage(path), normalizeAgyUsage(agy));
  });
  await executable(`console.log(${JSON.stringify(agy)}); process.exitCode = 1;`, async path => {
    const result = await readAgyUsage(path);
    assert.ok(result.supported && result.usage.status === "error");
  });
  assert.deepEqual(await readAgyUsage('/nonexistent/bb-agy'), { supported: true, usage: { status: "not_installed" } });
});

const kiro = "\u001b[1mEstimated Usage\u001b[0m | resets on 2026-10-01 | KIRO PRO MAX\nCredits (107.32 of 5,000 covered in plan)\n2%";

test("Kiro preserves fractional usage and does not invent a reset time", () => {
  const result = normalizeKiroUsage(kiro);
  assert.ok(result.supported && result.usage.status === "ok");
  assert.equal(result.usage.windows[0].usedPercent, 2.1464);
  assert.equal(result.usage.windows[0].resetsAt, null);
  assert.match(result.usage.windows[0].label, /107.32 \/ 5000.*2026-10-01/);
});

test("Kiro rejects missing, changed, invalid and zero-limit output", () => {
  for (const text of ["", "remaining credits: 100", kiro.replace("5,000", "0"), kiro.replace("2026-10-01", "2026-02-30")]) {
    const result = normalizeKiroUsage(text);
    assert.ok(result.supported && result.usage.status === "error");
  }
  assert.deepEqual(normalizeKiroUsage("You are not logged in, please log in"), { supported: true, usage: { status: "unauthenticated" } });
});

test("Codex reports all model-family windows without duplicating the legacy bucket", () => {
  const primary = { usedPercent: 20, windowDurationMins: 300, resetsAt: 1788744000 };
  const main = { limitId: "codex", planType: "pro", primary };
  const result = normalizeCodexLimits({ rateLimits: main, rateLimitsByLimitId: {
    codex: main,
    spark: { limitName: "Spark", secondary: { usedPercent: 120, windowDurationMins: 10080, resetsAt: null } },
  } });
  assert.ok(result.supported && result.usage.status === "ok");
  assert.deepEqual(result.usage.windows, [
    { label: "codex: 5-hour limit", usedPercent: 20, resetsAt: new Date(primary.resetsAt * 1000).toISOString() },
    { label: "Spark: Weekly limit", usedPercent: 100, resetsAt: null },
  ]);
});

test("Codex legacy windows work; absent or malformed limits are never reported as unused", () => {
  const result = normalizeCodexLimits({ rateLimits: { primary: { usedPercent: 0 } } });
  assert.ok(result.supported && result.usage.status === "ok");
  for (const raw of [null, {}, { rateLimits: {} }, { rateLimits: { primary: { usedPercent: "0" } } }]) {
    const invalid = normalizeCodexLimits(raw);
    assert.ok(invalid.supported && invalid.usage.status === "error");
  }
});

async function executable(body: string, run: (path: string) => Promise<void>) {
  const dir = await mkdtemp(join(tmpdir(), "bb-limits-test-"));
  const path = join(dir, "fixture.mjs");
  await writeFile(path, "#!/usr/bin/env node\n" + body, { mode: 0o755 });
  try { await run(path); } finally { await rm(dir, { recursive: true, force: true }); }
}

test("Kiro query captures real CLI output and maps missing executables", async () => {
  await executable(`console.log(${JSON.stringify(kiro)});`, async path => {
    assert.deepEqual(await readKiroUsage(path), normalizeKiroUsage(kiro));
  });
  assert.deepEqual(await readKiroUsage("/nonexistent/bb-kiro"), { supported: true, usage: { status: "not_installed" } });
});

test("Codex account query performs the handshake and exits without an agent turn", async () => {
  const raw = { rateLimits: { planType: "pro", primary: { usedPercent: 35, windowDurationMins: 300 } } };
  await executable(`
    import {createInterface} from 'node:readline';
    createInterface({input:process.stdin}).on('line', line => {
      const m=JSON.parse(line);
      const responses={initialize:{},'account/read':{account:{type:'chatgpt'}},'account/rateLimits/read':${JSON.stringify(raw)}};
      if(m.method==='initialized') return;
      if(!(m.method in responses)) process.exit(5);
      console.log(JSON.stringify({id:m.id,result:responses[m.method]}));
    });`, async path => {
    assert.deepEqual(await readCodexUsage(path), normalizeCodexLimits(raw));
  });
});

test("hung quota processes time out; caller cancellation stops the query", async () => {
  await executable("setInterval(()=>{}, 1000);", async path => {
    const start = Date.now();
    const result = await readKiroUsage(path, { timeoutMs: 50 });
    assert.ok(result.supported && result.usage.status === "error");
    assert.match(result.usage.message, /timed out/);
    assert.ok(Date.now() - start < 4000);
    const controller = new AbortController();
    const pending = readCodexUsage(path, { signal: controller.signal });
    controller.abort();
    const cancelled = await pending;
    assert.ok(cancelled.supported && cancelled.usage.status === "error");
    assert.match(cancelled.usage.message, /cancelled/);
  });
});
