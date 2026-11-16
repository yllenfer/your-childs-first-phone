# Asterisk

[Asterisk](https://www.asterisk.org/) is the open-source phone system that does the real work. This project runs plain Asterisk in Docker, with no FreePBX.

- Image: `andrius/asterisk`, pinned by digest in `compose.yaml` (Asterisk 23.5.0 on 2026-11-16).
- Host networking: SIP on port 5060 (UDP and TCP), audio on UDP 10000-20000. These are used on your home network and for outgoing connections only. **Never forward them on your router.**
- Inside the container Asterisk runs as user id 1000 and must be able to read the mounted config files.

## The three config files

### pjsip.conf - who can connect

| Section | Purpose |
| --- | --- |
| `transport-udp`, `transport-tcp` | Listen on 5060. TCP is what the linphone.org connection uses. |
| `kid` (endpoint, auth, aor) | The child's phone. Calls from it enter the dialplan at `from-phone`. Only G.711 audio, which every adapter supports. |
| `linphone-reg` | Signs in to linphone.org as the house account and keeps it signed in. `line=yes` tags the sign-in so incoming calls are matched to it. |
| `linphone` (endpoint, aor, identify) | Calls to and from linphone.org. Incoming calls enter at `from-linphone`. Accepts encrypted audio. |

### extensions.conf - what happens on a call

| Context | Rule |
| --- | --- |
| `from-phone` | `600` is an echo test. A single digit looks up `speed/<digit>` in the database and calls it. Anything else, or an empty button, gets a busy tone. |
| `from-linphone` | Takes the caller's username and domain. Rings the child's phone only if the domain is `sip.linphone.org` and `allowedapp/<username>` exists. Otherwise hangs up. |
| `from-trunk` | Placeholder for a real phone number through a SIP provider. Not wired up. |

`[globals]` holds `KID`, the name of the child's endpoint. If you rename `[kid]` in `pjsip.conf`, change it here and in `.env` (`KID_ENDPOINT`).

### manager.conf - how the web page talks to Asterisk

The manager interface (AMI) listens on `127.0.0.1:5038` only. The single user, `webui`, may only run CLI commands. The web page uses it for `database put/del/show` and `pjsip show endpoints`.

## The database

Buttons and allowed callers are rows in Asterisk's built-in database (`db/astdb.sqlite3`):

| Key | Value | Meaning |
| --- | --- | --- |
| `speed/1` | `mama123@sip.linphone.org` | Button 1 calls this Linphone user |
| `speedname/1` | `Mama` | Name shown on the page |
| `allowedapp/mama123` | `Mama` | This Linphone user may call in |
| `allowed/447700900123` | `Nana` | This phone number may call in (needs a trunk) |
| `config/childname` | `Sam` | Sent as the caller's name on outgoing calls |

## Useful commands

```bash
a() { docker exec asterisk asterisk -rx "$1"; }

a "pjsip show registrations"     # is the server signed in to linphone.org?
a "pjsip show endpoints"         # is the child's phone connected?
a "pjsip show contacts"          # who is registered right now
a "database show"                # every button and allowed caller
a "dialplan show from-linphone"  # the incoming-call rules as loaded
a "dialplan reload"              # after editing extensions.conf
a "module reload res_pjsip.so"   # after editing pjsip.conf (new transports need a restart)
docker logs --since 10m asterisk # recent calls
```

## Editing config files

- `;` starts a comment. Write `\;` for a real semicolon inside a value.
- Edit in place (`nano`). If a change does not take effect, the container is still reading the old file: run `docker compose restart asterisk`.
- Transports are not reloadable. Adding or changing one needs a restart.

## Why not FreePBX

The commonly used FreePBX Docker image is archived and stuck on an old release, and a full PBX interface is far more than a one-phone household needs. Three short config files are easier to read, back up and reason about.
