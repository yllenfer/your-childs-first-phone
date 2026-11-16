# Linphone accounts

Everyone uses free accounts on linphone.org. There are two kinds.

| Account | Who signs in to it | Example |
| --- | --- | --- |
| The **house** account | Only your server. Never a phone. | `samhome` |
| A **personal** account per relative | That relative's Linphone app | `mama123`, `nana123` |

The child's phone has no account of its own on linphone.org. It talks to your server, and the server holds the house account for it.

## 1. The house account

1. Go to <https://subscribe.linphone.org> and create an account. Choose a username relatives can remember, such as `samhome`. Each account needs its own email address.
2. Activate it from the confirmation email.
3. Give the username and password to `./scripts/setup.sh` (see [install.md](install.md)).

**Do not sign any phone in to the house account.** linphone.org remembers every device that signs in and rings it directly, which bypasses your allowed list. If you did, see [troubleshooting.md](troubleshooting.md#someone-not-on-the-list-can-still-call).

## 2. Each relative

1. They install **Linphone** from the App Store or Google Play.
2. In the app they choose **Create a Linphone account** and pick a username.
3. They tell you the username.
4. You open the admin page, tap a button, and type their name and username. That gives the child a button for them and puts them on the allowed list.
5. They call the house username (`samhome`) to reach the child.

Someone who should be able to call in but does not need a button: add them under "Who can call" instead.

## Testing without the adapter

You can sign a spare smartphone in to the server as the child's phone:

1. Linphone, then **Use a SIP account** (also called "third-party SIP account").
2. Username `kid`, the password from `pjsip.conf`, domain = your server's address, transport UDP.
3. The phone must be on your home network (or on the same private VPN as the server).

Dial `600` for an echo test, or `1` to call button 1.

This is for testing only. Phones put the app to sleep, so it will not ring reliably; the real adapter stays connected all the time.

## Why linphone.org

- Free accounts and a maintained app on both Android and iPhone.
- Its servers wake the app for incoming calls, so relatives do not need to keep it open.
- Its servers relay the audio, so calls work from behind home routers on both ends.
- It accepts sign-ins from a standard SIP server such as Asterisk. Older reports online say this was blocked; on 2026-11-16 it worked.

It is a free community service with no guarantee. If it ever stops accepting third-party servers, this project will need another SIP service or a paid phone number.
