import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from pwdlib import PasswordHash

from newsalert.db.session import DbSession
from newsalert.db.users import User

passwords = PasswordHash.recommended()
dummy_hash = passwords.hash("unused-login-timing-placeholder")


def csrf_token(request: Request) -> str:
    if "csrf" not in request.session:
        request.session["csrf"] = secrets.token_urlsafe(32)
    return request.session["csrf"]


def require_csrf(request: Request) -> None:
    expected = request.session.get("csrf")
    supplied = request.headers.get("x-csrf-token", "")
    if not expected or not secrets.compare_digest(expected, supplied):
        raise HTTPException(403, "Refresh the page and try again")


def current_user(request: Request, session: DbSession) -> User:
    user_id = request.session.get("user_id")
    user = session.get(User, user_id) if isinstance(user_id, int) else None
    if user is None:
        raise HTTPException(401, "Please sign in")
    return user


CurrentUser = Annotated[User, Depends(current_user)]
