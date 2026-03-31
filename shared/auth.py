"""
Authentication module for Snowflake Cortex A2A agents (SPCS runtime).
"""
import base64
import os
import time

import jwt
from cryptography.hazmat.primitives import hashes, serialization

SPCS_TOKEN_PATH = "/snowflake/session/token"


def get_spcs_session_token() -> str:
    """
    Read the SPCS session token from the standard token file.

    Returns:
        The session token string

    Raises:
        ValueError: If token file is not found or empty
    """
    try:
        with open(SPCS_TOKEN_PATH, "r") as token_file:
            token = token_file.read().strip()
            if not token:
                raise ValueError("SPCS session token file is empty")
            return token
    except FileNotFoundError:
        raise ValueError(
            f"SPCS session token not found at {SPCS_TOKEN_PATH}. "
            "Make sure you are running inside Snowpark Container Services."
        )


def generate_snowflake_jwt(account: str, user: str, private_key_path: str) -> str:
    """Generate a Snowflake JWT for key-pair authentication."""
    with open(private_key_path, "rb") as key_file:
        private_key = serialization.load_pem_private_key(key_file.read(), password=None)

    public_key_der = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    digest = hashes.Hash(hashes.SHA256())
    digest.update(public_key_der)
    fingerprint = base64.b64encode(digest.finalize()).decode("utf-8")

    qualified_name = f"{account.upper()}.{user.upper()}"
    payload = {
        "iss": f"{qualified_name}.SHA256:{fingerprint}",
        "sub": qualified_name,
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
    }
    return jwt.encode(payload, private_key, algorithm="RS256")


def get_auth_token_and_type() -> tuple[str, str]:
    """
    Get the SPCS session token for authentication.

    Returns:
        Tuple of (token, "OAUTH")
    """
    return get_spcs_session_token(), "OAUTH"
