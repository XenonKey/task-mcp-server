from fastmcp.server.auth import RemoteAuthProvider
from fastmcp.server.auth.providers.jwt import JWTVerifier
from pydantic import AnyHttpUrl

from config import settings


def build_auth_provider() -> RemoteAuthProvider:
    issuer = f"https://cognito-idp.{settings.aws_region}.amazonaws.com/{settings.cognito_user_pool_id}"
    jwks_uri = f"{issuer}/.well-known/jwks.json"

    token_verifier = JWTVerifier(jwks_uri=jwks_uri, issuer=issuer, algorithm="RS256")

    return RemoteAuthProvider(
        token_verifier=token_verifier,
        authorization_servers=[AnyHttpUrl(issuer)],
        base_url=settings.mcp_resource_server_url,
    )
