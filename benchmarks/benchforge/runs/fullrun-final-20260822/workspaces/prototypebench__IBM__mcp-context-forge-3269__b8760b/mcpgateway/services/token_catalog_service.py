def create_token(user_email, name, team_id=None):
    # 检查 (user_email, name, team_id) 是否已存在
    if Token.query.filter_by(user_email=user_email, name=name, team_id=team_id).first():
        raise ValueError("Token with the same name already exists for this user in the specified team.")
    
    # 创建新 token
    new_token = Token(user_email=user_email, name=name, team_id=team_id)
    db.session.add(new_token)
    db.session.commit()
    return new_token