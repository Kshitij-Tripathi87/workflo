import { z } from "zod";

export const uuidSchema = z.string().uuid();

export const orgIdSchema = uuidSchema;
export const projectIdSchema = uuidSchema;
export const userIdSchema = uuidSchema;
export const runIdSchema = uuidSchema;
export const eventIdSchema = uuidSchema;
export const receiptIdSchema = uuidSchema;

export type OrgId = z.infer<typeof orgIdSchema>;
export type ProjectId = z.infer<typeof projectIdSchema>;
export type UserId = z.infer<typeof userIdSchema>;
export type RunId = z.infer<typeof runIdSchema>;
export type EventId = z.infer<typeof eventIdSchema>;
export type ReceiptId = z.infer<typeof receiptIdSchema>;
