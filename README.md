# gname-eucc-toolkit

**Full-auto free-domain + mail pipeline.** One command: claim free `.eu.cc` domains on [gname.com](https://www.gname.com/) (voucher = $0.00), set DNS, wire mail (Cloudflare catch-all or self-hosted MX), watch everything in a dashboard.

```
python auto.py --domains 2 --mail cf --serve
```

## What's automated

| Stage | Script | How |
|---|---|---|
| Account registration | `gname_reg.py` | Playwright headless, solves the custom `GnSliderVerify` slider (reversed, see below), email code via IMAP |
| Login | `login.py` | Password tab + login slider + image captcha via any OpenAI-compatible vision model |
| Domain claim | `claim_domain.py` | Promo `POST /hd_eucc/freereg` claims 3 full-discount `.eu.cc` vouchers → Search → Add to Cart → cart select → Submit → Pay (contact form + czyz unlock + modal chain) → voucher auto-applied, **$0.00** hold; appends `data/eucc_domains.jsonl` |
| Live domain list | `list_domains.py` | Real dashboard API `POST /user_ym/get_ym_list` — domain, expire, coupon used, status |
| DNS records | `setup_dns.py` | A / MX / TXT / CNAME + NS change via in-page `/user_ym/jx_edit`; auto-handles operation-protection (czyz): channel enable `[1,4]`, challenge → email code → `aqbh_check`, tokenless `-101` session unlock → retry, and slider-gated email send (`code -105001` → site `slide_yz` popup → one-time code → `re_yzm` param). Wrong codes latch a ~1h block server-side — never brute-force codes |
| Self-hosted catch-all | `mail_catcher/catcher.py` | **RECOMMENDED**: tiny aiosmtpd MX server on your VPS (:25) — accepts `*@yourdomains`, stores `.eml`, relays copy to Gmail (SMTP_SSL 465). Works where free relays denylist the domain (ForwardEmail denylists all of `eu.cc`) |
| DNS record cleanup | `dns_clean.py` | `POST /user_ym/get_jx_list` → `/user_ym/jx_del`: purge stale records (`--match forwardemail`, `--ip 1.2.3.4`) |
| Outbound SMTP | `mail_catcher/submit.py` | Send mail **as your domain**: authenticated submission on VPS `:587` (LOGIN + STARTTLS), direct-MX delivery with automatic Gmail-relay fallback when outbound :25 is blocked. SPF TXT set automatically by `auto.py --mail dns` |
| OTP mailbox API | `mail_catcher/otp_api.py` | stdlib HTTP `:2525` over the catcher's mail store: `/next` issues a fresh mailbox, `/latest?address=..&wait=60` long-polls the OTP and parses the code, `/acquire`, `/list`, `/health` — register-then-read-OTP without IMAP |
| ForwardEmail mail | *(via `auto.py --mail fwd`)* | MX `mx1/mx2.forwardemail.net` + TXT `forward-email=DEST` through gname DNS. NOTE: ForwardEmail **denylists `eu.cc`** (5.1.1 at SMTP) — use `mail_catcher` for these domains |
| Cloudflare mail | `cf_mail.py` | Pure API: create zone → enable Email Routing → destination address → **catch-all rule** (every `*@yourdomain` forwards to your Gmail). MX/SPF auto-created by CF |
| Orchestration | `auto.py` | login → claim N → mail setup → NS switch → `data/status.json` |
| Dashboard | `dashboard.py` | stdlib HTTP (:8570): domains, pipeline status, live OTP inbox (codes parsed from subjects) |
| MFA bind | `mfa_bind.py` | TOTP on the account (keeps farm accounts recoverable) |
| Captcha RE | `gsv_deob*.py`, `gsv_deob2.js` | Deobfuscators for the site slider JS (7574 transitive aliases removed) |

## Quickstart

```
pip install playwright && playwright install chromium

export GNAME_EMAIL=you@gmail.com          # or use data/gname_accounts.jsonl bank
export GNAME_PASSWORD=***
export GM_EMAIL=you@gmail.com             # mailbox that receives codes/catch-all
export GM_APPPW=********                  # Gmail app password (IMAP)

python login.py                # or gname_reg.py to register a fresh account
python auto.py --domains 3 --prefix myname
python dashboard.py            # http://127.0.0.1:8570
```

### Instant catch-all mail — self-hosted MX (RECOMMENDED, proven E2E)
Deploy `mail_catcher/catcher.py` on any VPS with inbound :25 (see `mail_catcher/README.md`), then:
```
export DNS_A_IP=YOUR_VPS_IP
python auto.py --domains 3 --mail dns    # A mail->IP + MX @->mail.domain (prio 5)
```
Proven chain: external sender → public MX `mail.<domain>.eu.cc` → VPS :25 catcher → `.eml` stored + relayed to Gmail (`[catch otp-...@domain]` subject, verification code in body — `imap_code`/dashboard read it). Works for 3/3 live domains.
Proven outbound chain: client → VPS `:587` (auth LOGIN, TLS) → Gmail relay fallback → recipient inbox with `From: you@yourdomain` (marker test found in INBOX). Proven OTP loop: `/next` → mail to issued address → `/latest?wait=90` → `CODE VALID: True` (see `mail_catcher/README.md`).
Purge stale records anytime: `python dns_clean.py <domain> --match forwardemail` / `--ip OLD_IP`.

### ForwardEmail (non-denylisted domains only)
```
export MAIL_DEST=you@gmail.com     # default: GM_EMAIL
python auto.py --domains 3 --mail fwd
```
Sets MX (`mx1/mx2.forwardemail.net`) + TXT (`forward-email=you@gmail.com`). **`eu.cc` is denylisted by ForwardEmail free tier** (SMTP 5.1.1 "Recipient domain is denylisted") — use the self-hosted catcher above for these zones.

### Cloudflare catch-all mail (optional)
```
export CF_API_TOKEN=***       # Zone:Edit + Email Routing:Edit
export CF_ACCOUNT_ID=...
export CF_DEST_EMAIL=you@gmail.com
python auto.py --domains 1 --mail cf
```
`eu.cc` is on the Public Suffix List → Cloudflare accepts `yourname.eu.cc` as a Free-plan zone. CF returns 2 nameservers; the pipeline sets them at gname automatically (`setup_dns.py --ns`). Confirm the destination address from the CF email — after that **every address on your domain is live** and OTP codes land in your Gmail (visible in the dashboard inbox).

### Self-hosted MX (no Cloudflare)
```
export DNS_A_IP=1.2.3.4
python auto.py --domains 1 --mail dns   # A mail->IP + MX @->mail.domain
```

### Corporate mailboxes (Zoho Forever Free)
5 users × 5GB on your domain, free: add the domain in Zoho Mail → verify with a TXT record (`setup_dns.py DOM --txt "@=zoho-verification=..."`) → point MX to Zoho (`--mx @=mx.zoho.com:10 --mx @=mx2.zoho.com:20`) → SPF/DKIM TXT via the same script. Free tier has no IMAP (web/mobile only) — keep the CF catch-all → Gmail channel for OTP automation.

## Env reference

```
GNAME_HOME        state dir (default ./data)
GNAME_EMAIL / GNAME_PASSWORD   login creds (alternative: data/gname_accounts.jsonl)
GM_EMAIL / GM_APPPW    Gmail IMAP for codes + catch-all destination
MAIL_DEST         catch-all forward destination for --mail fwd (default GM_EMAIL)
VL_BASE / VL_MODEL / VL_KEY   vision endpoint for image captchas (default :16432 qwen3-vl-plus)
CF_API_TOKEN / CF_ACCOUNT_ID / CF_DEST_EMAIL   Cloudflare
DNS_A_IP          mail server IP for --mail dns
CONTACT_*         registrant contact template (first checkout)
GNAME_DASH_PORT   dashboard port (default 8570)
```

## How the slider bypass works

1. The site draws a 400px track but the client clamps the required distance to `width - barWidth` from a **config value of 360px**. Undershooting by 2px = silent reset with zero POSTs (why generic solvers "see nothing").
2. Payload `details` is AES-CBC: `{m: trajectory-hex, st, et, f: GnClientJS fingerprint, ...}` → token 40 hex / 300s.
3. Server gates: duration 10ms–30s, 3–1000 points, must reach the clamped distance.
4. Fix: **+40px overshoot** and saturate wiggles before mouseup (`human_drag` in `gname_core.py`). Both variants covered: embedded (`re_yzm`) and popup (`#pop-txyz`).

## Facts

- 3 full-discount `.eu.cc` vouchers per account; registration AND renewal $0
- Registry limits: no 2–3 letter names, no brand terms
- Dot-variant Gmails (`y.ourname@gmail.com`) register as separate accounts → 3 accounts = 9 free domains from one inbox
- ~90s per account, ~2min per domain claim

## Disclaimer

For security research and automation of your own accounts/infrastructure. Obey each service's ToS and local law.
