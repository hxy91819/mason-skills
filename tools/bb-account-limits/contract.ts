import { defineRpcContract } from "@get-bb/plugin-sdk";
import { z } from "zod";

const emptyInputSchema = z.object({}).strict();

const quotaWindowSchema = z.object({
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

export const cliproxyUsageSnapshotSchema = z.object({
  providers: z.array(z.object({
    id: z.string().min(1),
    displayName: z.string().min(1),
    usage: quotaUsageSchema,
  }).strict()),
}).strict();

export type CliproxyUsageSnapshot = z.infer<typeof cliproxyUsageSnapshotSchema>;

export const accountLimitsHostContract = defineRpcContract({
  readCliproxyUsage: {
    input: emptyInputSchema,
    output: cliproxyUsageSnapshotSchema,
  },
});

export const accountLimitsPanelSnapshotSchema = z.object({
  machines: z.array(z.object({
    id: z.string().min(1),
    displayName: z.string().min(1),
    status: z.enum(["connected", "disconnected", "error"]),
    providers: cliproxyUsageSnapshotSchema.shape.providers,
    error: z.string().min(1).nullable(),
  }).strict()),
}).strict();

export type AccountLimitsPanelSnapshot = z.infer<typeof accountLimitsPanelSnapshotSchema>;

export const accountLimitsPanelRpcContract = defineRpcContract({
  readCliproxyUsage: {
    input: emptyInputSchema,
    output: accountLimitsPanelSnapshotSchema,
  },
});
