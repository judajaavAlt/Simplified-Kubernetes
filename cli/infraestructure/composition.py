"""Composition root: the only place that knows the concrete implementations.

It builds every use case with its dependencies and injects them upwards.
"""
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from cli.application.create_template import CreateTemplate
from cli.application.inspect_template import InspectTemplate
from cli.application.list_templates import ListTemplates
from cli.application.login import Login, Logout
from cli.application.lookup import TemplateLookup
from cli.application.pull_template import PullTemplate
from cli.application.push_template import PushTemplate
from cli.application.rebuild_index import RebuildIndex
from cli.application.remove_template import RemoveTemplate
from cli.application.run_instance import RunInstance
from cli.application.sample_files import WriteSampleFiles
from cli.application.sessions import RegistrySessions
from cli.application.setup_template import SetupTemplate
from cli.application.tag_template import TagTemplate
from cli.application.work_prefix import SetWorkPrefix, ShowWorkPrefix
from cli.domain.ports import CommandRunner, Prompter, RegistryConnector
from cli.infraestructure.blob_store import FileBlobStore
from cli.infraestructure.http_registry import HttpRegistryConnector
from cli.infraestructure.json_stores import JsonCredentialStore, JsonSettingsStore
from cli.infraestructure.local_file_system import LocalFileSystem
from cli.infraestructure.settings import default_data_dir
from cli.infraestructure.sqlite_index import SQLiteTemplateIndex
from cli.infraestructure.subprocess_runner import SubprocessRunner
from cli.infraestructure.tar_archiver import TarArchiver
from cli.infraestructure.yaml_codec import YamlCodec
from cli.presentation.prompter import ClickPrompter
from cli.presentation.services import CliServices


def utc_now() -> datetime:
    """Return the current moment in UTC.

    Returns:
        A timezone aware datetime.
    """
    return datetime.now(timezone.utc)


def build_services(
    data_dir: Path | None = None,
    connector: RegistryConnector | None = None,
    runner: CommandRunner | None = None,
    prompter: Prompter | None = None,
    clock: Callable[[], datetime] = utc_now,
) -> CliServices:
    """Build every use case with its concrete dependencies.

    The data folder holds ``config.json``, ``credentials.json``,
    ``index.db``, ``manifests/`` and ``layers/``. The index tables are
    created here, on start.

    Args:
        data_dir: Data folder; None uses :func:`default_data_dir`.
        connector: Registry connector; None uses HTTP.
        runner: Command runner; None runs real programs.
        prompter: Asks the user; None uses the terminal.
        clock: Returns the current moment.

    Returns:
        The use cases the commands need.
    """
    data_dir = Path(data_dir) if data_dir else default_data_dir()
    fs = LocalFileSystem()
    codec = YamlCodec()
    archiver = TarArchiver()
    manifests = FileBlobStore(data_dir / "manifests", ".yaml")
    layers = FileBlobStore(data_dir / "layers", ".tar")
    index = SQLiteTemplateIndex(data_dir / "index.db")
    index.initialize()
    settings = JsonSettingsStore(data_dir / "config.json")
    credentials = JsonCredentialStore(data_dir / "credentials.json")
    connector = connector or HttpRegistryConnector()
    runner = runner or SubprocessRunner()
    prompter = prompter or ClickPrompter()
    lookup = TemplateLookup(index, settings)
    sessions = RegistrySessions(credentials, connector)

    return CliServices(
        create=CreateTemplate(
            fs=fs, codec=codec, archiver=archiver, manifests=manifests,
            layers=layers, index=index, settings=settings, clock=clock,
        ),
        list=ListTemplates(index),
        inspect=InspectTemplate(lookup, manifests, codec),
        setup=SetupTemplate(
            fs=fs, codec=codec, archiver=archiver, manifests=manifests,
            layers=layers, lookup=lookup, prompter=prompter,
        ),
        samples=WriteSampleFiles(
            fs=fs, codec=codec, manifests=manifests, lookup=lookup,
            prompter=prompter,
        ),
        tag=TagTemplate(index, lookup),
        remove=RemoveTemplate(
            index=index, manifests=manifests, layers=layers, lookup=lookup,
            sessions=sessions,
        ),
        reindex=RebuildIndex(index, manifests, layers, codec),
        push=PushTemplate(
            lookup=lookup, manifests=manifests, layers=layers, codec=codec,
            sessions=sessions,
        ),
        pull=PullTemplate(
            lookup=lookup, index=index, manifests=manifests, layers=layers,
            codec=codec, sessions=sessions, clock=clock,
        ),
        login=Login(credentials, connector, prompter),
        logout=Logout(credentials, connector),
        set_prefix=SetWorkPrefix(settings),
        show_prefix=ShowWorkPrefix(settings),
        instance=RunInstance(
            fs=fs, codec=codec, index=index, runner=runner, clock=clock,
        ),
    )
