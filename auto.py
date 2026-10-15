# -*- coding: utf-8 -*-
"""auto.py - one-command full pipeline.

  python auto.py --domains 2 [--prefix myname] [--mail cf|dns] [--serve]

Steps:
  1. login        - fresh cookies (skipped if valid cookies exist and --relogin not given)
  2. claim        - N free .eu.cc domains (voucher = $0.00)
  3. mail setup:
       --mail fwd : ForwardEmail catch-all via gname DNS (MX mx1/mx2.forwardemail.net
                    + TXT forward-email=MAIL_DEST). NO Cloudflare account needed;
                    any name@DOMAIN lands in MAIL_DEST (default: GM_EMAIL) instantly.
       --mail cf  : Cloudflare zone + Email Routing catch-all (needs CF_API_TOKEN,
                    CF_ACCOUNT_ID, CF_DEST_EMAIL), then sets gname NS to Cloudflare
       --mail dns : direct gname DNS records (A mail -> DNS_A_IP, MX @ -> mail.DOM)
                    for a self-hosted mail server
  4. status       - everything recorded to data/status.json + data/eucc_domains.jsonl
  5. --serve      - start dashboard after the run (http://127.0.0.1:8570)

Registering a NEW account instead of using an existing one: python gname_reg.py
"""
import sys, os, json, time, random, argparse, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from gname_core import BASE, DOMAINS_F, STATUS_F, log, load_status, save_status, domains

PY = sys.executable

def run(script, *args):
    cmd = [PY, os.path.join(HERE, script)] + list(args)
    log("$", " ".join(cmd))
    r = subprocess.run(cmd, cwd=HERE)
    return r.returncode

def cf_setup(dom):
    """Cloudflare zone + catch-all; returns dict with nameservers."""
    import cf_mail
    import io, contextlib
    buf = io.StringIO()
    rc = 1
    with contextlib.redirect_stdout(buf):
        try:
            rc = cf_mail.setup(dom)
        except SystemExit as e:
            rc = int(e.code or 1)
    out = buf.getvalue()
    log(out.strip())
    try:
        js = [json.loads(chunk) for chunk in re_json_chunks(out)]
        merged = {}
        for j in js:
            merged.update(j)
        return merged if rc == 0 else {"error": out[-300:]}
    except Exception:
        return {"error": out[-300:]}

def re_json_chunks(s):
    dec = json.JSONDecoder()
    i = 0
    while i < len(s):
        j = s.find("{", i)
        if j < 0:
            break
        try:
            obj, end = dec.raw_decode(s[j:])
            yield s[j:j + end]
            i = j + end
        except Exception:
            i = j + 1

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--domains", type=int, default=1)
    ap.add_argument("--prefix", default="reformwk")
    ap.add_argument("--mail", choices=["fwd", "cf", "dns", "none"], default="none")
    ap.add_argument("--relogin", action="store_true")
    ap.add_argument("--serve", action="store_true")
    args = ap.parse_args()

    st = load_status()

    # 1. login
    if args.relogin or not os.path.exists(os.path.join(BASE, "gname_cookies.json")):
        if run("login.py") != 0:
            log("LOGIN FAILED - abort"); return 1

    # 2. claim
    existing = {d["domain"] for d in domains()}
    claimed = []
    tries = 0
    while len(claimed) < args.domains and tries < args.domains + 3:
        tries += 1
        name = "%s%d" % (args.prefix, random.randint(10, 99))
        dom = name + ".eu.cc"
        if dom in existing:
            continue
        rc = run("claim_domain.py", name)
        if rc == 0:
            claimed.append(dom)
            existing.add(dom)
            log("CLAIMED:", dom)
        else:
            log("claim failed for", dom, "rc", rc)
        time.sleep(random.uniform(15, 30))

    # 3. mail
    for dom in claimed:
        st.setdefault(dom, {})
        if args.mail == "fwd":
            dest = os.environ.get("MAIL_DEST") or os.environ.get("GM_EMAIL", "")
            if not dest:
                log("MAIL_DEST/GM_EMAIL not set - skip mail"); continue
            run("setup_dns.py", dom,
                "--mx", "@=mx1.forwardemail.net:10",
                "--mx", "@=mx2.forwardemail.net:100",
                "--txt", "@=forward-email=" + dest)
            st[dom]["mail"] = "forwardemail-catchall"
            st[dom]["mail_dest"] = dest
        elif args.mail == "cf" and os.environ.get("CF_API_TOKEN"):
            r = cf_setup(dom)
            st[dom].update({"mail": "cloudflare-catchall", "cf": r})
            ns = r.get("nameservers") or []
            if ns:
                run("setup_dns.py", dom, "--ns", ",".join(ns))
                st[dom]["ns_set"] = ns
        elif args.mail == "dns":
            ip = os.environ.get("DNS_A_IP", "")
            if os.environ.get("GNAME_UID"):
                # ensure operation protection is SET (MFA + czyz[1,4]);
                # without it jx_edit writes fail with -101 on fresh accounts
                st[dom]["mfa_bind_rc"] = run("mfa_bind.py", "--uid", os.environ["GNAME_UID"])
            a_args = ["--a", "mail=" + ip] if ip else []
            t_args = ["--txt", "@=v=spf1 ip4:" + ip + " ~all"] if ip else []
            run("setup_dns.py", dom, *a_args, "--mx", "@=mail." + dom + ":5", *t_args)
            st[dom]["mail"] = "self-hosted-mx"
        else:
            st[dom]["mail"] = st[dom].get("mail", "pending")
        save_status(st)

    save_status(st)
    log("=== SUMMARY ===")
    log("claimed:", claimed or "none")
    log("bank:", DOMAINS_F, "status:", STATUS_F)
    log("next: python dashboard.py  (or auto.py --serve)")

    if args.serve:
        run("dashboard.py")
    return 0

if __name__ == "__main__":
    sys.exit(main())
