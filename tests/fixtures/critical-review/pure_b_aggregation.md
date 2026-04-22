# Plan: Migrate Order Ingestion to Event-Driven Processing

## Problem

The current order ingestion pipeline polls the `orders` table every 30 seconds for rows with
`status = 'pending'`. Under high load this produces lock contention on the table and a 30-second
worst-case latency spike visible to downstream fulfillment services. During Black Friday 2024 the
poller held a table-level advisory lock for 14 seconds, starving concurrent reads.

## Proposed Change

Replace the polling loop with an event-driven path:

1. A `BEFORE INSERT` trigger on the `orders` table publishes a `order.created` event to the
   `orders-inbound` Kafka topic (partition key: `tenant_id`).
2. The ingestion service subscribes to `orders-inbound` and processes each event exactly once using
   Kafka consumer group `ingestion-v2` with `enable.auto.commit=false` and manual `commitSync()`
   after each successful write to the downstream `order_items` table.
3. The legacy poller (`OrderPollingService`) is deleted. Its `@Scheduled(fixedDelay=30_000)` bean
   is removed from the Spring context.
4. A new `DeadLetterQueueHandler` consumes the `orders-inbound-dlq` topic and logs failed events
   for operator review. Retry logic: three attempts with exponential backoff (1 s, 4 s, 16 s) before
   routing to DLQ.

## Why This Fix Is Correct

The trigger-based publish is atomic with the INSERT — no polling window, no lock contention. Kafka
provides durable delivery with offset tracking; `commitSync()` after each downstream write gives
exactly-once semantics for the happy path. The DLQ handler gives operators visibility into
persistent failures without blocking the primary consumer. The poller deletion eliminates the lock
contention root cause entirely.

## Implementation Scope

The following changes are in scope for this plan:

- `db/migrations/V42__add_order_created_trigger.sql` — BEFORE INSERT trigger definition
- `src/main/kotlin/ingestion/KafkaConsumerConfig.kt` — consumer group configuration
- `src/main/kotlin/ingestion/OrderEventConsumer.kt` — new event-driven consumer
- `src/main/kotlin/ingestion/DeadLetterQueueHandler.kt` — DLQ consumer
- `src/main/kotlin/scheduling/OrderPollingService.kt` — **deleted**
- `src/test/kotlin/ingestion/OrderEventConsumerTest.kt` — happy-path and DLQ-routing unit tests

## Out of Scope

The following are explicitly deferred and will be addressed in follow-up work:

- Backfilling orders that arrived during the migration window
- Monitoring dashboards for consumer lag
- The existing `POST /internal/orders/reprocess` admin endpoint used by the operations team to
  manually re-trigger stalled orders
