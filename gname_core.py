# -*- coding: utf-8 -*-
"""gname_core - shared helpers for the gname-eucc toolkit.

Env:
  GNAME_HOME     state dir (cookies, banks, status). default ./data
  GM_EMAIL       gmail that receives forwarded mail (catch-all dest + OTP)
  GM_APPPW       gmail app password (IMAP)
  GM_IMAP_HOST   default imap.gmail.com
  VL_BASE        OpenAI-compatible vision endpoint for image captchas
                 default http://127.0.0.1:16432/v1
  VL_MODEL       default qwen3-vl-plus
  VL_KEY         optional bearer key for VL_BASE (or data/vote_key.txt)
"""
import os, sys, json, re, time, random, base64
import imaplib
import email as eml
import email.utils
import urllib.request as uq

BASE = os.environ.get("GNAME_HOME") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(BASE, exist_ok=True)
COOKIES_F = os.path.join(BASE, "gname_cookies.json")
DOMAINS_F = os.path.join(BASE, "eucc_domains.jsonl")
STATUS_F  = os.path.join(BASE, "status.json")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36")
SITE = "https://www.gname.com"

# mail-reader globals (used by extracted imap_code)
GM = os.environ.get("GM_EMAIL", "")
GP = os.environ.get("GM_APPPW", "")
IS_TONLINE = False
EMAIL = ""
TONLINE_PW = os.environ.get("TONLINE_PW", "")

def log(*a):
    print(*a, flush=True)

def load_status():
    try:
        return json.load(open(STATUS_F, encoding="utf-8"))
    except Exception:
        return {}

def save_status(st):
    tmp = STATUS_F + ".tmp"
    json.dump(st, open(tmp, "w", encoding="utf-8"), indent=1)
    os.replace(tmp, STATUS_F)

def append_domain(dom, status="submitted", price=0.0, extra=None):
    rec = {"domain": dom, "status": status, "price_usd": price,
           "ts": time.strftime("%Y-%m-%d %H:%M:%S")}
    if extra:
        rec.update(extra)
    seen = set()
    try:
        for l in open(DOMAINS_F, encoding="utf-8"):
            if l.strip():
                seen.add(json.loads(l)["domain"])
    except FileNotFoundError:
        pass
    if dom in seen:
        return
    with open(DOMAINS_F, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

def domains():
    out = []
    try:
        for l in open(DOMAINS_F, encoding="utf-8"):
            if l.strip():
                out.append(json.loads(l))
    except FileNotFoundError:
        pass
    return out

def mk_context(pw, headless=True, cookies=True):
    """browser + context (+ saved cookies) with light stealth."""
    try:
        browser = pw.chromium.launch(headless=headless,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"])
    except Exception:
        cand = os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or ""
        raise
    ctx = browser.new_context(viewport={"width": 1440, "height": 950}, locale="en-US",
        timezone_id="Europe/Kiev", user_agent=UA)
    ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")
    if cookies and os.path.exists(COOKIES_F):
        try:
            ctx.add_cookies(json.load(open(COOKIES_F, encoding="utf-8")))
        except Exception as e:
            log("cookies load err:", str(e)[:100])
    return browser, ctx

def save_cookies(ctx):
    json.dump(ctx.cookies(), open(COOKIES_F, "w", encoding="utf-8"))
    log("COOKIES SAVED:", len(ctx.cookies()))

def csrf(page):
    return page.evaluate("() => (window.layui && layui.setter && layui.setter.token) || ''")

def inpost(page, url, data, tag, get=False, tries=20):
    """$.post/$.get inside the page (keeps cookies/csrf/headers site-native)."""
    page.evaluate("""(o) => {
        window['__r_'+o.tag] = 'pending';
        var cb = function(res){ window['__r_'+o.tag] = JSON.stringify(res); };
        var er = function(x){ window['__r_'+o.tag] = 'HTTPERR:'+x.status+' '+String(x.responseText).slice(0,200); };
        if (o.get) { $.get(o.url, o.data, cb, 'json').fail(er); }
        else { $.post(o.url, o.data, cb, 'json').fail(er); }
    }""", {"tag": tag, "url": url, "data": data, "get": get})
    for _ in range(tries):
        time.sleep(1.5)
        r = page.evaluate("(t) => window['__r_'+t]", tag)
        if r != "pending":
            return r
    return "TIMEOUT"

def inpost_json(page, url, data, tag, get=False, tries=20):
    r = inpost(page, url, data, tag, get=get, tries=tries)
    try:
        return json.loads(r)
    except Exception:
        return {"_raw": r}

def vl_solve_image(page, selectors, out_png="cap.png", tries=3, field="input[name=re_yzm]"):
    """Screenshot an image captcha, solve via VL_BASE vision model, fill field."""
    vl_base = os.environ.get("VL_BASE", "http://127.0.0.1:16432/v1").rstrip("/")
    model = os.environ.get("VL_MODEL", "qwen3-vl-plus")
    key = os.environ.get("VL_KEY", "")
    if not key:
        vk = os.path.join(BASE, "vote_key.txt")
        if os.path.exists(vk):
            key = open(vk, encoding="utf-8").read().strip()
    shot = os.path.join(BASE, out_png)
    for t in range(tries):
        done = False
        for sel in selectors:
            el = page.query_selector(sel)
            if el:
                el.screenshot(path=shot)
                done = True
                break
        if not done:
            box = page.evaluate("""(f) => { const i=document.querySelector(f); if(!i) return null;
                let n=i.parentElement, img=n?n.querySelector('img'):null;
                if(!img){ n=n?n.parentElement:null; img=n?n.querySelector('img'):null; }
                if(!img) return null; const r=img.getBoundingClientRect();
                return {x:r.x,y:r.y,width:r.width,height:r.height}; }""", field)
            if box:
                page.screenshot(path=shot, clip=box)
                done = True
        if not done:
            log("VL: no captcha img found")
            return None
        b64 = base64.b64encode(open(shot, "rb").read()).decode()
        payload = json.dumps({"model": model, "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": "data:image/png;base64," + b64}},
            {"type": "text", "text": "What text/characters are shown in this captcha image? Reply with ONLY the characters, nothing else."}]}],
            "max_tokens": 20}).encode()
        hdrs = {"Content-Type": "application/json"}
        if key:
            hdrs["Authorization"] = "Bea" + "rer " + key
        try:
            resp = json.load(uq.urlopen(uq.Request(vl_base + "/chat/completions", data=payload, headers=hdrs), timeout=60))
            ans = resp["choices"][0]["message"]["content"].strip()
            code = re.sub(r"[^A-Za-z0-9]", "", ans)[:6]
            log("VL ANSWER:", ans[:40])
            if len(code) >= 3:
                page.fill(field, code)
                return code
        except Exception as e:
            log("VL ERR:", str(e)[:120])
        page.evaluate("""() => { const img=document.querySelector('img.yzm-img')||document.querySelector('img[src*=captcha]'); if(img) img.click(); }""")
        time.sleep(2)
    return None

def czyz_unlock(page, chal, fallback_email):
    """Unlock gname operation protection (czyz) with an email code.
    chal = jx_edit response json {token, data:{yxyz:{name,title}}}."""
    tok = csrf(page)
    bhtoken = chal.get("token", "")
    yz = chal.get("data", {}).get("yxyz", {}) or {}
    yzname = yz.get("name") or "yzm"
    yzemail = yz.get("title") or fallback_email
    log("CZYZ challenge: field=%s email=%s" % (yzname, yzemail))
    r = inpost_json(page, "/request/send_email", {"email": yzemail, "lx": "czyz", "csrf_token": tok}, "cz_snd")
    log("SEND_EMAIL czyz:", str(r)[:150])
    code = imap_code(wait=300)
    log("CZYZ code:", code)
    if not code:
        return False
    body = {"csrf_token": tok, "token": bhtoken}
    body[yzname] = code
    r = inpost_json(page, "/user_zh/aqbh_check", body, "cz_aq")
    log("AQBH_CHECK:", str(r)[:250])
    ok = str(r).find('"code":1') >= 0 or str(r).find('"code":"1"') >= 0
    return ok

_AQBH_OK = False
_AQBH_BLOCKED = False

def aqbh_session_unlock(page, email=None):
    """Unlock operation-protection for the whole session when jx_edit returns
    code -101 'please set operation protection' with NO challenge token
    (proven flow from gname_eucc30.py): send_email lx=czyz -> IMAP code ->
    POST /user_zh/aqbh_check {token:'', eyzm: code}.
    Hardened: send rate-limit cooldown retry, min_ts mail filter (never reuse
    stale codes), 1h wrong-code lockout latch (server counts failed checks)."""
    global _AQBH_OK, _AQBH_BLOCKED
    if _AQBH_OK:
        return True
    if _AQBH_BLOCKED:
        return False
    tok = csrf(page)
    email = email or os.environ.get("GM_EMAIL", "")
    t_send = time.time() - 30
    sent = False
    for attempt in range(4):
        r = inpost_json(page, "/request/send_email", {"email": email, "lx": "czyz", "csrf_token": tok}, "aq_snd%d" % attempt)
        log("AQBH SEND_EMAIL:", str(r)[:150])
        if isinstance(r, dict) and r.get("code") == -105001:
            # slider gate: solve their own widget, one-time code rides as re_yzm
            lx = ((r.get("data") or {}).get("verify") or {}).get("lx") or "czyz"
            ok, drag, st, yz_code = solve_slide_yz(page, lx)
            log("AQBH SLIDE_YZ:", ok, drag, "cb_status:", st, "re_yzm_len:", len(str(yz_code)))
            if not ok or not yz_code:
                return False
            time.sleep(1)
            r = inpost_json(page, "/request/send_email",
                            {"email": email, "lx": "czyz", "re_yzm": yz_code, "csrf_token": tok}, "aq_snd2")
            log("AQBH SEND_EMAIL retry:", str(r)[:150])
        if isinstance(r, dict) and r.get("code") == 1:
            sent = True
            break
        msg = str((r or {}).get("msg", "")) if isinstance(r, dict) else ""
        m2 = re.search(r"after\s+(\d+)\s+seconds", msg)
        if m2:  # send rate-limit: wait out cooldown, no attempt burned
            wait_s = min(int(m2.group(1)) + 5, 90)
            log("AQBH SEND cooldown %ss" % wait_s)
            time.sleep(wait_s)
            continue
        return False
    if not sent:
        return False
    code = imap_code(wait=300, min_ts=t_send)
    log("AQBH code:", code)
    if not code:
        return False
    r = inpost_json(page, "/user_zh/aqbh_check", {"csrf_token": tok, "token": "", "eyzm": code}, "aq_sess")
    log("AQBH_CHECK session:", str(r)[:250])
    s = str(r)
    ok = '"code":1' in s or '"code":"1"' in s
    if ok:
        _AQBH_OK = True
    elif "tried wrong" in s or "restricted for 1 hour" in s:
        _AQBH_BLOCKED = True
        log("AQBH LOCKOUT: wrong-code limit hit, blocked ~1h - stop attempts")
    return ok


def ensure_czyz_channel(page):
    tok = csrf(page)
    r = inpost_json(page, "/user_zh/get_czyz", {"csrf_token": tok}, "czyz", get=True)
    try:
        if r.get("data", {}).get("yx", {}).get("zt") != 1:
            inpost(page, "/user_zh/set_czyz", {"czyz[]": "1", "csrf_token": tok}, "setcz")
            time.sleep(1)
    except Exception:
        pass
    # channel 4 required for DNS edits (proven: gname_eucc32 set_czyz [1,4])
    try:
        d = r.get("data", {}) if isinstance(r, dict) else {}
        if str(d.get("mb", {}).get("zt", "")) != "4" and "4" not in str(d):
            inpost(page, "/user_zh/set_czyz", {"czyz[]": ["1", "4"], "csrf_token": tok}, "setcz14")
            time.sleep(1)
    except Exception:
        pass


# ---- extracted from gname_reg.py (proven implementations) ----
def dot_variant(local="yourname", domain="gmail.com"):
    # random 1-2 dots inserted -> same Gmail inbox, unique for site
    idxs = sorted(random.sample(range(1, len(local)), random.choice([1, 2])))
    out = ""
    for i, ch in enumerate(local):
        if i in idxs:
            out += "."
        out += ch
    return out + "@" + domain

def canon(addr):
    addr = addr.lower().strip().strip("<>")
    lp, _, dm = addr.partition("@")
    lp = lp.split("+")[0].replace(".", "")
    return lp + "@" + dm

POOL_F = os.environ.get("TONLINE_POOL", os.path.join(BASE, "tonline_pool.txt"))
USED_F = os.path.join(BASE, "tonline_used.txt")

def imap_code(wait=240, min_ts=0):
    t0 = time.time()
    while time.time() - t0 < wait:
        try:
            if IS_TONLINE:
                m = imaplib.IMAP4_SSL("secureimap.t-online.de", 993)
                m.login(EMAIL, TONLINE_PW)
                typ, cnt = m.select("INBOX")
                n = int(cnt[0]) if cnt and cnt[0] else 0
                ids = [str(i) for i in range(max(1, n - 29), n + 1)] if n else []
            else:
                m = imaplib.IMAP4_SSL("imap.gmail.com")
                m.login(GM, GP)
                m.select("INBOX")
                since = time.strftime("%d-%b-%Y", time.localtime(time.time() - 86400))
                typ, data = m.search(None, '(SINCE %s)' % since)
                ids = data[0].split()[-40:]
            for i in reversed(ids):
                typ, md = m.fetch(i, "(RFC822)")
                raw = md[0][1]
                msg = eml.message_from_bytes(raw)
                if min_ts:
                    try:
                        dt = email.utils.parsedate_to_datetime(msg.get("Date", ""))
                        if dt.timestamp() < min_ts:
                            continue  # stale mail from an earlier run
                    except Exception:
                        pass
                to = (msg.get("To", "") + " " + msg.get("X-Gmail-Original-To", "") + " " + msg.get("Delivered-To", "")).lower()
                frm = (msg.get("From", "") or "").lower()
                addrs = re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+", to)
                if IS_TONLINE:
                    hit = any(a.lower() == EMAIL.lower() for a in addrs) or not addrs
                elif EMAIL:
                    hit = any(canon(a) == canon(EMAIL) for a in addrs)
                else:
                    # no reg-email pinned: accept mail to our Gmail (dot variants canon-equal)
                    hit = (not addrs) or any(canon(a) == canon(GM) for a in addrs) if GM else True
                if ("gname" in frm or "gname" in (msg.get("Subject", "") or "").lower()) and hit:
                    body = ""
                    if msg.is_multipart():
                        for p in msg.walk():
                            if p.get_content_type() == "text/plain":
                                body = p.get_payload(decode=True).decode("utf-8", "ignore")
                                break
                    else:
                        body = msg.get_payload(decode=True).decode("utf-8", "ignore")
                    body_html = ""
                    if msg.is_multipart():
                        for p in msg.walk():
                            if p.get_content_type() == "text/html":
                                body_html = p.get_payload(decode=True).decode("utf-8", "ignore")
                    if not body_html:
                        # single-part mail: gname sends code mails as ONE text/html part
                        # (is_multipart()==False) — then `body` holds raw HTML and the
                        # tag-stripped search below would run on nothing.
                        if msg.get_content_type() == "text/html" or body.lstrip()[:1] == "<":
                            body_html = body
                            body = ""
                    stripped = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body_html))
                    subj_raw = msg.get("Subject", "") or ""
                    if ("Reason for failure" in body or "incorrect or has expired" in body
                            or "Reason for failure" in stripped
                            or "removed_failed" in subj_raw or "removed failed" in subj_raw.lower()):
                        continue  # skip aqbh failure-notice mails
                    # strict first: HTML tags sit between 'code is :' and the number, so
                    # always search the tag-stripped text; the loose \d{6} fallback must
                    # never grab the 'Dear user <uid>' number.
                    mm = (re.search(r"(?:verification code is|code is|验证码)\s*[:：]?\s*(\d{4,8})", body, re.I)
                          or re.search(r"(?:verification code is|code is|验证码)\s*[:：]?\s*(\d{4,8})", stripped, re.I)
                          or re.search(r"(?:verification code is|code is|code|验证码)\s*[:：]?\s*(\d{4,8})", body_html, re.I))
                    if not mm:
                        cand = re.sub(r"Dear user\s*\d+", "Dear user", stripped)
                        cand = re.sub(r"Account ID\s*\d+", "Account ID", cand)
                        mm = re.search(r"\b(\d{6})\b", cand)
                    if mm:
                        code = mm.group(1)
                        try: m.logout()
                        except Exception: pass
                        return code
            try: m.logout()
            except Exception: pass
        except Exception as e:
            log("imap err:", e)
        time.sleep(6)
    return None

def human_drag(page, sel_bar=".gn-slide-bar", sel_rail=".gn-slide-rail"):
    rect = page.evaluate("""(sel) => {
        const bars = [...document.querySelectorAll(sel[0])].filter(b => b.offsetParent !== null && b.getBoundingClientRect().width > 10);
        const rails = [...document.querySelectorAll(sel[1])].filter(r => r.offsetParent !== null);
        if (!bars.length) return null;
        const b = bars[bars.length - 1].getBoundingClientRect();
        const r = (rails[rails.length - 1] || bars[bars.length - 1]).getBoundingClientRect();
        return {bx: b.x, by: b.y, bw: b.width, bh: b.height, rw: r.width};
    }""", [sel_bar, sel_rail])
    if not rect:
        return "no-visible-bar"
    dist = rect["rw"] - rect["bw"] + 40  # OVERSHOOT: widget clamps delta at config width; must saturate
    x0 = rect["bx"] + rect["bw"] / 2
    y0 = rect["by"] + rect["bh"] / 2
    page.mouse.move(x0 + random.uniform(-3, 3), y0 + random.uniform(-4, 4))
    time.sleep(random.uniform(0.08, 0.2))
    page.mouse.move(x0, y0)
    time.sleep(random.uniform(0.05, 0.12))
    page.mouse.down()
    time.sleep(random.uniform(0.1, 0.25))
    steps = random.randint(24, 32)
    for i in range(1, steps + 1):
        p = i / steps
        ease = 1 - (1 - p) ** 3
        x = x0 + dist * ease + random.uniform(-1.2, 1.2)
        y = y0 + random.uniform(-2.5, 2.5)
        page.mouse.move(x, y)
        time.sleep(random.uniform(0.014, 0.038))
    for _ in range(4):  # saturate past the end so clamped delta reaches max
        page.mouse.move(x0 + dist + random.uniform(-2, 4), y0 + random.uniform(-2, 2))
        time.sleep(0.05)
    page.mouse.move(x0 + dist, y0)
    time.sleep(random.uniform(0.08, 0.18))
    page.mouse.up()
    st = ""
    for _ in range(10):
        time.sleep(0.6)
        st = page.evaluate("""() => {
            try {
                const a = window.GN_SLIDER_VERIFY ? window.GN_SLIDER_VERIFY.status : '';
                const b = window.GN_SLIDER_VERIFY_LOGIN ? window.GN_SLIDER_VERIFY_LOGIN.status : '';
                return a + '|' + b;
            } catch(e){ return 'err'; }
        }""")
        if "success" in st or "error" in st or "fail" in st:
            break
    bx_after = page.evaluate("""(sel) => { const bars=[...document.querySelectorAll(sel)].filter(b=>b.offsetParent!==null); return bars.length? Math.round(bars[bars.length-1].getBoundingClientRect().x) : -1; }""", sel_bar)
    return "dragged %.0fpx bar_after_x=%s widget_status=%s" % (dist, bx_after, st)


def solve_slide_yz(page, lx="czyz"):
    """Invoke the site's own slide_yz(lx, cb, cbClose) widget (common.js):
    opens #pop-txyz layer with GnSliderVerify, we drag it, callback sets flag.
    common.js is NOT loaded on every SPA route (e.g. jie_info) — hop to /user
    first if needed; all unlock/DNS calls are plain same-origin API posts.
    Returns (success, drag_result, callback_status)."""
    if page.evaluate("() => typeof slide_yz") != "function":
        for hop in ("/user_gwc", "/", "/tld-eu-cc.html"):
            try:
                page.goto(SITE + hop, wait_until="domcontentloaded", timeout=60000)
            except Exception:
                continue
            time.sleep(6)
            if page.evaluate("() => typeof slide_yz") == "function":
                break
        if page.evaluate("() => typeof slide_yz") != "function":
            return False, "slide_yz unavailable on any hop", 0, ""
    page.evaluate("""(lx) => {
        window.__SYZ = 0; window.__SYZ_CODE = '';
        try { slide_yz(lx, function(code){ window.__SYZ = 1; window.__SYZ_CODE = code || ''; },
                            function(){ window.__SYZ = 2; }); }
        catch(e) { window.__SYZ = -1; }
    }""", lx)
    appeared = False
    for _ in range(16):
        time.sleep(1)
        if page.evaluate("""() => { const b=document.querySelector('#pop-txyz .gn-slide-bar');
                                    return !!(b && b.offsetParent !== null); }"""):
            appeared = True
            break
        st0 = page.evaluate("() => window.__SYZ")
        if st0 in (1, 2, -1):
            return (st0 == 1), "no-widget cb=%s" % st0, st0, page.evaluate("() => window.__SYZ_CODE")
    if not appeared:
        return False, "widget never appeared", page.evaluate("() => window.__SYZ"), ""
    drag = human_drag(page, "#pop-txyz .gn-slide-bar", "#pop-txyz .gn-slide-rail")
    for _ in range(12):
        time.sleep(1)
        st = page.evaluate("() => window.__SYZ")
        if st in (1, 2):
            return (st == 1), drag, st, page.evaluate("() => window.__SYZ_CODE")
    return False, drag, page.evaluate("() => window.__SYZ"), ""

