from django.contrib.auth.tokens import PasswordResetTokenGenerator


class PasswordResetTokenGenerator(PasswordResetTokenGenerator):
    """
    Modified PasswordResetTokenGenerator that includes user email in the hash value
    to invalidate tokens when email changes.
    """
    
    def _make_hash_value(self, user, timestamp):
        # Include user's email in the hash value so tokens are invalidated when email changes
        login_timestamp = '' if user.last_login is None else user.last_login.replace(microsecond=0, tzinfo=None)
        return (
            str(user.pk) + user.password + str(login_timestamp) + str(timestamp) + user.email
        )
