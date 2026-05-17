# Repository Agent Instructions

## Development Attempt Logging

For every crawler development task, site-access experiment, parser fix, request
variant test, DB/S3 operation test, or retry intended to bypass a collection
failure, update the relevant channel development log before finishing.

Default log path:

```text
{retailer}_dev_log/{YYYYMMDD}_{retailer}_{product_type}_tests.md
```

Examples:

```text
lowes_dev_log/20260517_lowes_ldy_tests.md
bestbuy_dev_log/20260517_bestbuy_hhp_tests.md
```

Each entry must include:

- local time and timezone
- target channel, product type, step, and run root
- command or code path used
- key environment variables and request conditions
- request variant, browser/API mode, proxy/header/cookie settings when relevant
- result: success/failure, status code, row counts, elapsed time, and error body
- raw artifacts and manifests created
- code files changed
- interpretation and next recommended action

If a run fails due to sandboxing, network approval, timeout, anti-bot, response
size, parser mismatch, DB schema, or S3 access, record that cause explicitly.

Do not store secrets in the dev log. Redact API keys, passwords, database URLs,
session cookies, and authorization headers.

Runtime scripts should still write their own per-run logs under:

```text
{retailer}/data/{product_type}/{YYYYMMDD}/{subject}/logs/run.log
```

The development log is the human audit trail for why we tried something and
what we learned. The per-run log is the machine/runtime trace.
