from fastapi import Request, Response
import jwt

async def token_usage_middleware(request: Request, call_next):
    response = await call_next(request)
    status_code = response.status_code
    blocked = status_code >= 400  # Bug 3a: Update blocked flag based on status code

    if request.state.auth_method == "api_token":
        token = request.headers.get("Authorization").split(" ")[1]
        try:
            payload = jwt.decode(token, options={"verify_signature": False})
            # Log the token usage with the correct blocked flag
            log_token_usage(
                token=payload["jti"],
                user_id=payload["sub"],
                endpoint=request.url.path,
                status_code=status_code,
                blocked=blocked,
                block_reason="http_403" if status_code == 403 else None
            )
        except jwt.ExpiredSignatureError:
            # Handle expired token
            log_token_usage(
                token=payload["jti"],
                user_id=payload["sub"],
                endpoint=request.url.path,
                status_code=status_code,
                blocked=True,
                block_reason="revoked_or_expired"
            )
        except jwt.InvalidTokenError:
            # Handle invalid token
            log_token_usage(
                token=payload["jti"],
                user_id=payload["sub"],
                endpoint=request.url.path,
                status_code=status_code,
                blocked=True,
                block_reason="invalid_token"
            )
    elif status_code in (401, 403):  # Bug 3b: Log revoked or expired tokens
        if "Authorization" in request.headers:
            token = request.headers["Authorization"].split(" ")[1]
            try:
                payload = jwt.decode(token, options={"verify_signature": False})
                log_token_usage(
                    token=payload["jti"],
                    user_id=payload["sub"],
                    endpoint=request.url.path,
                    status_code=status_code,
                    blocked=True,
                    block_reason="revoked_or_expired" if status_code == 401 else "http_403"
                )
            except jwt.ExpiredSignatureError:
                log_token_usage(
                    token=payload["jti"],
                    user_id=payload["sub"],
                    endpoint=request.url.path,
                    status_code=status_code,
                    blocked=True,
                    block_reason="revoked_or_expired"
                )
            except jwt.InvalidTokenError:
                log_token_usage(
                    token=payload["jti"],
                    user_id=payload["sub"],
                    endpoint=request.url.path,
                    status_code=status_code,
                    blocked=True,
                    block_reason="invalid_token"
                )
    return response

# Placeholder for the logging function
def log_token_usage(token, user_id, endpoint, status_code, blocked, block_reason=None):
    print(f"Token Usage: {token}, User: {user_id}, Endpoint: {endpoint}, Status: {status_code}, Blocked: {blocked}, Reason: {block_reason}")