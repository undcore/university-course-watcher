# Telegram delivery recovery

Candidate deliveries are recorded in a durable outbox before the Telegram request. A confirmed Telegram receipt is reused to repair notification state after a process interruption without sending the same candidate again.

If a request was sent but its response was lost, the outbox blocks automatic retry because Telegram does not support idempotency keys or sent-message lookup. Inspect unresolved entries and resolve each one after checking the chat:

```bash
python scripts/resolve_delivery.py --watch course
python scripts/resolve_delivery.py --watch course --delivery-id <sha256> --outcome delivered
python scripts/resolve_delivery.py --watch course --delivery-id <sha256> --outcome retry
python scripts/resolve_delivery.py --watch graduate
```

The inspection output includes the stable logical key, a short public-notice message preview, and the last update time so the entry can be matched to the Telegram chat. Use `delivered` when that message exists in Telegram. Use `retry` only after confirming that it does not exist.
Commit and push the changed outbox JSON to `main` before rerunning the workflow so the runner receives the resolution.
