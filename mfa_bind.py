import os, json, time, re
from playwright.sync_api import sync_playwright
BASE = os.environ.get("GNAME_HOME", os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"))
with sync_playwright() as pw:
    b = pw.chromium.launch(headless=True, args=["--no-sandbox"])
    ctx = b.new_context(viewport={"width":1440,"height":950}, locale="en-US",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36")
    ctx.add_cookies(json.load(open(BASE+"/gname_cookies.json")))
    page = ctx.new_page()
    page.goto("https://www.gname.com/user/iframe#/safeModify/lx=4/type=0/txt=", wait_until="domcontentloaded", timeout=60000)
    time.sleep(9)
    body = page.evaluate("() => document.body.innerText.split(String.fromCharCode(10)).filter(l=>l.trim()).join(' | ').slice(0,1400)")
    print("BODY:", body, flush=True)
    fields = page.evaluate("""() => [...document.querySelectorAll('input,select')].map(e=>e.tagName+':'+(e.type||'')+':'+(e.name||'')+':'+(e.placeholder||'')+':'+(e.offsetParent?'vis':'hid'))""")
    print("FIELDS:", json.dumps(fields[:20]), flush=True)
    imgs = page.evaluate("""() => [...document.querySelectorAll('img')].filter(i=>i.offsetParent!==null).map(i=>({src:(i.src||'').slice(0,120), w:i.width, h:i.height}))""")
    print("IMGS:", json.dumps(imgs[:8]), flush=True)
    scripts = page.evaluate("""() => [...document.querySelectorAll('script')].filter(s=>!s.src && s.textContent.length>800).map(s=>s.textContent)""")
    for i,s in enumerate(scripts):
        eps = sorted(set(re.findall(r'["\']/[a-z_0-9/]{4,50}["\']', s)))
        eps = [e for e in eps if any(k in e for k in ('user_zh','request','mfa','aqbh','user_'))]
        if eps: print("script %d (%db) EPS:" % (i, len(s)), eps[:20], flush=True)
        open(BASE+"/mfa_inline_%d.js"%i,"w",encoding="utf-8").write(s)
    page.screenshot(path=BASE+"/mfa_page.png", full_page=True)
    json.dump(ctx.cookies(), open(BASE+"/gname_cookies.json","w"))
    b.close()
