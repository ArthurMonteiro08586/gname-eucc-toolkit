# Gname fill inline contact template -> agree -> Pay Now -> order (stage 11)
import sys, os, json, time, random, re
from playwright.sync_api import sync_playwright

BASE = os.environ.get("GNAME_HOME", os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"))
COOKIES_F = os.path.join(BASE, "gname_cookies.json")
BANK_F = os.path.join(BASE, "eucc_domains.jsonl")
MODE = sys.argv[1] if len(sys.argv) > 1 else "fill"  # fill = stop before PayNow; pay = full

C = {"first": "Sergiy", "last": "Melnyk", "country": "Ukraine", "prov": "Kyiv", "city": "Kyiv",
     "addr": "Khreshchatyk Street 22, apt 14", "areacode": "380", "phone": "992936096", "zip": "01001"}

with sync_playwright() as pw:
    try:
        browser = pw.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled", "--no-sandbox"])
    except Exception:
        cand = [d for d in os.listdir(r"C:/Users/User/AppData/Local/ms-playwright") if d.startswith("chromium-1")]
        exe = os.path.join(r"C:/Users/User/AppData/Local/ms-playwright", sorted(cand)[-1], "chrome-win", "chrome.exe")
        browser = pw.chromium.launch(headless=True, executable_path=exe, args=["--disable-blink-features=AutomationControlled"])
    ctx = browser.new_context(viewport={"width": 1366, "height": 900}, locale="en-US", timezone_id="Europe/Kiev",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36")
    ctx.add_cookies(json.load(open(COOKIES_F)))
    page = ctx.new_page()
    netlog = []
    def on_resp(r):
        u = r.url
        if "gname.com/request/" in u and not any(k in u for k in ("chaym", "login_status", "get_xygx", "get_cps", "get_yhq")):
            try:
                b = r.text()[:900]
                netlog.append({"url": u, "status": r.status, "body": b})
                print("NET", r.status, u.split("gname.com")[-1][:60], b[:300].replace("\n", " "), flush=True)
            except Exception:
                pass
    page.on("response", on_resp)

    page.goto("https://www.gname.com/user_gwc", wait_until="domcontentloaded", timeout=60000)
    time.sleep(4)
    # select all
    page.evaluate("""() => {
        const els = [...document.querySelectorAll('*')].filter(e=>e.offsetParent!==null && [...e.childNodes].some(n=>n.nodeType===3 && /select all/i.test(n.textContent)));
        const host = els[els.length-1];
        const scope = host.closest('div,li,tr') || host.parentElement;
        const r = host.getBoundingClientRect();
        const icons = [...scope.querySelectorAll('input,i,span,em,label')].filter(e=>{const b=e.getBoundingClientRect(); return b.width>0 && b.right <= r.left+2;});
        const t = icons.length ? icons[icons.length-1].getBoundingClientRect() : {x:r.left-28,y:r.y,width:28,height:r.height};
        window.__selbox = {x:t.x+t.width/2, y:t.y+t.height/2};
    }""")
    sb = page.evaluate("() => window.__selbox")
    page.mouse.click(sb["x"], sb["y"])
    time.sleep(1.5)
    print("COUNTER:", page.evaluate("() => {const m=document.body.innerText.match(/(\\d+) in total, (\\d+) selected/); return m?m[0]:'?';}"), flush=True)
    page.evaluate("""() => {
        const els=[...document.querySelectorAll('a,button,input,div,span')].filter(e=>e.offsetParent!==null);
        const cand=els.filter(e=>/^submit$/i.test(((e.innerText||e.value||'')).trim()));
        cand[cand.length-1].click();
    }""")
    try:
        page.wait_for_url("**/user_gwc/pay*", timeout=25000)
        page.wait_for_load_state("domcontentloaded", timeout=20000)
    except Exception:
        pass
    time.sleep(4)
    print("URL PAY:", page.url, flush=True)

    # agreement checkbox FIRST (coordinate click after scroll into view)
    page.evaluate("""() => {
        const els = [...document.querySelectorAll('*')].filter(e=>e.offsetParent!==null && [...e.childNodes].some(n=>n.nodeType===3 && /I have read and agree/i.test(n.textContent)));
        const host = els[els.length-1];
        host.scrollIntoView({block:'center'});
        const r = host.getBoundingClientRect();
        const scope = host.closest('div,li,tr') || host.parentElement;
        const icons = [...scope.querySelectorAll('input,i,span,em,label')].filter(e=>{const b=e.getBoundingClientRect(); return b.width>0 && b.right <= r.left+2;});
        const t = icons.length ? icons[icons.length-1].getBoundingClientRect() : {x:r.left-28,y:r.y,width:28,height:r.height};
        window.__agbox = {x:t.x+t.width/2, y:t.y+t.height/2};
    }""")
    time.sleep(1)
    ab = page.evaluate("() => window.__agbox")
    page.mouse.click(ab["x"], ab["y"])
    time.sleep(1)
    agchk = page.evaluate("""() => [...document.querySelectorAll('input[type=checkbox]')].filter(c=>c.checked).map(c=>c.name||'?')""")
    print("AGREED:", json.dumps(agchk), flush=True)

    # click Pay Now — template form only renders after it (with agreement checked)
    page.evaluate("""() => {
        const els=[...document.querySelectorAll('a,button,div,span,input')].filter(e=>e.offsetParent!==null);
        const cand=els.filter(e=>/^pay now$/i.test(((e.innerText||e.value||'')).trim()));
        if (cand.length) cand[cand.length-1].click();
    }""")
    try:
        page.wait_for_selector("input[name=xing]", timeout=15000)
        print("FORM VISIBLE", flush=True)
    except Exception:
        print("FORM NOT APPEARED", flush=True)
        toast = page.evaluate("""() => {
            const ts=[...document.querySelectorAll('[class*=toast],[class*=tips],[class*=msg],.layui-layer-content')].filter(e=>e.offsetParent!==null).map(e=>(e.innerText||'').trim().slice(0,120));
            return ts.filter(t=>t).slice(0,5);
        }""")
        print("TOASTS:", json.dumps(toast, ensure_ascii=False), flush=True)
    time.sleep(1.5)

    def fill_field(sel, val, click_dropdown_kw=None):
        try:
            el = page.query_selector(sel)
            if not el:
                print("MISS:", sel, flush=True)
                return False
            el.scroll_into_view_if_needed()
            el.click()
            el.fill(val)
            time.sleep(0.7)
            if click_dropdown_kw:
                # click suggestion containing kw
                r = page.evaluate("""(kw) => {
                    const items=[...document.querySelectorAll('li,div[class*=item],div[class*=option],dd')].filter(e=>e.offsetParent!==null && (e.innerText||'').trim().toLowerCase().includes(kw.toLowerCase()) && (e.innerText||'').trim().length<60);
                    if(!items.length) return 'noitems';
                    items[items.length-1].click();
                    return 'clicked:'+items[items.length-1].innerText.trim().slice(0,40);
                }""", click_dropdown_kw)
                print("DROPDOWN %s: %s" % (sel, r), flush=True)
                time.sleep(1)
            return True
        except Exception as e:
            print("FILL ERR %s: %s" % (sel, str(e)[:70]), flush=True)
            return False

    fill_field("input[name=xing]", C["first"])
    fill_field("input[name=ming]", C["last"])
    fill_field("input[placeholder='Country/Region']", C["country"], click_dropdown_kw="Ukraine")
    fill_field("input[name=sheng]", C["prov"], click_dropdown_kw="Kyiv")
    fill_field("input[name=shi]", C["city"], click_dropdown_kw="Kyiv")
    fill_field("input[name=gn_bczl_dzxx]", C["addr"])
    fill_field("input[placeholder='Area Code']", C["areacode"], click_dropdown_kw="380")
    fill_field("input[name=gn_wszl_phone]", C["phone"])
    fill_field("input[name=yzbm]", C["zip"])
    # dump filled state
    vals = page.evaluate("""() => [...document.querySelectorAll('input[type=text]')].filter(i=>i.offsetParent!==null).map(i=>({n:i.name,ph:i.placeholder,v:i.value}))""")
    print("VALS:", json.dumps(vals, ensure_ascii=False), flush=True)
    page.screenshot(path=os.path.join(BASE, "eucc11_filled.png"), full_page=True)

    # agreement already checked before Pay Now; just verify
    agchk = page.evaluate("""() => [...document.querySelectorAll('input[type=checkbox]')].filter(c=>c.checked).map(c=>c.name||'?')""")
    print("CHECKED:", json.dumps(agchk), flush=True)
    allbtns = page.evaluate("""() => [...document.querySelectorAll('a,button,div,span,input')].filter(e=>e.offsetParent!==null).map(e=>((e.innerText||e.value||'')).trim()).filter(t=>t && t.length<30 && /save|confirm|submit|ok|determine|pay|buy|order|next/i.test(t))""")
    print("BTNS NEAR:", json.dumps(sorted(set(allbtns))), flush=True)
    if MODE == "pay":
        # 1) form-level submit (Save/Confirm/Submit/Determine/OK), NOT Pay Now
        r1 = page.evaluate("""() => {
            const els=[...document.querySelectorAll('a,button,div,span,input')].filter(e=>e.offsetParent!==null);
            const cand=els.filter(e=>/^(save|confirm|submit|determine|ok)$/i.test(((e.innerText||e.value||'')).trim()));
            if(!cand.length) return 'none';
            cand[cand.length-1].click();
            return 'clicked:'+((cand[cand.length-1].innerText||cand[cand.length-1].value)||'').trim();
        }""")
        print("FORM SUBMIT:", r1, flush=True)
        time.sleep(4)
        # modal chain after Submit: Confirm -> Payment Confirm (layui popups). Click .layui-layer-btn0 (Confirm) each time.
        for mtry in range(4):
            vis = page.locator(".layui-layer:visible")
            n = vis.count()
            if n == 0:
                break
            txts = []
            for i in range(n):
                try:
                    txts.append(vis.nth(i).inner_text()[:150].replace("\n", " | "))
                except Exception:
                    pass
            print("LAYUI MODALS(%d): %s" % (n, " ;; ".join(txts)), flush=True)
            clicked = False
            try:
                btn = page.locator(".layui-layer-btn0:visible").last
                if btn.count():
                    btn.click(timeout=4000)
                    clicked = True
            except Exception as e:
                print("BTN0 ERR:", str(e)[:60], flush=True)
            print("LAYUI CONFIRM CLICK:", clicked, flush=True)
            time.sleep(4)
        # 2) slider if demanded
        try:
            nb = page.evaluate("() => [...document.querySelectorAll('.gn-slide-bar')].filter(b=>b.offsetParent!==null).length")
        except Exception:
            nb = 0
        print("SLIDER BARS:", nb, flush=True)
        # 3) Pay Now again if still on pay page
        try:
            still = "user_gwc/pay" in page.url and page.query_selector("input[name=xing]") is not None
        except Exception:
            still = False
        print("STILL ON FORM:", still, flush=True)
        r2 = page.evaluate("""() => {
            const els=[...document.querySelectorAll('a,button,div,span,input')].filter(e=>e.offsetParent!==null);
            const cand=els.filter(e=>/^pay now$/i.test(((e.innerText||e.value||'')).trim()));
            if(!cand.length) return 'none';
            cand[cand.length-1].click(); return 'clicked';
        }""")
        print("PAYNOW2:", r2, flush=True)
        time.sleep(3)
        # handle Warm Tips / confirm modal (real layui popups only)
        for mtry in range(3):
            vis = page.locator(".layui-layer:visible")
            n = vis.count()
            if n == 0:
                break
            txts = []
            for i in range(n):
                try:
                    txts.append(vis.nth(i).inner_text()[:200].replace("\n", " | "))
                except Exception:
                    pass
            print("MODAL%d:" % mtry, " ;; ".join(txts), flush=True)
            try:
                btn = page.locator(".layui-layer-btn0:visible").last
                if btn.count():
                    btn.click(timeout=4000)
                    print("MODAL CLICK: btn0", flush=True)
            except Exception as e:
                print("MODAL CLICK ERR:", str(e)[:60], flush=True)
            time.sleep(4)
        for _ in range(8):
            time.sleep(3)
            try:
                nb = page.evaluate("() => [...document.querySelectorAll('.gn-slide-bar')].filter(b=>b.offsetParent!==null).length")
                u = page.url
            except Exception:
                nb, u = 0, "?"
            if nb:
                print("SLIDER AT PAY2", flush=True)
                break
            if "user_gwc" not in u:
                break
        print("URL FINAL:", page.url, flush=True)
        try:
            bf = page.locator("body").inner_text()
            print("FINAL BODY:", bf[:1200].replace("\n", " | "), flush=True)
        except Exception:
            pass
        page.screenshot(path=os.path.join(BASE, "eucc11_result.png"), full_page=True)
    json.dump(netlog[-80:], open(os.path.join(BASE, "eucc_netlog11.json"), "w"), indent=1)
    json.dump(ctx.cookies(), open(COOKIES_F, "w"))
    browser.close()
