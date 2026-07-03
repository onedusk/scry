# API Change Impact Report -- June 2026

> Generated: 2026-06-15T12:00:00+00:00
> diode API version: 2026-04
> Next shopify version: 2026-07
> scry version: 0.1.0-golden

## Summary

6 changes detected, 3 affect diode, 3 require action before 2026-07-01.

## Action Required

### [CRITICAL] Product.barcode

- **Source**: schema diff
- **Deadline**: N/A
- **Affected files**: app/routes/products.ts
- **Affected features**: barcode-sync
- **What changed**: Field Product.barcode was removed.
- **Suggested action**: Review required

### [HIGH] productVariantsBulkUpdate input change

- **Source**: https://shopify.dev/changelog/variants-bulk-update
- **Deadline**: N/A
- **Affected files**: app/routes/products.ts
- **Affected features**: barcode-sync
- **What changed**: The variants argument now requires an explicit sku field.
- **Suggested action**: Add sku field to all productVariantsBulkUpdate calls.

### [HIGH] SubscriptionContract

- **Source**: schema diff
- **Deadline**: N/A
- **Affected files**: None identified
- **Affected features**: None identified
- **What changed**: Type SubscriptionContract was removed.
- **Suggested action**: Review required

## Deprecation Tracker

| Field/Feature | Deprecated In | Removed In | Project Uses? | Status |
|---|---|---|---|---|
| Products barcode field deprecation | Unknown | 2026-07-01 | Yes | MEDIUM |

## SDK Updates

| Package | Current | Latest | Type | Notes |
|---|---|---|---|---|
| @shopify/polaris | ^12.0.0 | 13.1.0 | major | Package @shopify/polaris has a newer version available. |

## Informational

- New webhook payload field: orders/create webhook now includes fulfillment_status.
- @shopify/polaris: ^12.0.0 → 13.1.0: Package @shopify/polaris has a newer version available.
