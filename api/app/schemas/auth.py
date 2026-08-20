"""The signed-in identity.

No password schema and no ceremony schemas exist here. Cloudflare Access authenticates;
this app reports who it said you are. See docs/adr/0007-drop-passkeys.md.
"""

from __future__ import annotations

from app.schemas.common import Schema


class SessionRead(Schema):
    user_id: int
    email: str
    display_name: str
