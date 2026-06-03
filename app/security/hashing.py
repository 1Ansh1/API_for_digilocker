"""One-way hashing utilities for PII protection.

All personally identifiable information received from DigiLocker is
hashed before storage so that raw PII is never persisted.
"""

import hashlib
import hmac

__all__ = ["hash_digilocker_id", "compute_proof_hash"]


def hash_digilocker_id(digilocker_id: str) -> str:
    """SHA-256 hash a DigiLocker user identifier.

    Parameters
    ----------
    digilocker_id:
        The raw DigiLocker ID of the user.

    Returns
    -------
    str
        Hex digest of the SHA-256 hash.
    """
    return hashlib.sha256(digilocker_id.encode("utf-8")).hexdigest()


def compute_proof_hash(
    user_id: str,
    digilocker_id: str,
    name: str,
    dob: str,
    gender: str,
    hmac_key: str,
) -> str:
    """Generate a composite proof hash for audit integrity.

    Combines demographic info and the external user ID into a secure HMAC signature.

    Parameters
    ----------
    user_id:
        The application-level external user ID.
    digilocker_id:
        The raw DigiLocker ID.
    name:
        User's full name.
    dob:
        User's date of birth.
    gender:
        User's gender.
    hmac_key:
        HMAC key used for signing the composite string.

    Returns
    -------
    str
        Hex digest of the HMAC-SHA256 signature.
    """
    data = f"{user_id}:{digilocker_id}:{name}:{dob}:{gender}"
    key = hmac_key.encode("utf-8") if hmac_key else b"default_key"
    return hmac.new(key, data.encode("utf-8"), hashlib.sha256).hexdigest()

