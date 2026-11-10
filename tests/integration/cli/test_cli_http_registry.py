"""The CLI against the real registry API, in-process (no server needed)."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.infraestructure.composition import bootstrap_admin, build_app
from api.infraestructure.settings import Settings
from cli.domain.errors import (
    NotLoggedInError,
    PasswordChangeRequiredError,
    RegistryError,
)
from cli.infraestructure.composition import build_services
from cli.infraestructure.http_registry import HttpRegistryConnector


pytestmark = pytest.mark.integration

REGISTRY = "registry.test:8000"
TEMPLATE = """\
tag: registry.test:8000/team/web:v1
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
build:
  commands:
    - print building [%service%]
deploy:
  commands: []
"""


class Prompter:
    def __init__(self):
        self.asked = 0

    def choose_conflict_action(self, paths):
        return "cancel"

    def confirm_overwrite(self, path):
        return False

    def ask_new_password(self):
        self.asked += 1
        return "devops-password2"


@pytest.fixture
def api(tmp_path):
    settings = Settings(data_dir=tmp_path / "api", pepper=b"p", hash_iterations=1_000)
    bootstrap_admin(settings, "root", "rootpassword")
    app = build_app(settings)
    connector = HttpRegistryConnector(
        lambda base_url: TestClient(app, base_url=base_url))
    admin = connector.connect(REGISTRY, secure=False)
    token = admin.login("root", "rootpassword")
    TestClient(app).post(
        "/v1/users", headers={"Authorization": f"Bearer {token}"},
        json={"nickname": "devops", "password": "temporary1", "role": "devops"},
    ).raise_for_status()
    return connector


def machine(tmp_path, name, connector, prompter=None):
    return build_services(tmp_path / name, connector=connector,
                          prompter=prompter or Prompter())


def test_errors_are_mapped(api):
    client = api.connect(REGISTRY, secure=False)

    with pytest.raises(PasswordChangeRequiredError):
        client.login("devops", "temporary1")
    with pytest.raises(RegistryError, match="401"):
        client.login("devops", "wrong-password")
    with pytest.raises(RegistryError, match="401"):
        api.connect(REGISTRY, False, "bad-token").resolve("team/web", "v1")


def test_unreachable_registry_is_a_registry_error():
    connector = HttpRegistryConnector()

    with pytest.raises(RegistryError, match="reach"):
        connector.connect("127.0.0.1:9", secure=False).login("a", "b")


def test_create_push_pull_setup_between_two_machines(api, tmp_path):
    project = tmp_path / "project"
    (project / "src").mkdir(parents=True)
    (project / "template.yaml").write_text(TEMPLATE, encoding="utf-8")
    (project / "src" / "main.py").write_text("name = '[%service%]'\n", encoding="utf-8")
    (project / "src" / "big.bin").write_bytes(bytes(range(256)) * 9000)

    devops_prompter = Prompter()
    devops = machine(tmp_path, "devops-pc", api, devops_prompter)
    created = devops.create.execute(project / "template.yaml")
    with pytest.raises(NotLoggedInError):
        devops.push.execute("registry.test:8000/team/web:v1", lambda e: None)
    devops.login.execute(REGISTRY, "devops", "temporary1", insecure=True)
    assert devops_prompter.asked == 1

    events = []
    pushed = devops.push.execute("registry.test:8000/team/web:v1", events.append)
    again = devops.push.execute("registry.test:8000/team/web:v1", lambda e: None)

    assert pushed.uploaded == 2 and again.skipped == 2
    assert any("piece 2/" in e for e in events)

    developer = machine(tmp_path, "developer-pc", api)
    developer.set_prefix.execute("registry.test:8000/team")
    developer.login.execute(REGISTRY, "devops", "devops-password2", insecure=True)
    pulled = developer.pull.execute("web:v1", lambda e: None)

    assert pulled.manifest_id == created.manifest_id
    output = tmp_path / "instance"
    developer.setup.execute("web:v1", output, None, False)
    assert (output / "app" / "main.py").read_text(encoding="utf-8") == "name = 'shop'\n"
    assert (output / "app" / "big.bin").read_bytes() == bytes(range(256)) * 9000
    assert (output / "config.template").exists()

    devops.remove.execute("registry.test:8000/team/web:v1", remote=True)
    with pytest.raises(RegistryError, match="404"):
        developer.pull.execute("web:v1", lambda e: None)
    assert developer.logout.execute(REGISTRY) is True
    assert developer.list.execute()[0].id == created.manifest_id


def test_credentials_survive_between_runs(api, tmp_path):
    first = machine(tmp_path, "pc", api)
    first.login.execute(REGISTRY, "devops", "temporary1", insecure=True)

    second = machine(tmp_path, "pc", api)

    assert second.logout.execute(REGISTRY) is True
    with pytest.raises(NotLoggedInError):
        second.logout.execute(REGISTRY)
