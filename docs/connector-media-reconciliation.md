# GEN-158: staged Connector media orphan reconciliation

The native `Message.attachment` is still the source of truth. PostgreSQL
transactions cannot atomically commit S3/local-storage file writes. A
`message.media.ready` upload that writes bytes but then loses its outer
PostgreSQL commit may leave a storage object with no Message reference.

Only **new, feature-gated** lifecycle files are saved under:
`organizations/<organization-public-id>/connector-media/<message-id>/<random-id>.<ext>`.

Legacy Connector M1, native VK, outbound uploads and voice are still under their
unchanged paths. No provider media URL or token is used in the namespace.

## Dry run and controlled cleanup

From the backend environment, after DB migration 0053:

```bash
python manage.py reconcile_connector_media --organization-id 123
python manage.py reconcile_connector_media --organization-id 123 --older-than-hours 24 --max-files 1000 --delete
```

- **Dry-run by default.** Nothing deletes files unless `--delete` is passed.
- Only scans the current *active* storage backend, within one explicitly named
  tenant, and only the new `connector-media` directory.
- Filename pattern must match a generated 32-character hex name with the
  current JPEG/PNG/PDF suffix.
- Files younger than 24 hours are protected by default. Minimum age is 1 hour,
  explicitly configured by the operator.
- Any attachment referenced by a Message is protected, regardless of status.
- Scans are bounded by `--max-files`; truncated reports must not be treated
  as complete.
- Reports aggregate counts only, not provider IDs or sensitive paths.
- Secondary fallback storage after an S3/local migration is **not** scanned;
  run appropriate storage migration/reconciliation procedures separately.
- Do not schedule automatic `--delete` until the Lab E2E and failure-recovery
  tests have been reviewed; start with periodic read-only scans.

The cleanup is intentionally conservative and idempotent. A late rollback
orphan is only safe to delete after the grace period. For crash/retry and
concurrent provider events, maintain the original idempotency contract and
verify the adapter can replay the same ready event ID.
