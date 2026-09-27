# 048 — The slow first load is a cold start, and it is 5.5 seconds
Status: done
Wave: 6   Lane: —
Blocked by: none
Read first: docs/adr/0001-hosting.md

## Goal
Opening the app after not using it for a while feels immediate rather than broken.

## What was measured

`fly logs -a pfa-web`, a real cold start on 2026-08-26:

```
20:52:57  Starting machine
20:52:58  Machine started in 1.293s
20:52:59  Health check 'health' has failed. Your app is not responding properly.
20:53:04  ▲ Next.js 16.3.1  ✓ Ready
20:53:04  machine became reachable in 5.478868974s
20:53:05  Health check 'health' is now passing.
```

**5.5 seconds before the first byte.** Fly's VM is not the problem — it boots in 1.3s.
The other 4.2s is Node starting the Next standalone server on a `shared-cpu-1x`.

Ruled out by measurement rather than reasoning, because the obvious suspects were wrong:

| Suspect | Measured | Verdict |
|---|---|---|
| Neon compute suspended | 287ms first connect, 43ms pooled | Not it |
| Query cost | 58ms for two counts over the full tables | Not it |
| Warm request handling | 55ms TTFB | Not it |
| **Next.js cold start** | **4.2s of a 5.5s wait** | **This** |

`min_machines_running = 0` with `auto_stop_machines = "stop"` means this is paid on
essentially every visit — one household's traffic is far too sparse to keep a machine
alive on its own.

## Acceptance criteria
- [x] `min_machines_running = 1` on `pfa-web`, so an ordinary visit never waits for a boot
- [x] The comment in `fly.web.toml` says what it costs and why, since the current one
      argues the opposite case and is what led here
- [x] Measured again after deploying, and the number recorded in this ticket
- [x] `pfa-api` left alone. It already has no autostop, deliberately: it sits behind
      `.internal` with no Fly proxy in front to wake it, so a sleeping API is simply
      unreachable rather than slow

## Files
- `fly.web.toml`

## Notes

**What this costs:** one `shared-cpu-1x` / 512MB machine running continuously, roughly
$2 a month. The idle-cost saving it replaces was real but it was buying a 5.5 second
wait on every visit to an app used a few times a day.

**Why not a bigger VM.** More CPU would cut the 4.2s, but it pays for a faster boot on
every visit rather than removing the boot. Keeping one machine warm makes startup time
matter only on deploys, where nobody is waiting on it.

**Why not `auto_stop_machines = "suspend"`.** Fly can snapshot memory and resume in
well under a second, which would be cheaper and nearly as fast. Rejected for now on the
"prefer boring" rule in CLAUDE.md: it is a second mechanism with its own failure modes,
to save about $2 a month on an app with one household. Worth revisiting only if the
always-on machine turns out to cost more than expected.

**The second machine still autostops.** `min_machines_running = 1` is a floor, not a
pin — the standby stays asleep until it is needed.

## Done — 2026-08-26

Deployed as v13. One machine `started` and passing, the other `stopped` — the floor
behaves as a floor.

| | Before | After |
|---|---|---|
| First byte, machine asleep | **5.48s** | n/a — it does not sleep |
| First byte, warm | 55ms | 52–66ms |
| Through Cloudflare | — | 48–68ms |

**The diagnosis was worth the measurement.** Neon suspending its compute was the
plausible-sounding cause and would have led to a pooler change, a keepalive ping, or a
paid Neon tier — none of which would have helped. It answers in 287ms cold and 43ms
pooled. The 4.2 seconds was Node.

**What is still slow, and deliberately not fixed:** the boot itself. It now happens on
deploys, where the release is already waiting, instead of in front of a person opening
their own app.
