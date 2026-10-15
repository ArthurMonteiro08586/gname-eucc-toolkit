# -*- coding: utf-8 -*-
"""Gname DNS automation via in-page /user_ym/jx_edit (A/MX/TXT/CNAME/NS records).

Handles operation protection (czyz) automatically: challenge -> email code
(IMAP) -> /user_zh/aqbh_check -> retry.

Usage:
  python setup_dns.py DOMAIN --a mail=1.2.3.4 [--mx @=mail.DOMAIN:10] [--txt @=v=spf1...]
  python setup_dns.py DOMAIN --ns ns1.example.com,ns2.example.com
Env: GM_EMAIL/GM_APPPW (czyz code), DNS_A_IP fallback for --a mail=<ip>
"""
import sys, os, json, time, argparse
from playwright.sync_api import sync_playwright
from gname_core import (SITE, log, mk_context, save_cookies, csrf, inpost,
                        inpost_json, czyz_unlock, ensure_czyz_channel,
                        aqbh_session_unlock)

IFRAME = SITE + "/user/iframe#/jie_info/ym=%s/dns=a.share-dns.com,b.share-dns.net"

_unlocked = False

def jx_edit(page, dom, rec, tag):
    """rec = {zj, lx, jlz, mx}. Returns parsed json; auto-unlocks czyz once."""
    global _unlocked
    tok = csrf(page)
    body = {"ym": dom, "ttl": "600", "xl": "0", "jxid": "", "csrf_token": tok}
    body.update(rec)
    r = inpost_json(page, "/user_ym/jx_edit", body, tag)
    j = r if isinstance(r, dict) else {}
    data = j.get("data")
    if isinstance(data, dict) and (data.get("yxyz") or j.get("token")):
        gm = os.environ.get("GM_EMAIL", "")
        if czyz_unlock(page, j, gm):
            time.sleep(2)
            r = inpost_json(page, "/user_ym/jx_edit", body, tag + "r")
    elif j.get("code") == -101 and not _unlocked:
        # 'please set operation protection' with no challenge token:
        # unlock the whole session via email code (proven eucc30 flow)
        log("JX -101: session aqbh unlock via email code")
        _unlocked = aqbh_session_unlock(page)
        if _unlocked:
            time.sleep(2)
            r = inpost_json(page, "/user_ym/jx_edit", body, tag + "r2")
    return r

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("domain")
    ap.add_argument("--a", action="append", default=[], help="subdomain=IP")
    ap.add_argument("--mx", action="append", default=[], help="subdomain=host:prio")
    ap.add_argument("--txt", action="append", default=[], help="subdomain=value")
    ap.add_argument("--cname", action="append", default=[], help="subdomain=target")
    ap.add_argument("--ns", default="", help="ns1,ns2 - change nameservers")
    args = ap.parse_args()
    dom = args.domain

    recs = []
    for s in args.a:
        zj, jlz = s.split("=", 1)
        recs.append({"zj": zj, "lx": "A", "jlz": jlz, "mx": 0})
    for s in args.mx:
        zj, rest = s.split("=", 1)
        jlz, _, prio = rest.partition(":")
        recs.append({"zj": zj, "lx": "MX", "jlz": jlz, "mx": int(prio or 10)})
    for s in args.txt:
        zj, jlz = s.split("=", 1)
        recs.append({"zj": zj, "lx": "TXT", "jlz": jlz, "mx": 0})
    for s in args.cname:
        zj, jlz = s.split("=", 1)
        recs.append({"zj": zj, "lx": "CNAME", "jlz": jlz, "mx": 0})
    if not recs and not args.ns:
        dip = os.environ.get("DNS_A_IP", "")
        if dip:
            recs = [{"zj": "mail", "lx": "A", "jlz": dip, "mx": 0},
                    {"zj": "@", "lx": "MX", "jlz": "mail." + dom, "mx": 10}]
        else:
            log("nothing to do: pass --a/--mx/--txt/--ns or DNS_A_IP")
            return 1

    with sync_playwright() as pw:
        browser, ctx = mk_context(pw)
        page = ctx.new_page()
        page.goto(IFRAME % dom, wait_until="domcontentloaded", timeout=60000)
        time.sleep(8)
        ensure_czyz_channel(page)

        if args.ns:
            nsl = [x.strip() for x in args.ns.split(",") if x.strip()]
            r = inpost_json(page, "/user_ym/dns_edit", {"ym": dom, "dns[]": nsl, "csrf_token": csrf(page)}, "ns")
            log("NS dns_edit:", str(r)[:250])
            if str(r).find('"code":1') < 0 and str(r).find('"code":"1"') < 0:
                j = r if isinstance(r, dict) else {}
                data = j.get("data")
                if isinstance(data, dict) and (data.get("yxyz") or j.get("token")):
                    czyz_unlock(page, j, os.environ.get("GM_EMAIL", ""))
                    time.sleep(2)
                    r = inpost_json(page, "/user_ym/dns_edit", {"ym": dom, "dns[]": nsl, "csrf_token": csrf(page)}, "nsr")
                    log("NS retry:", str(r)[:250])

        for i, rec in enumerate(recs):
            r = jx_edit(page, dom, rec, "jx%d" % i)
            log("JX %s %s=%s:" % (rec["lx"], rec["zj"], rec["jlz"][:40]), str(r)[:200])
            time.sleep(2)

        r = inpost_json(page, "/user_ym/get_jx_list", {"ym": dom, "csrf_token": csrf(page)}, "lst")
        recs_now = (r or {}).get("data") if isinstance(r, dict) else None
        if isinstance(recs_now, list):
            for x in recs_now:
                log("RECORDS:", x.get("zjt"), x.get("lx"), str(x.get("jxz"))[:60], "prio", x.get("mx"))
        else:
            log("RECORDS:", str(r)[:600])
        save_cookies(ctx)
        browser.close()
    return 0

if __name__ == "__main__":
    sys.exit(main())
