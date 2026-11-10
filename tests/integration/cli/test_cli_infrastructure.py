import io
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from cli.data.models import ArchiveEntry, Credentials
from cli.domain import references
from cli.domain.errors import CommandFailedError, NotFoundError, ValidationError
from cli.infraestructure.blob_store import FileBlobStore
from cli.infraestructure.json_stores import JsonCredentialStore, JsonSettingsStore
from cli.infraestructure.local_file_system import LocalFileSystem
from cli.infraestructure.settings import default_data_dir
from cli.infraestructure.sqlite_index import SQLiteTemplateIndex
from cli.infraestructure.subprocess_runner import SubprocessRunner
from cli.infraestructure.tar_archiver import TarArchiver
from cli.infraestructure.yaml_codec import YamlCodec


pytestmark = pytest.mark.integration

NOW = datetime(2026, 11, 2, tzinfo=timezone.utc)


# File system -------------------------------------------------------------------

def test_local_file_system(tmp_path):
    fs = LocalFileSystem()
    fs.write_bytes(tmp_path / "a/b/c.txt", b"hi")
    fs.make_dirs(tmp_path / "a/empty")

    assert fs.exists(tmp_path / "a/b/c.txt")
    assert fs.is_dir(tmp_path / "a") and not fs.is_dir(tmp_path / "a/b/c.txt")
    assert fs.list_dir(tmp_path / "a") == ["b", "empty"]
    assert fs.read_bytes(tmp_path / "a/b/c.txt") == b"hi"

    fs.copy(tmp_path / "a", tmp_path / "copy")
    fs.copy(tmp_path / "a/b/c.txt", tmp_path / "single.txt")
    fs.move(tmp_path / "copy", tmp_path / "moved")
    assert fs.read_bytes(tmp_path / "moved/b/c.txt") == b"hi"
    assert fs.read_bytes(tmp_path / "single.txt") == b"hi"
    assert not fs.exists(tmp_path / "copy")

    fs.remove(tmp_path / "moved")
    fs.remove(tmp_path / "single.txt")
    fs.remove(tmp_path / "missing")
    assert not fs.exists(tmp_path / "moved")
    with pytest.raises(NotFoundError):
        fs.read_bytes(tmp_path / "missing")
    with pytest.raises(NotFoundError):
        fs.copy(tmp_path / "missing", tmp_path / "x")


# Tar archiver (C-11) -------------------------------------------------------------

ENTRIES = [ArchiveEntry("app"), ArchiveEntry("app/main.py", b"print(1)\n"),
           ArchiveEntry("app/" + "x" * 120 + ".txt", b"long name")]


def test_tar_is_reproducible_and_roundtrips():
    archiver = TarArchiver()

    first = archiver.pack(ENTRIES)

    assert first == archiver.pack(ENTRIES)
    assert archiver.unpack(first) == ENTRIES


def test_tar_rejects_links():
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        info = tarfile.TarInfo("link")
        info.type = tarfile.SYMTYPE
        info.linkname = "/etc/passwd"
        tar.addfile(info)

    with pytest.raises(ValidationError):
        TarArchiver().unpack(buffer.getvalue())


def test_tar_rejects_garbage():
    with pytest.raises(ValidationError):
        TarArchiver().unpack(b"not a tar")


# YAML ------------------------------------------------------------------------------

def test_yaml_keeps_order_and_reports_errors():
    codec = YamlCodec()
    document = {"tag": "h:1/o/r:v", "layers": ["a"], "description": "ñ"}

    content = codec.dump(document)

    assert content.decode("utf-8").startswith("tag:")
    assert codec.load(content) == document
    with pytest.raises(ValidationError):
        codec.load(b"a: [unclosed")


@pytest.mark.parametrize(
    "content, expected",
    [
        (b"a: 1\nb:\n", ["line 2: 'b' has no value"]),
        (b"a: null\nb: ~\nc: []\nd: ''\n", []),
        (b"items:\n  -\n  - x\n", ["line 2: empty list item"]),
        (b"a: 1\n---\nkind: Pod\nspec:\n", ["line 4: 'spec' has no value"]),
        (b"", []),
    ],
)
def test_yaml_problems(content, expected):
    assert YamlCodec().problems(content) == expected


def test_yaml_syntax_errors_have_a_line():
    problems = YamlCodec().problems(b"a: 1\nb: [unclosed\n")

    assert len(problems) == 1 and problems[0].startswith("line ")


# Blob store --------------------------------------------------------------------

def test_file_blob_store(tmp_path):
    store = FileBlobStore(tmp_path / "manifests", ".yaml")

    store.save("ab" * 32, b"content")

    assert (tmp_path / "manifests" / f"{'ab' * 32}.yaml").read_bytes() == b"content"
    assert store.exists("ab" * 32)
    assert store.read("ab" * 32) == b"content"
    assert [i for i, _ in store.list()] == ["ab" * 32]
    store.delete("ab" * 32)
    store.delete("ab" * 32)
    assert store.list() == []
    with pytest.raises(NotFoundError):
        store.read("ab" * 32)
    with pytest.raises(ValueError):
        store.save("../escape", b"x")


# SQLite index (C-17) -------------------------------------------------------------

def test_sqlite_index_contract(tmp_path):
    index = SQLiteTemplateIndex(tmp_path / "index.db")
    index.initialize()
    index.initialize()
    v1 = references.parse("h:80/org/app:v1")
    v2 = references.parse("h:80/org/app:v2")

    index.add_manifest("m1", ("l1", "l2"), 10, NOW)
    index.add_manifest("m1", ("other",), 99, NOW)
    index.add_manifest("m2", ("l2",), 5, datetime(2026, 11, 3, tzinfo=timezone.utc))
    index.set_tag(v1, "m1")
    index.set_tag(v2, "m1")
    index.set_tag(v2, "m2")

    assert index.has_manifest("m1") and not index.has_manifest("x")
    assert sorted(index.manifest_ids()) == ["m1", "m2"]
    assert index.layers_of("m1") == ("l1", "l2")
    assert index.get_tag(v1) == "m1" and index.get_tag(v2) == "m2"
    assert index.tags_of("m1") == [v1]
    records = index.list_manifests()
    assert [r.id for r in records] == ["m2", "m1"]
    assert records[1].size == 10 and records[1].created_at == NOW
    assert records[0].tags == (v2,)
    assert index.layer_in_use("l1")

    index.remove_tag(v1)
    assert index.tags_of("m1") == []
    index.remove_manifest("m1")
    assert not index.layer_in_use("l1") and index.layer_in_use("l2")

    index.record_dry_run("m2", "build", NOW)
    index.record_dry_run("m2", "build", NOW)
    assert index.has_dry_run("m2", "build")
    assert not index.has_dry_run("m2", "deploy")

    index.clear_templates()
    assert index.manifest_ids() == [] and index.get_tag(v2) is None
    assert index.has_dry_run("m2", "build")


# JSON stores (C-27, C-28) --------------------------------------------------------

def test_settings_store_keeps_other_keys(tmp_path):
    path = tmp_path / "config.json"
    path.write_text('{"company": "judajaav"}', encoding="utf-8")
    store = JsonSettingsStore(path)

    assert store.get_prefix() is None
    store.set_prefix("h:80/org")

    assert JsonSettingsStore(path).get_prefix() == "h:80/org"
    assert '"company"' in path.read_text(encoding="utf-8")
    store.set_prefix(None)
    assert store.get_prefix() is None


def test_credential_store_keeps_one_session_per_registry(tmp_path):
    store = JsonCredentialStore(tmp_path / "credentials.json")
    a = Credentials("a:1", "t1", "dev", True)
    b = Credentials("b:2", "t2", "ops", False)

    store.save(a)
    store.save(b)

    reopened = JsonCredentialStore(tmp_path / "credentials.json")
    assert reopened.get("a:1") == a and reopened.get("b:2") == b
    reopened.delete("a:1")
    assert reopened.get("a:1") is None
    assert JsonCredentialStore(tmp_path / "none.json").get("a:1") is None


# Data folder (C-48) ----------------------------------------------------------------

def test_default_data_dir_per_system(tmp_path):
    assert default_data_dir({"EASYK8S_DATA": str(tmp_path)}, "Linux") == tmp_path
    assert default_data_dir({"LOCALAPPDATA": "C:/L"}, "Windows") == (
        Path("C:/L") / "judajaav" / "easyK8s")
    assert default_data_dir({"XDG_DATA_HOME": "/x"}, "Linux") == Path("/x/easyk8s")
    assert default_data_dir({"HOME": "/home/u"}, "Linux") == (
        Path("/home/u") / ".local" / "share" / "easyk8s")


# Process runner (C-34, C-35) -------------------------------------------------------

def test_runner_runs_programs_without_shell(tmp_path):
    runner = SubprocessRunner()
    env = runner.environment()
    env["EASYK8S_TEST"] = "value with spaces"
    script = ("import os, pathlib; "
              "pathlib.Path('out.txt').write_text(os.environ['EASYK8S_TEST'])")

    code = runner.run([sys.executable, "-c", script], tmp_path, env, False)

    assert code == 0
    assert (tmp_path / "out.txt").read_text() == "value with spaces"
    assert runner.run([sys.executable, "-c", "raise SystemExit(4)"],
                      tmp_path, env, False) == 4


def test_runner_reports_missing_programs(tmp_path):
    with pytest.raises(CommandFailedError, match="not found"):
        SubprocessRunner().run(["easyk8s-missing-program"], tmp_path, {}, False)


def test_runner_admin_on_linux_uses_sudo(tmp_path, monkeypatch):
    calls = []
    runner = SubprocessRunner(system_name="Linux", is_root=lambda: False)
    monkeypatch.setattr(
        "cli.infraestructure.subprocess_runner.shutil.which",
        lambda name, path=None: f"/usr/bin/{name}")
    monkeypatch.setattr(
        "cli.infraestructure.subprocess_runner.subprocess.run",
        lambda argv, **kwargs: calls.append(argv) or type("R", (), {"returncode": 0})())

    runner.check_admin()
    runner.run(["kubectl", "apply"], tmp_path, {}, True)

    assert calls == [["/usr/bin/sudo", "/usr/bin/kubectl", "apply"]]


def test_runner_admin_on_windows_needs_an_elevated_terminal():
    runner = SubprocessRunner(system_name="Windows", is_elevated=lambda: False)

    with pytest.raises(Exception, match="administrator"):
        runner.check_admin()
    SubprocessRunner(system_name="Windows", is_elevated=lambda: True).check_admin()
