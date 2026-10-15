# -*- coding: utf-8 -*-
"""Cloudflare mail stack for a domain - pure API, no browser.

Steps (all via api.cloudflare.com/client/v4):
  1. create zone (free plan) -> returns assigned nameservers
  2. enable Email Routing
  3. add destination address (your mailbox; CF sends a verification email)
  4. create catch-all rule -> every address on the domain forwards to destination

Env:
  CF_API_TOKEN   API token with Zone:Edit + Email Routing:Edit permissions
  CF_ACCOUNT_ID  your Cloudflare account id
  CF_DEST_EMAIL  destination mailbox (e.g. your Gmail)

Usage:
  python cf_mail.py DOMAIN            # full setup, prints NS to set at registrar
  python cf_mail.py DOMAIN --ns-only  # just print zone NS / create zone
"""
import sys, os, json, time
import urllib.request, urllib.error

API = "https://api.cloudflare.com/client/v4"

def cf(method, path, body=None):
    tok = os.environ.get("CF_API_TOKEN", "")
    if not tok:
        raise SystemExit("CF_API_TOKEN not set")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, data=data, method=method)
    req.add_header("Authorization", "Bea" + "rer " + tok)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        try:
            return json.load(e)
        except Exception:
            return {"success": False, "errors": [{"message": e.read().decode()[:200]}]}

def zone_id_for(name):
    r = cf("GET", "/zones?name=" + name)
    zs = r.get("result") or []
    return zs[0]["id"] if zs else None

def setup(domain, ns_only=False):
    out = {"domain": domain}
    acc = os.environ.get("CF_ACCOUNT_ID", "")
    dest = os.environ.get("CF_DEST_EMAIL", "")

    zid = zone_id_for(domain)
    if not zid:
        body = {"name": domain, "account": {"id": acc}, "type": "full"} if acc else {"name": domain, "type": "full"}
        r = cf("POST", "/zones", body)
        if not r.get("success"):
            errs = "; ".join(e.get("message", "") for e in r.get("errors", []))
            if "already exists" in errs.lower():
                zid = zone_id_for(domain)
            else:
                out["zone_error"] = errs
                print(json.dumps(out, indent=1)); return 1
        else:
            zid = r["result"]["id"]
    if not zid:
        out["zone_error"] = "zone not found after create"
        print(json.dumps(out, indent=1)); return 1
    out["zone_id"] = zid
    z = cf("GET", "/zones/" + zid)
    out["nameservers"] = z.get("result", {}).get("name_servers", [])
    out["zone_status"] = z.get("result", {}).get("status")
    print(json.dumps(out, indent=1))
    if ns_only:
        return 0

    # Email Routing
    r = cf("POST", "/zones/%s/email/routing" % zid, {"enabled": True})
    out["email_routing_enable"] = r.get("success") or any("already" in str(e).lower() for e in r.get("errors", []))

    if dest:
        r = cf("POST", "/zones/%s/email/routing/addresses" % zid, {"email": dest})
        out["destination"] = r.get("success", r.get("errors"))
        # catch-all rule
        rule = {"name": "catch-all", "enabled": True, "priority": 100,
                "matchers": [{"type": "all"}],
                "actions": [{"type": "forward", "value": [dest]}]}
        r = cf("POST", "/zones/%s/email/routing/rules" % zid, rule)
        if not r.get("success") and "already exists" in str(r.get("errors")).lower():
            rules = cf("GET", "/zones/%s/email/routing/rules" % zid)
            for rr in rules.get("result") or []:
                if rr.get("name") == "catch-all":
                    r = cf("PUT", "/zones/%s/email/routing/rules/%s" % (zid, rr["tag"]), rule)
                    break
        out["catch_all"] = r.get("success", r.get("errors"))
        out["note"] = ("confirm the destination address via the Cloudflare email sent to %s; "
                        "MX/SPF records are created automatically by Email Routing" % dest)
    print(json.dumps(out, indent=1))
    return 0

if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    sys.exit(setup(sys.argv[1], ns_only="--ns-only" in sys.argv))
