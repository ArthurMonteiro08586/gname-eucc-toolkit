# -*- coding: utf-8 -*-
"""Catch-all MX server for your own domains (self-hosted, ForwardEmail-free).

Runs on port 25, accepts mail for ANY address on ANY domain pointed at this box,
stores the .eml under MAIL_DIR and relays a readable copy to a Gmail inbox
(SMTP_SSL 465, app password) so OTP codes land where your IMAP readers look.

Deploy: see mail_catcher/README.md — systemd unit + env.json {gm, gp}.
Env file format (JSON): {"gm": "you@gmail.com", "gp": "app-password"}  # optional
"""
import asyncio, json, os, re, smtplib, ssl, time
from email.mime.message import MIMEMessage
from email.mime.text import MIMEText
import email as eml
from aiosmtpd.controller import Controller

BASE = os.path.dirname(os.path.abspath(__file__))
MAIL_DIR = os.path.join(BASE, "mail")
ENV_FILE = os.path.join(BASE, "env.json")
os.makedirs(MAIL_DIR, exist_ok=True)


def load_env():
    try:
        with open(ENV_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def relay_to_gmail(rcpts, raw: bytes):
    env = load_env()
    gm, gp = env.get("gm", ""), env.get("gp", "")
    if not gm or not gp:
        return "no-relay-creds"
    try:
        orig = eml.message_from_bytes(raw)
        subj = str(orig.get("Subject", ""))[:120]
        frm = str(orig.get("From", ""))[:120]
        wrap = MIMEText(
            "Caught for: %s\nFrom: %s\nSubject: %s\nTime: %s\n\n----- ORIGINAL MESSAGE -----\n\n%s"
            % (", ".join(rcpts)[:300], frm, subj, time.strftime("%Y-%m-%d %H:%M:%S"),
               orig.as_string()[:60000]),
            "plain", "utf-8")
        wrap["Subject"] = "[catch %s] %s" % (rcpts[0][:60], subj)
        wrap["From"] = gm
        wrap["To"] = gm
        s = smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=45,
                             context=ssl.create_default_context())
        s.login(gm, gp)
        s.sendmail(gm, [gm], wrap.as_string())
        s.quit()
        return "relayed"
    except Exception as e:
        return "relay-fail: %s %s" % (type(e).__name__, str(e)[:100])


class CatchAll:
    async def handle_RCPT(self, server, session, envelope, address, rcpt_options):
        envelope.rcpt_tos.append(address)
        return "250 OK"

    async def handle_DATA(self, server, session, envelope):
        rcpts = list(envelope.rcpt_tos)
        raw = envelope.content
        if isinstance(raw, str):
            raw = raw.encode("utf-8", "replace")
        ts = time.strftime("%Y%m%d-%H%M%S")
        safe = re.sub(r"[^A-Za-z0-9@._-]", "_", rcpts[0] if rcpts else "none")[:80]
        path = os.path.join(MAIL_DIR, "%s_%s.eml" % (ts, safe))
        with open(path, "wb") as f:
            f.write(raw)
        status = relay_to_gmail(rcpts, raw)
        print("[catch] %s -> %s (%s) %d bytes" % (envelope.mail_from, rcpts, status, len(raw)), flush=True)
        return "250 Message accepted for delivery"


def main():
    host = os.environ.get("CATCH_HOST", "0.0.0.0")
    port = int(os.environ.get("CATCH_PORT", "25"))
    c = Controller(CatchAll(), hostname=host, port=port, server_hostname="mail.local")
    c.start()
    print("[catch] listening on %s:%d, maildir=%s" % (host, port, MAIL_DIR), flush=True)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        c.stop()


if __name__ == "__main__":
    main()
