import hashlib
from pathlib import Path

import pytest

from cli.application.run_instance import RunInstance
from cli.data.models import InstanceConfig, Stage, Variable, VariableType
from cli.domain import documents
from cli.domain.errors import (
    CliError,
    CommandFailedError,
    DryRunRequiredError,
    NotFoundError,
    ValidationError,
)
from cli_fakes import FakeRunner, make_world


pytestmark = pytest.mark.unit

TEMPLATE_ID = "c" * 64
BUILD = Stage(
    (Variable("image", VariableType.STR, "img"),),
    (
        "makeDirectory out",
        "writeFile out/info.txt built [%service%]",
        "copyPath out/info.txt out/copy.txt",
        "movePath out/copy.txt out/moved.txt",
        "setEnv MODE prod",
        "changeDirectory out",
        "print hello [%service%]",
        "docker build -t [%image%]:[%service%] .",
        "removePath moved.txt",
    ),
)
DEPLOY = Stage((), ("kubectl apply -f k8s",))


def world(template_id=TEMPLATE_ID, runner=None):
    w = make_world()
    if runner:
        w.runner = runner
    config = InstanceConfig(
        template_id, "reg:5000/org/web:v1",
        (Variable("service", VariableType.STR, "shop"),), BUILD, DEPLOY)
    w.fs.write_bytes(Path("proj/config.template"),
                     w.codec.dump(documents.config_to_document(config)))
    w.output = []
    return w


def run(w, stages=("build",), dry_run=False, admin=False, env_files=None):
    return RunInstance(
        fs=w.fs, codec=w.codec, index=w.index, runner=w.runner, clock=w.clock,
    ).execute(
        Path("proj/config.template"), stages, env_files or {}, Path("proj"),
        dry_run, admin, w.output.append,
    )


def test_dry_run_shows_resolved_commands_and_is_recorded():
    w = world()

    report = run(w, ("build", "deploy"), dry_run=True)

    build = report.plan[0][1]
    assert report.plan[0][0] == "build"
    assert build[0].native == "mkdir -p out"
    assert build[7].text == "docker build -t img:shop ."
    assert build[8].destructive
    assert report.executed == 0
    assert w.runner.calls == [] and not w.fs.exists(Path("proj/out"))
    assert w.index.has_dry_run(TEMPLATE_ID, "build")
    assert w.index.has_dry_run(TEMPLATE_ID, "deploy")


def test_dry_run_on_windows_shows_powershell():
    w = world(runner=FakeRunner("Windows"))

    report = run(w, dry_run=True)

    assert report.plan[0][1][0].native.startswith("New-Item")


def test_running_without_a_previous_dry_run_is_refused():
    w = world()

    with pytest.raises(DryRunRequiredError, match="dry-run"):
        run(w)

    assert w.runner.calls == [] and not w.fs.exists(Path("proj/out"))


def test_dry_run_is_per_stage():
    w = world()
    run(w, ("build",), dry_run=True)

    with pytest.raises(DryRunRequiredError):
        run(w, ("deploy",))


def test_execution_runs_standard_commands_and_programs_in_order():
    w = world()
    run(w, dry_run=True)

    report = run(w)

    assert report.executed == len(BUILD.commands)
    assert w.fs.text("proj/out/info.txt") == "built shop\n"
    assert not w.fs.exists(Path("proj/out/copy.txt"))
    assert not w.fs.exists(Path("proj/out/moved.txt"))
    assert w.output == ["hello shop"]
    argv, cwd, env, admin = w.runner.calls[0]
    assert argv == ["docker", "build", "-t", "img:shop", "."]
    assert cwd == "proj/out"
    assert env["MODE"] == "prod" and env["BASE"] == "1"
    assert admin is False


def test_env_file_overrides_values():
    w = world()
    w.fs.write_bytes(Path("my-build.env"), b'image = "web"\nservice = api\n')
    run(w, dry_run=True)

    run(w, env_files={"build": Path("my-build.env")})

    assert w.runner.calls[0][0][3] == "web:api"


def test_default_env_file_is_optional_but_explicit_must_exist():
    w = world()
    run(w, dry_run=True)

    with pytest.raises(NotFoundError):
        run(w, env_files={"build": Path("missing.env")})


def test_a_failing_program_stops_the_stages():
    w = world(runner=FakeRunner(codes={"docker": 5}))
    run(w, ("build", "deploy"), dry_run=True)

    with pytest.raises(CommandFailedError, match="5"):
        run(w, ("build", "deploy"))

    assert [c[0][0] for c in w.runner.calls] == ["docker"]


def test_a_missing_program_is_a_command_failure():
    w = world()
    w.fs.write_bytes(Path("proj/config.template"), w.codec.dump(
        documents.config_to_document(InstanceConfig(
            TEMPLATE_ID, "", (), Stage((), ("missing --flag",)), Stage()))))
    run(w, dry_run=True)

    with pytest.raises(CommandFailedError):
        run(w)


def test_a_failing_standard_command_is_a_command_failure():
    w = world()
    w.fs.write_bytes(Path("proj/config.template"), w.codec.dump(
        documents.config_to_document(InstanceConfig(
            TEMPLATE_ID, "", (), Stage((), ("copyPath nope x",)), Stage()))))
    run(w, dry_run=True)

    with pytest.raises(CommandFailedError):
        run(w)


def test_admin_is_checked_before_running():
    w = world(runner=FakeRunner(admin_ok=False))
    run(w, dry_run=True)

    with pytest.raises(CliError, match="administrator"):
        run(w, admin=True)

    assert w.runner.calls == [] and not w.fs.exists(Path("proj/out"))


def test_admin_flag_reaches_the_runner():
    w = world()
    run(w, dry_run=True)

    run(w, admin=True)

    assert w.runner.admin_checked
    assert w.runner.calls[0][3] is True


def test_config_without_template_id_uses_its_own_hash():
    w = world(template_id=None)
    content = w.fs.read_bytes(Path("proj/config.template"))

    report = run(w, dry_run=True)

    assert report.key == hashlib.sha256(content).hexdigest()
    assert w.index.has_dry_run(report.key, "build")


def test_errors_in_inputs():
    w = world()

    with pytest.raises(ValidationError):
        run(w, stages=())
    w.fs.remove(Path("proj/config.template"))
    with pytest.raises(NotFoundError):
        run(w, dry_run=True)
