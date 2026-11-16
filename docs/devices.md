# Devices

## Required

### 1. A computer that is always on

It runs Asterisk (the phone system) and the admin page, both in Docker.

- Any 64-bit Intel/AMD machine running Linux with Docker and Docker Compose.
- Tested on: a desktop PC, Ubuntu 26.04, wired to the home router. The load is tiny; an old laptop or mini PC is plenty.
- It must be on the same home network as the phone adapter, with a fixed address (reserve its IP in your router).
- No Linux machine? Run Debian in a virtual machine: see [install.md](install.md#option-b-a-debian-virtual-machine).
- ARM boards (Raspberry Pi) are untested.

### 2. An analog telephone adapter (ATA)

A small box that turns an ordinary corded phone into a network phone. One phone port is enough.

| Model | Notes |
| --- | --- |
| Cisco SPA112 (2 ports) | Cheap second-hand. No longer updated by Cisco, so keep it on your home network only and factory-reset it on arrival. |
| Grandstream HT801 (1 port) | Current model, still supported. |

**Neither has been tested with this project yet.** The adapter must be able to:

- register to a SIP server by IP address with a username and password (the `kid` account in `pjsip.conf`);
- send a single digit immediately, without waiting for more digits (a "dial plan" setting on the adapter).

Your internet provider's router may have a phone port. It is normally locked to the provider and cannot be used for this.

### 3. A corded analog phone

Any corded phone works. For a small child, a **photo phone** is ideal: its large memory buttons hold a picture of each person. Program each memory button to dial one digit (1, 2, 3...).

Phones with no keypad lock still cannot dial anything except the configured buttons: the server answers every other number with a busy tone.

### 4. Cables

- Ethernet cable: adapter to router.
- Phone cable (RJ11): adapter "Phone 1" port to the phone. Usually included with the phone.

### 5. A smartphone for each relative

With the free Linphone app (Android or iPhone) and their own free linphone.org account. See [linphone.md](linphone.md).

## Optional

- **Tailscale** (or another private VPN) on the server and your own phone, so you can open the admin page when you are away from home.
- **A spare smartphone** to stand in for the child's phone while you wait for the adapter. Note the iPhone limitation in [troubleshooting.md](troubleshooting.md#the-test-phone-keeps-disconnecting-iphone).

## Not needed

- A phone number or SIP provider subscription.
- Port forwarding, a static public IP, or a domain name.
- FreePBX or any other phone-system interface.
