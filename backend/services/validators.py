INSTITUTIONAL_EMAIL_DOMAIN = "unmsm.edu.pe"


def is_institutional_email(email: str) -> bool:
    """Return whether an address belongs to the exact UNMSM domain."""
    if not isinstance(email, str):
        return False

    normalized_email = email.strip().casefold()
    local_part, separator, domain = normalized_email.rpartition("@")

    return bool(
        separator
        and local_part
        and "@" not in local_part
        and domain == INSTITUTIONAL_EMAIL_DOMAIN
    )
