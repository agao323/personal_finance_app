/**
 * Whether this is the public demo build.
 *
 * Read from a `NEXT_PUBLIC_` variable so the value is **inlined at build time**. That
 * is the point: `process.env.NEXT_PUBLIC_DEMO === "true"` collapses to a literal, and
 * the bundler drops the branch that does not run. The demo bundle therefore does not
 * merely decline to authenticate — it does not contain the code that could.
 *
 * A runtime flag would leave the sign-in path shipped and one condition away from
 * being reachable, which is exactly the shape ticket 037 rejects for the demo
 * boundary generally.
 */
export const IS_DEMO = process.env.NEXT_PUBLIC_DEMO === "true";
