from pathlib import Path

import click

from cli.domain import ids
from cli.presentation import formatting
from cli.presentation.context import services


@click.command()
@click.option("-c", "--config", "config_file", default="config.template",
              show_default=True, type=click.Path(path_type=Path),
              help="config.template written by 'template setup'.")
@click.option("-b", "--build", "build", is_flag=True, help="Run the build stage.")
@click.option("-d", "--deploy", "deploy", is_flag=True, help="Run the deploy stage.")
@click.option("--build-file", type=click.Path(path_type=Path),
              help="Build values (default: build.env if it exists).")
@click.option("--deploy-file", type=click.Path(path_type=Path),
              help="Deploy values (default: deploy.env if it exists).")
@click.option("--dry-run", is_flag=True,
              help="Show the commands without running them.")
@click.option("--base-path", default=".", show_default=True,
              type=click.Path(path_type=Path, file_okay=False),
              help="Working directory of the commands.")
@click.option("--admin", is_flag=True,
              help="Run programs as administrator (sudo on Linux).")
def instance(config_file, build, deploy, build_file, deploy_file, dry_run,
             base_path, admin):
    """Build (-b) and/or deploy (-d) an instantiated template.

    The first use of a template needs --dry-run to review its commands.
    \f
    Args:
        config_file: Path of ``config.template``.
        build: Run the build stage.
        deploy: Run the deploy stage.
        build_file: Build values file, or None.
        deploy_file: Deploy values file, or None.
        dry_run: Only show the commands.
        base_path: Working directory of the commands.
        admin: Run programs as administrator.
    """
    stages = tuple(s for s, on in (("build", build), ("deploy", deploy)) if on)
    result = services().instance.execute(
        config_file, stages, {"build": build_file, "deploy": deploy_file},
        base_path, dry_run, admin, click.echo,
    )
    if dry_run:
        for line in formatting.plan_lines(result.plan):
            click.echo(line)
        click.echo(f"\nDry run recorded for {ids.short(result.key)}; "
                   "run again without --dry-run to execute.")
    else:
        click.echo(f"Executed {result.executed} command(s)")
