import type { PublicAgentEvent } from "@workflo/contracts";

/**
 * The event bus is delivery, never truth.
 *
 * Invariant:
 *   - ledger commit succeeds + bus publish fails  → event is STILL recorded
 *     (consumers recover via replay)
 *   - bus publish + ledger insert fails           → must never happen
 *     (ledger.append commits BEFORE publish is attempted)
 *
 * The interface is transport-neutral: Redis/NATS/Kafka/WebSocket adapters can
 * implement it later without touching consumers.
 */

export interface DeliveryReport {
  delivered: number;
  failed: number;
  errors: Error[];
}

export type EventHandler = (event: PublicAgentEvent) => Promise<void> | void;

export interface DisposableSubscription {
  dispose(): Promise<void>;
}

export interface EventBus {
  publish(event: PublicAgentEvent): Promise<DeliveryReport>;
  subscribe(handler: EventHandler): Promise<DisposableSubscription>;
}

/** In-process bus for development and tests. */
export class InMemoryEventBus implements EventBus {
  private readonly handlers = new Set<EventHandler>();

  async subscribe(handler: EventHandler): Promise<DisposableSubscription> {
    this.handlers.add(handler);
    return {
      dispose: async () => {
        this.handlers.delete(handler);
      },
    };
  }

  async publish(event: PublicAgentEvent): Promise<DeliveryReport> {
    const results = await Promise.allSettled(
      [...this.handlers].map((handler) => Promise.resolve(handler(event))),
    );
    const errors = results
      .filter(
        (r): r is PromiseRejectedResult => r.status === "rejected",
      )
      .map((r) => (r.reason instanceof Error ? r.reason : new Error(String(r.reason))));
    return {
      delivered: results.length - errors.length,
      failed: errors.length,
      errors,
    };
  }

  get subscriberCount(): number {
    return this.handlers.size;
  }
}
