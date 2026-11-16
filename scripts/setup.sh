#!/usr/bin/env bash
# First-time setup: creates .env, manager.conf, pjsip.conf, the database file and the
# web page's data folder. Safe to re-run: it never overwrites a file that already exists.
set -euo pipefail
cd "$(dirname "$0")/.."

rand() { python3 -c "import secrets,string;print(''.join(secrets.choice(string.ascii_letters+string.digits) for _ in range($1)))"; }

umask 077
if [ ! -f .env ]; then
  secret=$(rand 32)
  sed -e "s/^AMI_SECRET=.*/AMI_SECRET=$secret/" -e "s/^HOST_UID=.*/HOST_UID=$(id -u)/" -e "s/^HOST_GID=.*/HOST_GID=$(id -g)/" .env.example > .env
  echo "created .env"
fi
secret=$(grep '^AMI_SECRET=' .env | cut -d= -f2-)

if [ ! -f manager.conf ]; then
  sed "s/^secret=change-me.*/secret=$secret/" manager.conf.example > manager.conf
  echo "created manager.conf"
fi

if [ ! -f pjsip.conf ]; then
  read -rp "Linphone username of the HOUSE account (the one relatives will call): " house
  read -rsp "Password of that Linphone account (not shown): " housepw; echo
  kidpw=$(rand 20)
  HOUSE="$house" HOUSEPW="$housepw" KIDPW="$kidpw" python3 - <<'PY'
import os
s = open("pjsip.conf.example").read()
s = s.replace("HOUSE-USERNAME", os.environ["HOUSE"])
# ";" starts a comment in Asterisk config files, so escape it inside the password.
s = s.replace("CHANGE-ME-HOUSE-LINPHONE-PASSWORD", os.environ["HOUSEPW"].replace(";", "\\;"))
s = s.replace("CHANGE-ME-KID-PASSWORD", os.environ["KIDPW"])
open("pjsip.conf", "w").write(s)
PY
  echo "created pjsip.conf"
  echo "The child's phone (ATA) signs in as: username 'kid', password '$kidpw'"
  echo "(it is also in pjsip.conf under [kid])"
fi

mkdir -p db webui-data
[ -f db/astdb.sqlite3 ] || { : > db/astdb.sqlite3; echo "created db/astdb.sqlite3"; }
# Asterisk runs as uid 1000 inside the container and must be able to read its config.
chmod 644 db/astdb.sqlite3 2>/dev/null || true
if [ "$(id -u)" != "1000" ]; then
  echo "NOTE: your user id is $(id -u), but Asterisk in the container runs as uid 1000."
  echo "      Run: sudo chown 1000 pjsip.conf manager.conf db db/astdb.sqlite3"
fi
echo "Done. Next: docker compose up -d --build   then open http://<this-machine>:8099"
