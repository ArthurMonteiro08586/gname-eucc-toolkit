# gname-eucc-toolkit

Free `.eu.cc` domain farm on [gname.com](https://www.gname.com/) + full mail stack: Cloudflare DNS, catch-all Email Routing, corporate mailboxes, OTP automation for autoregs.

**What you get:**
- $0 domains: every gname account receives **3 full-discount .eu.cc vouchers** (registration AND renewal at $0)
- Custom slider captcha `GnSliderVerify` fully reversed (not supported by any solver service)
- One domain = unlimited mailboxes via Cloudflare Email Routing catch-all
- Corporate mail on your domain via Zoho Forever Free

## Files

| File | Purpose |
|---|---|
| `gname_reg.py` | Autoreg: Playwright headless Chromium, solves the embedded + popup sliders, reads the email code via IMAP, logs into the dashboard. ~90s/account |
| `domain_claim.py` | Claims a free .eu.cc with a voucher, appends result to `data/eucc_domains.jsonl` |
| `mfa_bind.py` | Binds TOTP MFA on the account (keeps the farm accounts recoverable) |
| `gsv_deob_v2.py`, `gsv_deob2.py` | Deobfuscators for the site's slider JS (7574 transitive aliases removed) |
| `gsv_deob2.js` | The readable deobfuscated slider code |
| `gsv_keynames.json`, `gsv_strings.json` | String/key maps used by the deobfuscators |

## Environment (never hardcode credentials)

```
GM_EMAIL=yourbox@gmail.com          # Gmail that receives dot-variant mail
GM_APPPW=********                   # Gmail app password (IMAP)
GNAME_PW_PREFIX=Any                 # prefix for generated account passwords
TONLINE_POOL=data/tonline_pool.txt  # optional: email:pass pool (used when no arg given)
GNAME_HOME=./data                   # state dir (cookies, accounts, domains jsonl)
```

Run:

```
pip install playwright && playwright install chromium
python gname_reg.py your.name@gmail.com   # or omit arg to pull from TONLINE_POOL
python domain_claim.py
python mfa_bind.py
```

## How the slider bypass works

1. Site draws a 400px track but the client clamps the required distance to `width - barWidth` from a **config value of 360px**. Undershooting by even 2px triggers a silent reset with zero POST requests (that's why naive solvers "see nothing").
2. Payload `details` is AES-CBC encrypted: `{m: trajectory points (hex), st, et, f: GnClientJS fingerprint, d, t, t2}` → response token is 40 hex chars, valid 300s.
3. Server gates: duration 10ms–30s, 3–1000 points, must "reach" the clamped distance.
4. Solution: drag with **+40px overshoot** and 4 saturate wiggles before mouseup. Both sliders: embedded (`lx=register`, field `re_yzm`) and popup (`lx=reg`, `#pop-txyz`) before `send_email`.

## Full setup: domain → Cloudflare → mail

### 1. Get the domain
Register (autoreg above) → dashboard → claim a free .eu.cc with a voucher (`domain_claim.py`). Registry limits: no 2–3 letter names, no brand terms; everything else passes. 3 accounts from one Gmail (dot-variants don't collide) = **9 free domains**.

### 2. Cloudflare zone + DNS
- `eu.cc` is on the **Public Suffix List** (line 16098), so Cloudflare accepts `yourname.eu.cc` as a zone on the Free plan.
- Cloudflare → Add Site → your domain → Free plan → copy the two assigned NS.
- gname → Domain Management → **Modify DNS** → replace NS with Cloudflare's (same via their API `/api/domain/dns`).
- Propagation: minutes to a few hours. Cloudflare now serves your DNS (A/AAAA/MX/TXT).

### 3. Catch-all mail (OTP engine)
- Cloudflare → **Email Routing** → Enable (free). CF auto-creates the MX + SPF TXT records.
- Add your Gmail as destination address, confirm it.
- Turn on **Catch-all address** → every mailbox `*@yourdomain.eu.cc` now lands in your Gmail.
- Read codes over Gmail IMAP with an app password — that's what `gname_reg.py`'s `imap_code()` pattern does. Unlimited unique emails, no temp-mail services, no plus-alias canonicalization problems.

### 4. Corporate mail on the domain (real mailboxes)
- **Zoho Mail Forever Free**: 5 users, 5GB each, single custom domain, web + mobile apps. Free, but **IMAP/POP/ActiveSync are NOT included** on the free tier (web/app access only).
- Setup: Zoho Mail → add domain → verify with a TXT record in Cloudflare DNS → point MX to Zoho's records (replace CF Email Routing MX for those users, or keep catch-all on a subdomain) → add SPF/DKIM TXT in Cloudflare.
- Result: `you@yourdomain.eu.cc` corporate mailbox for forms, support, banking-style signups; catch-all on the same domain feeds the OTP automation.

### Combined topology (what we run)
```
yourname.eu.cc  (gname, $0, renewed $0)
   └── NS → Cloudflare (free zone, PSL-backed)
        ├── Email Routing catch-all → Gmail → IMAP → autoreg OTP
        ├── A/AAAA records → any host/VPS
        └── MX → Zoho Forever Free (5 corporate mailboxes, web/app)
```

## Disclaimer

For security research and automation of your own accounts/infrastructure. Obey each service's ToS and local law.
