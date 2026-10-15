# -*- coding: utf-8 -*-
"""otp_api.py — HTTP API over the catcher mailbox store (port 2525, stdlib only).

Endpoints:
  GET /next?domain=reformwk59.eu.cc        -> {"address": "user42@domain"}  (least-recently-used free mailbox)
  GET /acquire?address=user42@domain&ttl=600 -> lock mailbox to caller (X-Client-Id header optional)
  GET /latest?address=user42@domain&wait=60 -> {"found": true, "subject":..., "body":..., "code": "123456", "ts":...}
                                               long-polls up to `wait` seconds for new mail
  GET /list?domain=reformwk59.eu.cc        -> recent addresses with mail
  GET /health                              -> ok

State: mailboxes.json (address -> {last_used, locked_until, client}) next to script.
Mail source: ../mail/*.eml written by catcher.py (filename contains recipient).

Run on the VPS:  python3 otp_api.py   (systemd: otpapi.service)
"""
import email as eml
import json
import os
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
MAILDIR = os.path.join(HERE, "mail")
STATE_F = os.path.join(HERE, "mailboxes.json")
PORT = int(os.environ.get("OTP_API_PORT") or 2525)
POOL = int(os.environ.get("OTP_POOL") or 500)  # user1..userN per domain

CODE_RE = re.compile(r"(?:verification code is|code is|code|код)[:\s]*([0-9]{4,8})", re.I)


def load_state():
    try:
        return json.load(open(STATE_F, encoding="utf-8"))
    except Exception:
        return {}


def save_state(st):
    tmp = STATE_F + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f)
    os.replace(tmp, STATE_F)


def mails_for(address):
    """Scan MAILDIR for .eml whose filename/body contains address; newest first."""
    out = []
    if not os.path.isdir(MAILDIR):
        return out
    low = address.lower()
    for fn in os.listdir(MAILDIR):
        if not fn.endswith(".eml"):
            continue
        p = os.path.join(MAILDIR, fn)
        try:
            if low not in fn.lower():
                head = open(p, "rb").read(2048).decode(errors="replace").lower()
                if low not in head:
                    continue
            raw = open(p, "rb").read()
            msg = eml.message_from_bytes(raw)
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        body = part.get_payload(decode=True).decode(errors="replace")
                        break
                if not body:
                    body = str(msg.get_payload())
            else:
                payload = msg.get_payload(decode=True)
                body = payload.decode(errors="replace") if isinstance(payload, bytes) else str(payload or "")
            out.append({
                "file": fn, "mtime": os.path.getmtime(p),
                "subject": str(msg.get("Subject") or ""),
                "from": str(msg.get("From") or ""),
                "body": body[:4000],
            })
        except Exception:
            continue
    out.sort(key=lambda x: -x["mtime"])
    return out


class H(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _json(self, obj, code=200):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        st = load_state()
        now = time.time()
        if u.path == "/health":
            return self._json({"ok": True, "mails": len(os.listdir(MAILDIR)) if os.path.isdir(MAILDIR) else 0})
        if u.path == "/next":
            dom = q.get("domain", "").lower()
            if not dom:
                return self._json({"error": "domain required"}, 400)
            taken = {a for a, v in st.items() if a.endswith("@" + dom) and (v.get("locked_until", 0) > now or v.get("last_used", 0) > now - 3600)}
            picked = None
            for i in range(1, POOL + 1):
                cand = "user%d@%s" % (i, dom)
                if cand in taken:
                    continue
                picked = cand
                break
            if not picked:
                return self._json({"error": "pool exhausted"}, 503)
            st[picked] = {"last_used": now, "locked_until": now + int(q.get("ttl", 600)), "client": self.headers.get("X-Client-Id", "")}
            save_state(st)
            return self._json({"address": picked})
        if u.path == "/acquire":
            addr = q.get("address", "").lower()
            st[addr] = {"last_used": now, "locked_until": now + int(q.get("ttl", 600)), "client": self.headers.get("X-Client-Id", "")}
            save_state(st)
            return self._json({"acquired": addr})
        if u.path == "/latest":
            addr = q.get("address", "").lower()
            wait = min(int(q.get("wait", 60)), 300)
            since = float(q.get("since", 0))
            t0 = time.time()
            while True:
                ms = [m for m in mails_for(addr) if m["mtime"] > since]
                if ms:
                    m = ms[0]
                    code = ""
                    mm = CODE_RE.search(m["body"]) or CODE_RE.search(m["subject"])
                    if mm:
                        code = mm.group(1)
                    return self._json({"found": True, "subject": m["subject"], "from": m["from"],
                                       "body": m["body"][:2000], "code": code, "ts": m["mtime"]})
                if time.time() - t0 > wait:
                    return self._json({"found": False})
                time.sleep(2)
        if u.path == "/list":
            dom = q.get("domain", "").lower()
            seen = {}
            for fn in os.listdir(MAILDIR) if os.path.isdir(MAILDIR) else []:
                mm = re.search(r"catch ([^@\]]+@[^@\]]+)\]", fn)
                if mm and (not dom or mm.group(1).endswith(dom)):
                    seen[mm.group(1)] = max(seen.get(mm.group(1), 0), os.path.getmtime(os.path.join(MAILDIR, fn)))
            return self._json({"addresses": sorted(seen, key=lambda a: -seen[a])[:50]})
        return self._json({"error": "unknown path"}, 404)


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), H)
    print("otp_api listening :%d maildir=%s" % (PORT, MAILDIR), flush=True)
    srv.serve_forever()
