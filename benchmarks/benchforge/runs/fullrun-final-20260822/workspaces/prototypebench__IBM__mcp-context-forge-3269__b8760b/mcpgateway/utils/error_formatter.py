def format_error(error):
    if isinstance(error, IntegrityError):
        if any(constraint in str(error) for constraint in [
            "uq_email_api_tokens_user_name_team",
            "uq_email_api_tokens_user_name",
            "uq_email_api_tokens_user_email_name",
            "email_api_tokens.user_email",
            "email_api_tokens.name"
        ]):
            return {"error": "A token with the same name already exists for this user in the specified team."}
    
    # 其他错误处理...