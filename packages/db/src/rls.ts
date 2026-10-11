import { orgIdSchema, userIdSchema } from "@workflo/contracts";

/**
 * Transaction-scoped tenant context.
 *
 * RLS policies read these GUCs via current_setting(..., true).
 * Missing org context fails closed (policy expression evaluates NULL).
 */
export const TenantGuc = {
  OrgId: "app.current_org_id",
  UserId: "app.current_user_id",
} as const;

export interface TenantContext {
  readonly orgId: string;
  readonly userId?: string | undefined;
}

export function parseTenantContext(input: TenantContext): TenantContext {
  return {
    orgId: orgIdSchema.parse(input.orgId),
    ...(input.userId ? { userId: userIdSchema.parse(input.userId) } : {}),
  };
}
