"""
Authentication module for Snowflake Cortex A2A Agent.
Handles JWT generation using Key-Pair authentication.
"""
import time
import base64
import jwt
from cryptography.hazmat.primitives import serialization, hashes


def generate_snowflake_jwt(account: str, user: str, private_key_path: str) -> str:
    """
    Generates a secure, short-lived JWT for Snowflake API access.
    
    The JWT issuer includes the public key fingerprint as required by Snowflake.
    
    Args:
        account: Snowflake account locator (e.g., ABC12345)
        user: Snowflake username
        private_key_path: Path to the RSA private key file (.p8)
    
    Returns:
        A signed JWT token string
    
    Raises:
        ValueError: If private key file is not found
    """
    
    # Load Private Key
    try:
        with open(private_key_path, "rb") as key_file:
            private_key = serialization.load_pem_private_key(
                key_file.read(), 
                password=None  # Add password here if your key is encrypted
            )
    except FileNotFoundError:
        raise ValueError(f"Private Key not found at {private_key_path}")

    # Compute public key fingerprint (SHA256)
    public_key = private_key.public_key()
    public_key_der = public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    
    digest = hashes.Hash(hashes.SHA256())
    digest.update(public_key_der)
    fingerprint = base64.b64encode(digest.finalize()).decode('utf-8')

    # Generate JWT claims
    # Use uppercase for Account/User to avoid common 403 errors
    qualified_name = f"{account.upper()}.{user.upper()}"
    
    # Snowflake requires the fingerprint in the issuer claim
    issuer_with_fingerprint = f"{qualified_name}.SHA256:{fingerprint}"
    
    payload = {
        "iss": issuer_with_fingerprint,
        "sub": qualified_name,
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600  # 1 hour expiration
    }
    
    # Sign Token
    token = jwt.encode(payload, private_key, algorithm="RS256")
    return token
