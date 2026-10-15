# -*- coding: utf-8 -*-
"""submit.py — authenticated SMTP submission (port 587) with real outbound delivery.

Clients auth with LOGIN (user = anything@yourdomain, pass = env sp), then mail is
delivered DIRECTLY to recipient MX from the VPS (From: you@yourdomain preserved).

Zero deps beyond aiosmtpd (same as catcher.py). Pure-python MX resolver included.

Run:  python3 submit.py            (port 587, env file next to script: env.json {sp})
Test: swaks --server VPS --port 587 --auth LOGIN --auth-user me@reformwk59.eu.cc \
        --auth-password $SP --to someone@gmail.com --from me@reformwk59.eu.cc
Or python: smtplib.SMTP(host,587) -> starttls() -> login('me@domain', SP) -> sendmail(...)

NOTE: add SPF to the domain for deliverability:
  setup_dns.py <domain> --txt "@=v=spf1 ip4:<VPS_IP> ~all"
"""
import asyncio, json, os, re, smtplib, socket, ssl, struct, random, sys, time
from aiosmtpd.controller import Controller
from aiosmtpd.smtp import SMTP as SMTPsrv, LoginPassword, AuthResult

HERE = os.path.dirname(os.path.abspath(__file__))
ENV = json.load(open(os.path.join(HERE, "env.json"))) if os.path.exists(os.path.join(HERE, "env.json")) else {}
SP = ENV.get("sp") or os.environ.get("SUBMIT_PASS") or ""
PORT = int(ENV.get("submit_port") or os.environ.get("SUBMIT_PORT") or 587)
LOG = os.path.join(HERE, "submit.log")


def log(*a):
    line = " ".join(str(x) for x in a)
    print(time.strftime("[%H:%M:%S]"), line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ---------- minimal DNS MX resolver (no deps) ----------
def _qname(name):
    return b"".join(bytes([len(p)]) + p.encode() for p in name.split(".") if p) + b"\x00"


def _parse_name(msg, off):
    labels, jumped, orig = [], False, off
    while True:
        ln = msg[off]
        if ln == 0:
            off += 1
            break
        if ln & 0xC0 == 0xC0:
            ptr = struct.unpack("!H", msg[off:off + 2])[0] & 0x3FFF
            if not jumped:
                orig = off + 2
            off, jumped = ptr, True
            continue
        labels.append(msg[off + 1:off + 1 + ln].decode(errors="replace"))
        off += ln + 1
    return ".".join(labels), (orig if jumped else off)


def resolve_mx(domain, timeout=6):
    """Return list of (prio, host) for domain; falls back to A of domain itself."""
    tid = random.randint(0, 65535)
    q = struct.pack("!HHHHHH", tid, 0x0100, 1, 0, 0, 0) + _qname(domain) + struct.pack("!HH", 15, 1)
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(timeout)
        for dns in ("1.1.1.1", "8.8.8.8"):
            try:
                s.sendto(q, (dns, 53))
                msg, _ = s.recvfrom(4096)
                ancount = struct.unpack("!H", msg[6:8])[0]
                if ancount == 0:
                    continue
                # skip question
                _, off = _parse_name(msg, 12)
                off += 4
                out = []
                for _ in range(ancount):
                    _, off = _parse_name(msg, off)
                    rtype, rdlen = struct.unpack("!HH", msg[off + 8:off + 12])
                    rd_start = off + 10
                    if rtype == 15:
                        prio = struct.unpack("!H", msg[rd_start:rd_start + 2])[0]
                        exch, _ = _parse_name(msg, rd_start + 2)
                        out.append((prio, exch.rstrip(".")))
                    off = rd_start + rdlen
                s.close()
                if out:
                    return sorted(out)
            except Exception:
                continue
        s.close()
    except Exception:
        pass
    try:
        socket.gethostbyname(domain)
        return [(10, domain.rstrip("."))]
    except Exception:
        return []


def deliver(mail_from, rcpt, data):
    dom = rcpt.split("@")[-1].lower()
    mxs = resolve_mx(dom)
    errs = []
    for prio, host in mxs[:4]:
        try:
            ip = socket.gethostbyname(host)
            s = smtplib.SMTP(ip, 25, timeout=30)
            s.ehlo(socket.gethostname() or "submit")
            try:
                s.starttls(context=ssl.create_default_context())
                s.ehlo()
            except Exception:
                pass
            s.sendmail(mail_from, [rcpt], data)
            s.quit()
            log("DELIVERED", rcpt, "via", host, ip)
            return True
        except Exception as e:
            errs.append("%s:%s:%s" % (host, type(e).__name__, str(e)[:60]))
    log("DIRECT FAIL", rcpt, "|".join(errs), "-> trying gmail relay")
    return relay_gmail(rcpt, data)


def relay_gmail(rcpt, data):
    gm, gp = ENV.get("gm"), ENV.get("gp")
    if not gm or not gp:
        log("RELAY FAIL no gm/gp in env.json")
        return False
    try:
        s = smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=45)
        s.login(gm, gp)
        s.sendmail(gm, [rcpt], data)
        s.quit()
        log("RELAYED via gmail ->", rcpt)
        return True
    except Exception as e:
        log("RELAY FAIL", rcpt, type(e).__name__, str(e)[:120])
        return False


def authenticator(server, session, envelope, mechanism, auth_data):
    if not SP:
        return AuthResult(success=False, handled=False)
    if not isinstance(auth_data, LoginPassword):
        return AuthResult(success=False, handled=False)
    if auth_data.password.decode(errors="replace") == SP:
        return AuthResult(success=True, handled=True, auth_data=auth_data)
    return AuthResult(success=False, handled=False)


class SubmitHandler:
    async def handle_DATA(self, server, session, envelope):
        ok = deliver(envelope.mail_from, envelope.rcpt_tos[0], envelope.content)
        return "250 OK" if ok else "451 delivery failed"


def _tls_context():
    cert = os.path.join(HERE, "cert.pem")
    key = os.path.join(HERE, "key.pem")
    if os.path.exists(cert) and os.path.exists(key):
        c = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        c.load_cert_chain(cert, key)
        return c
    return None


def main():
    if not SP:
        print("FATAL: set sp in env.json or SUBMIT_PASS env", file=sys.stderr)
        return 1
    c = Controller(SubmitHandler(), hostname="0.0.0.0", port=PORT,
                   authenticator=authenticator,
                   auth_required=True, auth_require_tls=False,
                   tls_context=_tls_context())
    c.start()
    log("submit listening :%d (auth LOGIN, pass from env)" % PORT)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        c.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
