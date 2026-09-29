# References

Version-pinned notes on the external things this code depends on, written for an agent
whose training data may describe a different version. Each note names its source, the
version it describes, the date someone last checked it against that source, and the files
in this repo that rely on it. Plain text, `*-llms.txt`, so it can be read into context
whole. A check fails if a file here is missing from this page.

When a note and the source disagree, the source wins — update the note and its date. When a
note and this repo's code disagree, one of them is a bug: find out which.

| Note | Covers | Pinned to | Verified |
|---|---|---|---|
| [nextjs-16-llms.txt](nextjs-16-llms.txt) | Next.js 16's breaking changes this app runs into: `proxy.ts`, async request APIs, typegen, no `next lint` | next 16.3.1 | 2026-09-27 |
| [openapi-typescript-llms.txt](openapi-typescript-llms.txt) | How `api-types.ts` is generated and what its shapes look like | openapi-typescript 7.13.0 | 2026-09-27 |
| [cloudflare-access-jwt-llms.txt](cloudflare-access-jwt-llms.txt) | Verifying `Cf-Access-Jwt-Assertion` at the origin | Cloudflare docs as of the date | 2026-09-27 |
| [fly-private-networking-llms.txt](fly-private-networking-llms.txt) | `.internal`, 6PN, why not Flycast, `fly ips list` | Fly docs as of the date | 2026-09-27 |
| [neon-pooling-llms.txt](neon-pooling-llms.txt) | Pooled vs direct connection strings, transaction-mode limits | Neon docs as of the date | 2026-09-27 |
| [simplefin-protocol-llms.txt](simplefin-protocol-llms.txt) | The SimpleFIN protocol and Bridge limits, for ticket 075 | protocol 2.0.0-draft | 2026-09-27 |
