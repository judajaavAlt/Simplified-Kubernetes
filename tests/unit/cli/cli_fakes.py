"""In-memory doubles of the CLI ports, shared by the CLI unit tests."""
import base64
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from types import SimpleNamespace

from cli.data.models import (
    ArchiveEntry,
    Credentials,
    DownloadTicket,
    ManifestRecord,
    PieceInfo,
    RemoteManifest,
    UploadTicket,
)
from cli.domain.errors import (
    ChecksumRejectedError,
    CommandFailedError,
    NotFoundError,
    PasswordChangeRequiredError,
    RegistryError,
    ValidationError,
)
from cli.domain.ports import CommandRunner, Prompter, RegistryClient, RegistryConnector
from cli.persistence.archiver import Archiver
from cli.persistence.blob_store import BlobStore
from cli.persistence.document_codec import DocumentCodec
from cli.persistence.file_system import FileSystem
from cli.persistence.settings_store import CredentialStore, SettingsStore
from cli.persistence.template_index import TemplateIndex


def sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def key(path) -> str:
    text = str(path).replace("\\", "/")
    return PurePosixPath(text).as_posix() if text else "."


class FakeFileSystem(FileSystem):
    def __init__(self, files=None):
        self.files: dict[str, bytes] = {}
        self.dirs: set[str] = set()
        for path, content in (files or {}).items():
            self.write_bytes(Path(path), content if isinstance(content, bytes)
                             else content.encode("utf-8"))

    def _under(self, k):
        prefix = "" if k == "." else k + "/"
        return [p for p in list(self.files) + list(self.dirs) if p.startswith(prefix)]

    def exists(self, path):
        k = key(path)
        return k == "." or k in self.files or k in self.dirs or bool(self._under(k))

    def is_dir(self, path):
        k = key(path)
        return k not in self.files and (k == "." or k in self.dirs or bool(self._under(k)))

    def list_dir(self, path):
        k = key(path)
        prefix = "" if k == "." else k + "/"
        return sorted({p[len(prefix):].split("/")[0] for p in self._under(k)})

    def read_bytes(self, path):
        k = key(path)
        if k not in self.files:
            raise NotFoundError(f"File not found: {k}")
        return self.files[k]

    def text(self, path):
        return self.read_bytes(path).decode("utf-8")

    def write_bytes(self, path, content):
        k = key(path)
        self.files[k] = content
        parent = PurePosixPath(k).parent
        if str(parent) != ".":
            self.make_dirs(parent)

    def make_dirs(self, path):
        k = PurePosixPath(key(path))
        while str(k) != ".":
            self.dirs.add(k.as_posix())
            k = k.parent

    def remove(self, path):
        k = key(path)
        self.files.pop(k, None)
        self.dirs.discard(k)
        for p in self._under(k):
            self.files.pop(p, None)
            self.dirs.discard(p)

    def copy(self, source, target):
        s, t = key(source), key(target)
        if not self.exists(source):
            raise NotFoundError(s)
        if s in self.files:
            self.write_bytes(Path(t), self.files[s])
            return
        for p in self._under(s):
            new = t + p[len(s):]
            if p in self.files:
                self.write_bytes(Path(new), self.files[p])
            else:
                self.make_dirs(Path(new))
        self.make_dirs(Path(t))

    def move(self, source, target):
        self.copy(source, target)
        self.remove(source)


class FakeArchiver(Archiver):
    def pack(self, entries):
        data = [[e.path, None if e.content is None
                 else base64.b64encode(e.content).decode()] for e in entries]
        return json.dumps(data).encode()

    def unpack(self, content):
        return [ArchiveEntry(p, None if c is None else base64.b64decode(c))
                for p, c in json.loads(content)]


class FakeCodec(DocumentCodec):
    def dump(self, document):
        return json.dumps(document, indent=1).encode()

    def load(self, content):
        try:
            return json.loads(content)
        except ValueError as error:
            raise ValidationError(f"Invalid document: {error}")

    def problems(self, content):
        # BROKEN marks a broken file; a placeholder left means no substitution.
        found = []
        if b"BROKEN" in content:
            found.append("line 1: broken")
        if b"[%" in content:
            found.append("line 1: placeholder left")
        return found


class FakeBlobStore(BlobStore):
    def __init__(self, clock):
        self.blobs, self.times, self.clock = {}, {}, clock

    def save(self, blob_id, content):
        self.blobs[blob_id] = content
        self.times[blob_id] = self.clock()

    def read(self, blob_id):
        if blob_id not in self.blobs:
            raise NotFoundError(f"Blob not found: {blob_id}")
        return self.blobs[blob_id]

    def exists(self, blob_id):
        return blob_id in self.blobs

    def delete(self, blob_id):
        self.blobs.pop(blob_id, None)

    def list(self):
        return [(i, self.times[i]) for i in self.blobs]


class FakeIndex(TemplateIndex):
    def __init__(self):
        self.manifests, self.tags, self.dry_runs = {}, {}, set()

    def initialize(self):
        pass

    def add_manifest(self, manifest_id, layers, size, created_at):
        self.manifests.setdefault(manifest_id, (tuple(layers), size, created_at))

    def has_manifest(self, manifest_id):
        return manifest_id in self.manifests

    def manifest_ids(self):
        return list(self.manifests)

    def layers_of(self, manifest_id):
        return self.manifests.get(manifest_id, ((),))[0]

    def remove_manifest(self, manifest_id):
        self.manifests.pop(manifest_id, None)
        self.tags = {r: m for r, m in self.tags.items() if m != manifest_id}

    def list_manifests(self):
        records = [ManifestRecord(i, c, s, tuple(self.tags_of(i)))
                   for i, (_, s, c) in self.manifests.items()]
        return sorted(records, key=lambda r: r.created_at, reverse=True)

    def set_tag(self, reference, manifest_id):
        self.tags[reference] = manifest_id

    def get_tag(self, reference):
        return self.tags.get(reference)

    def remove_tag(self, reference):
        self.tags.pop(reference, None)

    def tags_of(self, manifest_id):
        return [r for r, m in self.tags.items() if m == manifest_id]

    def layer_in_use(self, layer_id):
        return any(layer_id in l for l, _, _ in self.manifests.values())

    def clear_templates(self):
        self.manifests, self.tags = {}, {}

    def record_dry_run(self, key, stage, at):
        self.dry_runs.add((key, stage))

    def has_dry_run(self, key, stage):
        return (key, stage) in self.dry_runs


class FakeSettings(SettingsStore):
    def __init__(self, prefix=None):
        self.prefix = prefix

    def get_prefix(self):
        return self.prefix

    def set_prefix(self, prefix):
        self.prefix = prefix


class FakeCredentials(CredentialStore):
    def __init__(self):
        self.items = {}

    def get(self, registry):
        return self.items.get(registry)

    def save(self, credentials):
        self.items[credentials.registry] = credentials

    def delete(self, registry):
        self.items.pop(registry, None)


class FakeRegistry:
    """State of a fake registry API with the same rules as the real one."""

    def __init__(self, chunk_size=4):
        self.chunk_size = chunk_size
        self.users = {"dev": ["secret12", False]}
        self.tokens = set()
        self.blobs = {}
        self.manifests = {}  # (repo, sig) -> layers
        self.layers = set()  # (repo, sig)
        self.tags = {}  # (repo, tag) -> sig
        self.uploads = {}
        self.downloads = {}
        self.reject_next_chunk = 0
        self.corrupt_next_download = 0
        self.calls = []


class FakeClient(RegistryClient):
    def __init__(self, server: FakeRegistry, token):
        self.server, self.token = server, token

    def _auth(self):
        if self.token not in self.server.tokens:
            raise RegistryError("401 authentication_error")

    def login(self, nickname, password):
        user = self.server.users.get(nickname)
        if not user or user[0] != password:
            raise RegistryError("Invalid credentials")
        if user[1]:
            raise PasswordChangeRequiredError("Change the password")
        token = f"token-{len(self.server.tokens)}"
        self.server.tokens.add(token)
        return token

    def change_password(self, nickname, current, new):
        user = self.server.users[nickname]
        if user[0] != current:
            raise RegistryError("Invalid credentials")
        self.server.users[nickname] = [new, False]

    def logout(self):
        self.server.tokens.discard(self.token)

    def start_upload(self, repository, kind, signature, size, layers=()):
        self._auth()
        self.server.calls.append(("start_upload", kind, signature))
        if signature in self.server.blobs:
            self._register(repository, kind, signature, layers)
            return UploadTicket("exists", None, 0, self.server.chunk_size)
        upload_id = f"up-{len(self.server.uploads)}"
        self.server.uploads[upload_id] = dict(
            repository=repository, kind=kind, signature=signature,
            size=size, layers=tuple(layers), pieces={},
        )
        pieces = -(-size // self.server.chunk_size)
        return UploadTicket("started", upload_id, pieces, self.server.chunk_size)

    def upload_chunk(self, upload_id, index, signature, content):
        self._auth()
        self.server.calls.append(("chunk", upload_id, index))
        if self.server.reject_next_chunk:
            self.server.reject_next_chunk -= 1
            raise ChecksumRejectedError("422 checksum_mismatch")
        assert sha(content) == signature
        self.server.uploads[upload_id]["pieces"][index] = content

    def finish_upload(self, upload_id):
        self._auth()
        session = self.server.uploads.pop(upload_id)
        data = b"".join(session["pieces"][i] for i in sorted(session["pieces"]))
        if sha(data) != session["signature"]:
            raise RegistryError("422 checksum_mismatch")
        self.server.blobs[session["signature"]] = data
        self._register(session["repository"], session["kind"],
                       session["signature"], session["layers"])
        return session["signature"]

    def cancel_upload(self, upload_id):
        self.server.calls.append(("cancel", upload_id))
        self.server.uploads.pop(upload_id, None)

    def _register(self, repository, kind, signature, layers):
        if kind == "layer":
            self.server.layers.add((repository, signature))
        else:
            self.server.manifests[(repository, signature)] = tuple(layers)

    def set_tag(self, repository, tag, manifest):
        self._auth()
        self.server.tags[(repository, tag)] = manifest

    def resolve(self, repository, reference):
        self._auth()
        signature = self.server.tags.get((repository, reference), reference)
        if (repository, signature) not in self.server.manifests:
            raise RegistryError("404 not_found")
        return RemoteManifest(signature, self.server.manifests[(repository, signature)])

    def start_download(self, repository, signature):
        self._auth()
        data = self.server.blobs[signature]
        size = self.server.chunk_size
        parts = [data[i:i + size] for i in range(0, len(data), size)]
        download_id = f"down-{len(self.server.downloads)}"
        self.server.downloads[download_id] = parts
        return DownloadTicket(
            download_id, signature, len(data),
            tuple(PieceInfo(i, sha(p), len(p)) for i, p in enumerate(parts)),
        )

    def download_chunk(self, download_id, index):
        self._auth()
        if self.server.corrupt_next_download:
            self.server.corrupt_next_download -= 1
            return b"corrupted"
        return self.server.downloads[download_id][index]

    def finish_download(self, download_id, signature):
        self.server.calls.append(("finish_download", download_id))
        return True

    def delete_manifest(self, repository, reference):
        self._auth()
        signature = self.server.tags.get((repository, reference), reference)
        self.server.manifests.pop((repository, signature), None)
        self.server.tags = {k: v for k, v in self.server.tags.items()
                            if v != signature}
        self.server.calls.append(("delete", repository, reference))
        return signature


class FakeConnector(RegistryConnector):
    def __init__(self, server):
        self.server = server
        self.connections = []

    def connect(self, registry, secure=True, token=None):
        self.connections.append((registry, secure, token))
        return FakeClient(self.server, token)


class FakeRunner(CommandRunner):
    def __init__(self, system="Linux", codes=None, admin_ok=True):
        self._system = system
        self.codes = codes or {}
        self.admin_ok = admin_ok
        self.calls = []
        self.admin_checked = False

    def system(self):
        return self._system

    def environment(self):
        return {"BASE": "1"}

    def check_admin(self):
        self.admin_checked = True
        if not self.admin_ok:
            from cli.domain.errors import CliError
            raise CliError("Run the terminal as administrator")

    def run(self, argv, cwd, env, admin):
        if argv[0] == "missing":
            raise CommandFailedError("Program not found: missing")
        self.calls.append((list(argv), key(cwd), dict(env), admin))
        return self.codes.get(argv[0], 0)


class FakePrompter(Prompter):
    def __init__(self, action="cancel", confirmations=(), new_password="newsecret1"):
        self.action = action
        self.confirmations = list(confirmations)
        self.new_password = new_password
        self.asked = []

    def choose_conflict_action(self, paths):
        self.asked.append(("conflicts", list(paths)))
        return self.action

    def confirm_overwrite(self, path):
        self.asked.append(("confirm", path))
        return self.confirmations.pop(0)

    def ask_new_password(self):
        self.asked.append(("password",))
        return self.new_password


class Clock:
    def __init__(self):
        self.now = datetime(2026, 11, 2, tzinfo=timezone.utc)

    def __call__(self):
        self.now += timedelta(seconds=1)
        return self.now


def make_world(files=None, prefix=None, system="Linux"):
    clock = Clock()
    server = FakeRegistry()
    return SimpleNamespace(
        fs=FakeFileSystem(files),
        archiver=FakeArchiver(),
        codec=FakeCodec(),
        manifests=FakeBlobStore(clock),
        layers=FakeBlobStore(clock),
        index=FakeIndex(),
        settings=FakeSettings(prefix),
        credentials=FakeCredentials(),
        server=server,
        connector=FakeConnector(server),
        runner=FakeRunner(system),
        prompter=FakePrompter(),
        clock=clock,
    )


def template_document(**overrides):
    document = {
        "tag": "reg:5000/org/web:v1",
        "description": "Web service",
        "template": {"layers": [{"origin": "src", "objective": "app"}]},
        "instantiation": {"arguments": [
            {"name": "service", "type": "str", "default": "shop",
             "description": "Service name"},
            {"name": "port", "type": "int", "default": 8080},
        ]},
        "build": {
            "arguments": [{"name": "image", "type": "str", "default": "img"}],
            "commands": ["docker build -t [%image%]:[%service%] ."],
        },
        "deploy": {"commands": ["kubectl apply -f k8s"]},
    }
    document.update(overrides)
    return document


def project_files(document=None, extra=None):
    files = {
        "proj/template.yaml": json.dumps(document or template_document()),
        "proj/src/main.py": "name = '[%service%]'\nport = [%port%]\n",
        "proj/src/[%service%].txt": "plain\n",
        "proj/src/literal.txt": r"keep \[%service%] as is" + "\n",
        "proj/src/logo.png": b"\x89PNG\x00\x01[%service%]",
    }
    files.update(extra or {})
    return files


def project_world(document=None, extra=None, prefix=None):
    """World with a template project in ``proj`` and an empty folder."""
    world = make_world(project_files(document, extra), prefix)
    world.fs.make_dirs(Path("proj/src/empty"))
    return world
