"""Validation of ``template.yaml`` (C-09, C-12, C-15)."""
from collections.abc import Callable

from cli.data.models import LayerSource, TemplateSpec
from cli.domain import commands
from cli.domain.documents import parse_stage, parse_variables
from cli.domain.errors import ValidationError


def parse_template(document, exists: Callable[[str], bool]) -> TemplateSpec:
    """Validate a ``template.yaml`` and report every problem together.

    Required: ``tag``, ``template.layers`` (at least one, each with an
    existing ``origin`` and an ``objective``), ``instantiation``, ``build``
    and ``deploy``. Variables are optional, but each one needs a valid
    name, a valid type and a default of that type, and names cannot repeat
    inside a section. Commands must be valid and only use declared
    variables. ``description`` and ``readme`` are optional.

    Args:
        document: Parsed YAML.
        exists: Tells whether a path relative to ``template.yaml`` exists.

    Returns:
        The validated template.

    Raises:
        ValidationError: With one message per problem.
    """
    if not isinstance(document, dict):
        raise ValidationError("template.yaml must be a mapping")
    errors = []

    tag = document.get("tag")
    if not isinstance(tag, str) or not tag:
        errors.append("Missing 'tag'")

    layers = _layers(document.get("template"), exists, errors)

    instantiation = document.get("instantiation")
    if not isinstance(instantiation, dict):
        errors.append("Missing section 'instantiation'")
        instantiation = {}
    shared = parse_variables(
        instantiation.get("arguments"), "instantiation", errors
    )
    build = parse_stage(document.get("build"), "build", errors)
    deploy = parse_stage(document.get("deploy"), "deploy", errors)

    shared_names = [v.name for v in shared]
    for stage in (build, deploy):
        names = shared_names + [v.name for v in stage.variables]
        for line in stage.commands:
            errors.extend(commands.validate(line, names))

    description = document.get("description") or ""
    readme = document.get("readme")
    if readme is not None and (not isinstance(readme, str) or not exists(readme)):
        errors.append(f"The readme {readme!r} does not exist")

    if errors:
        raise ValidationError(errors)
    return TemplateSpec(
        tag=tag,
        layers=layers,
        instantiation=shared,
        build=build,
        deploy=deploy,
        description=str(description),
        readme=readme,
    )


def _layers(template, exists, errors: list[str]) -> tuple[LayerSource, ...]:
    """Read ``template.layers``, collecting every problem.

    Args:
        template: Content of the ``template`` section.
        exists: Tells whether a path exists.
        errors: List that receives the problems.

    Returns:
        The valid layers.
    """
    if not isinstance(template, dict):
        errors.append("Missing section 'template'")
        return ()
    items = template.get("layers")
    if not isinstance(items, list) or not items:
        errors.append("'template.layers' needs at least one layer")
        return ()
    result = []
    for item in items:
        origin = item.get("origin") if isinstance(item, dict) else None
        objective = item.get("objective") if isinstance(item, dict) else None
        if not isinstance(origin, str) or not isinstance(objective, str):
            errors.append("Every layer needs an 'origin' and an 'objective'")
        elif not exists(origin):
            errors.append(f"The origin '{origin}' does not exist")
        else:
            result.append(LayerSource(origin, objective))
    return tuple(result)
