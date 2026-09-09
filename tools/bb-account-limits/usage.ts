import { cliproxyProviderDisplayName, config } from "./config.js";
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

function xaiPeriodLabel(value: unknown): string {
  const type = asString(value)?.toLowerCase() ?? "";
  if (type.includes("week")) return "Weekly limit";
  if (type.includes("month")) return "Monthly limit";
  return "Current period";
}

export function normalizeGrokUsage(raw: unknown, account: CliproxyUsageAccount): ProviderUsageResult {
  const response = asRecord(raw);
  const quota = response && asRecord(response.config);
  if (!quota) return usageError("Cliproxy returned an unrecognized Grok quota response.");
  const period = asRecord(quota.currentPeriod);
  const resetsAt = parseReset(period?.end ?? quota.billingPeriodEnd);
  const windows: Array<{ label: string; usedPercent: number; resetsAt: string | null }> = [];
  const periodUsage = Number(quota.creditUsagePercent);
  if (Number.isFinite(periodUsage) && periodUsage >= 0 && periodUsage <= 100) {
    windows.push({
      label: xaiPeriodLabel(period?.type),
      usedPercent: periodUsage,
      resetsAt,
    });
  }
  const products = Array.isArray(quota.productUsage) ? quota.productUsage.map(asRecord) : [];
  for (const product of products) {
    if (!product) continue;
    const name = asString(product.product);
    const usedPercent = Number(product.usagePercent);
    if (!name || !Number.isFinite(usedPercent) || usedPercent < 0 || usedPercent > 100) continue;
    windows.push({ label: name, usedPercent, resetsAt });
  }
  if (!windows.length) return usageError("Cliproxy returned no usable Grok quota windows.");
  return { supported: true, usage: { status: "ok", accountEmail: null, planLabel: usageLabel(account), windows } };
}

function antigravityBucketLabel(group: JsonRecord, bucket: JsonRecord): string {
  const groupLabel = asString(group.displayName) ?? "Antigravity";
  const window = asString(bucket.window)?.toLowerCase();
  const limitLabel = window === "weekly" ? "Weekly limit"
    : window === "5h" ? "5-hour limit"
      : (asString(bucket.displayName) ?? "Quota").replace(/\s+remaining$/i, "");
  return `${groupLabel}: ${limitLabel}`;
}

export function normalizeAntigravityUsage(raw: unknown, account: CliproxyUsageAccount): ProviderUsageResult {
  const response = asRecord(raw);
  const groups = response && Array.isArray(response.groups) ? response.groups.map(asRecord).filter((value): value is JsonRecord => value !== null) : [];
  const windows = groups.flatMap(group => {
    const buckets = Array.isArray(group.buckets) ? group.buckets.map(asRecord).filter((value): value is JsonRecord => value !== null) : [];
    return buckets.flatMap(bucket => {
      const remainingFraction = Number(bucket.remainingFraction);
      if (!Number.isFinite(remainingFraction) || remainingFraction < 0 || remainingFraction > 1) return [];
      return [{
        label: antigravityBucketLabel(group, bucket),
        usedPercent: Number(((1 - remainingFraction) * 100).toFixed(10)),
        resetsAt: parseReset(bucket.resetTime),
      }];
    });
  });
  if (!windows.length) return usageError("Cliproxy returned an unrecognized Antigravity quota response.");
  return { supported: true, usage: { status: "ok", accountEmail: null, planLabel: usageLabel(account), windows } };
}

function positiveNumber(value: unknown): number | null {
  const numeric = typeof value === "string" ? Number(value.replaceAll(",", "")) : Number(value);
  return Number.isFinite(numeric) && numeric > 0 ? numeric : null;
}

function kimiWindowLabel(raw: JsonRecord, fallback: string): string {
  const duration = positiveNumber(raw.duration);
  const unit = asString(raw.timeUnit)?.toLowerCase();
  if (unit === "time_unit_minute" && duration === 300) return "5-hour limit";
  if (unit === "time_unit_minute" && duration === 10080) return "Weekly limit";
  return unit === "time_unit_minute" && duration ? `${duration}-minute limit` : fallback;
}

function kimiUsageWindow(raw: JsonRecord, label: string): { label: string; usedPercent: number; resetsAt: string | null } | null {
  const limit = positiveNumber(raw.limit);
  const used = typeof raw.used === "string" ? Number(raw.used.replaceAll(",", "")) : Number(raw.used);
  if (!limit || !Number.isFinite(used) || used < 0 || used > limit) return null;
  return { label, usedPercent: Number((used / limit * 100).toFixed(10)), resetsAt: parseReset(raw.resetTime) };
}

export function normalizeKimiUsage(raw: unknown, account: CliproxyUsageAccount): ProviderUsageResult {
  const response = asRecord(raw);
  if (!response) return usageError("Cliproxy returned an unrecognized Kimi quota response.");
  const windows: Array<{ label: string; usedPercent: number; resetsAt: string | null }> = [];
  const weekly = asRecord(response.usage);
  if (weekly) {
    const window = kimiUsageWindow(weekly, "Weekly limit");
    if (window) windows.push(window);
  }
  const limits = Array.isArray(response.limits) ? response.limits.map(asRecord).filter((value): value is JsonRecord => value !== null) : [];
  for (const limit of limits) {
    const detail = asRecord(limit.detail);
    if (!detail) continue;
    const window = kimiUsageWindow(detail, kimiWindowLabel(asRecord(limit.window) ?? {}, "Current limit"));
    if (window) windows.push(window);
  }
  if (!windows.length) return usageError("Cliproxy returned an unrecognized Kimi quota response.");
  return { supported: true, usage: { status: "ok", accountEmail: null, planLabel: usageLabel(account), windows } };
}

function codexWhamWindowLabel(value: JsonRecord, fallback: string): string {
  const seconds = positiveNumber(value.limit_window_seconds);
  if (seconds === 18_000) return "5-hour limit";
  if (seconds === 604_800) return "Weekly limit";
  return seconds ? `${Math.round(seconds / 60)}-minute limit` : fallback;
}

function codexWhamWindows(raw: JsonRecord, prefix: string): Array<{ label: string; usedPercent: number; resetsAt: string | null }> {
  const windows: Array<{ label: string; usedPercent: number; resetsAt: string | null }> = [];
  for (const key of ["primary_window", "secondary_window"] as const) {
    const window = asRecord(raw[key]);
    if (!window) continue;
    const usedPercent = Number(window.used_percent);
    if (!Number.isFinite(usedPercent) || usedPercent < 0 || usedPercent > 100) continue;
    const label = codexWhamWindowLabel(window, key === "primary_window" ? "Current limit" : "Secondary limit");
    windows.push({ label: prefix ? `${prefix}: ${label}` : label, usedPercent, resetsAt: parseReset(window.reset_at) });
  }
  return windows;
}

export function normalizeCliproxyCodexUsage(raw: unknown, account: CliproxyUsageAccount): ProviderUsageResult {
  const response = asRecord(raw);
  const primary = response && asRecord(response.rate_limit);
  if (!response || !primary) return usageError("Cliproxy returned an unrecognized Codex quota response.");
  const windows = codexWhamWindows(primary, "");
  const additional = Array.isArray(response.additional_rate_limits) ? response.additional_rate_limits.map(asRecord).filter((value): value is JsonRecord => value !== null) : [];
  for (const limit of additional) {
    const label = asString(limit.limit_name) ?? asString(limit.metered_feature) ?? "Additional limit";
    const rateLimit = asRecord(limit.rate_limit);
    if (rateLimit) windows.push(...codexWhamWindows(rateLimit, label));
  }
  if (!windows.length) return usageError("Cliproxy returned an unrecognized Codex quota response.");
  return { supported: true, usage: { status: "ok", accountEmail: null, planLabel: asString(response.plan_type) ?? usageLabel(account), windows } };
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

interface CliproxyApiCall {
  method: string;
  url: string;
  header: Record<string, string>;
  data?: string;
}

async function callCliproxyApi(
  managementBaseUrl: string,
  managementKey: string | undefined,
  authIndex: string,
  request: CliproxyApiCall,
  signal: AbortSignal | undefined,
  timeoutMs: number,
): Promise<{ status: number; body: unknown }> {
  const response = await fetchCliproxy(`${managementBaseUrl}/api-call`, {
    method: "POST",
    headers: { ...managementHeaders(managementKey), "content-type": "application/json" },
    body: JSON.stringify({
      auth_index: authIndex,
      ...request,
    }),
  }, signal, timeoutMs);
  const envelope = asRecord(await readJson(response));
  const status = typeof envelope?.status_code === "number" ? envelope.status_code : response.status;
  const body = typeof envelope?.body === "string" ? (() => { try { return JSON.parse(envelope.body); } catch { return null; } })() : envelope?.body;
  return { status, body };
}

async function readClaudeUsageThroughCliproxy(
  managementBaseUrl: string,
  managementKey: string | undefined,
  authIndex: string,
  signal: AbortSignal | undefined,
  timeoutMs: number,
): Promise<{ status: number; body: unknown }> {
  return callCliproxyApi(managementBaseUrl, managementKey, authIndex, {
    method: "GET",
    url: "https://api.anthropic.com/api/oauth/usage",
    header: { Authorization: "Bearer $TOKEN$", "anthropic-beta": "oauth-2025-04-20" },
  }, signal, timeoutMs);
}

async function readGrokUsageThroughCliproxy(
  managementBaseUrl: string,
  managementKey: string | undefined,
  authIndex: string,
  signal: AbortSignal | undefined,
  timeoutMs: number,
): Promise<{ status: number; body: unknown }> {
  return callCliproxyApi(managementBaseUrl, managementKey, authIndex, {
    method: "GET",
    url: "https://cli-chat-proxy.grok.com/v1/billing?format=credits",
    header: {
      Authorization: "Bearer $TOKEN$",
      "x-xai-token-auth": "xai-grok-cli",
      "x-grok-client-version": "0.2.91",
      accept: "*/*",
      "user-agent": "grok-pager/0.2.91 grok-shell/0.2.91 (linux; x86_64)",
    },
  }, signal, timeoutMs);
}

async function readAntigravityUsageThroughCliproxy(
  managementBaseUrl: string,
  managementKey: string | undefined,
  authIndex: string,
  signal: AbortSignal | undefined,
  timeoutMs: number,
): Promise<{ status: number; body: unknown }> {
  const header = { Authorization: "Bearer $TOKEN$", Accept: "*/*", "Content-Type": "application/json", "User-Agent": "antigravity" };
  const load = await callCliproxyApi(managementBaseUrl, managementKey, authIndex, {
    method: "POST",
    url: "https://daily-cloudcode-pa.googleapis.com/v1internal:loadCodeAssist",
    header,
    data: JSON.stringify({ metadata: { ideType: "ANTIGRAVITY" } }),
  }, signal, timeoutMs);
  const project = asString(asRecord(load.body)?.cloudaicompanionProject);
  if (load.status < 200 || load.status >= 300 || !project) return { status: load.status, body: null };
  return callCliproxyApi(managementBaseUrl, managementKey, authIndex, {
    method: "POST",
    url: "https://daily-cloudcode-pa.googleapis.com/v1internal:retrieveUserQuotaSummary",
    header,
    data: JSON.stringify({ project }),
  }, signal, timeoutMs);
}

async function readKimiUsageThroughCliproxy(
  managementBaseUrl: string,
  managementKey: string | undefined,
  authIndex: string,
  signal: AbortSignal | undefined,
  timeoutMs: number,
): Promise<{ status: number; body: unknown }> {
  return callCliproxyApi(managementBaseUrl, managementKey, authIndex, {
    method: "GET",
    url: "https://api.kimi.com/coding/v1/usages",
    header: { Authorization: "Bearer $TOKEN$" },
  }, signal, timeoutMs);
}

async function readCodexUsageThroughCliproxy(
  managementBaseUrl: string,
  managementKey: string | undefined,
  authIndex: string,
  signal: AbortSignal | undefined,
  timeoutMs: number,
): Promise<{ status: number; body: unknown }> {
  return callCliproxyApi(managementBaseUrl, managementKey, authIndex, {
    method: "GET",
    url: "https://chatgpt.com/backend-api/wham/usage",
    header: {
      Authorization: "Bearer $TOKEN$",
      "Content-Type": "application/json",
      "User-Agent": "codex_cli_rs/0.76.0",
    },
  }, signal, timeoutMs);
}

async function readCliproxyAccountUsage(
  account: CliproxyUsageAccount,
  selected: JsonRecord,
  options: CliproxyUsageOptions,
): Promise<ProviderUsageResult> {
  const managementBaseUrl = options.managementBaseUrl.replace(/\/$/, "");
  const timeoutMs = options.timeoutMs ?? 20_000;
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
  if (account.provider.toLowerCase() === "xai" && authIndex) {
    const upstream = await readGrokUsageThroughCliproxy(managementBaseUrl, options.managementKey, authIndex, options.signal, timeoutMs);
    if (upstream.status >= 200 && upstream.status < 300) {
      const normalized = normalizeGrokUsage(upstream.body, account);
      if (hasOkUsage(normalized)) return normalized;
    }
    const cached = normalizeCliproxyCachedUsage(selected, account);
    if (hasOkUsage(cached)) return cached;
    return usageError(`Cliproxy could not read Grok quota (${upstream.status}).`);
  }
  if (account.provider.toLowerCase() === "antigravity" && authIndex) {
    const upstream = await readAntigravityUsageThroughCliproxy(managementBaseUrl, options.managementKey, authIndex, options.signal, timeoutMs);
    if (upstream.status >= 200 && upstream.status < 300) {
      const normalized = normalizeAntigravityUsage(upstream.body, account);
      if (hasOkUsage(normalized)) return normalized;
    }
    const cached = normalizeCliproxyCachedUsage(selected, account);
    if (hasOkUsage(cached)) return cached;
    return usageError(`Cliproxy could not read Antigravity quota (${upstream.status}).`);
  }
  if (account.provider.toLowerCase() === "kimi" && authIndex) {
    const upstream = await readKimiUsageThroughCliproxy(managementBaseUrl, options.managementKey, authIndex, options.signal, timeoutMs);
    if (upstream.status >= 200 && upstream.status < 300) {
      const normalized = normalizeKimiUsage(upstream.body, account);
      if (hasOkUsage(normalized)) return normalized;
    }
    const cached = normalizeCliproxyCachedUsage(selected, account);
    if (hasOkUsage(cached)) return cached;
    return usageError(`Cliproxy could not read Kimi quota (${upstream.status}).`);
  }
  if (account.provider.toLowerCase() === "codex" && authIndex) {
    const upstream = await readCodexUsageThroughCliproxy(managementBaseUrl, options.managementKey, authIndex, options.signal, timeoutMs);
    if (upstream.status >= 200 && upstream.status < 300) {
      const normalized = normalizeCliproxyCodexUsage(upstream.body, account);
      if (hasOkUsage(normalized)) return normalized;
    }
    const cached = normalizeCliproxyCachedUsage(selected, account);
    if (hasOkUsage(cached)) return cached;
    return usageError(`Cliproxy could not read Codex quota (${upstream.status}).`);
  }
  return normalizeCliproxyCachedUsage(selected, account);
}

function aggregateCliproxyUsage(
  accounts: readonly CliproxyUsageAccount[],
  results: readonly ProviderUsageResult[],
): ProviderUsageResult {
  const windows = results.flatMap((result, index) => {
    const usage = asRecord(result.usage);
    if (usage?.status !== "ok" || !Array.isArray(usage.windows)) return [];
    return usage.windows.flatMap(rawWindow => {
      const window = asRecord(rawWindow);
      if (!window) return [];
      const label = asString(window.label);
      const usedPercent = Number(window.usedPercent);
      if (!label || !Number.isFinite(usedPercent) || usedPercent < 0 || usedPercent > 100) return [];
      return [{
        label: `${usageLabel(accounts[index]!)} · ${label}`,
        usedPercent,
        resetsAt: typeof window.resetsAt === "string" ? window.resetsAt : null,
      }];
    });
  });
  if (!windows.length) return usageError("Cliproxy did not return quota data for any configured account.");
  const displayName = cliproxyProviderDisplayName(accounts[0]?.provider ?? "Cliproxy");
  const successful = results.filter(hasOkUsage).length;
  return {
    supported: true,
    usage: {
      status: "ok",
      accountEmail: null,
      planLabel: `${displayName} · Cliproxy · ${successful}/${accounts.length} accounts`,
      windows,
    },
  };
}

async function readCliproxyAuthFiles(options: CliproxyUsageOptions): Promise<unknown> {
  const managementBaseUrl = options.managementBaseUrl.replace(/\/$/, "");
  const response = await fetchCliproxy(`${managementBaseUrl}/auth-files`, {
    headers: managementHeaders(options.managementKey),
  }, options.signal, options.timeoutMs ?? 20_000);
  if (!response.ok) throw new Error(`cliproxy-credential-query-${response.status}`);
  return readJson(response);
}

function cliproxyQueryError(error: unknown, signal: AbortSignal | undefined): ProviderUsageResult {
  if (signal?.aborted || (error as Error).message === "cliproxy-query-cancelled") return usageError("Cliproxy quota query cancelled.");
  if ((error as Error).message === "cliproxy-query-timed-out") return usageError("Cliproxy quota query timed out.");
  const status = /^cliproxy-credential-query-(\d+)$/u.exec((error as Error).message)?.[1];
  if (status) return usageError(`Cliproxy credential query failed (${status}).`);
  return usageError("Could not query Cliproxy quota.");
}

/**
 * Query a selected credential via CLIProxyAPI's authenticated management API.
 * Claude uses the proxy's token substitution for a fresh official usage read;
 * cached rate-limit signals provide a read-only fallback when the upstream call
 * is temporarily unavailable.
 */
export async function readCliproxyUsage(account: CliproxyUsageAccount, options: CliproxyUsageOptions): Promise<ProviderUsageResult> {
  try {
    const selected = getSelectedCliproxyRecord(await readCliproxyAuthFiles(options), account);
    if (isUsageResult(selected)) return selected;
    return await readCliproxyAccountUsage(account, selected, options);
  } catch (error) {
    return cliproxyQueryError(error, options.signal);
  }
}

export async function readCliproxyProviderUsage(
  accounts: readonly CliproxyUsageAccount[],
  options: CliproxyUsageOptions,
): Promise<ProviderUsageResult> {
  if (!accounts.length) return usageError("Cliproxy provider has no configured accounts.");
  try {
    const authFiles = await readCliproxyAuthFiles(options);
    const results = await Promise.all(accounts.map(async account => {
      try {
        const selected = getSelectedCliproxyRecord(authFiles, account);
        return isUsageResult(selected)
          ? selected
          : await readCliproxyAccountUsage(account, selected, options);
      } catch (error) {
        return cliproxyQueryError(error, options.signal);
      }
    }));
    return aggregateCliproxyUsage(accounts, results);
  } catch (error) {
    return cliproxyQueryError(error, options.signal);
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
