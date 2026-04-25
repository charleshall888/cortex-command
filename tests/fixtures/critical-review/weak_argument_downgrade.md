# Plan: Fix incorrect tax calculation for cross-state shipping in checkout service

## Problem

The `CheckoutService.calculateTax()` function applies the buyer's billing-address state tax rate
to the entire order subtotal, including line items shipped to a different `ship_to` address. For
orders where `ship_to.state != billing_address.state`, this produces an incorrect tax amount on
the receipt. Customer support has logged 47 tickets in Q1 2026 from buyers disputing tax line
items on multi-address orders. The audit team confirmed the calculation is wrong against the
state-tax authority's published rules: tax must be computed using the destination state's rate,
not the billing state's rate.

## Proposed Fix

Update `CheckoutService.calculateTax()` to compute tax per-line-item using `line.ship_to.state`
instead of `order.billing_address.state`. The function already receives the full `Order` object
and each line carries its own `ship_to`, so no signature change is required.

```python
def calculateTax(order: Order) -> Decimal:
    total = Decimal("0.00")
    for line in order.lines:
        rate = TAX_RATES[line.ship_to.state]   # was: TAX_RATES[order.billing_address.state]
        total += line.subtotal * rate
    return total.quantize(Decimal("0.01"))
```

The `TAX_RATES` table is exhaustively keyed on every value of the `ShipToState` enum (50 states,
DC, all US territories, and APO/FPO codes); the type system guarantees `line.ship_to.state` is
always present in the table, so no KeyError is reachable. The function is the single callsite
for tax computation in the checkout flow (verified via `grep -r calculateTax src/`). The change
is wrapped in a unit test that asserts a two-line order with lines shipping to CA (7.25%) and OR
(0%) computes the correct per-line tax instead of applying the billing state's rate to both.

## Rationale

The bug is a single-line lookup error: the function uses the wrong field. Switching the lookup
to the destination state matches the published tax authority rules and resolves the customer
support tickets. The unit test pins the corrected behavior so future refactors cannot regress
it.

## Implementation Notes

- The change is to one file: `src/checkout/checkout_service.py`.
- One new unit test added: `tests/checkout/test_calculate_tax_multi_destination.py`.
- The change is forward-only: it applies to orders placed after the deploy. Historic orders
  remain on their original computed tax for audit-trail integrity, and refunds against historic
  orders continue to use the original tax line — the refund flow reads stored tax from the
  order record, not by re-invoking calculateTax(). This invariant is verified by the existing
  refund test suite (`tests/checkout/test_refund_flow.py::test_refund_uses_stored_tax`).
- The existing tax dashboard at `/internal/reports/tax-by-state` continues to aggregate by
  `billing_address.state` rather than `ship_to.state`. Updating the dashboard's grouping is
  deferred to a follow-up ticket — the dashboard is a finance-team reporting tool and reads
  from a separate aggregation pipeline (a nightly batch job over the `orders_archive` table),
  not from the live checkout path. The receipt sent to the buyer reflects the corrected
  per-line tax regardless of dashboard state.
- No changes to the receipt template or email confirmation — those already display the per-line
  tax breakdown as computed by `calculateTax()` and will reflect the corrected values
  automatically.
