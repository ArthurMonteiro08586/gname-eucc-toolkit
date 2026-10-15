# -*- coding: utf-8 -*-
"""Gname login + cookie save.

Credentials: env GNAME_EMAIL / GNAME_PASSWORD, or bank file
data/gname_accounts.jsonl (line index as argv[1]).

Usage: python login.py [bank_index]
"""
import sys, os, re, json, time
from playwright.sync_api import sync_playwright
from gname_core import (BASE, COOKIES_F, SITE, UA, log, mk_context,
                        save_cookies, human_drag, vl_solve_image)

def pick_creds():
    # argv[1] = bank index OR uid; env GNAME_UID also selects by uid
    sel = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("GNAME_UID", "")
    if sel:
        bank_f = os.path.join(BASE, "gname_accounts.jsonl")
        bank = [json.loads(l) for l in open(bank_f, encoding="utf-8") if l.strip()]
        acc = None
        if sel.isdigit():
            by_uid = [a for a in bank if str(a.get("uid")) == sel]
            if by_uid:
                acc = by_uid[0]
            else:
                acc = bank[int(sel)]
        if acc is None:
            raise SystemExit("account not found: " + sel)
        log("BANK PICK: uid", acc.get("uid"), acc.get("email"))
        return acc["email"], acc["password"]
    e, p = os.environ.get("GNAME_EMAIL", ""), os.environ.get("GNAME_PASSWORD", "")
    if not (e and p):
        bank_f = os.path.join(BASE, "gname_accounts.jsonl")
        if os.path.exists(bank_f):
            acc = json.loads(open(bank_f, encoding="utf-8").readline())
            return acc["email"], acc["password"]
        raise SystemExit("set GNAME_EMAIL/GNAME_PASSWORD or provide data/gname_accounts.jsonl")
    return e, p

def main():
    email, password = pick_creds()
    log("LOGIN AS:", email)
    with sync_playwright() as pw:
        browser, ctx = mk_context(pw, cookies=False)
        page = ctx.new_page()
        page.goto(SITE + "/login", wait_until="domcontentloaded", timeout=60000)
        time.sleep(3)
        # Password tab (default is email-code / QR)
        page.evaluate("""() => {
            const els = [...document.querySelectorAll('a,span,div,li,button')]
                .filter(e=>e.offsetParent!==null && (e.innerText||'').trim()==='Password');
            if (els.length) els[0].click();
        }""")
        time.sleep(2)
        filled = page.evaluate("""(creds) => {
            const set = (el, v) => { el.value = v; el.dispatchEvent(new Event('input',{bubbles:true})); el.dispatchEvent(new Event('change',{bubbles:true})); };
            const vis = [...document.querySelectorAll('input')].filter(i=>i.offsetParent!==null);
            let em = vis.find(i=>['lg_yx','re_yx'].includes(i.name)) || vis.find(i=>/mail/i.test(i.placeholder));
            let pw = vis.find(i=>i.type==='password');
            if (!em || !pw) return 'no-fields';
            set(em, creds[0]); set(pw, creds[1]);
            return 'ok';
        }""", [email, password])
        log("FILLED:", filled)
        time.sleep(1)
        rail = page.query_selector(".gn-slide-rail")
        if rail and rail.is_visible():
            log("SLIDER:", human_drag(page))
            time.sleep(2)
        if page.query_selector("input[name=re_yzm]"):
            vl_solve_image(page, ["img.yzm-img", "img[src*=captcha]", "img[src*=yzm]", "img[src*=code]"],
                           out_png="login_captcha.png", tries=3, field="input[name=re_yzm]")
        page.evaluate("""() => {
            const b = document.querySelector('button.login-btn[type=submit]') ||
                      [...document.querySelectorAll('button')].find(x=>/log ?in|sign in/i.test(x.innerText||''));
            if (b) b.click();
        }""")
        time.sleep(6)
        log("AFTER URL:", page.url)
        body = page.locator("body").inner_text()[:200].replace("\n", " | ")
        log("BODY:", body)
        ok = "/user" in page.url or "ID:" in page.locator("body").inner_text()[:3000]
        save_cookies(ctx)
        # identity proof: list domains of the logged-in account
        if ok:
            try:
                from gname_core import inpost_json, csrf
                r = inpost_json(page, "/user_ym/get_ym_list",
                                {"page": 1, "limit": 50, "csrf_token": csrf(page)}, "idcheck")
                data = (r or {}).get("data") or {}
                lst = data.get("data") if isinstance(data, dict) else data
                doms = [x.get("ym") for x in (lst or [])]
                log("ACCOUNT DOMAINS:", doms if doms else "(none)")
            except Exception as e:
                log("ACCOUNT DOMAINS: err", str(e)[:80])
        browser.close()
        log("LOGIN:", "OK" if ok else "CHECK-MANUALLY")
        return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
