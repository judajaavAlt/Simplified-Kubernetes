from dataclasses import dataclass

from cli.application.create_template import CreateTemplate
from cli.application.inspect_template import InspectTemplate
from cli.application.list_templates import ListTemplates
from cli.application.login import Login, Logout
from cli.application.pull_template import PullTemplate
from cli.application.push_template import PushTemplate
from cli.application.rebuild_index import RebuildIndex
from cli.application.remove_template import RemoveTemplate
from cli.application.run_instance import RunInstance
from cli.application.sample_files import WriteSampleFiles
from cli.application.setup_template import SetupTemplate
from cli.application.tag_template import TagTemplate
from cli.application.work_prefix import SetWorkPrefix, ShowWorkPrefix


@dataclass
class CliServices:
    """Every use case the commands can call.

    The composition root in infraestructure builds it with the real
    implementations; tests can build it with fakes. Each attribute is the
    use case of the command with a similar name.
    """

    create: CreateTemplate
    list: ListTemplates
    inspect: InspectTemplate
    setup: SetupTemplate
    samples: WriteSampleFiles
    tag: TagTemplate
    remove: RemoveTemplate
    reindex: RebuildIndex
    push: PushTemplate
    pull: PullTemplate
    login: Login
    logout: Logout
    set_prefix: SetWorkPrefix
    show_prefix: ShowWorkPrefix
    instance: RunInstance
