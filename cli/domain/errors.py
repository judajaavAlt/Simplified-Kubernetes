class CliError(Exception):
    """Base class of the errors shown to the user as ``Error: <message>``.

    Attributes:
        exit_code: Exit code of the process (C-39).
    """

    exit_code = 1


class ValidationError(CliError):
    """The input breaks one or more rules; every problem is reported.

    Attributes:
        errors: One message per problem.
    """

    def __init__(self, errors):
        """Create the error.

        Args:
            errors: One message, or a list with one message per problem.
        """
        self.errors = [errors] if isinstance(errors, str) else list(errors)
        super().__init__("\n".join(self.errors))


class NotFoundError(CliError):
    """A template, file or session does not exist."""


class AmbiguousReferenceError(CliError):
    """An ID prefix matches more than one template."""


class CancelledError(CliError):
    """The user cancelled the operation; nothing was changed."""


class DryRunRequiredError(CliError):
    """A stage of a template must be run with ``--dry-run`` first."""


class RegistryError(CliError):
    """The registry refused a request or could not be reached."""

    exit_code = 2


class NotLoggedInError(RegistryError):
    """There is no session for the registry."""


class PasswordChangeRequiredError(RegistryError):
    """The registry asks the user to change the password first."""


class ChecksumRejectedError(RegistryError):
    """The registry rejected a piece because its SHA-256 did not match."""


class CommandFailedError(CliError):
    """A build or deploy command failed."""

    exit_code = 3
