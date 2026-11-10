import io
import tarfile

from cli.data.models import ArchiveEntry
from cli.domain.errors import ValidationError
from cli.persistence.archiver import Archiver


class TarArchiver(Archiver):
    """Reproducible tarballs (C-11).

    Entries are written in the given order with fixed dates, owners and
    permissions, so the same files always produce the same bytes and the
    same SHA-256 on any machine.
    """

    def pack(self, entries: list[ArchiveEntry]) -> bytes:
        """Pack entries into a tarball.

        Args:
            entries: Files and folders, already sorted.

        Returns:
            The tarball bytes.
        """
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w", format=tarfile.GNU_FORMAT) as tar:
            for entry in entries:
                info = tarfile.TarInfo(entry.path)
                info.mtime = 0
                info.uid = info.gid = 0
                info.uname = info.gname = ""
                if entry.content is None:
                    info.type = tarfile.DIRTYPE
                    info.mode = 0o755
                    tar.addfile(info)
                else:
                    info.mode = 0o644
                    info.size = len(entry.content)
                    tar.addfile(info, io.BytesIO(entry.content))
        return buffer.getvalue()

    def unpack(self, content: bytes) -> list[ArchiveEntry]:
        """Read the entries of a tarball.

        Args:
            content: Tarball bytes.

        Returns:
            The files and folders in stored order.

        Raises:
            ValidationError: If it is not a tarball or has links or devices.
        """
        try:
            with tarfile.open(fileobj=io.BytesIO(content), mode="r:") as tar:
                entries = []
                for member in tar.getmembers():
                    name = member.name.rstrip("/")
                    if member.isdir():
                        entries.append(ArchiveEntry(name))
                    elif member.isfile():
                        entries.append(
                            ArchiveEntry(name, tar.extractfile(member).read())
                        )
                    else:
                        raise ValidationError(
                            f"Layers can only contain files and folders: {name}"
                        )
                return entries
        except tarfile.TarError as error:
            raise ValidationError(f"Invalid layer: {error}") from None
