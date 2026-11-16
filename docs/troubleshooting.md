# Troubleshooting

Every problem here actually happened while building this project. The shipped configuration already contains the fixes; this page explains them so you can recognise the symptoms.

To watch what the server sees during a call:

```bash
docker exec asterisk asterisk -rx "pjsip set logger on"
docker logs -f --since 1m asterisk
docker exec asterisk asterisk -rx "pjsip set logger off"   # when done: the log contains call encryption keys
```

## Someone not on the list can still call

**Symptom:** you remove a person from "Who can call", they call the house address, and a phone still rings.

**Cause:** a phone was signed in to the *house* linphone.org account at some point. linphone.org keeps that phone as a registered device and rings it directly. The call reaches the server too, which hangs up, but the other phone has already rung. Logging out inside the app does not remove the device.

**Fix:**

1. Sign in at <https://subscribe.linphone.org> as the house account.
2. Open **Devices > Manage** and delete every phone listed. Keep the entry for your server.
3. Never sign a phone in to the house account again.

**How to confirm the server is doing the blocking:** the log shows `Linphone call from user=<name>` followed by `Hangup(... "21")`.

## Incoming calls never reach the server

**Symptom:** the server shows `Registered`, the child's button works, but calls to the house address never appear in the server's log.

**Cause:** the server registered over UDP. linphone.org then tries to deliver calls to the server's private home address, which is unreachable from the internet.

**Fix (already in `pjsip.conf.example`):** register over TCP. The server opens one outgoing connection and incoming calls return down it, so no router changes are needed.

```ini
transport=transport-tcp
server_uri=sip:sip.linphone.org\;transport=tcp
```

## A setting in pjsip.conf is ignored

**Symptom:** you add `;transport=tcp` to an address and nothing changes.

**Cause:** in Asterisk config files `;` starts a comment, so everything after it is dropped without any warning.

**Fix:** write `\;` for a literal semicolon.

## Every incoming call takes 5-10 extra seconds, or fails with "488"

**Symptom:** the log shows `Couldn't negotiate stream 0:audio` and `488 Not Acceptable Here`, then the call arrives on a second or third attempt.

**Cause:** the Linphone app offers encrypted audio first (`RTP/SAVPF`, then `RTP/SAVP`), and only falls back to plain audio after the server refuses twice.

**Fix (already in `pjsip.conf.example`)** on the `linphone` endpoint:

```ini
media_encryption=sdes
media_encryption_optimistic=yes
use_avpf=yes
```

## A config change has no effect after a reload

**Symptom:** you edit `pjsip.conf`, reload, and Asterisk still shows the old value.

**Cause:** each config file is mounted into the container as a single file. Tools that save by writing a new file and renaming it (`sed -i`, some editors) leave the container reading the old one.

**Check:**

```bash
docker exec asterisk grep -c use_avpf /etc/asterisk/pjsip.conf
```

**Fix:** `docker compose restart asterisk`. `nano` edits in place and does not cause this.

## The test phone keeps disconnecting (iPhone)

**Symptom:** a smartphone signed in as the child's phone shows "not connected" on the admin page unless the app is open on screen.

**Cause:** iOS suspends the app, and a home server cannot wake it. This affects only softphones used for testing.

**Fix:** none needed. The analog adapter stays registered permanently.

## Buttons and allowed callers vanish after an update

**Cause:** Asterisk stores them in its internal database, inside the container. Asterisk 23 ignores the `astdbdir` setting, so moving the database folder does not work.

**Fix (already in `compose.yaml`):** the database file itself is mounted from `./db/astdb.sqlite3`.

## The call history on the child's test phone shows "1", not a name

That is the number that was dialled. The server translates it. A corded phone has no screen, so this only shows up when testing with a softphone.

## Wrong password shows a blank page

Fixed in v0.2.0. Update to the current version.
