import logging
import secrets

logger = logging.getLogger(__name__)


def generate_license_key() -> str:
    return secrets.token_urlsafe(48)


def normalize_domain(domain: str) -> str:
    """Strip scheme, path, port for comparison."""
    d = (domain or "").strip().lower()
    if d.startswith("http://"):
        d = d[7:]
    elif d.startswith("https://"):
        d = d[8:]
    d = d.split("/")[0].split(":")[0]
    return d


def validate_domain_format(domain: str) -> bool:
    domain = normalize_domain(domain)
    if not domain or len(domain) > 255:
        return False
    if domain in ("localhost", "127.0.0.1"):
        return True
    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789.-")
    return all(c in allowed for c in domain) and "." in domain
