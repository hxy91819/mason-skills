import assert from "node:assert/strict";
import { test } from "node:test";
import { mkdtemp, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { normalizeAgyUsage, normalizeAntigravityUsage, normalizeClaudeUsage, normalizeCliproxyCachedUsage, normalizeCliproxyCodexUsage, normalizeGrokUsage, normalizeKimiUsage, readAgyUsage, readCliproxyProviderUsage, readCliproxyUsage, normalizeCodexLimits, normalizeKiroUsage, readCodexUsage, readKiroUsage } from "./usage.js";

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

test("Claude usage converts Cliproxy's official usage response into BB windows", () => {
  const result = normalizeClaudeUsage({ limits: [
    { kind: "session", percent: 8, resets_at: "2026-09-09T11:00:00+00:00" },
    { kind: "weekly_all", percent: 63, resets_at: "2026-09-12T10:00:00+00:00" },
    { kind: "weekly_scoped", percent: 95, resets_at: "2026-09-12T10:00:00+00:00" },
  ] }, { provider: "claude", authIndex: "account-1", label: "Claude work" });
  assert.ok(result.supported && result.usage.status === "ok");
  assert.deepEqual(result.usage.windows, [
    { label: "5-hour limit", usedPercent: 8, resetsAt: "2026-09-09T11:00:00.000Z" },
    { label: "Weekly limit", usedPercent: 63, resetsAt: "2026-09-12T10:00:00.000Z" },
    { label: "Weekly scoped limit", usedPercent: 95, resetsAt: "2026-09-12T10:00:00.000Z" },
  ]);
  for (const invalid of [{}, { limits: [{ kind: "session", percent: 101 }] }]) {
    const invalidResult = normalizeClaudeUsage(invalid, { provider: "claude", authIndex: "account-1" });
    assert.ok(invalidResult.supported && invalidResult.usage.status === "error");
  }
});

test("Grok usage exposes both the current period and product quota", () => {
  const result = normalizeGrokUsage({ config: {
    currentPeriod: { type: "USAGE_PERIOD_TYPE_WEEKLY", end: "2026-09-12T06:53:49.038097+00:00" },
    creditUsagePercent: 7,
    productUsage: [{ product: "GrokBuild", usagePercent: 7 }],
  } }, { provider: "xai", authIndex: "account-1", label: "Grok" });
  assert.ok(result.supported && result.usage.status === "ok");
  assert.deepEqual(result.usage.windows, [
    { label: "Weekly limit", usedPercent: 7, resetsAt: "2026-09-12T06:53:49.038Z" },
    { label: "GrokBuild", usedPercent: 7, resetsAt: "2026-09-12T06:53:49.038Z" },
  ]);
});

test("Antigravity converts each authoritative quota bucket from remaining to used", () => {
  const result = normalizeAntigravityUsage({ groups: [
    { displayName: "Gemini Models", buckets: [
      { window: "weekly", remainingFraction: 0.79, resetTime: "2026-09-12T10:00:00Z" },
      { window: "5h", remainingFraction: 0.84, resetTime: "2026-09-09T11:00:00Z" },
    ] },
    { displayName: "Claude and GPT models", buckets: [
      { window: "weekly", remainingFraction: 1, resetTime: "2026-09-12T10:00:00Z" },
    ] },
  ] }, { provider: "antigravity", authIndex: "account-1", label: "Gemini · 账号 1" });
  assert.ok(result.supported && result.usage.status === "ok");
  assert.deepEqual(result.usage.windows, [
    { label: "Gemini Models: Weekly limit", usedPercent: 21, resetsAt: "2026-09-12T10:00:00.000Z" },
    { label: "Gemini Models: 5-hour limit", usedPercent: 16, resetsAt: "2026-09-09T11:00:00.000Z" },
    { label: "Claude and GPT models: Weekly limit", usedPercent: 0, resetsAt: "2026-09-12T10:00:00.000Z" },
  ]);
  for (const invalid of [{}, { groups: [{ buckets: [{ remainingFraction: 1.01 }] }] }]) {
    const invalidResult = normalizeAntigravityUsage(invalid, { provider: "antigravity", authIndex: "account-1" });
    assert.ok(invalidResult.supported && invalidResult.usage.status === "error");
  }
});

test("Kimi converts its weekly and rolling-window token quotas into percentages", () => {
  const result = normalizeKimiUsage({
    subType: "kimi-code-pro",
    usage: { limit: "1,000", used: "250", remaining: "750", resetTime: "2026-09-12T10:00:00Z" },
    limits: [{
      window: { duration: 300, timeUnit: "TIME_UNIT_MINUTE" },
      detail: { limit: "200", used: "10", remaining: "190", resetTime: "2026-09-09T13:00:00Z" },
    }],
  }, { provider: "kimi", authIndex: "account-1", label: "Kimi" });
  assert.ok(result.supported && result.usage.status === "ok");
  assert.deepEqual(result.usage.windows, [
    { label: "Weekly limit", usedPercent: 25, resetsAt: "2026-09-12T10:00:00.000Z" },
    { label: "5-hour limit", usedPercent: 5, resetsAt: "2026-09-09T13:00:00.000Z" },
  ]);
  for (const invalid of [{}, { usage: { limit: "0", used: "0" } }, { usage: { limit: "100", used: "101" } }]) {
    const invalidResult = normalizeKimiUsage(invalid, { provider: "kimi", authIndex: "account-1" });
    assert.ok(invalidResult.supported && invalidResult.usage.status === "error");
  }
});

test("Cliproxy Codex exposes the main and additional model-family windows", () => {
  const result = normalizeCliproxyCodexUsage({
    plan_type: "pro",
    rate_limit: { primary_window: { used_percent: 20, limit_window_seconds: 18_000, reset_at: 1788951600 } },
    additional_rate_limits: [{
      limit_name: "Codex Spark",
      rate_limit: { secondary_window: { used_percent: 35, limit_window_seconds: 604_800, reset_at: 1789207200 } },
    }],
  }, { provider: "codex", authIndex: "account-1", label: "Codex" });
  assert.ok(result.supported && result.usage.status === "ok");
  assert.deepEqual(result.usage.windows, [
    { label: "5-hour limit", usedPercent: 20, resetsAt: "2026-09-09T11:00:00.000Z" },
    { label: "Codex Spark: Weekly limit", usedPercent: 35, resetsAt: "2026-09-12T10:00:00.000Z" },
  ]);
  for (const invalid of [{}, { rate_limit: { primary_window: { used_percent: 101 } } }]) {
    const invalidResult = normalizeCliproxyCodexUsage(invalid, { provider: "codex", authIndex: "account-1" });
    assert.ok(invalidResult.supported && invalidResult.usage.status === "error");
  }
});

test("cached Claude rate-limit signals are a safe fallback and deduplicate model snapshots", () => {
  const result = normalizeCliproxyCachedUsage({ model_quotas: {
    latest: { observed_at: "2026-09-09T10:00:00Z", signals: {
      "Anthropic-Ratelimit-Unified-5h-Utilization": "0.05",
      "Anthropic-Ratelimit-Unified-5h-Reset": "1788951600",
      "Anthropic-Ratelimit-Unified-7d-Utilization": "0.62",
      "Anthropic-Ratelimit-Unified-7d-Reset": "1789207200",
    } },
    old: { observed_at: "2026-09-09T09:00:00Z", signals: {
      "Anthropic-Ratelimit-Unified-5h-Utilization": "0.99",
      "Anthropic-Ratelimit-Unified-5h-Reset": "1788948000",
    } },
  } }, { provider: "claude", authIndex: "account-1", label: "Claude work" });
  assert.ok(result.supported && result.usage.status === "ok");
  assert.deepEqual(result.usage.windows, [
    { label: "5-hour limit", usedPercent: 5, resetsAt: "2026-09-09T11:00:00.000Z" },
    { label: "Weekly limit", usedPercent: 62, resetsAt: "2026-09-12T10:00:00.000Z" },
  ]);
  const invalidResult = normalizeCliproxyCachedUsage({ quota: { signals: {} } }, { provider: "claude", authIndex: "account-1" });
  assert.ok(invalidResult.supported && invalidResult.usage.status === "error");
});

test("configured cached windows make new Cliproxy provider signals usable without a code change", () => {
  const result = normalizeCliproxyCachedUsage({ quota: { signals: {
    "X-Custom-Usage": "47.5",
    "X-Custom-Reset": "1788951600",
  } } }, {
    provider: "custom-provider",
    authIndex: "account-1",
    label: "Custom account",
    cachedWindows: [{
      label: "Monthly credits",
      usedPercentSignal: "x-custom-usage",
      resetsAtSignal: "x-custom-reset",
      scale: "percent",
    }],
  });
  assert.ok(result.supported && result.usage.status === "ok");
  assert.deepEqual(result.usage.windows, [
    { label: "Monthly credits", usedPercent: 47.5, resetsAt: "2026-09-09T11:00:00.000Z" },
  ]);
});

test("Cliproxy queries the selected credential, uses token substitution only inside management API, and falls back to cache", async () => {
  const originalFetch = globalThis.fetch;
  const requests: Array<{ url: string; init?: RequestInit }> = [];
  globalThis.fetch = async (input, init) => {
    const url = String(input);
    requests.push({ url, init });
    if (url.endsWith("/auth-files")) return new Response(JSON.stringify({ files: [{
      provider: "claude", auth_index: "account-1", model_quotas: { model: { signals: {
        "Anthropic-Ratelimit-Unified-5h-Utilization": "0.25",
        "Anthropic-Ratelimit-Unified-5h-Reset": "1788951600",
      } } },
    }] }), { status: 200 });
    return new Response(JSON.stringify({ status_code: 403, body: "{}" }), { status: 200 });
  };
  try {
    const result = await readCliproxyUsage({ provider: "claude", authIndex: "account-1", label: "Claude work" }, {
      managementBaseUrl: "http://cliproxy.test/v0/management",
      managementKey: "test-management-key",
    });
    assert.ok(result.supported && result.usage.status === "ok");
    assert.equal(result.usage.planLabel, "Claude work (cached)");
    assert.equal(requests.length, 2);
    assert.equal(new Headers(requests[0].init?.headers).get("authorization"), "Bearer test-management-key");
    const apiCall = JSON.parse(String(requests[1].init?.body));
    assert.deepEqual(apiCall.header, { Authorization: "Bearer $TOKEN$", "anthropic-beta": "oauth-2025-04-20" });
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("Cliproxy provider aggregation keeps successful account limits when another account fails", async () => {
  const originalFetch = globalThis.fetch;
  const requests: string[] = [];
  globalThis.fetch = async (input, init) => {
    const url = String(input);
    requests.push(url);
    if (url.endsWith("/auth-files")) return new Response(JSON.stringify({ files: [
      { provider: "claude", auth_index: "account-1" },
      { provider: "claude", auth_index: "account-2" },
    ] }), { status: 200 });
    const body = JSON.parse(String(init?.body));
    if (body.auth_index === "account-2") return new Response(JSON.stringify({ status_code: 503, body: "{}" }), { status: 200 });
    return new Response(JSON.stringify({ status_code: 200, body: JSON.stringify({ limits: [
      { kind: "weekly_all", percent: 42, resets_at: "2026-09-12T10:00:00Z" },
    ] }) }), { status: 200 });
  };
  try {
    const result = await readCliproxyProviderUsage([
      { provider: "claude", authIndex: "account-1", label: "账号 1" },
      { provider: "claude", authIndex: "account-2", label: "账号 2" },
    ], { managementBaseUrl: "http://cliproxy.test/v0/management" });
    assert.ok(result.supported && result.usage.status === "ok");
    assert.equal(result.usage.planLabel, "Claude · Cliproxy · 1/2 accounts");
    assert.deepEqual(result.usage.windows, [
      { label: "账号 1 · Weekly limit", usedPercent: 42, resetsAt: "2026-09-12T10:00:00.000Z" },
    ]);
    assert.equal(requests.filter(url => url.endsWith("/auth-files")).length, 1);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("Antigravity gets a project before requesting the provider quota summary", async () => {
  const originalFetch = globalThis.fetch;
  const apiCalls: Array<Record<string, unknown>> = [];
  globalThis.fetch = async (input, init) => {
    const url = String(input);
    if (url.endsWith("/auth-files")) return new Response(JSON.stringify({ files: [{ provider: "antigravity", auth_index: "account-1" }] }), { status: 200 });
    const call = JSON.parse(String(init?.body));
    apiCalls.push(call);
    if (call.url.endsWith(":loadCodeAssist")) {
      return new Response(JSON.stringify({ status_code: 200, body: JSON.stringify({ cloudaicompanionProject: "project-1" }) }), { status: 200 });
    }
    return new Response(JSON.stringify({ status_code: 200, body: JSON.stringify({ groups: [{ displayName: "Gemini Models", buckets: [
      { window: "weekly", remainingFraction: 0.5, resetTime: "2026-09-12T10:00:00Z" },
    ] }] }) }), { status: 200 });
  };
  try {
    const result = await readCliproxyUsage({ provider: "antigravity", authIndex: "account-1", label: "Gemini · 账号 1" }, {
      managementBaseUrl: "http://cliproxy.test/v0/management",
    });
    assert.ok(result.supported && result.usage.status === "ok");
    assert.deepEqual(result.usage.windows, [
      { label: "Gemini Models: Weekly limit", usedPercent: 50, resetsAt: "2026-09-12T10:00:00.000Z" },
    ]);
    assert.equal(apiCalls.length, 2);
    assert.match(String(apiCalls[0].url), /daily-cloudcode-pa\.googleapis\.com\/v1internal:loadCodeAssist$/);
    assert.match(String(apiCalls[1].url), /daily-cloudcode-pa\.googleapis\.com\/v1internal:retrieveUserQuotaSummary$/);
    assert.deepEqual(JSON.parse(String(apiCalls[1].data)), { project: "project-1" });
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("Kimi reads the official coding-plan usage endpoint through Cliproxy", async () => {
  const originalFetch = globalThis.fetch;
  const apiCalls: Array<Record<string, unknown>> = [];
  globalThis.fetch = async (input, init) => {
    const url = String(input);
    if (url.endsWith("/auth-files")) return new Response(JSON.stringify({ files: [{ provider: "kimi", auth_index: "account-1" }] }), { status: 200 });
    const call = JSON.parse(String(init?.body));
    apiCalls.push(call);
    return new Response(JSON.stringify({ status_code: 200, body: JSON.stringify({
      usage: { limit: "100", used: "20", remaining: "80", resetTime: "2026-09-12T10:00:00Z" },
      limits: [],
    }) }), { status: 200 });
  };
  try {
    const result = await readCliproxyUsage({ provider: "kimi", authIndex: "account-1", label: "Kimi" }, {
      managementBaseUrl: "http://cliproxy.test/v0/management",
    });
    assert.ok(result.supported && result.usage.status === "ok");
    assert.deepEqual(result.usage.windows, [{ label: "Weekly limit", usedPercent: 20, resetsAt: "2026-09-12T10:00:00.000Z" }]);
    assert.equal(apiCalls.length, 1);
    assert.match(String(apiCalls[0].url), /^https:\/\/api\.kimi\.com\/coding\/v1\/usages$/);
    assert.deepEqual(apiCalls[0].header, { Authorization: "Bearer $TOKEN$" });
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("Codex reads the authenticated web usage endpoint through Cliproxy", async () => {
  const originalFetch = globalThis.fetch;
  const apiCalls: Array<Record<string, unknown>> = [];
  globalThis.fetch = async (input, init) => {
    const url = String(input);
    if (url.endsWith("/auth-files")) return new Response(JSON.stringify({ files: [{ provider: "codex", auth_index: "account-1" }] }), { status: 200 });
    const call = JSON.parse(String(init?.body));
    apiCalls.push(call);
    return new Response(JSON.stringify({ status_code: 200, body: JSON.stringify({
      plan_type: "pro",
      rate_limit: { primary_window: { used_percent: 20, limit_window_seconds: 18_000, reset_at: 1788951600 } },
    }) }), { status: 200 });
  };
  try {
    const result = await readCliproxyUsage({ provider: "codex", authIndex: "account-1", label: "Codex" }, {
      managementBaseUrl: "http://cliproxy.test/v0/management",
    });
    assert.ok(result.supported && result.usage.status === "ok");
    assert.deepEqual(result.usage.windows, [{ label: "5-hour limit", usedPercent: 20, resetsAt: "2026-09-09T11:00:00.000Z" }]);
    assert.equal(apiCalls.length, 1);
    assert.match(String(apiCalls[0].url), /^https:\/\/chatgpt\.com\/backend-api\/wham\/usage$/);
    assert.deepEqual(apiCalls[0].header, {
      Authorization: "Bearer $TOKEN$",
      "Content-Type": "application/json",
      "User-Agent": "codex_cli_rs/0.76.0",
    });
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("Cliproxy queries time out rather than leaving BB's usage refresh pending", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (_input, init) => new Promise<Response>((_resolve, reject) => {
    init?.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")), { once: true });
  });
  try {
    const result = await readCliproxyUsage({ provider: "claude", authIndex: "account-1" }, {
      managementBaseUrl: "http://cliproxy.test/v0/management",
      timeoutMs: 10,
    });
    assert.ok(result.supported && result.usage.status === "error");
    assert.match(result.usage.message, /timed out/);
  } finally {
    globalThis.fetch = originalFetch;
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
