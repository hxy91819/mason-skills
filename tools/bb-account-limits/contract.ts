import { defineRpcContract } from "@get-bb/plugin-sdk";
import { z } from "zod";

const providerIdsSchema = z.array(z.string().min(1)).min(1).max(64);

const quotaWindowSchema = z.object({
  accountLabel: z.string().min(1).nullable(),
  label: z.string().min(1),
  usedPercent: z.number().finite().min(0).max(100),
  resetsAt: z.string().datetime().nullable(),
}).strict();

const quotaUsageSchema = z.discriminatedUnion("status", [
  z.object({ status: z.literal("ok"), planLabel: z.string().nullable(), windows: z.array(quotaWindowSchema) }).strict(),
  z.object({ status: z.literal("unauthenticated") }).strict(),
  z.object({ status: z.literal("expired") }).strict(),
  z.object({ status: z.literal("not_installed") }).strict(),
  z.object({ status: z.literal("error"), message: z.string().min(1) }).strict(),
]);

const accountQuotaWindowSchema = z.object({
  // 外部来源提供的窗口身份，避免同名模型窗口在池聚合时混合。
  id: z.string().min(1).optional(),
  label: z.string().min(1),
  usedPercent: z.number().finite().min(0).max(100),
  resetsAt: z.string().datetime().nullable(),
}).strict();

const accountQuotaUsageSchema = z.discriminatedUnion("status", [
  z.object({ status: z.literal("ok"), planLabel: z.string().nullable(), windows: z.array(accountQuotaWindowSchema) }).strict(),
  z.object({ status: z.literal("unauthenticated") }).strict(),
  z.object({ status: z.literal("expired") }).strict(),
  z.object({ status: z.literal("not_installed") }).strict(),
  z.object({ status: z.literal("error"), message: z.string().min(1) }).strict(),
]);

// key 是 authIndex 的 sha256 前 16 位（host 侧计算），稳定且不含凭据；weight 供池聚合加权。
const cliproxyAccountUsageSchema = z.object({
  key: z.string().min(1),
  label: z.string().min(1),
  weight: z.number().finite().positive(),
  updatedAt: z.string().datetime().nullable().optional(),
  usage: accountQuotaUsageSchema,
}).strict();

export type CliproxyAccountUsageEntry = z.infer<typeof cliproxyAccountUsageSchema>;

export const cliproxyUsageSnapshotSchema = z.object({
  providers: z.array(z.object({
    id: z.string().min(1),
    displayName: z.string().min(1),
    usage: quotaUsageSchema,
    accounts: z.array(cliproxyAccountUsageSchema),
  }).strict()),
}).strict();

export type CliproxyUsageSnapshot = z.infer<typeof cliproxyUsageSnapshotSchema>;

export const accountLimitsHostContract = defineRpcContract({
  readCliproxyUsage: {
    input: z.object({ providerIds: providerIdsSchema.optional() }).strict(),
    output: cliproxyUsageSnapshotSchema,
  },
});

const panelProviderSchema = z.object({
  id: z.string().min(1),
  displayName: z.string().min(1),
  usage: quotaUsageSchema,
  accounts: z.array(cliproxyAccountUsageSchema),
  updatedAt: z.string().datetime().nullable(),
}).strict();

export const accountLimitsPanelSnapshotSchema = z.object({
  machines: z.array(z.object({
    id: z.string().min(1),
    displayName: z.string().min(1),
    source: z.enum(["cliproxy", "account-pool"]).optional(),
    status: z.enum(["connected", "disconnected", "error"]),
    providers: z.array(panelProviderSchema),
    error: z.string().min(1).nullable(),
  }).strict()),
}).strict();

export type AccountLimitsPanelSnapshot = z.infer<typeof accountLimitsPanelSnapshotSchema>;

export const accountLimitsPanelReadInputSchema = z.object({
  providerIds: providerIdsSchema.optional(),
  force: z.boolean().optional(),
}).strict();

export type AccountLimitsPanelReadInput = z.infer<typeof accountLimitsPanelReadInputSchema>;

export const accountLimitsReadInputSchema = accountLimitsPanelReadInputSchema.extend({
  source: z.enum(["cliproxy", "account-pool"]).optional(),
});
export type AccountLimitsReadInput = z.infer<typeof accountLimitsReadInputSchema>;

export const accountLimitsPanelRpcContract = defineRpcContract({
  readAccountLimits: {
    input: accountLimitsReadInputSchema,
    output: accountLimitsPanelSnapshotSchema,
  },
  readCliproxyUsage: {
    input: accountLimitsPanelReadInputSchema,
    output: accountLimitsPanelSnapshotSchema,
  },
});
