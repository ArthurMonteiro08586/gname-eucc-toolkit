# -*- coding: utf-8 -*-
"""list_domains.py - list LIVE domains on the logged-in gname account.

Uses the real dashboard API: POST /user_ym/get_ym_list  (discovered via eucc.js).
Usage:  python login.py [IDX] && python list_domains.py [--json]
Output: domain | expire | auto-renew | status  (+ free-renewal availability)
"""
import sys, os, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.sync_api import sync_playwright
from gname_core import SITE, mk_context, log, inpost_json, csrf

def main():
    as_json = "--json" in sys.argv
    with sync_playwright() as pw:
        browser, ctx = mk_context(pw)
        page = ctx.new_page()
        page.set_default_timeout(30000)
        page.goto(SITE + "/user/iframe#/index", wait_until="domcontentloaded", timeout=60000)
        time.sleep(6)
        tok = csrf(page)
        r = inpost_json(page, "/user_ym/get_ym_list", {"page": 1, "limit": 50, "csrf_token": tok}, "ymlist")
        browser.close()
    code = (r or {}).get("code")
    data = (r or {}).get("data") or []
    if code != 1:
        log("API ERR:", json.dumps(r, ensure_ascii=False)[:300])
        return 1
    out = []
    for d in data:
        out.append({
            "domain": d.get("ym"),
            "expire": d.get("dqsj"),
            "autorenew": d.get("sfxufei"),
            "status": d.get("ztstr") or d.get("zt"),
            "coupon_used": d.get("yhqid"),
        })
    if as_json:
        print(json.dumps(out, ensure_ascii=False, indent=1))
    else:
        log("DOMAINS ON ACCOUNT:", len(out))
        for o in out:
            log(" -", o["domain"], "| exp:", o["expire"], "| autorenew:", o["autorenew"],
                "| coupon:", o["coupon_used"] or "-")
    return 0

if __name__ == "__main__":
    sys.exit(main())
