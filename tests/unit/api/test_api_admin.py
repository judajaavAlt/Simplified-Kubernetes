import pytest

from api.application.admin.list_audit_events import ListAuditEvents
from api.domain.errors import PermissionDenied
from transfer_helpers import push


pytestmark = pytest.mark.unit


def test_admin_reads_the_audit_log_newest_first(world):
    push(world, world.devops, b"blob")

    events = ListAuditEvents(audit=world.audit).execute(world.admin, limit=2)

    assert [e.event for e in events] == ["upload.finish", "upload.chunk"]


@pytest.mark.parametrize("actor", ["devops", "developer"])
def test_only_admin_reads_the_audit_log(world, actor):
    with pytest.raises(PermissionDenied):
        ListAuditEvents(audit=world.audit).execute(getattr(world, actor))
