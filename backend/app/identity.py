"""Compatibility exports. Identity is resolved in app.authn."""

from app.authn import DEMO_USER_HEADER, require_roles, require_user

require_role = require_roles
__all__ = ["DEMO_USER_HEADER", "require_roles", "require_role", "require_user"]
