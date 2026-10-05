import {
  accountLimitsPanelSnapshotSchema,
  type AccountLimitsPanelReadInput,
  type AccountLimitsPanelSnapshot,
  type AccountLimitsReadInput,
  type CliproxyAccountUsageEntry,
} from "./contract.js";
import type { UsageMeasurement, UsageResourceList } from "./usage-source-contract.js";

type PanelMachine = AccountLimitsPanelSnapshot["machines"][number];
type PanelProvider = PanelMachine["providers"][number];

const MACHINE_ID = "source:account-pool";
const providerId = (id: string) => `account-pool:${id}`;
const providerName = (id: string) => ({ "claude-code": "Claude", codex: "Codex" })[id] ?? id;

function accountUsage(measurement: UsageMeasurement): CliproxyAccountUsageEntry["usage"] {
  const usage = measurement.usage;
  if (usage.status !== "ok") {
    return usage.status === "error" ? { status: "error", message: usage.message } : { status: usage.status };
  }
  return {
    status: "ok",
    planLabel: usage.planLabel,
    windows: usage.windows.map(window => ({
      id: JSON.stringify([window.kind, window.id, window.model]),
      label: window.model && !window.label.includes(window.model) ? `${window.label} · ${window.model}` : window.label,
      usedPercent: Math.min(100, window.usedPercent),
      resetsAt: window.resetsAt,
    })),
  };
}

function panelProvider(id: string, accounts: CliproxyAccountUsageEntry[]): PanelProvider {
  const healthy = accounts.filter(account => account.usage.status === "ok");
  const observations = healthy.flatMap(account => account.updatedAt ? [account.updatedAt] : []);
  return {
    id: providerId(id),
    displayName: providerName(id),
    updatedAt: observations.sort()[0] ?? null,
    accounts,
    usage: healthy.length === 0
      ? { status: "error", message: "该供应商的全部账号额度查询均失败。" }
      : {
          status: "ok",
          planLabel: `${healthy.length}/${accounts.length} accounts`,
          windows: healthy.flatMap(account => account.usage.status === "ok"
            ? account.usage.windows.map(window => ({ label: window.label, usedPercent: window.usedPercent, resetsAt: window.resetsAt, accountLabel: account.label }))
            : []),
        },
  };
}

export interface AccountPoolPanelDependencies {
  listResources(): Promise<UsageResourceList>;
  getResource(resourceId: string, refresh: boolean): Promise<UsageMeasurement>;
}

/** Only consumes public provider-usage.v1 RPCs. Account Pooler owns its cache and credentials. */
export function createAccountPoolPanelReader(deps: AccountPoolPanelDependencies) {
  const previous = new Map<string, CliproxyAccountUsageEntry>();
  let lastMachine: PanelMachine | null = null;
  return async (input: AccountLimitsPanelReadInput): Promise<AccountLimitsPanelSnapshot> => {
    try {
      const inventory = await deps.listResources();
      const liveIds = new Set(inventory.resources.map(resource => resource.id));
      for (const id of previous.keys()) if (!liveIds.has(id)) previous.delete(id);
      const entries: Array<{ provider: string; account: CliproxyAccountUsageEntry }> = [];
      // Bound RPC concurrency; a failed account must not hide other accounts.
      for (let offset = 0; offset < inventory.resources.length; offset += 3) {
        entries.push(...await Promise.all(inventory.resources.slice(offset, offset + 3).map(async resource => {
          const selected = !input.providerIds || input.providerIds.includes(providerId(resource.providerId));
          const cached = previous.get(resource.id);
          if (!selected && cached) return { provider: resource.providerId, account: cached };
          let account: CliproxyAccountUsageEntry;
          try {
            // Unselected resources without a previous observation remain unqueried.
            if (!selected) {
              account = { key: resource.id, label: resource.label, weight: 1, updatedAt: null,
                usage: { status: "error", message: "此账号额度尚未读取。" } };
            } else {
              const measurement = await deps.getResource(resource.id, input.force === true);
              account = {
                key: resource.id, label: measurement.usage.accountEmail ?? resource.label, weight: 1,
                updatedAt: measurement.observedAt === null ? null : new Date(measurement.observedAt).toISOString(),
                usage: accountUsage(measurement),
              };
            }
          } catch {
            account = { key: resource.id, label: resource.label, weight: 1, updatedAt: null,
              usage: { status: "error", message: "读取此账号的 Account Pooler 额度失败，请重试。" } };
          }
          previous.set(resource.id, account);
          return { provider: resource.providerId, account };
        })));
      }
      const groups = new Map<string, CliproxyAccountUsageEntry[]>();
      for (const entry of entries) {
        const group = groups.get(entry.provider) ?? [];
        group.push(entry.account);
        groups.set(entry.provider, group);
      }
      const snapshot = accountLimitsPanelSnapshotSchema.parse({ machines: [{
        id: MACHINE_ID, displayName: "Account Pooler", source: "account-pool", status: "connected",
        providers: [...groups].map(([id, accounts]) => panelProvider(id, accounts)), error: null,
      }] });
      lastMachine = snapshot.machines[0]!;
      return snapshot;
    } catch {
      return { machines: [{
        ...(lastMachine ?? { id: MACHINE_ID, displayName: "Account Pooler", source: "account-pool", providers: [] }),
        status: lastMachine ? "connected" : "error",
        error: lastMachine
          ? "Account Pooler 暂时不可用，正在显示上次读取的额度。"
          : "Account Pooler 未启用或暂时不可用，无法读取其账号额度。",
      }] };
    }
  };
}

/** Source-specific refresh never calls the other source. The page merges the returned source snapshot. */
export function createAccountLimitsReader(
  cliproxy: (input: AccountLimitsPanelReadInput) => Promise<AccountLimitsPanelSnapshot>,
  accountPool: (input: AccountLimitsPanelReadInput) => Promise<AccountLimitsPanelSnapshot>,
) {
  return async ({ source, ...input }: AccountLimitsReadInput): Promise<AccountLimitsPanelSnapshot> => {
    const readers = source === "cliproxy" ? [cliproxy] : source === "account-pool" ? [accountPool] : [cliproxy, accountPool];
    const results = await Promise.allSettled(readers.map(reader => reader(input)));
    const machines = results.flatMap((result, index): PanelMachine[] => {
      if (result.status === "fulfilled") return result.value.machines;
      const failedSource = source ?? (index === 0 ? "cliproxy" : "account-pool");
      return [{ id: `source:${failedSource}`, displayName: failedSource === "account-pool" ? "Account Pooler" : "Cliproxy",
        source: failedSource, status: "error", providers: [], error: "读取此来源的额度失败，请重试。" }];
    });
    return accountLimitsPanelSnapshotSchema.parse({ machines });
  };
}
