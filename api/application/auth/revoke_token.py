from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from api.domain import tokens as token_rules
from api.persistence.repository.user_token import UserTokenRepository


@dataclass
class RevokeToken:
    """Log out by revoking a bearer token.

    Attributes:
        tokens: Stores the token hashes.
        clock: Returns the current moment.
    """

    tokens: UserTokenRepository
    clock: Callable[[], datetime]

    def execute(self, raw_token: str) -> None:
        """Revoke a token; unknown or already revoked tokens are ignored.

        Args:
            raw_token: Token as sent by the client.
        """
        signature = token_rules.signature_of(raw_token)
        token = self.tokens.get_by_signature(signature)

        if token is None or token.revoked_at is not None:
            return

        self.tokens.revoke(signature, self.clock())
