"""The ``easyk8s`` commands end to end, with a temporary data folder."""
from pathlib import Path

import pytest

from cli.infraestructure.composition import build_services
from cli.userInterface.app import run


pytestmark = pytest.mark.integration

TEMPLATE = """\
tag: reg.local:5000/team/web:v1
description: Web service
template:
  layers:
    - origin: src
      objective: app
instantiation:
  arguments:
    - name: service
      type: str
      default: shop
      description: Service name
build:
  arguments:
    - name: image
      type: str
      default: img
  commands:
    - makeDirectory dist
    - writeFile dist/info.txt [%service%] [%image%]
    - print built [%service%]
deploy:
  commands:
    - easyk8s-missing-program apply
"""


class Prompter:
    def choose_conflict_action(self, paths):
        return "cancel"

    def confirm_overwrite(self, path):
        return False

    def ask_new_password(self):
        return "unused"


@pytest.fixture
def cli(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "proj" / "src").mkdir(parents=True)
    (tmp_path / "proj" / "template.yaml").write_text(TEMPLATE, encoding="utf-8")
    (tmp_path / "proj" / "src" / "main.py").write_text(
        "name = '[%service%]'\n", encoding="utf-8")

    def invoke(*argv):
        code = run(list(argv), lambda: build_services(
            tmp_path / "data", prompter=Prompter()))
        out, err = capsys.readouterr()
        return code, out, err

    return invoke


def test_help_works_without_creating_data(cli, tmp_path):
    code, out, _ = cli("--help")

    assert code == 0
    assert "template" in out and "instance" in out and "work" in out
    assert not (tmp_path / "data").exists()


def test_create_list_inspect(cli):
    code, out, _ = cli("template", "create", "-c", "proj/template.yaml")
    assert code == 0
    assert "reg.local:5000/team/web:v1" in out

    code, out, _ = cli("template", "list")
    assert code == 0
    header, row = out.splitlines()[:2]
    assert header.split() == ["REPOSITORY", "TAG", "ID", "CREATED", "SIZE"]
    assert row.split()[:2] == ["reg.local:5000/team/web", "v1"]
    assert len(row.split()[2]) == 12

    code, out, _ = cli("template", "inspect", "reg.local:5000/team/web:v1")
    assert code == 0
    assert "Web service" in out and "service" in out and "makeDirectory dist" in out


def test_setup_samples_and_conflicts(cli, tmp_path):
    cli("template", "create", "-c", "proj/template.yaml")
    ref = "reg.local:5000/team/web:v1"

    code, out, _ = cli("template", "setup", ref, "-s", "-o", "inst")
    assert code == 0
    assert (tmp_path / "inst" / "values.env").exists()
    (tmp_path / "inst" / "values.env").write_text("service = api\n", encoding="utf-8")

    code, out, _ = cli("template", "setup", ref, "-o", "inst",
                       "-v", "inst/values.env")
    assert code == 0
    assert (tmp_path / "inst/app/main.py").read_text(encoding="utf-8") == "name = 'api'\n"

    code, _, err = cli("template", "setup", ref, "-o", "inst")
    assert code == 1 and "Error: Cancelled" in err
    code, _, _ = cli("template", "setup", ref, "-o", "inst", "--force")
    assert code == 0
    assert (tmp_path / "inst/app/main.py").read_text(encoding="utf-8") == "name = 'shop'\n"


def test_work_tag_and_rm(cli):
    cli("template", "create", "-c", "proj/template.yaml")

    assert cli("work", "set", "reg.local:5000/team")[0] == 0
    assert cli("work", "show")[1].strip() == "reg.local:5000/team"
    assert cli("template", "tag", "web:v1", "web:prod")[0] == 0
    assert "reg.local:5000/team/web:prod" in cli("template", "list")[1] or (
        "prod" in cli("template", "list")[1])

    code, out, _ = cli("template", "rm", "web:v1")
    assert code == 0 and "Untagged: reg.local:5000/team/web:v1" in out
    code, out, _ = cli("template", "rm", "web:prod")
    assert "Deleted:" in out
    assert "No templates" in cli("template", "list")[1]
    assert cli("work", "clear")[0] == 0
    assert "No default prefix" in cli("work", "show")[1]


def test_instance_requires_a_dry_run_then_runs(cli, tmp_path):
    cli("template", "create", "-c", "proj/template.yaml")
    cli("template", "setup", "reg.local:5000/team/web:v1", "-o", "inst")
    config = "inst/config.template"

    code, _, err = cli("instance", "-b", "-c", config, "--base-path", "inst")
    assert code == 1 and "--dry-run" in err

    code, out, _ = cli("instance", "-b", "-c", config, "--base-path", "inst",
                       "--dry-run")
    assert code == 0
    assert "writeFile dist/info.txt shop img" in out
    assert "mkdir -p dist" in out or "New-Item" in out

    code, out, _ = cli("instance", "-b", "-c", config, "--base-path", "inst")
    assert code == 0
    assert "built shop" in out
    assert (tmp_path / "inst/dist/info.txt").read_text() == "shop img\n"


def test_failing_deploy_exits_with_3(cli):
    cli("template", "create", "-c", "proj/template.yaml")
    cli("template", "setup", "reg.local:5000/team/web:v1", "-o", "inst")
    args = ("instance", "-d", "-c", "inst/config.template", "--base-path", "inst")
    cli(*args, "--dry-run")

    code, _, err = cli(*args)

    assert code == 3 and "Program not found" in err


def test_error_codes_and_verbose(cli):
    code, _, err = cli("template", "inspect", "missing")
    assert code == 1 and err.startswith("Error: Template 'missing' not found")
    assert "Traceback" not in err

    code, _, err = cli("--verbose", "template", "inspect", "missing")
    assert "Traceback" in err

    code, _, err = cli("template", "nope")
    assert code == 1

    code, _, err = cli("instance")
    assert code == 1 and "-b" in err

    code, _, err = cli("login", "127.0.0.1:9", "-u", "a", "-p", "b", "--insecure")
    assert code == 2 and "Error:" in err


def test_validation_errors_are_listed(cli, tmp_path):
    (tmp_path / "proj" / "template.yaml").write_text(
        TEMPLATE.replace("default: shop", "default: 3").replace("src", "nope"),
        encoding="utf-8")

    code, _, err = cli("template", "create", "-c", "proj/template.yaml")

    assert code == 1
    assert "nope" in err and "service" in err
