"""Who you are.

**Cloudflare Access is the authentication** and the `users` table is the allowlist.
There is no password endpoint, no passkey ceremony, and no application session — this
router reports the identity `deps.current_user` resolved and nothing else. See
docs/adr/0007-drop-passkeys.md for why the passkey layer that used to live here was
removed, and docs/SECURITY.md#auth for what stands in its place.

There is no sign-out route. The only session is Cloudflare's, and only Cloudflare can
end it: `/cdn-cgi/access/logout` on this hostname. Worth knowing that it fails when the
Access organisation in the cookie no longer resolves, which is why `web/src/proxy.ts`
clears `CF_Authorization` from the origin on a failed assertion (ticket 042). That is
now the only in-browser recovery from a stuck Access session.

Route docstrings are part of the frozen contract — see the note in `routers/rules.py`.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.deps import CurrentUser
from app.schemas.auth import SessionRead
from app.schemas.common import ErrorResponse

router = APIRouter(prefix="/auth", tags=["auth"], responses={401: {"model": ErrorResponse}})


@router.get("/session", response_model=SessionRead)
def read_session(user: CurrentUser) -> SessionRead:
    """The signed-in household member."""
    return SessionRead(user_id=user.id, email=user.email, display_name=user.display_name)
