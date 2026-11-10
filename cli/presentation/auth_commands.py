import click

from cli.presentation.context import services


@click.command()
@click.argument("registry")
@click.option("-u", "--username", prompt=True, help="User name.")
@click.option("-p", "--password", prompt=True, hide_input=True, help="Password.")
@click.option("--insecure", is_flag=True, help="Use HTTP instead of HTTPS.")
def login(registry, username, password, insecure):
    """Log in to REGISTRY (host:port) and save the token.
    \f
    Args:
        registry: ``host:port``.
        username: User name; asked when omitted.
        password: Password; asked when omitted.
        insecure: Use HTTP instead of HTTPS.
    """
    services().login.execute(registry, username, password, insecure)
    click.echo(f"Logged in to {registry} as {username}")


@click.command()
@click.argument("registry")
def logout(registry):
    """Log out of REGISTRY and forget its token.
    \f
    Args:
        registry: ``host:port``.
    """
    revoked = services().logout.execute(registry)
    suffix = "" if revoked else " (the registry could not revoke the token)"
    click.echo(f"Logged out of {registry}{suffix}")
