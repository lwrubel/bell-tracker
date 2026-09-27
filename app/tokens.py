"""Signed, expiring password-reset tokens.

No table: the token carries the user id plus a fingerprint of the current
password hash, so it stops working as soon as the password changes - which
makes each link single-use.
"""

import hashlib

from flask import current_app
from itsdangerous import BadSignature, URLSafeTimedSerializer

from app import db
from app.models import User

RESET_SALT = "password-reset"
RESET_MAX_AGE = 60 * 60  # seconds


def _serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt=RESET_SALT)


def _password_fingerprint(user):
    return hashlib.sha256(user.password_hash.encode()).hexdigest()[:16]


def make_reset_token(user):
    return _serializer().dumps({"uid": user.id, "ph": _password_fingerprint(user)})


def verify_reset_token(token, max_age=RESET_MAX_AGE):
    """Return the token's user, or None if it's invalid, expired, or used."""
    try:
        data = _serializer().loads(token, max_age=max_age)
    except BadSignature:  # SignatureExpired is a subclass
        return None
    user = db.session.get(User, data.get("uid"))
    if user is None or data.get("ph") != _password_fingerprint(user):
        return None
    return user
