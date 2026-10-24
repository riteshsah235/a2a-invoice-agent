from fastapi import Request, Header, HTTPException, status
from app.utils.crypto import derive_principal_id


def verify_a2a_version(a2a_version: str = Header(None, alias="A2A-Version")) -> str:
    """Verify that the A2A-Version header is present and exactly 1.0."""
    if not a2a_version:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing A2A-Version header. Expected: 1.0",
        )
    if a2a_version.strip() != "1.0":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported A2A-Version: '{a2a_version}'. Expected: 1.0",
        )
    return a2a_version.strip()


def verify_content_type(request: Request):
    """Verify that POST requests use application/a2a+json content type."""
    if request.method == "POST":
        content_type = request.headers.get("content-type", "")
        # Allow application/a2a+json (and strip charset if present)
        main_type = content_type.split(";")[0].strip().lower()
        if main_type != "application/a2a+json":
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"Invalid Content-Type: '{content_type}'. Expected 'application/a2a+json'",
            )


def get_current_principal(authorization: str = Header(None, alias="Authorization")) -> str:
    """Validate Bearer token authentication and derive isolated principal identity."""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    parts = authorization.strip().split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization scheme. Expected: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = parts[1].strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token cannot be empty",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return derive_principal_id(token)
