#!/usr/bin/env python3
"""mfa_bind.py — bind TOTP MFA + enable operation-protection channels on a gname account.

WHY: gname DNS/domain writes fail in two opposite states:
  -100 "Please remove operation protection" -> session must pass aqbh email-code unlock FIRST
  -101 "please set operation protection"    -> protection channels must be SET (czyz [1,4])
Proven sequence (2026-10-16, uid 510198 / reformvk21.eu.cc):
  1. login -> GET secret from #/safeModify/lx=4/type=0/txt= (input[name=secret] or img src secret=)
  2. if writes return -100: aqbh_session_unlock (email code via IMAP; GM_EMAIL/GM_APPPW env)
  3. POST /user_zh/set_aqlb {secret, code=totp(secret)}      -> MFA bound
  4. POST /user_zh/set_czyz czyz[]=1&czyz[]=4                -> email+MFA channels ON
  5. now /user_ym/jx_edit writes succeed (setup_dns.py)

Usage:
  python mfa_bind.py [--uid 510198] [--bank path/to/gname_accounts.jsonl] [--out mfa.json]
Env: GM_EMAIL, GM_APPPW (gmail app-password) for the -100 email-code unlock.
Secrets stay local: writes mfa_secret to --out (default gname_mfa.json, gitignored).
"""
import argparse, base64, hashlib, hmac, json, os, re, struct, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.sync_api import sync_playwright
import gname_core as G
from gname_core import mk_context, save_cookies, csrf, inpost_json, inpost, aqbh_session_unlock

SITE = G.SITE


def totp(secret, period=30, digits=6):
    key = base64.b32decode(secret.upper().replace(" ", ""), casefold=True)
    ctr = int(time.time()) // period
    h = hmac.new(key, struct.pack(">Q", ctr), hashlib.sha1).digest()
    o = h[-1] & 0x0F
    return str((struct.unpack(">I", h[o:o + 4])[0] & 0x7FFFFFFF) % (10 ** digits)).zfill(digits)


def get_secret(page):
    return page.evaluate("""() => {
        let s = (document.querySelector('input[name=secret]')||{}).value || '';
        if (!s) { const img=[...document.querySelectorAll('img')].map(i=>i.src).find(x=>x.includes('secret=')); if(img) s=new URL(img).searchParams.get('secret'); }
        return s;
    }""")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--uid", default=os.environ.get("GNAME_UID", ""))
    ap.add_argument("--bank", default=os.environ.get("GNAME_BANK", "gname_accounts.jsonl"))
    ap.add_argument("--out", default="gname_mfa.json")
    a = ap.parse_args()

    acc = None
    for line in open(a.bank, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        if a.uid and str(d.get("uid")) == str(a.uid):
            acc = d
        elif not a.uid:
            acc = d  # first without --uid
        if acc:
            break
    if not acc:
        print("FATAL: uid not found in bank"); sys.exit(2)
    G.EMAIL = acc["email"]

    with sync_playwright() as pw:
        browser, ctx = mk_context(pw, cookies=True)
        page = ctx.new_page()
        page.goto(SITE + "/user", wait_until="domcontentloaded", timeout=60000)
        time.sleep(4)
        tok = csrf(page)
        r = inpost_json(page, "/user_ym/get_ym_list", {"page": 1, "limit": 50, "csrf_token": tok}, "idcheck")
        d = (r or {}).get("data") or {}
        lst = d.get("data") if isinstance(d, dict) else d
        print("ACCOUNT DOMAINS:", [x.get("ym") for x in (lst or [])], flush=True)

        page.goto(SITE + "/user/iframe#/safeModify/lx=4/type=0/txt=", wait_until="domcontentloaded", timeout=60000)
        time.sleep(8)
        sec = get_secret(page)
        print("SECRET len:", len(sec or ""), flush=True)
        if not sec:
            print("FATAL: no secret (page may require aqbh unlock first)"); save_cookies(ctx); browser.close(); sys.exit(5)

        bound = False
        for rnd in range(3):
            r = inpost_json(page, "/user_zh/set_aqlb",
                            {"secret": sec, "code": totp(sec), "csrf_token": csrf(page)}, "bind%d" % rnd)
            print("SET_AQLB try%d:" % rnd, str(r)[:200], flush=True)
            s = str(r)
            if isinstance(r, dict) and str(r.get("code")) == "1":
                bound = True; break
            if "remove operation protection" in s:
                if not aqbh_session_unlock(page, email=os.environ.get("GM_EMAIL")):
                    time.sleep(20); continue
                r2 = inpost_json(page, "/user_zh/set_aqlb",
                                 {"secret": sec, "code": totp(sec), "csrf_token": csrf(page)}, "bindB%d" % rnd)
                print("SET_AQLB after unlock:", str(r2)[:200], flush=True)
                if isinstance(r2, dict) and str(r2.get("code")) == "1":
                    bound = True; break
                time.sleep(2); continue
            break

        r = inpost(page, "/user_zh/set_czyz", {"czyz[]": ["1", "4"], "csrf_token": csrf(page)}, "cz")
        print("SET_CZYZ[1,4]:", str(r)[:200], flush=True)
        json.dump({"uid": str(acc.get("uid", "")), "mfa_secret": sec, "bound": bound, "ts": int(time.time())},
                  open(a.out, "w"))
        save_cookies(ctx)
        browser.close()
        print("MFA_BIND DONE bound=%s czyz=%s" % (bound, str(r)[:60]), flush=True)
        sys.exit(0 if bound else 3)


if __name__ == "__main__":
    main()
