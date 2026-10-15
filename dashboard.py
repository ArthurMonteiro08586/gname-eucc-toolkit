# -*- coding: utf-8 -*-
"""Dashboard for the gname-eucc toolkit - stdlib only.

Shows: domains bank (data/eucc_domains.jsonl), pipeline status (data/status.json),
live OTP inbox (IMAP over GM_EMAIL/GM_APPPW - catch-all forwarded codes).

Env: GNAME_DASH_PORT (default 8570), GNAME_DASH_HOST (default 127.0.0.1)
Usage: python dashboard.py
"""
import os, json, time, html, re, imaplib, email as eml
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from gname_core import BASE, DOMAINS_F, STATUS_F, domains, load_status, log

HOST = os.environ.get("GNAME_DASH_HOST", "127.0.0.1")
PORT = int(os.environ.get("GNAME_DASH_PORT", "8570"))

CSS = """body{background:#0d1117;color:#e6edf3;font:14px/1.5 Consolas,monospace;margin:24px}
h1{color:#58a6ff;font-size:20px}h2{color:#7ee787;font-size:16px;margin-top:28px}
table{border-collapse:collapse;width:100%}td,th{border:1px solid #30363d;padding:6px 10px;text-align:left}
th{background:#161b22}.ok{color:#7ee787}.warn{color:#d29922}.err{color:#f85149}
.card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px 16px;margin:8px 0}
code{background:#21262d;padding:2px 6px;border-radius:4px}a{color:#58a6ff}"""

def inbox(limit=20):
    gm, gp = os.environ.get("GM_EMAIL", ""), os.environ.get("GM_APPPW", "")
    if not (gm and gp):
        return None
    try:
        m = imaplib.IMAP4_SSL("imap.gmail.com")
        m.login(gm, gp)
        m.select("INBOX")
        since = time.strftime("%d-%b-%Y", time.localtime(time.time() - 3 * 86400))
        typ, data = m.search(None, "(SINCE %s)" % since)
        ids = data[0].split()[-limit:]
        rows = []
        for i in reversed(ids):
            typ, d = m.fetch(i, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
            head = d[0][1].decode("utf-8", "ignore")
            msg = eml.message_from_string(head)
            subj = msg.get("Subject", "")
            frm = msg.get("From", "")
            code = ""
            mm = re.search(r"\b(\d{4,8})\b", subj)
            if mm:
                code = mm.group(1)
            rows.append({"from": frm[:60], "subject": subj[:90], "date": msg.get("Date", "")[:31], "code": code})
        m.logout()
        return rows
    except Exception as e:
        return [{"error": str(e)[:120]}]

def page():
    doms = domains()
    st = load_status()
    p = ["<!doctype html><meta charset=utf-8><style>%s</style>" % CSS]
    p.append("<h1>gname-eucc toolkit</h1>")
    p.append("<div class=card>domains: <b>%d</b> &nbsp;|&nbsp; state dir: <code>%s</code> &nbsp;|&nbsp; %s</div>"
             % (len(doms), html.escape(BASE), time.strftime("%Y-%m-%d %H:%M:%S")))
    p.append("<h2>Domains</h2><table><tr><th>domain</th><th>status</th><th>price</th><th>claimed</th><th>mail mode</th><th>ns</th></tr>")
    for d in doms:
        ds = st.get(d["domain"], {})
        cls = "ok" if d.get("status") in ("active", "submitted") else "warn"
        p.append("<tr><td><b>%s</b></td><td class=%s>%s</td><td>$%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
            html.escape(d["domain"]), cls, html.escape(str(d.get("status"))), d.get("price_usd", 0),
            html.escape(str(d.get("ts", ""))), html.escape(str(ds.get("mail", "-"))),
            html.escape(",".join(ds.get("nameservers", [])) or "-")))
    p.append("</table>")
    if st:
        p.append("<h2>Pipeline status</h2><div class=card><pre>%s</pre></div>"
                 % html.escape(json.dumps(st, indent=1)[:3000]))
    ib = inbox()
    p.append("<h2>OTP inbox (catch-all &rarr; Gmail)</h2>")
    if ib is None:
        p.append("<div class=card>set <code>GM_EMAIL</code> + <code>GM_APPPW</code> to see forwarded codes</div>")
    elif ib and "error" in ib[0]:
        p.append("<div class='card err'>IMAP: %s</div>" % html.escape(ib[0]["error"]))
    else:
        p.append("<table><tr><th>code</th><th>from</th><th>subject</th><th>date</th></tr>")
        for r in ib:
            p.append("<tr><td class=ok><b>%s</b></td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
                html.escape(r.get("code", "")), html.escape(r.get("from", "")),
                html.escape(r.get("subject", "")), html.escape(r.get("date", ""))))
        p.append("</table>")
    p.append("<p><a href=/api/domains>/api/domains</a> <a href=/api/inbox>/api/inbox</a> <a href=/api/status>/api/status</a></p>")
    return "".join(p)

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/api/domains":
            body = json.dumps(domains()).encode()
        elif u.path == "/api/status":
            body = json.dumps(load_status()).encode()
        elif u.path == "/api/inbox":
            body = json.dumps(inbox() or []).encode()
        else:
            body = page().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json" if u.path.startswith("/api") else "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *a):
        pass

if __name__ == "__main__":
    log("dashboard on http://%s:%d" % (HOST, PORT))
    HTTPServer((HOST, PORT), H).serve_forever()
