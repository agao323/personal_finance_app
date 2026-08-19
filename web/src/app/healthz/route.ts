/**
 * Liveness for the Fly health check.
 *
 * Exists because the check cannot point at `/` any more: ticket 035 made that redirect
 * unauthenticated visitors to `/login`, Fly's HTTP check wants a 2xx, and a 307 reads
 * as a failing machine. The deploy that followed timed out waiting for health on a
 * machine that was serving perfectly.
 *
 * Pointing the check at `/login` instead would work today and break the day the sign-in
 * page moves or gains a redirect of its own. This route says what it is for, returns
 * the same thing forever, and is exempt from the auth redirect deliberately rather
 * than by coincidence.
 *
 * Liveness only — it reports that this process is serving, and deliberately does not
 * check the API or the database. A web machine that Fly restarts because Postgres
 * blinked is a worse outage than the one it was trying to fix. `/api/ready` is the
 * readiness probe, and it is for humans and uptime checks, not for the orchestrator.
 */
export function GET() {
  return Response.json({ status: "ok" });
}
