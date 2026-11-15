# Changelog

All notable changes to this package are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the package uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.1] – 2026-11-15

- `links.list` uses the `data_room_id` filter (`room_id` still accepted by the API but deprecated); date filters accept a date or date-time.
- Webhook endpoint deliveries can be paged (`page`, `limit`, `total`, `next_page`).
- `disabled_reason` on webhook endpoints may be `null`.
- Data room guest details use a named schema; removing guests or documents requires a body.

## [0.1.0] – 2026-11-15

First release, generated from HelpRange API spec version 2026-11-15 (not published yet; this entry describes
everything that will ship in it).

### Added

- Client with every REST API v2 endpoint, grouped by tag: account, folders, documents, links, triggers, data rooms,
  NDAs, e-signature, offers, store, lead forms, activity, webhook endpoints.
- Data rooms end to end: `data_rooms.create` (with folders and NDA settings), `update`, `delete(confirm=True)`;
  sub-resources `data_rooms.guests` (`list`, `invite`, `remove`), `data_rooms.documents` (`list`, `add`, `remove`,
  `move`), `data_rooms.folders`, `data_rooms.questions`, `data_rooms.request_items`, `data_rooms.access_requests`,
  `data_rooms.signature_requests`; `ndas.list`.
- `links.list` (every share link of the team, with filters and pagination) and `links.views` (the views of one link).
- `webhook_endpoints`: `list`, `create`, `get`, `update`, `delete`, `rotate_secret`, `send_test`, `deliveries`,
  `redeliver`.
- Typed request and response models for every endpoint.
- `share()` – upload a file and create a share link in one call.
- Automatic `Idempotency-Key` (UUID v4) on every POST / PATCH, reused across retries; `idempotency_key=` on every
  POST / PATCH method (or `request_options={"idempotency_key": …}`) to set your own.
- Retries with backoff on 429 (any method, honouring Retry-After), on 408/5xx/connection errors/timeouts (GET and
  keyed POST / PATCH) and on 409 `idempotency_key_in_progress` (up to 5 extra attempts).
- Typed errors with status, code and body (incl. `IdempotencyKeyInProgressError`, `UnprocessableEntityError`,
  `IdempotencyKeyReusedError`); test-mode (`hr_test_`) detection; rate-limit headers after each response.
- Webhook signature verification (`HelpRange-Signature`, v1 scheme, rotation-aware) and a signing helper for tests.
- Sync (`HelpRange`) and async (`AsyncHelpRange`) clients.
- `helprange` command-line tool: login, whoami, share, documents, `links` (all links, filters `--document`
  `--folder` `--room` `--status` `--label`), `views --link LINK_ID` / `views DOCUMENT_ID`, `rooms create NAME
  [--folder …] [--nda] [--invite EMAIL …]`, `rooms delete ID --yes`, rooms list/show/index/documents/guests/add/
  invite/questions; `--json` output everywhere.
