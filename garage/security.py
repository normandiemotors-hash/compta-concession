"""Mots de passe (PBKDF2), sessions et jetons CSRF."""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

ITERATIONS = 600_000
SESSION_JOURS = 7


def hash_password(mot_de_passe, salt=None):
    salt = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", mot_de_passe.encode("utf-8"), bytes.fromhex(salt), ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${salt}${dk.hex()}"


def verify_password(mot_de_passe, stored):
    try:
        _algo, iters, salt, hexhash = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", mot_de_passe.encode("utf-8"), bytes.fromhex(salt), int(iters))
        return hmac.compare_digest(dk.hex(), hexhash)
    except Exception:
        return False


def new_token():
    return secrets.token_urlsafe(32)


def hash_token(token):
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def _maintenant():
    return datetime.now().replace(microsecond=0)


def create_session(conn, utilisateur_id, jours=SESSION_JOURS):
    token = new_token()
    csrf = secrets.token_urlsafe(24)
    expire = (_maintenant() + timedelta(days=jours)).isoformat(timespec="seconds")
    conn.execute("DELETE FROM sessions WHERE expire_le < ?", (_maintenant().isoformat(timespec="seconds"),))
    conn.execute(
        "INSERT INTO sessions(hash_token, utilisateur_id, csrf, expire_le) VALUES (?,?,?,?)",
        (hash_token(token), utilisateur_id, csrf, expire),
    )
    conn.commit()
    return token, csrf


def get_session(conn, token):
    if not token:
        return None
    return conn.execute(
        """SELECT s.hash_token, s.csrf, s.expire_le, u.id AS utilisateur_id, u.nom_utilisateur, u.role
           FROM sessions s JOIN utilisateurs u ON u.id = s.utilisateur_id
           WHERE s.hash_token = ? AND s.expire_le >= ?""",
        (hash_token(token), _maintenant().isoformat(timespec="seconds")),
    ).fetchone()


def destroy_session(conn, token):
    if token:
        conn.execute("DELETE FROM sessions WHERE hash_token = ?", (hash_token(token),))
        conn.commit()


def csrf_ok(req):
    if req.session is None:
        return False
    sent = req.form.get("csrf") or req.headers.get("X-CSRF-Token", "")
    return hmac.compare_digest(sent, req.session["csrf"])
