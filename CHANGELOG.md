# Changelog

All notable changes to this project. Newest first.

## [0.4.1] - 2026-11-16

### Added
- Browser-tab icon (`webui/favicon.svg`; replace the file to use your own).
- Optional `ADMIN_USER`, `ADMIN_PASSWORD` and `CHILD_NAME` in `.env` create the parent account at first start, so the Register page can be skipped.

## [0.4.0] - 2026-11-16

First public release.

### Added
- **Register page.** The first visit creates the single parent account. Registration closes once an account exists.
- **Log in with username and password.** Passwords are stored as salted PBKDF2-SHA256 hashes in `webui-data/config.json`.
- **Child's name.** Asked at registration and used across the page ("Sam's buttons", "Who can call Sam") and as caller ID on outgoing calls.
- **Settings page**: child's name, house Linphone address, change password (which signs out other devices).
- `scripts/setup.sh`, `.env.example`, `pjsip.conf.example`, `manager.conf.example`.
- Documentation in `docs/`.
- MIT license.

### Changed
- The child's endpoint name is configurable (`KID` in `extensions.conf`, `KID_ENDPOINT` in `.env`). Default `kid`.
- The web page no longer takes its password from `UI_PASSWORD`.

## [0.3.0] - 2026-11-16

Relatives call with the Linphone app only. No VPN, no phone number.

### Added
- Asterisk registers to linphone.org as the "house" account.
- Buttons can call a Linphone username; allowed callers can be Linphone usernames.
- Incoming calls are checked against the allowed list and otherwise hung up.

### Fixed
- Incoming calls never reached the server over UDP: the registration now uses TCP.
- `;transport=tcp` was silently dropped from `pjsip.conf` because `;` starts a comment: now written `\;`.
- Incoming calls failed with `488 Not Acceptable Here` and retried: the linphone endpoint now accepts encrypted audio (`media_encryption=sdes`, optimistic, `use_avpf=yes`).

### Removed
- Per-relative accounts on the home server (they required every relative to install a VPN).

## [0.2.0] - 2026-11-16

### Added
- Redesigned page: phone keypad for the buttons, plain name-and-number forms, connection badge.
- A proper sign-in page with a 30-day session instead of the browser's password pop-up.
- Buttons and allowed callers survive a container rebuild (`db/astdb.sqlite3` is mounted).
- The Asterisk image is pinned by digest.

### Fixed
- A wrong password returned an empty reply.
- The page could hang forever if Asterisk closed the connection.
- Requests from other websites are refused.

## [0.1.0] - 2026-11-16

- Plain Asterisk in Docker with one endpoint for the child's phone.
- A minimal web page storing speed dials and allowed callers in the Asterisk database.
- Echo test on 600.
