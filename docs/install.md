# Install

You need a Linux machine with Docker that stays on. Pick option A or B, then continue with "Set up the phone system".

## Option A: a Linux machine you already have

Install Docker and the Compose plugin following [Docker's instructions](https://docs.docker.com/engine/install/), then check:

```bash
docker compose version
```

Tested on Ubuntu 26.04.

## Option B: a Debian virtual machine

Use this if your always-on computer runs Windows or macOS, or you want the phone system kept separate. **This path was written from general knowledge and has not been tested for this project.**

1. Install [VirtualBox](https://www.virtualbox.org/) and download the Debian "netinst" ISO from [debian.org](https://www.debian.org/distrib/).
2. Create a VM: Debian 64-bit, 2 GB RAM, 1 CPU, 10 GB disk.
3. **Set the network adapter to "Bridged Adapter"**, not NAT. The VM must get its own address on your home network, or the phone adapter cannot reach it.
4. Install Debian. At software selection, choose only "SSH server" and "standard system utilities".
5. In your router, reserve the VM's IP address so it never changes.
6. Log in and install Docker:

   ```bash
   sudo apt update
   sudo apt install -y git curl
   curl -fsSL https://get.docker.com | sudo sh
   sudo usermod -aG docker $USER
   ```

   Log out and back in so the group change applies.
7. Set the VM to start with the host computer (VirtualBox: "Start VM on host boot", or your system's autostart).

The host computer must not sleep. If it sleeps, the phone stops working.

## Set up the phone system

1. Create the **house** Linphone account first: see [linphone.md](linphone.md#1-the-house-account).

2. Get the code and run the setup script:

   ```bash
   git clone https://github.com/yllenfer/your-childs-first-phone.git
   cd your-childs-first-phone
   ./scripts/setup.sh
   ```

   It asks for the house account's username and password and creates:

   | File | What it is |
   | --- | --- |
   | `.env` | random secret shared by the web page and Asterisk |
   | `manager.conf` | lets the web page talk to Asterisk, from this machine only |
   | `pjsip.conf` | the child's phone account (`kid`) and the linphone.org sign-in |
   | `db/astdb.sqlite3` | where buttons and allowed callers are stored |
   | `webui-data/` | where the parent account is stored |

   It prints the password for the `kid` account. You will type it into the phone adapter later.

3. Start it:

   ```bash
   docker compose up -d --build
   ```

4. Check that the server signed in to linphone.org:

   ```bash
   docker exec asterisk asterisk -rx "pjsip show registrations"
   ```

   The line should end with `Registered`. If it says `Rejected` or `Unregistered`, see [troubleshooting.md](troubleshooting.md).

5. Open `http://<server-address>:8099`. The first visit shows **Register**: enter your child's name, a username and a password of at least 10 characters. Do this straight away, because whoever opens the page first becomes the owner.

6. In **Settings**, type the house Linphone username so the main page can remind you what relatives should dial.

7. Add people: [linphone.md](linphone.md#2-each-relative).

## Connect the phone

> Not tested yet in this project. These are the settings the adapter needs; menu names differ by model.

1. Factory-reset the adapter and connect it to your router. Find its address in your router's device list and open it in a browser.
2. On the line/phone-port page set:
   - SIP server (proxy/registrar): your server's home-network IP address, port 5060, UDP
   - User ID and authentication ID: `kid`
   - Password: the `kid` password from `pjsip.conf`
   - Codec: G.711 (`PCMU`/`PCMA`, also called ulaw/alaw)
3. Set the adapter's dial plan so one digit is sent without waiting for more. Untested starting points: `(x|600)` on Cisco SPA adapters, `{x|600}` on Grandstream HT80x. Expect button 6 to pause for a moment, because it could be the start of 600; remove `600` from the dial plan once testing is done.
4. The main page of the admin site should now show "phone is connected". Pick up the phone and dial `600`: you should hear your own voice echoed back.

## Updating

```bash
git pull
docker compose up -d --build
```

Your settings are in files that Git ignores, so they are kept.

Editing a config file by hand? Read [asterisk.md](asterisk.md#editing-config-files) first: some editors replace the file, and the running container then keeps reading the old copy.

## Backup

Copy the whole folder, including the hidden `.env`:

```bash
tar czf first-phone-backup.tgz -C .. your-childs-first-phone
```

The backup contains passwords. Store it somewhere private.
