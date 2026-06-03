"""Unit tests for cryptographic, state, nonce, and hashing utilities."""


from app.security.hashing import compute_proof_hash, hash_digilocker_id
from app.security.pkce import generate_code_challenge, generate_code_verifier
from app.security.state import generate_nonce, generate_state


def test_pkce_generation() -> None:
    """Test that PKCE code verifier and challenge are generated properly."""
    verifier = generate_code_verifier()

    # RFC 7636: A code verifier is a high-entropy cryptographic random string
    # using unreserved characters, with a minimum length of 43 and max of 128.
    assert len(verifier) >= 43
    assert len(verifier) <= 128

    # Unreserved characters: [A-Z], [a-z], [0-9], "-", ".", "_", "~"
    allowed_chars = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")
    assert set(verifier).issubset(allowed_chars)

    challenge = generate_code_challenge(verifier)

    # Base64URL-encoded string should not contain padding character '='
    assert "=" not in challenge
    assert len(challenge) > 0


def test_state_and_nonce_generation() -> None:
    """Test that state and nonce tokens are generated properly and are unique."""
    state1 = generate_state()
    state2 = generate_state()
    nonce1 = generate_nonce()
    nonce2 = generate_nonce()

    assert len(state1) >= 43
    assert len(nonce1) >= 43
    assert state1 != state2
    assert nonce1 != nonce2


def test_pii_hashing() -> None:
    """Test that PII hashing functions are deterministic and secure."""
    digilocker_id = "mock-digilocker-id-123"

    hash1 = hash_digilocker_id(digilocker_id)
    hash2 = hash_digilocker_id(digilocker_id)

    # Deterministic SHA-256 hex digests
    assert hash1 == hash2
    assert len(hash1) == 64

    # Different inputs yield different hashes
    assert hash1 != hash_digilocker_id("another-id")


def test_proof_hash_computation() -> None:
    """Test that the composite proof hash is deterministic and uses HMAC."""
    user_id = "user-123"
    dl_id = "dl-456"
    name = "John Doe"
    dob = "1990-01-01"
    gender = "M"
    hmac_key = "secret-key"

    h1 = compute_proof_hash(user_id, dl_id, name, dob, gender, hmac_key)
    h2 = compute_proof_hash(user_id, dl_id, name, dob, gender, hmac_key)

    # Deterministic
    assert h1 == h2
    assert len(h1) == 64

    # Modifying any parameter should yield a different hash
    assert h1 != compute_proof_hash(user_id, dl_id, "Jane Doe", dob, gender, hmac_key)
    assert h1 != compute_proof_hash(user_id, dl_id, name, dob, gender, "different-key")
