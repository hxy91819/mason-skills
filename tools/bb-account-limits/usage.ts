import { config } from "./config.js";
import { spawn } from "node:child_process";
import { readFile } from "node:fs/promises";
import { homedir } from "node:os";
import { stripVTControlCharacters } from "node:util";
import { createInterface } from "node:readline";
import { z } from "zod";
import { providerUsageResultSchema, withoutBridgeRuntimeEnv, type ProviderUsageResult } from "@get-bb/plugin-sdk/provider-bridge";

const windowSchema = z.object({
  usedPercent: z.number().finite().nonnegative(),
  windowDurationMins: z.number().positive().nullish(),
  resetsAt: z.number().finite().nonnegative().nullish(),
});
const bucketSchema = z.object({
  limitId: z.string().nullish(), limitName: z.string().nullish(), planType: z.string().nullish(),
  primary: windowSchema.nullish(), secondary: windowSchema.nullish(),
});
const limitsSchema = z.object({
  rateLimits: bucketSchema,
  rateLimitsByLimitId: z.record(z.string(), bucketSchema).nullish(),
});

export function usageError(message: string): ProviderUsageResult {
  return { supported: true, usage: { status: "error", message, planLabel: null, accountEmail: null } };
}

export function normalizeCodexLimits(raw: unknown): ProviderUsageResult {
  const result = limitsSchema.safeParse(raw);
  if (!result.success) return usageError("Codex returned an unrecognized account limits response.");
  const { rateLimits, rateLimitsByLimitId } = result.data;
  const buckets = rateLimitsByLimitId && Object.keys(rateLimitsByLimitId).length
    ? Object.entries(rateLimitsByLimitId) : [[rateLimits.limitId ?? "codex", rateLimits] as const];
  const windows = buckets.flatMap(([id, bucket]) => {
    const prefix = buckets.length > 1 ? `${bucket.limitName ?? id}: ` : "";
    return (["primary", "secondary"] as const).flatMap(key => {
      const value = bucket[key];
      if (!value) return [];
      const minutes = value.windowDurationMins;
      const label = minutes === 10080 ? "Weekly limit" : minutes === 300 ? "5-hour limit"
        : minutes ? `${minutes}-minute limit` : key === "primary" ? "Current limit" : "Secondary limit";
      const date = value.resetsAt == null ? null : new Date(value.resetsAt * 1000);
      return [{ label: prefix + label, usedPercent: Math.min(100, value.usedPercent), resetsAt: date && Number.isFinite(date.getTime()) ? date.toISOString() : null }];
    });
  });
  if (!windows.length) return usageError("This Codex account did not return subscription quota windows.");
  return { supported: true, usage: { status: "ok", accountEmail: null, planLabel: rateLimits.planType ?? null, windows } };
}

export function normalizeKiroUsage(raw: string): ProviderUsageResult {
  const text = stripVTControlCharacters(raw);
  if (/not logged in|please log in/i.test(text)) return { supported: true, usage: { status: "unauthenticated" } };
  if (/token.{0,30}expired|session.{0,30}expired/i.test(text)) return { supported: true, usage: { status: "expired" } };
  const heading = text.match(/Estimated Usage\s*\|\s*resets on (\d{4}-\d{2}-\d{2})\s*\|\s*([^\r\n]+)/);
  const credits = text.match(/Credits\s*\(([\d,.]+) of ([\d,.]+) covered in plan\)/);
  if (!heading || !credits) return usageError("Kiro returned an unrecognized /usage format; no quota estimate was made.");
  const used = Number(credits[1].replaceAll(",", ""));
  const limit = Number(credits[2].replaceAll(",", ""));
  const date = new Date(`${heading[1]}T00:00:00Z`);
  if (!Number.isFinite(used) || !Number.isFinite(limit) || limit <= 0 || !Number.isFinite(date.getTime()) || date.toISOString().slice(0, 10) !== heading[1]) {
    return usageError("Kiro returned invalid credit totals or a reset date.");
  }
  return { supported: true, usage: {
    status: "ok", accountEmail: null, planLabel: heading[2].trim(),
    // CLI 只提供重置日期；不把补充 credits 或超额计费混进套餐额度。
    windows: [{ label: `Plan credits (${used} / ${limit}); resets ${heading[1]}`, usedPercent: Math.min(100, used / limit * 100), resetsAt: null }],
  } };
}

export interface QueryOptions { timeoutMs?: number; signal?: AbortSignal; cwd?: string; }

export interface CliproxyUsageAccount {
  provider: string;
  authIndex?: string;
  account?: string;
  label?: string;
  cachedWindows?: Array<{
    label: string;
    usedPercentSignal: string;
    resetsAtSignal?: string;
    scale?: "fraction" | "percent";
  }>;
}

export interface CliproxyUsageOptions {
  managementBaseUrl: string;
  managementKey?: string;
  timeoutMs?: number;
  signal?: AbortSignal;
}

export function normalizeAgyUsage(raw: string): ProviderUsageResult {
  const text = stripVTControlCharacters(raw).trim();
  if (/not logged in|not logged into|please log in/i.test(text)) return { supported: true, usage: { status: "unauthenticated" } };
  if (/(?:token|session).{0,30}expired/i.test(text)) return { supported: true, usage: { status: "expired" } };
  const windows = [];
  for (const line of text.split(/\r?\n/)) {
    const cols = line.split("\t").map(value => value.trim());
    const [group, metric, remaining, reset] = cols;
    if (cols.length !== 4 || !group || !["Weekly Limit Remaining", "Five Hour Limit Remaining"].includes(metric)
      || !/^\d+(?:\.\d+)?%$/.test(remaining) || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(reset)) {
      return usageError("AGY returned an unrecognized /usage format; no quota estimate was made.");
    }
    const percent = Number(remaining.slice(0, -1));
    const date = new Date(reset);
    if (percent > 100 || !Number.isFinite(date.getTime()) || date.toISOString().replace(".000Z", "Z") !== reset) {
      return usageError("AGY returned invalid quota values or a reset timestamp.");
    }
    // AGY 返回剩余百分比，BB 的进度条需要已用百分比。
    windows.push({ label: `${group}: ${metric === "Weekly Limit Remaining" ? "Weekly limit" : "5-hour limit"}`,
      usedPercent: Number((100 - percent).toFixed(10)), resetsAt: date.toISOString() });
  }
  return { supported: true, usage: { status: "ok", accountEmail: null, planLabel: null, windows } };
}

export async function readAgyUsage(command = config.agy, options: QueryOptions = {}): Promise<ProviderUsageResult> {
  return runQuery(command, ["--print", "/usage"], options, (child, finish) => {
    let output = "";
    child.stdin.end();
    child.stdout.on("data", chunk => {
      if (output.length <= 128 * 1024) output += chunk.toString();
      if (output.length > 128 * 1024) finish(usageError("AGY usage output exceeded the size limit."));
    });
    // 启动日志可能在认证完成前声称未登录，不能据此覆盖最终额度结果。
    child.stderr.resume();
    return () => child.exitCode === 0 ? normalizeAgyUsage(output) : usageError("AGY account limits command failed; check the CLI login.");
  });
}

function spawnQuery(command: string, args: string[], options: QueryOptions) {
  return spawn(command, args, { cwd: options.cwd ?? homedir(), env: withoutBridgeRuntimeEnv(process.env), stdio: ["pipe", "pipe", "pipe"], detached: process.platform !== "win32" });
}

export async function readKiroUsage(command = config.kiro, options: QueryOptions = {}): Promise<ProviderUsageResult> {
  return runQuery(command, ["chat", "--no-interactive", "/usage"], options, (child, finish) => {
    let output = "";
    let diagnostic = "";
    child.stdin.end();
    child.stdout.on("data", chunk => {
      if (output.length <= 128 * 1024) output += chunk.toString();
      if (output.length > 128 * 1024) finish(usageError("Kiro usage output exceeded the size limit."));
    });
    child.stderr.on("data", chunk => { diagnostic = (diagnostic + chunk.toString()).slice(-8192); });
    return () => normalizeKiroUsage(output + "\n" + diagnostic);
  });
}

export async function readCodexUsage(command = config.codex, options: QueryOptions = {}): Promise<ProviderUsageResult> {
  return runQuery(command, ["app-server"], options, (child, finish) => {
    const lines = createInterface({ input: child.stdout });
    const send = (id: number, method: string, params?: unknown) => child.stdin.write(JSON.stringify({ id, method, ...(params === undefined ? {} : { params }) }) + "\n");
    let bytes = 0;
    child.stdout.on("data", chunk => { bytes += chunk.length; if (bytes > 1024 * 1024) finish(usageError("Codex account response exceeded the size limit.")); });
    child.stderr.resume();
    lines.on("line", line => {
      let message;
      try { message = JSON.parse(line); } catch { return; }
      if (!message || typeof message !== "object") return;
      if (message.error && [1, 2, 3].includes(message.id)) {
        const detail = String(message.error.message ?? "");
        if (/not authenticated|not logged in|requires.*auth/i.test(detail)) finish({ supported: true, usage: { status: "unauthenticated" } });
        else if (/expired|401/.test(detail)) finish({ supported: true, usage: { status: "expired" } });
        else finish(usageError("Codex account limits request failed."));
      } else if (message.id === 1 && message.result) {
        child.stdin.write(JSON.stringify({ method: "initialized" }) + "\n");
        send(2, "account/read", { refreshToken: false });
      } else if (message.id === 2 && message.result) {
        const account = message.result.account;
        if (!account) finish({ supported: true, usage: { status: "unauthenticated" } });
        else if (account.type === "apiKey" || account.type === "amazonBedrock") finish(usageError("This Codex login does not expose ChatGPT subscription limits."));
        else send(3, "account/rateLimits/read");
      } else if (message.id === 3 && message.result) {
        finish(normalizeCodexLimits(message.result));
      }
    });
    send(1, "initialize", { clientInfo: { name: "bb_account_limits", version: "0.1.0" } });
    return () => usageError("Codex exited before returning account limits.");
  });
}

type QueryChild = ReturnType<typeof spawnQuery>;
type SetupQuery = (child: QueryChild, finish: (result: ProviderUsageResult) => void) => () => ProviderUsageResult;

async function runQuery(command: string, args: string[], options: QueryOptions, setup: SetupQuery): Promise<ProviderUsageResult> {
  if (options.signal?.aborted) return usageError("Account limits query cancelled.");
  return new Promise(resolve => {
    const child = spawnQuery(command, args, options);
    let result: ProviderUsageResult | undefined;
    let closed = false;
    let stopping: ReturnType<typeof setTimeout> | undefined;
    const kill = (signal: NodeJS.Signals) => {
      try {
        if (process.platform !== "win32" && child.pid) process.kill(-child.pid, signal);
        else child.kill(signal);
      } catch { /* 子进程可能已在信号到达前退出。 */ }
    };
    const finish = (next: ProviderUsageResult) => {
      if (result || closed) return;
      result = next;
      child.stdin.end();
      // 先让共享 wrapper 正常退出并完成认证同步，超时才清理进程组。
      stopping = setTimeout(() => { kill("SIGTERM"); stopping = setTimeout(() => kill("SIGKILL"), 1000); }, 1000);
    };
    const timer = setTimeout(() => finish(usageError("Account limits query timed out.")), options.timeoutMs ?? 20000);
    const abort = () => finish(usageError("Account limits query cancelled."));
    options.signal?.addEventListener("abort", abort, { once: true });
    child.stdin.on("error", () => finish(usageError("Account limits process closed its input.")));
    child.on("error", error => finish((error as NodeJS.ErrnoException).code === "ENOENT" ? { supported: true, usage: { status: "not_installed" } } : usageError("Could not start account limits query.")));
    const onExit = setup(child, finish);
    child.on("close", () => {
      closed = true;
      clearTimeout(timer);
      clearTimeout(stopping);
      options.signal?.removeEventListener("abort", abort);
      resolve(providerUsageResultSchema.parse(result ?? onExit()));
    });
  });
}

type JsonRecord = Record<string, unknown>;

function asRecord(value: unknown): JsonRecord | null {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? value as JsonRecord : null;
}

function asString(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function usageLabel(account: CliproxyUsageAccount): string {
  return account.label ?? account.account ?? account.authIndex ?? account.provider;
}

function managementHeaders(key: string | undefined): HeadersInit {
  return key ? { authorization: `Bearer ${key}` } : {};
}

function parseReset(value: unknown): string | null {
  if (typeof value === "number" || (typeof value === "string" && /^\d+(?:\.\d+)?$/.test(value))) {
    const seconds = Number(value);
    const date = new Date(seconds * 1000);
    return Number.isFinite(date.getTime()) ? date.toISOString() : null;
  }
  if (typeof value !== "string") return null;
  const date = new Date(value);
  return Number.isFinite(date.getTime()) ? date.toISOString() : null;
}

function cliproxyRecordMatches(record: JsonRecord, account: CliproxyUsageAccount): boolean {
  if (String(record.provider ?? record.type ?? "").toLowerCase() !== account.provider.toLowerCase()) return false;
  if (account.authIndex) return record.auth_index === account.authIndex || record.authIndex === account.authIndex;
  const selected = account.account?.toLowerCase();
  if (!selected) return false;
  return [record.account, record.email, record.name, record.label]
    .some(value => typeof value === "string" && value.toLowerCase() === selected);
}

function getSelectedCliproxyRecord(raw: unknown, account: CliproxyUsageAccount): JsonRecord | ProviderUsageResult {
  const response = asRecord(raw);
  const files = response && Array.isArray(response.files) ? response.files.map(asRecord).filter((value): value is JsonRecord => value !== null) : [];
  const matches = files.filter(record => cliproxyRecordMatches(record, account));
  if (matches.length === 1) return matches[0];
  if (matches.length > 1) return usageError("Cliproxy account selector matches more than one credential; configure authIndex.");
  return usageError("Cliproxy account was not found; check the configured provider and selector.");
}

function isUsageResult(value: JsonRecord | ProviderUsageResult): value is ProviderUsageResult {
  return "supported" in value;
}

function hasOkUsage(result: ProviderUsageResult): boolean {
  return asRecord(result.usage)?.status === "ok";
}

function labelForClaudeLimit(limit: JsonRecord): string {
  const kind = asString(limit.kind) ?? asString(limit.group) ?? "quota";
  const labels: Record<string, string> = {
    session: "5-hour limit",
    weekly_all: "Weekly limit",
    weekly_scoped: "Weekly scoped limit",
  };
  return labels[kind] ?? kind.replaceAll("_", " ");
}

export function normalizeClaudeUsage(raw: unknown, account: CliproxyUsageAccount): ProviderUsageResult {
  const response = asRecord(raw);
  const limits = response && Array.isArray(response.limits) ? response.limits.map(asRecord).filter((value): value is JsonRecord => value !== null) : [];
  const windows = limits.flatMap(limit => {
    const usedPercent = Number(limit.percent);
    if (!Number.isFinite(usedPercent) || usedPercent < 0 || usedPercent > 100) return [];
    return [{ label: labelForClaudeLimit(limit), usedPercent, resetsAt: parseReset(limit.resets_at) }];
  });
  if (!windows.length) return usageError("Cliproxy returned an unrecognized Claude quota response.");
  return { supported: true, usage: { status: "ok", accountEmail: null, planLabel: usageLabel(account), windows } };
}

function cachedQuotaSignals(record: JsonRecord): JsonRecord[] {
  const sources: JsonRecord[] = [];
  const quota = asRecord(record.quota);
  if (quota) sources.push(quota);
  const modelQuotas = asRecord(record.model_quotas);
  if (modelQuotas) {
    for (const value of Object.values(modelQuotas)) {
      const source = asRecord(value);
      if (source) sources.push(source);
    }
  }
  return sources.sort((left, right) => {
    const leftTime = Date.parse(asString(left.observed_at) ?? "") || 0;
    const rightTime = Date.parse(asString(right.observed_at) ?? "") || 0;
    return rightTime - leftTime;
  });
}

function signalWindowLabel(segment: string): string {
  const labels: Record<string, string> = {
    "5h": "5-hour limit",
    "7d": "Weekly limit",
    "7d_oi": "Weekly Opus limit",
  };
  return labels[segment.toLowerCase()] ?? segment.replaceAll("_", " ");
}

function readCachedSignal(sources: JsonRecord[], signalName: string): unknown {
  for (const source of sources) {
    const signals = asRecord(source.signals);
    if (!signals) continue;
    const match = Object.entries(signals).find(([name]) => name.toLowerCase() === signalName.toLowerCase());
    if (match) return match[1];
  }
  return undefined;
}

function normalizeConfiguredCachedWindows(sources: JsonRecord[], account: CliproxyUsageAccount): ProviderUsageResult | null {
  if (!account.cachedWindows?.length) return null;
  const windows = account.cachedWindows.flatMap(window => {
    const sourceValue = Number(readCachedSignal(sources, window.usedPercentSignal));
    const usedPercent = window.scale === "fraction" ? sourceValue * 100 : sourceValue;
    if (!Number.isFinite(usedPercent) || usedPercent < 0 || usedPercent > 100) return [];
    return [{
      label: window.label,
      usedPercent,
      resetsAt: window.resetsAtSignal ? parseReset(readCachedSignal(sources, window.resetsAtSignal)) : null,
    }];
  });
  if (!windows.length) return usageError("Cliproxy has no cached quota signals matching this account's configured windows.");
  return { supported: true, usage: {
    status: "ok", accountEmail: null, planLabel: `${usageLabel(account)} (cached)`, windows,
  } };
}

export function normalizeCliproxyCachedUsage(raw: unknown, account: CliproxyUsageAccount): ProviderUsageResult {
  const record = asRecord(raw);
  if (!record) return usageError("Cliproxy returned an unrecognized credential record.");
  const sources = cachedQuotaSignals(record);
  const configured = normalizeConfiguredCachedWindows(sources, account);
  if (configured) return configured;
  const windows = new Map<string, { label: string; usedPercent: number; resetsAt: string | null }>();
  for (const source of sources) {
    const signals = asRecord(source.signals);
    if (!signals) continue;
    for (const [name, rawUtilization] of Object.entries(signals)) {
      const match = /^anthropic-ratelimit-unified-(.+)-utilization$/i.exec(name);
      if (!match) continue;
      const utilization = Number(rawUtilization);
      if (!Number.isFinite(utilization) || utilization < 0 || utilization > 1) continue;
      const segment = match[1].toLowerCase();
      if (windows.has(segment)) continue;
      const resetKey = name.replace(/-utilization$/i, "-reset");
      const resetValue = Object.entries(signals).find(([key]) => key.toLowerCase() === resetKey.toLowerCase())?.[1];
      windows.set(segment, {
        label: signalWindowLabel(segment),
        usedPercent: utilization * 100,
        resetsAt: parseReset(resetValue),
      });
    }
  }
  if (!windows.size) return usageError("Cliproxy has no cached quota signals for this account yet.");
  return { supported: true, usage: {
    status: "ok", accountEmail: null, planLabel: `${usageLabel(account)} (cached)`, windows: [...windows.values()],
  } };
}

async function readJson(response: Response): Promise<unknown> {
  try { return await response.json(); } catch { return null; }
}

async function fetchCliproxy(
  input: string,
  init: RequestInit,
  signal: AbortSignal | undefined,
  timeoutMs: number,
): Promise<Response> {
  if (signal?.aborted) throw new Error("cliproxy-query-cancelled");
  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => { timedOut = true; controller.abort(); }, timeoutMs);
  const abort = () => controller.abort();
  signal?.addEventListener("abort", abort, { once: true });
  try {
    return await fetch(input, { ...init, signal: controller.signal });
  } catch (error) {
    if (timedOut) throw new Error("cliproxy-query-timed-out");
    throw error;
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", abort);
  }
}

async function readClaudeUsageThroughCliproxy(
  managementBaseUrl: string,
  managementKey: string | undefined,
  authIndex: string,
  signal: AbortSignal | undefined,
  timeoutMs: number,
): Promise<{ status: number; body: unknown }> {
  const response = await fetchCliproxy(`${managementBaseUrl}/api-call`, {
    method: "POST",
    headers: { ...managementHeaders(managementKey), "content-type": "application/json" },
    body: JSON.stringify({
      auth_index: authIndex,
      method: "GET",
      url: "https://api.anthropic.com/api/oauth/usage",
      header: { Authorization: "Bearer $TOKEN$", "anthropic-beta": "oauth-2025-04-20" },
    }),
  }, signal, timeoutMs);
  const envelope = asRecord(await readJson(response));
  const status = typeof envelope?.status_code === "number" ? envelope.status_code : response.status;
  const body = typeof envelope?.body === "string" ? (() => { try { return JSON.parse(envelope.body); } catch { return null; } })() : envelope?.body;
  return { status, body };
}

/**
 * Query a selected credential via CLIProxyAPI's authenticated management API.
 * Claude uses the proxy's token substitution for a fresh official usage read;
 * cached rate-limit signals provide a read-only fallback when the upstream call
 * is temporarily unavailable.
 */
export async function readCliproxyUsage(account: CliproxyUsageAccount, options: CliproxyUsageOptions): Promise<ProviderUsageResult> {
  const managementBaseUrl = options.managementBaseUrl.replace(/\/$/, "");
  const timeoutMs = options.timeoutMs ?? 20_000;
  try {
    const response = await fetchCliproxy(`${managementBaseUrl}/auth-files`, {
      headers: managementHeaders(options.managementKey),
    }, options.signal, timeoutMs);
    if (!response.ok) return usageError(`Cliproxy credential query failed (${response.status}).`);
    const selected = getSelectedCliproxyRecord(await readJson(response), account);
    if (isUsageResult(selected)) return selected;
    const authIndex = asString(selected.auth_index) ?? asString(selected.authIndex);
    if (account.provider.toLowerCase() === "claude" && authIndex) {
      const upstream = await readClaudeUsageThroughCliproxy(managementBaseUrl, options.managementKey, authIndex, options.signal, timeoutMs);
      if (upstream.status >= 200 && upstream.status < 300) {
        const normalized = normalizeClaudeUsage(upstream.body, account);
        if (hasOkUsage(normalized)) return normalized;
      }
      const cached = normalizeCliproxyCachedUsage(selected, account);
      if (hasOkUsage(cached)) return cached;
      return usageError(`Cliproxy could not read Claude quota (${upstream.status}).`);
    }
    return normalizeCliproxyCachedUsage(selected, account);
  } catch (error) {
    if (options.signal?.aborted || (error as Error).message === "cliproxy-query-cancelled") return usageError("Cliproxy quota query cancelled.");
    if ((error as Error).message === "cliproxy-query-timed-out") return usageError("Cliproxy quota query timed out.");
    return usageError("Could not query Cliproxy quota.");
  }
}

export async function readCliproxyManagementKey(options: {
  managementKeyEnv?: string;
  managementKeyFile?: string;
}): Promise<string | undefined> {
  const fromEnv = options.managementKeyEnv ? process.env[options.managementKeyEnv]?.trim() : undefined;
  if (fromEnv) return fromEnv;
  if (!options.managementKeyFile) return undefined;
  try {
    const fromFile = (await readFile(options.managementKeyFile, "utf8")).trim();
    return fromFile || undefined;
  } catch {
    return undefined;
  }
}
