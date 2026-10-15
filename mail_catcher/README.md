# mail_catcher — self-hosted catch-all MX

ForwardEmail (and most free catch-all relays) **denylist the whole `eu.cc` zone**,
so `--mail fwd` does not deliver for these domains. This catcher replaces it with
your own MX on any VPS with inbound port 25 open.

## How it works
1. DNS: `A mail.<yourdomain> = VPS_IP`, `MX @ = mail.<yourdomain> (prio 5)`.
2. `catcher.py` listens on `0.0.0.0:25`, accepts mail for **any address / any domain**.
3. Each message is stored as `.eml` under `mail/` and relayed to your Gmail
   (SMTP_SSL 465, app password from `env.json`) with subject `[catch <rcpt>] <orig subject>`,
   so existing IMAP code-readers (`gname_core.imap_code`, dashboard inbox) see OTPs instantly.

## Deploy (Ubuntu 22.04+/Debian, root)
```
mkdir -p /root/mailcatch && cp catcher.py /root/mailcatch/
pip3 install --break-system-packages aiosmtpd
cat > /root/mailcatch/env.json <<'EOF'
{"gm": "you@gmail.com", "gp": "your-gmail-app-password"}
EOF
chmod 600 /root/mailcatch/env.json
# systemd unit:
cat > /etc/systemd/system/mailcatch.service <<'EOF'
[Unit]
Description=Mail catch-all MX server
After=network.target
[Service]
WorkingDirectory=/root/mailcatch
ExecStart=/usr/bin/python3 /root/mailcatch/catcher.py
Restart=always
RestartSec=3
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload && systemctl enable --now mailcatch
```

## Point your domains at it (from this toolkit)
```
python setup_dns.py yourdomain.eu.cc --a "mail=VPS_IP" --mx "@=mail.yourdomain.eu.cc:5"
```
Or one-command: `DNS_A_IP=VPS_IP python auto.py --domains 3 --mail dns`.

## Verify
```
# port open from the internet (not from ISPs that block 25, e.g. home lines):
curl -s "https://check-host.net/check-tcp?host=VPS_IP:25&max_nodes=3" -H "Accept: application/json"
# send a test to the VPS directly (bypasses DNS):
python3 -c "import smtplib;s=smtplib.SMTP('VPS_IP',25);s.sendmail('t@t.t',['otp@test.yourdomain.eu.cc'],'Subject: t\r\n\r\nhi');s.quit()"
journalctl -u mailcatch -n 5   # should log '(relayed)'
```

Proven: gname `.eu.cc` domains → VPS MX → Gmail inbox, verification code visible in body
(subject `[catch otp-...@domain]`), stored `.eml` on the box.
