# Your Child's First Phone

A screen-free home phone for a young child.

- The child picks up a corded phone and presses **1** for Mum, **2** for Dad, **3** for Nana. Nothing else can be dialled.
- Only people you approve can make it ring. Everyone else is hung up on before the phone makes a sound.
- Relatives anywhere in the world call for free with one app ([Linphone](https://www.linphone.org/)). No phone number, no monthly fee.
- Nothing is opened on your router.
- You manage it all from a small web page: who each button calls, and who may call in.

> **This phone cannot call emergency services (112, 911, 999).** It can only call the people on its buttons. Do not make it the only phone in the house.

## How it works

```
 Relative's phone            linphone.org             Your home server              Child's phone
 (Linphone app,       --->   (free SIP service)  <--- (Asterisk, signed in   --->   (corded phone on an
  their own account)                                   as the "house" account)       analog adapter)
```

1. You create one free linphone.org account for the house, for example `samhome`.
2. Asterisk, running in Docker on a computer at home, signs in to that account. The connection goes *out* from your home, so the router needs no port forwarding.
3. A relative calls `samhome` from the Linphone app. Asterisk checks the caller against your allowed list and either rings the child's phone or hangs up.
4. When the child presses a button, Asterisk calls that relative's Linphone account.

## What you need

| Device | Notes |
| --- | --- |
| An always-on computer running Linux with Docker | We used a desktop PC with Ubuntu 26.04. A Debian VM works too, see [docs/install.md](docs/install.md). |
| An analog telephone adapter (ATA) | Cisco SPA112 or Grandstream HT801. **Not tested yet in this project**, see [Status](#status). |
| A corded analog phone | Any will do. A "photo phone" with picture memory buttons is ideal for small children. |
| Cables | Ethernet from the adapter to your router, and a phone (RJ11) cable from the adapter to the phone. |
| A smartphone for each relative | With the free Linphone app. |

Full list with details: [docs/devices.md](docs/devices.md).

## Quick start

```bash
git clone https://github.com/yllenfer/your-childs-first-phone.git
cd your-childs-first-phone
./scripts/setup.sh              # asks for the house Linphone account, creates the config files
docker compose up -d --build
```

Then open `http://<your-server>:8099`, **register** the parent account (this page appears only once), and set up the first button.

Step-by-step instructions: [docs/install.md](docs/install.md), then [docs/linphone.md](docs/linphone.md).

## The admin page

- **Register** (first visit only): your username, password, and your child's name. Prefer not to register? Set `ADMIN_USER`, `ADMIN_PASSWORD` and `CHILD_NAME` in `.env` before the first start and you go straight to Log in.
- **Log in**: stays signed in for 30 days on that device.
- **Buttons**: tap a key, type a name and that person's Linphone username.
- **Who can call**: the allowed list. Saving a button also adds that person here.
- **Settings**: child's name, the house Linphone address, change password.

The page is plain HTTP and is meant for your home network or a private VPN such as Tailscale. Do not expose it to the internet.

## Status

Built and tested in one day (2026-11-16), so treat it as an early version.

| Part | State |
| --- | --- |
| Web page: register, log in, buttons, allowed list | Tested |
| Server signs in to linphone.org with nothing open on the router | Tested |
| Calls from someone **not** on the list are hung up | Tested with a real call |
| An allowed relative calls in and the child's phone rings and answers | Tested, using a softphone as the child's phone |
| Child presses a button and the relative's phone rings | Tested, using a softphone as the child's phone |
| Audio quality over a long call, from another country | Not tested |
| The analog adapter (ATA) and a real corded phone | **Not tested yet** |
| A real phone number through a SIP trunk | Not included; the dialplan has a placeholder |

## Documentation

- [docs/devices.md](docs/devices.md) - what to buy
- [docs/install.md](docs/install.md) - server setup, including a Debian VM
- [docs/linphone.md](docs/linphone.md) - accounts for the house and for relatives
- [docs/troubleshooting.md](docs/troubleshooting.md) - the problems we hit and how they were fixed
- [docs/asterisk.md](docs/asterisk.md) - how the Asterisk configuration works
- [CHANGELOG.md](CHANGELOG.md) - version history

## Security notes

- Callers are identified by their linphone.org username, which linphone.org authenticates. Anyone who gains access to an allowed relative's Linphone account can call the child.
- Secrets live in `.env`, `pjsip.conf`, `manager.conf` and `webui-data/`. All are in `.gitignore`; never commit them.
- The Asterisk manager interface listens on `127.0.0.1` only and the web page can only run CLI commands through it.
- Never forward SIP (5060) or RTP (10000-20000) ports on your router.

## License

[MIT](LICENSE)
