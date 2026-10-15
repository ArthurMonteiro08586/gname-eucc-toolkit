# -*- coding: utf-8 -*-
"""dns_clean.py <domain> [--match SUBSTR ...] [--ip OLD_IP] — list DNS records and delete matches.

Proven endpoints: POST /user_ym/get_jx_list (records w/ ids), POST /user_ym/jx_del {ym, jxid}.
Use to purge stale records (e.g. old forwardemail MX/TXT or duplicate A mail=<old-ip>).
"""
import sys, os, time, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gname_core import SITE, log, mk_context, save_cookies, csrf, inpost_json, ensure_czyz_channel
from playwright.sync_api import sync_playwright


def main():
    dom = sys.argv[1]
    matches, only_ip = [], ""
    i = 2
    while i < len(sys.argv):
        if sys.argv[i] == "--match":
            matches.append(sys.argv[i + 1].lower()); i += 2
        elif sys.argv[i] == "--ip":
            only_ip = sys.argv[i + 1]; i += 2
        else:
            i += 1

    with sync_playwright() as pw:
        browser, ctx = mk_context(pw)
        page = ctx.new_page()
        page.goto(SITE + "/user/iframe#/jie_info/ym=%s/dns=a.share-dns.com,b.share-dns.net" % dom,
                  wait_until="domcontentloaded", timeout=60000)
        time.sleep(10)
        ensure_czyz_channel(page)
        tok = csrf(page)
        r = inpost_json(page, "/user_ym/get_jx_list", {"ym": dom, "csrf_token": tok}, "list")
        data = (r or {}).get("data") or []
        for x in data:
            print("REC", x.get("id"), x.get("zjt"), x.get("lx"), str(x.get("jxz"))[:60],
                  "prio", x.get("mx"), flush=True)
        doomed = []
        for rec in data:
            v = json.dumps(rec).lower()
            if matches and any(m in v for m in matches):
                doomed.append(rec)
            elif only_ip and rec.get("lx") == "A" and rec.get("jxz") == only_ip:
                doomed.append(rec)
        for rec in doomed:
            rr = inpost_json(page, "/user_ym/jx_del",
                             {"ym": dom, "jxid": rec.get("id"), "id": rec.get("id"), "csrf_token": tok},
                             "del")
            ok = isinstance(rr, dict) and rr.get("code") == 1
            print("DEL", rec.get("id"), rec.get("zjt"), rec.get("lx"), "->", "OK" if ok else str(rr)[:120], flush=True)
            time.sleep(1.5)
        save_cookies(ctx)
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
