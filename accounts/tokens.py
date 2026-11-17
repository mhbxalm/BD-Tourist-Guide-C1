from django.contrib.auth.tokens import PasswordResetTokenGenerator


class EmailVerificationTokenGenerator(PasswordResetTokenGenerator):
    """Generate verification tokens invalidated when verification state changes."""

    def _make_hash_value(self, user, timestamp):
        """Include email-verification state in the token's signed value."""
        return f"{user.pk}{timestamp}{user.is_email_verified}"


email_verification_token = EmailVerificationTokenGenerator()
