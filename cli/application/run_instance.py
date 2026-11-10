"""``instance``: build and deploy an instantiated project (C-34 to C-38, C-47)."""
import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from cli.data.models import InstanceConfig
from cli.domain import commands, documents, env_file
from cli.domain.commands import CommandView
from cli.domain.errors import (
    CliError,
    CommandFailedError,
    DryRunRequiredError,
    NotFoundError,
    ValidationError,
)
from cli.domain.ports import CommandRunner
from cli.persistence.document_codec import DocumentCodec
from cli.persistence.file_system import FileSystem
from cli.persistence.template_index import TemplateIndex


STAGES = ("build", "deploy")


@dataclass(frozen=True)
class InstanceReport:
    """Outcome of ``instance``.

    Attributes:
        key: Manifest ID used to remember dry runs.
        plan: For each stage, how its resolved commands look.
        executed: Commands run; 0 for a dry run.
    """

    key: str
    plan: list[tuple[str, list[CommandView]]] = field(default_factory=list)
    executed: int = 0


@dataclass
class _State:
    """Working directory and environment shared by the commands.

    Attributes:
        cwd: Current working directory.
        env: Environment variables.
    """

    cwd: Path
    env: dict[str, str]


@dataclass
class RunInstance:
    """Resolve and run the build and deploy commands of ``config.template``.

    Attributes:
        fs: User files.
        codec: YAML codec.
        index: Local index, which remembers the dry runs.
        runner: Runs external programs.
        clock: Returns the current moment.
    """

    fs: FileSystem
    codec: DocumentCodec
    index: TemplateIndex
    runner: CommandRunner
    clock: Callable[[], datetime]

    def execute(
        self,
        config_path: Path,
        stages: tuple[str, ...],
        env_files: dict[str, Path | None],
        base_path: Path,
        dry_run: bool,
        admin: bool,
        output: Callable[[str], None],
    ) -> InstanceReport:
        """Show or run the commands of the selected stages.

        A dry run resolves every command, shows it (with the equivalent of
        the current system for standard commands and a mark on destructive
        ones) and records it. A real run is only allowed after a dry run of
        the same manifest and stage on this machine; it runs the commands
        in order and stops at the first failure.

        Args:
            config_path: Path of ``config.template``.
            stages: Stages to run, among ``build`` and ``deploy``.
            env_files: ``.env`` file per stage; a missing key or None reads
                ``<stage>.env`` if it exists.
            base_path: Initial working directory of the commands.
            dry_run: Only show the commands.
            admin: Run programs with administrator rights.
            output: Receives the text of ``print`` commands.

        Returns:
            The plan and the number of commands run.

        Raises:
            ValidationError: If no stage is selected or a value or command
                is invalid.
            NotFoundError: If ``config.template`` or an explicit ``.env``
                file do not exist.
            DryRunRequiredError: If a stage was never run with ``--dry-run``.
            CliError: If ``admin`` is requested but not possible.
            CommandFailedError: If a command fails.
        """
        stages = tuple(s for s in STAGES if s in stages)
        if not stages:
            raise ValidationError("Select a stage: -b (build) and/or -d (deploy)")
        content = self.fs.read_bytes(config_path)
        config = documents.config_from_document(self.codec.load(content))
        key = config.template_id or hashlib.sha256(content).hexdigest()
        resolved = {
            stage: self._resolve(config, stage, env_files.get(stage))
            for stage in stages
        }
        system = self.runner.system()
        plan = [
            (stage, [commands.describe(argv, system) for argv in resolved[stage]])
            for stage in stages
        ]
        if dry_run:
            for stage in stages:
                self.index.record_dry_run(key, stage, self.clock())
            return InstanceReport(key, plan, 0)

        missing = [s for s in stages if not self.index.has_dry_run(key, s)]
        if missing:
            flags = " ".join(f"-{s[0]}" for s in missing)
            raise DryRunRequiredError(
                f"The first use of a template needs a dry run; check the "
                f"commands with 'easyk8s instance {flags} --dry-run'"
            )
        if admin:
            self.runner.check_admin()
        state = _State(base_path, self.runner.environment())
        executed = 0
        for stage in stages:
            for argv in resolved[stage]:
                self._run(argv, state, admin, output)
                executed += 1
        return InstanceReport(key, plan, executed)

    def _resolve(self, config: InstanceConfig, stage: str, env_path):
        """Resolve the commands of one stage.

        Args:
            config: Content of ``config.template``.
            stage: ``build`` or ``deploy``.
            env_path: Explicit ``.env`` file, or None.

        Returns:
            The argument list of each command.

        Raises:
            NotFoundError: If the explicit ``.env`` file does not exist.
        """
        path = env_path or Path(f"{stage}.env")
        overrides = {}
        if self.fs.exists(path):
            overrides = env_file.parse(self.fs.read_bytes(path).decode("utf-8"))
        elif env_path is not None:
            raise NotFoundError(f"File not found: {env_path}")
        return commands.resolve_stage(
            getattr(config, stage), config.instantiation, overrides
        )

    def _run(self, argv, state: _State, admin: bool, output) -> None:
        """Run one command.

        Args:
            argv: Resolved command.
            state: Working directory and environment.
            admin: Run programs with administrator rights.
            output: Receives the text of ``print``.

        Raises:
            CommandFailedError: If the command fails.
        """
        name, args = argv[0], argv[1:]
        if name not in commands.STANDARD_COMMANDS:
            code = self.runner.run(argv, state.cwd, dict(state.env), admin)
            if code != 0:
                raise CommandFailedError(
                    f"'{' '.join(argv)}' failed with exit code {code}"
                )
            return
        try:
            self._standard(name, args, state, output)
        except (CliError, OSError) as error:
            raise CommandFailedError(f"'{' '.join(argv)}' failed: {error}")

    def _standard(self, name: str, args: list[str], state: _State, output) -> None:
        """Run a standard command the same way on every system.

        Args:
            name: Standard command.
            args: Its arguments.
            state: Working directory and environment.
            output: Receives the text of ``print``.

        Raises:
            NotFoundError: If a source path or folder does not exist.
        """
        if name == "makeDirectory":
            self.fs.make_dirs(state.cwd / args[0])
        elif name == "removePath":
            self.fs.remove(state.cwd / args[0])
        elif name == "copyPath":
            self.fs.copy(state.cwd / args[0], state.cwd / args[1])
        elif name == "movePath":
            self.fs.move(state.cwd / args[0], state.cwd / args[1])
        elif name == "writeFile":
            text = " ".join(args[1:]) + "\n"
            self.fs.write_bytes(state.cwd / args[0], text.encode("utf-8"))
        elif name == "changeDirectory":
            target = state.cwd / args[0]
            if not self.fs.is_dir(target):
                raise NotFoundError(f"Folder not found: {target}")
            state.cwd = target
        elif name == "setEnv":
            state.env[args[0]] = args[1]
        else:
            output(" ".join(args))
