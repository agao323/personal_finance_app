# Verifying the Access gate and the origin lock

Ticket 036. Run this after any change to the Fly configuration, the Access policy, or
the DNS records — and record the results in the table in `docs/adr/0002-auth.md`.

"It should be private" is not the same as having checked.

## 1. The Access application exists and its policy is right

Cloudflare dashboard → Zero Trust → Access → Applications.

- Application on `allofmymoney.com`, covering `*` (the whole hostname).
- Policy: **Allow**, with an **Emails** rule listing exactly the household's addresses.
  Not a domain rule — `@gmail.com` is not a household.
- Copy the **Application Audience (AUD) tag**. It goes in the Fly secret below.

```bash
fly secrets set CF_ACCESS_AUD=<the aud tag> -a pfa-web
```

`CF_ACCESS_TEAM_DOMAIN` is already in `fly.web.toml`. Both must be present or the
origin does not enforce the assertion at all.

## 2. An unauthenticated request cannot reach the app

From a browser with no Cloudflare session — a private window is not enough if you are
already signed in to Cloudflare in that profile; use a different browser or a fresh
profile.

```bash
curl -sS -o /dev/null -w '%{http_code} %{redirect_url}\n' https://allofmymoney.com/
```

**Expected:** a 302 to `https://<team>.cloudflareaccess.com/...`, never a 200.

## 3. The API has no public address

```bash
fly ips list -a pfa-api
```

**Expected:** no `v4` or `v6` public address. A `private_v6` entry is correct and
expected — that is the address the web app proxies to.

Then confirm from outside:

```bash
curl -sS --max-time 10 https://pfa-api.fly.dev/health
```

**Expected:** DNS failure or a connection timeout. A response of any kind, including a
404, means the app is publicly addressable and must be fixed before real data goes in.

## 4. The origin rejects a request that did not pass Access

This is the defense-in-depth check. It only means anything once `CF_ACCESS_AUD` is set.

```bash
fly ssh console -a pfa-web -C "curl -sS -o /dev/null -w '%{http_code}\n' http://localhost:3000/"
```

**Expected:** `403`. The request came from inside the machine, so it carries no
`Cf-Access-Jwt-Assertion`, and the origin should refuse it.

If it returns 200, the variables are not both set — check `fly secrets list -a pfa-web`.

## 5. Headers

```bash
curl -sSI https://allofmymoney.com/ | grep -iE 'strict-transport|x-robots|x-frame'
```

**Expected:** `Strict-Transport-Security` with a two-year max-age, `X-Robots-Tag:
noindex, nofollow`, `X-Frame-Options: DENY`.

## 6. The demo is *not* covered by any of this

Once ticket 037 exists, confirm the opposite for `demo.allofmymoney.com`: no Access
application, `X-Robots-Tag: all`, and a 200 from a clean browser. A demo behind Access
is a demo nobody can see.
