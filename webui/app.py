"""Your Child's First Phone - admin page. Python standard library only.

What it does
  * First visit: a Register page creates the one parent account (and asks the child's name).
    Or set ADMIN_USER, ADMIN_PASSWORD and CHILD_NAME in .env to have the account created
    at start-up, so you go straight to Log in.
  * After that: Log in, then choose who each phone button calls and who may call the child.

Where things are stored
  * /data/config.json (a mounted folder): the parent account (salted password hash),
    the child's name, the house Linphone address, and the cookie signing key.
  * The Asterisk database, written through the manager interface (AMI "Command"):
      speed/<digit>      -> "user@sip.linphone.org" (a Linphone user) or digits (a phone number)
      speedname/<digit>  -> the name shown on that button
      allowedapp/<user>  -> name of a Linphone user allowed to ring the child's phone
      allowed/<digits>   -> name of an ordinary phone number allowed to ring it (needs a SIP trunk)
      config/childname   -> the child's name, used by the dialplan as caller ID
"""
import hashlib, hmac, html, json, os, re, secrets, socket, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

AMI_HOST = os.environ.get("AMI_HOST", "127.0.0.1")
AMI_PORT = int(os.environ.get("AMI_PORT", "5038"))
AMI_USER = os.environ.get("AMI_USER", "webui")
AMI_SECRET = os.environ["AMI_SECRET"]
PORT = int(os.environ.get("PORT", "8099"))
DATA_DIR = os.environ.get("DATA_DIR", "/data")
KID = os.environ.get("KID_ENDPOINT", "kid")          # the child's phone in pjsip.conf
LINE = os.environ.get("LINE_ENDPOINT", "linphone")   # the linphone.org connection in pjsip.conf
LP_DOMAIN = os.environ.get("LINPHONE_DOMAIN", "sip.linphone.org")

CONFIG_PATH = os.path.join(DATA_DIR, "config.json")
FAVICON_PATH = os.environ.get("FAVICON_PATH", "/favicon.svg")
COOKIE = "firstphone"
SESSION_DAYS = 30
PBKDF2_ROUNDS = 310_000

NAME = re.compile(r'^[^\x00-\x1f\x7f"\\<>]{1,40}$')
USERNAME = re.compile(r"^[A-Za-z0-9._-]{3,32}$")
LP_USER = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
config_lock = threading.Lock()
login_lock = threading.Lock()


# ------------------------------------------------------------------ config

def load_config():
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def save_config(cfg):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = CONFIG_PATH + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(cfg, f, indent=1)
    os.replace(tmp, CONFIG_PATH)


def registered(cfg):
    return bool(cfg.get("username") and cfg.get("hash"))


def hash_password(password, salt_hex):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), PBKDF2_ROUNDS).hex()


def child(cfg):
    return cfg.get("child_name") or "your child"


def possessive(name):
    return name + ("'" if name.endswith(("s", "S")) else "'s")


# ---------------------------------------------------------------- Asterisk

def ami(command):
    with socket.create_connection((AMI_HOST, AMI_PORT), timeout=5) as s:
        f = s.makefile("rb")
        f.readline()  # banner

        def message():
            lines = []
            while True:
                raw = f.readline()
                if not raw:
                    raise RuntimeError("Asterisk closed the connection")
                line = raw.decode("utf-8", "replace").rstrip("\r\n")
                if line == "":
                    if lines:
                        return lines
                    continue
                lines.append(line)

        s.sendall(f"Action: Login\r\nUsername: {AMI_USER}\r\nSecret: {AMI_SECRET}\r\nEvents: off\r\n\r\n".encode())
        if "Success" not in "".join(message()):
            raise RuntimeError("Asterisk rejected the login")
        s.sendall(f"Action: Command\r\nCommand: {command}\r\n\r\n".encode())
        return "\n".join(message())


def entries(family):
    out = ami(f"database show {family}")
    return dict(re.findall(rf"^(?:Output: )?/{family}/(\S+)\s*:\s*(.*?)\s*$", out, re.M))


def endpoints():
    """Endpoint name -> state, from 'pjsip show endpoints'."""
    out = ami("pjsip show endpoints")
    found = {}
    for name, state in re.findall(r"^(?:Output: )?\s*Endpoint:\s+([^\s<]\S*)\s+(.+?)\s{2,}", out, re.M):
        found[name.split("/")[0]] = state.strip()
    return found


def is_up(eps, name):
    state = eps.get(name, "")
    return bool(state) and state != "Unavailable"


def db_put(family, key, value):
    ami(f'database put {family} {key} "{value}"')


def db_del(family, key):
    ami(f"database del {family} {key}")


# ----------------------------------------------------------------- helpers

def normalize_number(text):
    """Return (digits_with_country_code, error)."""
    t = text.strip()
    digits = re.sub(r"\D", "", t)
    if t.startswith("+"):
        pass
    elif digits.startswith("00"):
        digits = digits[2:]
    else:
        return None, "Start the number with + and its country code, for example +44 7700 900123."
    if not 8 <= len(digits) <= 15:
        return None, "That number doesn't look complete."
    return digits, None


def parse_contact(text):
    """A Linphone username or a phone number -> (kind, value, error). kind is "app" or "number"."""
    t = text.strip()
    if re.fullmatch(r"[+0-9 ().-]+", t):
        digits, err = normalize_number(t)
        return "number", digits, err
    u = t.lower()
    if u.startswith("sip:"):
        u = u[4:]
    if u.endswith("@" + LP_DOMAIN):
        u = u[: -len(LP_DOMAIN) - 1]
    if not LP_USER.match(u):
        return "app", None, "Type their Linphone username, for example nana123."
    return "app", u, None


def pretty(digits):
    """Readable form: +34 600 111 222, +44 7700 900123, +57 300 123 4567."""
    def split(rest, sizes):
        out, i = [], 0
        for n in sizes:
            if i < len(rest):
                out.append(rest[i:i + n])
                i += n
        if i < len(rest):
            out[-1] += rest[i:]
        return " ".join(out)
    layouts = {"34": (3, 3, 3), "44": (4, 6), "57": (3, 3, 4), "1": (3, 3, 4)}
    for cc, sizes in layouts.items():
        if digits.startswith(cc) and len(digits) > len(cc) + 4:
            return f"+{cc} " + split(digits[len(cc):], sizes)
    return "+" + digits


def describe(dest):
    if dest.isdigit():
        return pretty(dest)
    if dest.endswith("@" + LP_DOMAIN):
        return "Linphone: " + dest.split("@")[0]
    return dest


def shown(dest):
    """What to put back in the edit box for a stored destination."""
    return pretty(dest) if dest.isdigit() else dest.split("@")[0]


def sign(cfg, exp):
    return hmac.new(bytes.fromhex(cfg["cookie_key"]), str(exp).encode(), hashlib.sha256).hexdigest()


def esc(s):
    return html.escape(str(s), quote=True)


MESSAGES = {
    "saved": "Saved.",
    "savedboth": "Saved. They can also call in now.",
    "removed": "Removed.",
    "allowed": "Added. They can now call in.",
    "settings": "Settings saved.",
    "password": "Password changed.",
    "out": "You're signed out.",
    "welcome": "Your account is ready. Now set up the first button.",
}

CSS = """
:root{--bg:#f6f3ee;--card:#fff;--ink:#1f2328;--muted:#6b6f76;--line:#e6e0d6;--accent:#2f6f5e;
--accent-ink:#fff;--soft:#e7f1ed;--warn:#9a3b1b;--warn-soft:#fbeae4;--key:#fbfaf7}
@media (prefers-color-scheme:dark){:root{--bg:#16181b;--card:#1f2226;--ink:#eceae6;--muted:#9aa0a6;
--line:#2e3237;--accent:#6cc2a6;--accent-ink:#0f1a16;--soft:#1d2e28;--warn:#f0a08a;--warn-soft:#3a231c;--key:#24282d}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif}
a{color:var(--accent)}
.wrap{max-width:760px;margin:0 auto;padding:20px 16px 48px}
header{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:20px;flex-wrap:wrap}
header nav{display:flex;gap:8px;align-items:center}
h1{font-size:1.5rem;margin:0}
h1 a{color:inherit;text-decoration:none}
h2{font-size:1.15rem;margin:0 0 4px}
.sub{color:var(--muted);margin:0 0 16px;font-size:.95rem}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:20px;margin-bottom:20px}
.pills{display:flex;gap:6px;flex-wrap:wrap}
.pill{display:inline-flex;align-items:center;gap:6px;font-size:.85rem;padding:4px 10px;border-radius:999px;
background:var(--warn-soft);color:var(--warn)}
.pill.ok{background:var(--soft);color:var(--accent)}
.pill::before{content:"";width:8px;height:8px;border-radius:50%;background:currentColor}
.keys{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
.key{display:flex;flex-direction:column;gap:2px;min-height:96px;padding:12px;border-radius:14px;border:1px solid var(--line);
background:var(--key);color:var(--ink);text-decoration:none}
.key:hover{border-color:var(--accent)}
.key .d{font-size:1.6rem;font-weight:700;line-height:1}
.key .n{font-weight:600;overflow-wrap:anywhere}
.key .t{color:var(--muted);font-size:.8rem;overflow-wrap:anywhere}
.key.empty .n{color:var(--muted);font-weight:400}
.key.off{opacity:.45;pointer-events:none}
.list{list-style:none;margin:0;padding:0}
.list li{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 0;border-top:1px solid var(--line)}
.list li:first-child{border-top:0}
.list .who{font-weight:600}.list .num{color:var(--muted);font-size:.9rem}
label{display:block;font-weight:600;margin:14px 0 6px}
.hint{color:var(--muted);font-size:.85rem;margin-top:4px;font-weight:400}
input[type=text],input[type=tel],input[type=password]{width:100%;padding:12px;border-radius:10px;border:1px solid var(--line);
background:var(--bg);color:var(--ink);font:inherit}
.row{display:grid;grid-template-columns:1fr 1fr;gap:12px}
@media (max-width:520px){.row{grid-template-columns:1fr}}
button,.btn{appearance:none;border:0;border-radius:10px;padding:12px 18px;font:inherit;font-weight:600;cursor:pointer;
background:var(--accent);color:var(--accent-ink);text-decoration:none;display:inline-block}
button.ghost,.btn.ghost{background:transparent;color:var(--ink);border:1px solid var(--line)}
button.danger{background:transparent;color:var(--warn);border:1px solid var(--line);padding:8px 12px;font-weight:500}
.actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:18px;align-items:center}
.note{padding:12px 14px;border-radius:10px;background:var(--soft);color:var(--accent);margin-bottom:16px}
.note.err{background:var(--warn-soft);color:var(--warn)}
.narrow{max-width:420px;margin:8vh auto 0}
.empty-state{color:var(--muted);padding:8px 0}
"""


def layout(title, body, cfg=None, signed_in=True):
    top = ""
    if signed_in:
        heading = f"{possessive(child(cfg))} phone" if cfg else "First Phone"
        top = (f"<header><h1><a href='/'>{esc(heading)}</a></h1><nav><a class='btn ghost' href='/settings'>Settings</a>"
               f"<form method=post action=/logout><button class=ghost>Log out</button></form></nav></header>")
    return (f"<!doctype html><html lang=en><head><meta charset=utf-8>"
            f"<meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<title>{esc(title)}</title><link rel=icon type='image/svg+xml' href='/favicon.svg'>"
            f"<style>{CSS}</style></head>"
            f"<body><div class=wrap>{top}{body}</div></body></html>")


def note(code, error=None):
    if error:
        return f"<div class='note err'>{esc(error)}</div>"
    if code in MESSAGES:
        return f"<div class=note>{esc(MESSAGES[code])}</div>"
    return ""


# ------------------------------------------------------------------- pages

def register_page(error=None, form=None):
    form = form or {}
    body = f"""<div class='card narrow'>
<h1 style='margin-bottom:4px'>Your Child's First Phone</h1>
<p class=sub>Create the parent account. This page only appears once, before any account exists.</p>
{note(None, error)}
<form method=post action=/register>
<label for=cn>Your child's name</label>
<input id=cn type=text name=child_name maxlength=40 value='{esc(form.get("child_name", ""))}' placeholder="Sam" required>
<label for=un>Your username</label>
<input id=un type=text name=username maxlength=32 value='{esc(form.get("username", ""))}' autocomplete=username
autocapitalize=none autocorrect=off required>
<label for=pw>Password</label>
<input id=pw type=password name=password autocomplete=new-password minlength=10 required>
<div class=hint>At least 10 characters.</div>
<label for=pw2>Password again</label>
<input id=pw2 type=password name=password2 autocomplete=new-password minlength=10 required>
<div class=actions><button>Create account</button></div>
</form></div>"""
    return layout("Register · First Phone", body, signed_in=False)


def login_page(cfg, error=None, msg=""):
    body = f"""<div class='card narrow'>
<h1 style='margin-bottom:4px'>{esc(possessive(child(cfg)))} phone</h1>
<p class=sub>Log in to manage who {esc(child(cfg))} can call.</p>
{note(msg, error)}
<form method=post action=/login>
<label for=un>Username</label>
<input id=un type=text name=username autocomplete=username autocapitalize=none autocorrect=off autofocus required>
<label for=pw>Password</label>
<input id=pw type=password name=password autocomplete=current-password required>
<div class=actions><button>Log in</button></div>
</form></div>"""
    return layout("Log in · First Phone", body, signed_in=False)


def key_tile(d, speed, names):
    if d in speed:
        name = names.get(d) or describe(speed[d])
        return (f"<a class=key href='/key?d={d}'><span class=d>{d}</span>"
                f"<span class=n>{esc(name)}</span><span class=t>{esc(describe(speed[d]))}</span></a>")
    return f"<a class='key empty' href='/key?d={d}'><span class=d>{d}</span><span class=n>Not set</span></a>"


def home_page(cfg, msg="", error=None):
    kid = child(cfg)
    speed, names = entries("speed"), entries("speedname")
    apps, numbers = entries("allowedapp"), entries("allowed")
    eps = endpoints()
    pills = (f"<span class='pill ok'>{esc(possessive(kid))} phone is connected</span>" if is_up(eps, KID)
             else f"<span class=pill>{esc(possessive(kid))} phone is not connected</span>")
    pills += ("<span class='pill ok'>Linphone line is up</span>" if is_up(eps, LINE)
              else "<span class=pill>Linphone line is down</span>")

    keys = [key_tile(d, speed, names) for d in "123456789"]
    keys.append("<div class='key off'><span class=d>*</span></div>")
    keys.append(key_tile("0", speed, names))
    keys.append("<div class='key off'><span class=d>#</span></div>")

    rows = [(name, "Linphone: " + u, "app", u) for u, name in apps.items()]
    rows += [(name, pretty(n), "number", n) for n, name in numbers.items()]
    people = "".join(
        f"<li><div><div class=who>{esc(name)}</div><div class=num>{esc(how)}</div></div>"
        f"<form method=post action=/allowed/del><input type=hidden name=kind value={kind}>"
        f"<input type=hidden name=id value='{esc(ident)}'><button class=danger>Remove</button></form></li>"
        for name, how, kind, ident in sorted(rows, key=lambda r: r[0].lower()))
    if not people:
        people = "<li class=empty-state>Nobody yet. Until you add someone, every incoming call is hung up.</li>"

    house = cfg.get("house_address", "")
    how_to = (f" They call <b>{esc(house)}</b> from the Linphone app." if house
              else " Add the phone's Linphone address in <a href='/settings'>Settings</a> so you can see it here.")

    body = f"""{note(msg, error)}
<div class=card>
<div style='display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap'>
<h2>{esc(possessive(kid))} buttons</h2><div class=pills>{pills}</div></div>
<p class=sub>Tap a button to choose who it calls. Buttons without a name do nothing.</p>
<div class=keys>{''.join(keys)}</div>
</div>
<div class=card>
<h2>Who can call {esc(kid)}</h2>
<p class=sub>Only these people make the phone ring. Everyone else is hung up on.{how_to}</p>
<ul class=list>{people}</ul>
<form method=post action=/allowed>
<div class=row>
<div><label for=an>Name</label><input id=an type=text name=name maxlength=40 placeholder="Nana" required></div>
<div><label for=au>Their Linphone username</label><input id=au type=text name=contact placeholder="nana123"
autocapitalize=none autocorrect=off required></div>
</div>
<div class=actions><button>Allow this person</button></div>
</form>
</div>"""
    return layout(f"{possessive(kid)} phone", body, cfg)


def key_page(cfg, d, error=None, form=None):
    kid = child(cfg)
    speed, names = entries("speed"), entries("speedname")
    cur = speed.get(d, "")
    form = form or {}
    name = form.get("name", names.get(d, ""))
    contact = form.get("contact", shown(cur) if cur else "")
    remove = ""
    if cur:
        remove = (f"<form method=post action=/key/del style='margin-top:12px'><input type=hidden name=d value='{d}'>"
                  f"<button class=danger>Clear button {d}</button></form>")
    body = f"""{note(None, error)}
<div class=card>
<h2>Button {d}</h2>
<p class=sub>When {esc(kid)} presses {d}, the phone calls this person.</p>
<form method=post action=/key>
<input type=hidden name=d value='{d}'>
<label for=nm>Name</label>
<input id=nm type=text name=name maxlength=40 value='{esc(name)}' placeholder="Mama" required>
<label for=ct>Their Linphone username</label>
<input id=ct type=text name=contact value='{esc(contact)}' placeholder="mama123" autocapitalize=none autocorrect=off required>
<div class=hint>The username they chose in the Linphone app. They are also added to "Who can call {esc(kid)}".</div>
<div class=actions><button>Save button {d}</button><a class='btn ghost' href='/'>Cancel</a></div>
</form>
{remove}
</div>"""
    return layout(f"Button {d}", body, cfg)


def settings_page(cfg, msg="", error=None):
    body = f"""{note(msg, error)}
<div class=card>
<h2>Phone</h2>
<form method=post action=/settings>
<label for=cn>Your child's name</label>
<input id=cn type=text name=child_name maxlength=40 value='{esc(cfg.get("child_name", ""))}' required>
<label for=ha>The phone's Linphone address</label>
<input id=ha type=text name=house_address maxlength=64 value='{esc(cfg.get("house_address", ""))}' placeholder="samhome"
autocapitalize=none autocorrect=off>
<div class=hint>The Linphone username relatives dial to reach the phone. Shown on the main page as a reminder;
changing it here does not change the server's sign-in.</div>
<div class=actions><button>Save</button><a class='btn ghost' href='/'>Back</a></div>
</form>
</div>
<div class=card>
<h2>Change password</h2>
<form method=post action=/password>
<input type=hidden name=username value='{esc(cfg.get("username", ""))}' autocomplete=username>
<label for=op>Current password</label>
<input id=op type=password name=current autocomplete=current-password required>
<label for=np>New password</label>
<input id=np type=password name=password autocomplete=new-password minlength=10 required>
<label for=np2>New password again</label>
<input id=np2 type=password name=password2 autocomplete=new-password minlength=10 required>
<div class=actions><button>Change password</button></div>
</form>
</div>"""
    return layout("Settings", body, cfg)


# ------------------------------------------------------------------ server

class Handler(BaseHTTPRequestHandler):
    server_version = "FirstPhone"
    sys_version = ""

    def signed_in(self, cfg):
        if not registered(cfg):
            return False
        for part in self.headers.get("Cookie", "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == COOKIE and "." in v:
                exp, sig = v.split(".", 1)
                if exp.isdigit() and int(exp) > time.time() and hmac.compare_digest(sig, sign(cfg, exp)):
                    return True
        return False

    def same_origin(self):
        origin = self.headers.get("Origin") or self.headers.get("Referer")
        if not origin:
            return True
        return urlsplit(origin).netloc == self.headers.get("Host", "")

    def send(self, body, code=200, headers=()):
        data = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "same-origin")
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def go(self, where, headers=()):
        self.send_response(303)
        self.send_header("Location", where)
        self.send_header("Content-Length", "0")
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()

    def session_cookie(self, cfg):
        exp = int(time.time()) + SESSION_DAYS * 86400
        return ("Set-Cookie", f"{COOKIE}={exp}.{sign(cfg, exp)}; Max-Age={SESSION_DAYS * 86400}; Path=/; "
                              f"HttpOnly; SameSite=Strict")

    def broken(self, cfg, e):
        body = (f"<div class='note err'>Can't reach Asterisk right now ({esc(e)}). "
                f"Check that the asterisk container is running.</div><a class=btn href='/'>Try again</a>")
        self.send(layout("Problem", body, cfg), 502)

    def form(self):
        length = min(int(self.headers.get("Content-Length", 0) or 0), 10_000)
        raw = self.rfile.read(length).decode("utf-8", "replace")
        return {k: v[0].strip() for k, v in parse_qs(raw).items()}

    def favicon(self):
        try:
            with open(FAVICON_PATH, "rb") as f:
                data = f.read()
        except OSError:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            return self.end_headers()
        self.send_response(200)
        self.send_header("Content-Type", "image/svg+xml")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "public, max-age=86400")
        self.end_headers()
        self.wfile.write(data)

    # -- GET
    def do_GET(self):
        url = urlsplit(self.path)
        if url.path in ("/favicon.svg", "/favicon.ico"):
            return self.favicon()
        cfg = load_config()
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        if not registered(cfg):
            return self.send(register_page()) if url.path == "/register" else self.go("/register")
        if url.path == "/register":
            return self.go("/")
        if url.path == "/login":
            return self.go("/") if self.signed_in(cfg) else self.send(login_page(cfg, msg=q.get("m", "")))
        if not self.signed_in(cfg):
            return self.go("/login")
        try:
            if url.path == "/":
                return self.send(home_page(cfg, q.get("m", "")))
            if url.path == "/key" and re.fullmatch(r"[0-9]", q.get("d", "")):
                return self.send(key_page(cfg, q["d"]))
            if url.path == "/settings":
                return self.send(settings_page(cfg, q.get("m", "")))
        except Exception as e:
            return self.broken(cfg, e)
        self.go("/")

    # -- POST
    def do_POST(self):
        path = urlsplit(self.path).path
        if not self.same_origin():
            return self.send("Forbidden", 403)
        f = self.form()
        cfg = load_config()

        if path == "/register":
            return self.register(f)
        if not registered(cfg):
            return self.go("/register")

        if path == "/login":
            with login_lock:
                ok = (hmac.compare_digest(f.get("username", "").lower().encode(), cfg["username"].lower().encode())
                      & hmac.compare_digest(hash_password(f.get("password", ""), cfg["salt"]), cfg["hash"]))
                if not ok:
                    time.sleep(1.5)
            if not ok:
                return self.send(login_page(cfg, "That username or password isn't right."), 401)
            return self.go("/", [self.session_cookie(cfg)])

        if path == "/logout":
            return self.go("/login?m=out", [("Set-Cookie", f"{COOKIE}=; Max-Age=0; Path=/; HttpOnly; SameSite=Strict")])

        if not self.signed_in(cfg):
            return self.go("/login")

        try:
            if path == "/key":
                return self.save_key(cfg, f)
            if path == "/key/del" and re.fullmatch(r"[0-9]", f.get("d", "")):
                db_del("speed", f["d"])
                db_del("speedname", f["d"])
                return self.go("/?m=removed")
            if path == "/allowed":
                return self.save_allowed(cfg, f)
            if path == "/allowed/del":
                ident = f.get("id", "")
                if f.get("kind") == "app" and LP_USER.match(ident):
                    db_del("allowedapp", ident)
                elif f.get("kind") == "number" and re.fullmatch(r"[0-9]{8,15}", ident):
                    db_del("allowed", ident)
                return self.go("/?m=removed")
            if path == "/settings":
                return self.save_settings(cfg, f)
            if path == "/password":
                return self.change_password(cfg, f)
        except Exception as e:
            return self.broken(cfg, e)
        self.go("/")

    def register(self, f):
        with config_lock:
            cfg = load_config()
            if registered(cfg):
                return self.go("/login")
            err = None
            if not NAME.match(f.get("child_name", "")):
                err = "Type your child's name."
            elif not USERNAME.match(f.get("username", "")):
                err = "Username: 3-32 letters, numbers, dots, dashes or underscores."
            elif len(f.get("password", "")) < 10:
                err = "The password needs at least 10 characters."
            elif f.get("password") != f.get("password2"):
                err = "The two passwords don't match."
            if err:
                return self.send(register_page(err, f), 400)
            salt = secrets.token_hex(16)
            cfg.update(username=f["username"], salt=salt, hash=hash_password(f["password"], salt),
                       child_name=f["child_name"], cookie_key=secrets.token_hex(32))
            cfg.setdefault("house_address", os.environ.get("HOUSE_ADDRESS", ""))
            save_config(cfg)
        try:
            db_put("config", "childname", cfg["child_name"])
        except Exception:
            pass  # Asterisk may still be starting; Settings can save it again.
        self.go("/?m=welcome", [self.session_cookie(cfg)])

    def save_key(self, cfg, f):
        d = f.get("d", "")
        if not re.fullmatch(r"[0-9]", d):
            return self.go("/")
        name = f.get("name", "")
        if not NAME.match(name):
            return self.send(key_page(cfg, d, "Give the button a name (no quote marks).", f), 400)
        kind, value, err = parse_contact(f.get("contact", ""))
        if err:
            return self.send(key_page(cfg, d, err, f), 400)
        if kind == "app":
            db_put("speed", d, f"{value}@{LP_DOMAIN}")
            db_put("allowedapp", value, name)
        else:
            db_put("speed", d, value)
            db_put("allowed", value, name)
        db_put("speedname", d, name)
        self.go("/?m=savedboth")

    def save_allowed(self, cfg, f):
        name = f.get("name", "")
        kind, value, err = parse_contact(f.get("contact", ""))
        if not NAME.match(name):
            err = "Add a name (no quote marks)."
        if err:
            return self.send(home_page(cfg, error=err), 400)
        db_put("allowedapp" if kind == "app" else "allowed", value, name)
        self.go("/?m=allowed")

    def save_settings(self, cfg, f):
        name = f.get("child_name", "")
        house = f.get("house_address", "").lower()
        if house.endswith("@" + LP_DOMAIN):
            house = house[: -len(LP_DOMAIN) - 1]
        if not NAME.match(name):
            return self.send(settings_page(cfg, error="Type your child's name."), 400)
        if house and not LP_USER.match(house):
            return self.send(settings_page(cfg, error="The Linphone address should be just the username."), 400)
        with config_lock:
            cfg = load_config()
            cfg.update(child_name=name, house_address=house)
            save_config(cfg)
        db_put("config", "childname", name)
        self.go("/settings?m=settings")

    def change_password(self, cfg, f):
        if not hmac.compare_digest(hash_password(f.get("current", ""), cfg["salt"]), cfg["hash"]):
            time.sleep(1.5)
            return self.send(settings_page(cfg, error="The current password isn't right."), 400)
        if len(f.get("password", "")) < 10:
            return self.send(settings_page(cfg, error="The new password needs at least 10 characters."), 400)
        if f.get("password") != f.get("password2"):
            return self.send(settings_page(cfg, error="The two new passwords don't match."), 400)
        with config_lock:
            cfg = load_config()
            salt = secrets.token_hex(16)
            # A new cookie key signs everyone else out.
            cfg.update(salt=salt, hash=hash_password(f["password"], salt), cookie_key=secrets.token_hex(32))
            save_config(cfg)
        self.go("/settings?m=password", [self.session_cookie(cfg)])


def seed_account():
    """Create the parent account from .env if none exists yet (skips the Register page)."""
    user, pw = os.environ.get("ADMIN_USER", ""), os.environ.get("ADMIN_PASSWORD", "")
    if not user or not pw:
        return
    with config_lock:
        cfg = load_config()
        if registered(cfg):
            return
        if not USERNAME.match(user) or len(pw) < 10:
            print("ADMIN_USER / ADMIN_PASSWORD ignored: username 3-32 simple characters, password 10+ characters")
            return
        salt = secrets.token_hex(16)
        cfg.update(username=user, salt=salt, hash=hash_password(pw, salt), cookie_key=secrets.token_hex(32))
        name = os.environ.get("CHILD_NAME", "")
        if NAME.match(name):
            cfg.setdefault("child_name", name)
        cfg.setdefault("house_address", os.environ.get("HOUSE_ADDRESS", ""))
        save_config(cfg)
        print(f"created the parent account '{user}' from .env")
    for _ in range(10):  # Asterisk may still be starting
        try:
            if cfg.get("child_name"):
                db_put("config", "childname", cfg["child_name"])
            break
        except Exception:
            time.sleep(3)


if __name__ == "__main__":
    threading.Thread(target=seed_account, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
