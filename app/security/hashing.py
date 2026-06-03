"""One-way hashing utilities for PII protection.

All personally identifiable information received from DigiLocker is
hashed before storage so that raw PII is never persisted.

Functions to be implemented:
    - hash_digilocker_id: SHA-256 hash a DigiLocker user identifier.
    - compute_proof_hash: Generate a composite proof hash for audit integrity.
"""
