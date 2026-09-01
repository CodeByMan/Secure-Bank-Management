# Security Notes

Secure Bank Manager is a local educational prototype, not a production banking
system. It is designed to demonstrate defensive application patterns on a
single-process SQLite deployment.

## Secrets

Set distinct, random `SECRET_KEY` and `HMAC_SECRET_KEY` values in `.env`. The
application rejects missing, short, default, or identical values outside test
mode. Never commit `.env`, database files, or generated credentials.

## Audit-chain scope

Audit events are linked by sequence, previous hash, SHA-256 content hash, and
HMAC-SHA256 signature. Verification detects modified events and missing
interior sequence numbers while the HMAC key remains secret. Local anchors are
stored in the same database and therefore are not independent evidence.

Without an external, independently retained anchor, complete database
deletion, tail truncation, and post-compromise rewriting may not be detectable.

## Deployment scope

Use the supplied Docker Compose configuration only for bounded local use. It
binds to host loopback and runs one Gunicorn worker because SQLite writes are
serialized. Use HTTPS, secure cookies, external rate-limit storage, migrations,
backups, monitoring, and an independent audit anchor before any real deployment.
