from sqlalchemy.exc import IntegrityError
from mcpgateway.utils.error_formatter import format_error

@app.post("/tokens")
def create_token_route():
    try:
        # 现有逻辑...
    except IntegrityError as e:
        if any(constraint in str(e) for constraint in [
            "uq_email_api_tokens_user_name_team",
            "uq_email_api_tokens_user_name",
            "uq_email_api_tokens_user_email_name",
            "email_api_tokens.user_email",
            "email_api_tokens.name"
        ]):
            return {"error": "A token with the same name already exists for this user in the specified team."}, 409
        else:
            raise

@app.post("/tokens/teams/{team_id}")
def create_team_token_route(team_id: int):
    try:
        # 现有逻辑...
    except IntegrityError as e:
        if any(constraint in str(e) for constraint in [
            "uq_email_api_tokens_user_name_team",
            "uq_email_api_tokens_user_name",
            "uq_email_api_tokens_user_email_name",
            "email_api_tokens.user_email",
            "email_api_tokens.name"
        ]):
            return {"error": "A token with the same name already exists for this user in the specified team."}, 409
        else:
            raise