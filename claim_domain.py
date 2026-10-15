# -*- coding: utf-8 -*-
"""claim_domain.py - claim a FREE .eu.cc domain on an existing gname account.

Flow (proven against gname checkout):
  PROMO /tld-eu-cc.html -> POST /hd_eucc/freereg (claim 3 full-discount
  .eu.cc vouchers, auto-applied at checkout => $0.00)
  -> search page -> [slider if gated] -> Add to Cart on the eu.cc row
  -> /user_gwc: select-all (coordinate click) -> Submit -> /user_gwc/pay
  -> agreement (coordinate click) -> Pay Now -> contact form (first purchase only)
  -> submit -> czyz unlock if challenged -> layui modal chain
  -> full-discount voucher => $0.00 -> append data/eucc_domains.jsonl

Usage:  python claim_domain.py [NAME]        # domain = NAME.eu.cc
        (default NAME = reformwk<rand>)
Env:    GNAME_HOME, CONTACT_* (defaults below), GM_EMAIL/GM_APPPW for czyz codes.
Account: cookies from data/gname_cookies.json (python login.py [IDX] first).
"""
import sys, os, json, time, random, re, io
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.sync_api import sync_playwright
from gname_core import *

NAME = (sys.argv[1] if len(sys.argv) > 1 else "reformwk%d" % random.randint(10, 99))
if NAME.endswith(".eu.cc"):
    NAME = NAME[:-6]
DOM = NAME + ".eu.cc"

CONTACT = {
    "first": os.environ.get("CONTACT_FIRST", "John"),
    "last": os.environ.get("CONTACT_LAST", "Smith"),
    "country": os.environ.get("CONTACT_COUNTRY", "United States"),
    "prov": os.environ.get("CONTACT_PROV", "California"),
    "city": os.environ.get("CONTACT_CITY", "Los Angeles"),
    "addr": os.environ.get("CONTACT_ADDR", "123 Main Street"),
    "areacode": os.environ.get("CONTACT_AREACODE", "1"),
    "phone": os.environ.get("CONTACT_PHONE", "2135550142"),
    "zip": os.environ.get("CONTACT_ZIP", "90001"),
}

def coord_click_text(page, pattern, tag):
    """Click the custom checkbox/icon rendered LEFT of a text node (gname UI)."""
    page.evaluate("""(re) => {
        const els = [...document.querySelectorAll('*')].filter(e=>e.offsetParent!==null && [...e.childNodes].some(n=>n.nodeType===3 && new RegExp(re,'i').test(n.textContent)));
        if (!els.length) { window.__cb = null; return; }
        const host = els[els.length-1];
        host.scrollIntoView({block:'center'});
        const r = host.getBoundingClientRect();
        const scope = host.closest('div,li,tr') || host.parentElement;
        const icons = [...scope.querySelectorAll('input,i,span,em,label')].filter(e=>{const b=e.getBoundingClientRect(); return b.width>0 && b.right <= r.left+2;});
        const t = icons.length ? icons[icons.length-1].getBoundingClientRect() : {x:r.left-28,y:r.y,width:28,height:r.height};
        window.__cb = {x:t.x+t.width/2, y:t.y+t.height/2};
    }""", pattern)
    cb = page.evaluate("() => window.__cb")
    if not cb:
        log(tag + ": text not found")
        return False
    page.mouse.click(cb["x"], cb["y"])
    time.sleep(1.2)
    return True

def click_button(page, pattern):
    return page.evaluate("""(re) => {
        const els=[...document.querySelectorAll('a,button,div,span,input')].filter(e=>e.offsetParent!==null);
        const cand=els.filter(e=>new RegExp(re,'i').test(((e.innerText||e.value||'')).trim()) && ((e.innerText||e.value||'').trim().length<30));
        if(!cand.length) return 'none';
        cand[cand.length-1].click();
        return 'clicked';
    }""", pattern)

def fill_field(page, sel, val, dropdown_kw=None):
    el = page.query_selector(sel)
    if not el:
        return False
    el.scroll_into_view_if_needed()
    el.click()
    el.fill(val)
    time.sleep(0.6)
    if dropdown_kw:
        page.evaluate("""(kw) => {
            const items=[...document.querySelectorAll('li,div[class*=item],div[class*=option],dd')].filter(e=>e.offsetParent!==null && (e.innerText||'').trim().toLowerCase().includes(kw.toLowerCase()) && (e.innerText||'').trim().length<60);
            if(items.length) items[items.length-1].click();
        }""", dropdown_kw)
        time.sleep(0.8)
    return True

def modal_chain(page, rounds=6):
    for _ in range(rounds):
        time.sleep(2)
        btn = page.locator(".layui-layer-btn0:visible").last
        if btn.count():
            try:
                btn.click(timeout=4000)
                log("MODAL: btn0 clicked")
                continue
            except Exception:
                pass
        break
    time.sleep(4)

def main():
    log("CLAIM DOMAIN:", DOM)
    with sync_playwright() as pw:
        browser, ctx = mk_context(pw, headless=os.environ.get("HEADLESS", "1") == "1")
        page = ctx.new_page()
        page.set_default_timeout(40000)

        # 0. claim full-discount .eu.cc vouchers (promo campaign; idempotent:
        #    already-claimed accounts get lqsl=0 and keep their ksy remainder)
        page.goto(SITE + "/tld-eu-cc.html", wait_until="domcontentloaded", timeout=60000)
        time.sleep(3)
        try:
            r = page.evaluate("""() => new Promise((res) => {
                $.post('/hd_eucc/freereg', {}, function(d){ res(d); }, 'json')
                 .fail(function(x){ res({err: x.status, t: String(x.responseText).slice(0,120)}); });
            })""")
            log("VOUCHER CLAIM:", json.dumps(r, ensure_ascii=False)[:250])
        except Exception as e:
            log("voucher claim err:", str(e)[:80])

        # 1. search -> Add to Cart (slider-gated search supported)
        page.goto(SITE + "/search?ym=" + DOM, wait_until="domcontentloaded", timeout=60000)
        time.sleep(5)
        found = False
        for _ in range(4):
            if DOM in page.locator("body").inner_text():
                found = True
                break
            if page.evaluate("() => !!document.querySelector('#pop-txyz .gn-slide-bar, .gn-slide-rail')"):
                log("SEARCH SLIDER:", solve_popup_slider(page))
                time.sleep(3)
                continue
            page.reload(wait_until="domcontentloaded", timeout=60000)
            time.sleep(5)
        if not found:
            log("domain never rendered on search page")
            save_cookies(ctx); browser.close()
            return 2
        clicked = page.evaluate("""(dom) => {
            const els = [...document.querySelectorAll('tr,div,li')].filter(e=>e.offsetParent!==null && (e.innerText||'').includes(dom));
            for (const e of els.reverse()) {
                const b = [...e.querySelectorAll('a,button')].find(x=>/add to cart|register now/i.test((x.innerText||'').trim()));
                if (b) { const t=b.innerText.trim(); b.click(); return 'clicked:'+t; }
            }
            return 'not-found';
        }""", DOM)
        log("CART CLICK:", clicked)
        time.sleep(5)
        # post-click slider (add-to-cart can be captcha-gated)
        for _ in range(2):
            nb = page.evaluate("() => [...document.querySelectorAll('.gn-slide-bar')].filter(b=>b.offsetParent!==null).length")
            if not nb:
                break
            log("SLIDER AFTER ADD:", solve_popup_slider(page))
            time.sleep(3)
        if not clicked.startswith("clicked"):
            # maybe already in cart from a previous run - verify at /user_gwc
            page.goto(SITE + "/user_gwc", wait_until="domcontentloaded", timeout=60000)
            time.sleep(4)
            if DOM not in page.locator("body").inner_text():
                log("not in cart either - abort")
                save_cookies(ctx); browser.close()
                return 2
            log("already in cart - continuing")
            goto_cart = False
        else:
            time.sleep(4)
            goto_cart = True

        # 2. cart page -> select all -> Submit
        if goto_cart:
            page.goto(SITE + "/user_gwc", wait_until="domcontentloaded", timeout=60000)
            time.sleep(4)
        coord_click_text(page, "select all", "SELECTALL")
        log("COUNTER:", page.evaluate("() => {const m=document.body.innerText.match(/(\\d+) in total, (\\d+) selected/); return m?m[0]:'?';}"))
        log("SUBMIT:", click_button(page, "^submit$"))
        try:
            page.wait_for_url("**/user_gwc/pay*", timeout=25000)
            page.wait_for_load_state("domcontentloaded", timeout=20000)
        except Exception:
            log("PAY URL not reached, url:", page.url)
        time.sleep(4)

        # 3. agreement -> Pay Now
        coord_click_text(page, "I have read and agree", "AGREEMENT")
        log("PAYNOW:", click_button(page, "^pay now$"))
        try:
            page.wait_for_selector("input[name=xing]", timeout=15000)
            log("CONTACT FORM visible")
            fill_field(page, "input[name=xing]", CONTACT["first"])
            fill_field(page, "input[name=ming]", CONTACT["last"])
            fill_field(page, "input[placeholder='Country/Region']", CONTACT["country"], CONTACT["country"])
            fill_field(page, "input[name=sheng]", CONTACT["prov"], CONTACT["prov"])
            fill_field(page, "input[name=shi]", CONTACT["city"], CONTACT["city"])
            fill_field(page, "input[name=gn_bczl_dzxx]", CONTACT["addr"])
            fill_field(page, "input[placeholder='Area Code']", CONTACT["areacode"], CONTACT["areacode"])
            fill_field(page, "input[name=gn_wszl_phone]", CONTACT["phone"])
            fill_field(page, "input[name=yzbm]", CONTACT["zip"])
            time.sleep(1)
        except Exception:
            log("no contact form (template saved on account) - ok")

        # 4. deterministic sequence (mirrors proven eucc11): form Save/Submit ->
        #    modal chain -> Pay Now again if still on form -> modals -> slider guard
        def body_has_success():
            b = page.locator("body").inner_text()
            return bool(re.search(r"Regis(?:t)?ration Successful|Congratulation|Pay Successfully|submitted successfully|temporary hold", b)) or "user_dd" in page.url

        def dump_fail():
            try:
                page.screenshot(path=os.path.join(BASE, "claim_fail.png"), full_page=True)
                toasts = page.evaluate("""() => [...document.querySelectorAll('[class*=toast],[class*=tips],[class*=msg],.layui-layer-content')].filter(e=>e.offsetParent!==null).map(e=>(e.innerText||'').trim().slice(0,150)).filter(t=>t).slice(0,6)""")
                log("TOASTS:", json.dumps(toasts, ensure_ascii=False)[:600])
                log("BODY:", page.locator("body").inner_text()[:600].replace("\n", " | "))
            except Exception as e:
                log("dump err:", str(e)[:80])

        for rnd in range(3):
            body = page.locator("body").inner_text()
            if re.search(r"Operation Protection|Security Verification", body):
                log("CZYZ/verification modal on checkout")
                tok = csrf(page)
                r = inpost_json(page, "/request/send_email",
                                {"email": os.environ.get("GM_EMAIL", ""), "lx": "czyz", "csrf_token": tok}, "cz_snd")
                log("SEND_EMAIL:", str(r)[:120])
                code = imap_code()
                log("CODE:", code)
                filled = False
                if code:
                    filled = page.evaluate("""(code) => {
                        const ins=[...document.querySelectorAll('.layui-layer input[type=text], .layui-layer input:not([type])')].filter(i=>i.offsetParent!==null);
                        if(!ins.length) return false;
                        ins[0].value=code; ins[0].dispatchEvent(new Event('input',{bubbles:true}));
                        return true;
                    }""", code)
                if filled:
                    modal_chain(page, rounds=4)
                    continue
                if czyz_unlock(page, {"token": "", "data": {}}, os.environ.get("GM_EMAIL", "")):
                    continue
                log("czyz unlock FAILED")
                break
            # form-level save/submit ONLY (never Pay Now here)
            if page.query_selector("input[name=xing]") is not None:
                log("FORM SUBMIT:", click_button(page, r"^(save|confirm|submit|determine|ok)$"))
                time.sleep(3)
            modal_chain(page)
            if body_has_success():
                break
            # still on pay page -> Pay Now again
            if "user_gwc/pay" in page.url:
                log("PAYNOW2:", click_button(page, r"^pay now$"))
                time.sleep(3)
                modal_chain(page)
            # slider guard (gname can throw a final drag at pay)
            for _ in range(6):
                nb = page.evaluate("() => [...document.querySelectorAll('.gn-slide-bar')].filter(b=>b.offsetParent!==null).length")
                if not nb:
                    break
                log("SLIDER AT PAY:", human_drag(page))
                time.sleep(3)
            if body_has_success():
                break
            if "user_gwc" not in page.url:
                break
            time.sleep(2)

        time.sleep(3)
        ok = body_has_success()
        log("RESULT:", "SUCCESS" if ok else "FAIL", "| url:", page.url)
        if not ok:
            dump_fail()
        try:
            append_domain(DOM, status="submitted" if ok else "failed", price=0.0,
                          extra={"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "url": page.url})
            log("BANK APPENDED:", DOMAINS_F)
        except Exception as e:
            log("bank write error:", e)
        save_cookies(ctx)
        browser.close()
        return 0 if ok else 3

def solve_popup_slider(page):
    try:
        return human_drag(page, "#pop-txyz .gn-slide-bar", "#pop-txyz .gn-slide-rail")
    except Exception as e:
        return "popup drag fail %r" % e

if __name__ == "__main__":
    sys.exit(main())
