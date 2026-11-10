"""Conversion between models and the YAML documents of the CLI.

Documents are plain dictionaries; reading and writing YAML is done by the
infrastructure. Keys keep a fixed order so the same manifest always
produces the same bytes and therefore the same ID (C-10).
"""
from cli.data.models import (
    InstanceConfig,
    Manifest,
    Stage,
    TemplatedFile,
    Variable,
    VariableType,
)
from cli.domain import values, variables
from cli.domain.errors import ValidationError


def parse_variables(items, section: str, errors: list[str]) -> tuple[Variable, ...]:
    """Read a list of variables, collecting every problem.

    Args:
        items: ``arguments`` list of a section; None means no variables.
        section: Name of the section, used in the messages.
        errors: List that receives the problems.

    Returns:
        The valid variables.
    """
    if items is None:
        return ()
    if not isinstance(items, list):
        errors.append(f"'{section}.arguments' must be a list")
        return ()
    result, seen = [], set()
    for item in items:
        if not isinstance(item, dict):
            errors.append(f"Every argument of '{section}' must be a mapping")
            continue
        name = item.get("name")
        if not variables.is_valid_name(name):
            errors.append(f"Invalid variable name {name!r} in '{section}'")
            continue
        if name in seen:
            errors.append(f"Variable '{name}' is repeated in '{section}'")
            continue
        seen.add(name)
        try:
            vtype = VariableType(item.get("type"))
        except ValueError:
            errors.append(
                f"Variable '{name}' has an invalid type {item.get('type')!r}; "
                "use str, int, bool or float"
            )
            continue
        default = item.get("default")
        problems = values.check_default(name, default, vtype)
        if problems:
            errors.extend(problems)
            continue
        if vtype is VariableType.FLOAT:
            default = float(default)
        result.append(
            Variable(name, vtype, default, str(item.get("description") or ""))
        )
    return tuple(result)


def parse_stage(document, section: str, errors: list[str]) -> Stage:
    """Read a build or deploy section, collecting every problem.

    Args:
        document: Content of the section.
        section: ``build`` or ``deploy``.
        errors: List that receives the problems.

    Returns:
        The stage; empty if the section is invalid.
    """
    if not isinstance(document, dict):
        errors.append(f"Missing section '{section}'")
        return Stage()
    commands = document.get("commands") or []
    if not isinstance(commands, list) or not all(
        isinstance(command, str) for command in commands
    ):
        errors.append(f"'{section}.commands' must be a list of strings")
        commands = []
    return Stage(
        parse_variables(document.get("arguments"), section, errors),
        tuple(commands),
    )


def variable_to_document(variable: Variable) -> dict:
    """Write a variable as a document.

    Args:
        variable: Variable to write.

    Returns:
        ``name``, ``type``, ``default`` and, if any, ``description``.
    """
    document = {
        "name": variable.name,
        "type": variable.type.value,
        "default": variable.default,
    }
    if variable.description:
        document["description"] = variable.description
    return document


def stage_to_document(stage: Stage) -> dict:
    """Write a stage as a document.

    Args:
        stage: Stage to write.

    Returns:
        ``arguments`` and ``commands``.
    """
    return {
        "arguments": [variable_to_document(v) for v in stage.variables],
        "commands": list(stage.commands),
    }


def manifest_to_document(manifest: Manifest) -> dict:
    """Write a manifest as a document with a fixed key order.

    Args:
        manifest: Manifest to write.

    Returns:
        The document.
    """
    return {
        "tag": manifest.reference,
        "description": manifest.description,
        "readme": manifest.readme,
        "layers": list(manifest.layers),
        "files": [
            {"path": f.path, "variables": list(f.variables)}
            for f in manifest.files
        ],
        "instantiation": {
            "arguments": [variable_to_document(v) for v in manifest.instantiation]
        },
        "build": stage_to_document(manifest.build),
        "deploy": stage_to_document(manifest.deploy),
    }


def manifest_from_document(document) -> Manifest:
    """Read a manifest document.

    Args:
        document: Parsed YAML.

    Returns:
        The manifest.

    Raises:
        ValidationError: If the document is not a valid manifest.
    """
    errors = []
    if not isinstance(document, dict):
        raise ValidationError("The manifest is not a mapping")
    layers = document.get("layers")
    files = document.get("files", [])
    if not isinstance(document.get("tag"), str):
        errors.append("The manifest has no tag")
    if not isinstance(layers, list) or not all(isinstance(l, str) for l in layers):
        errors.append("The manifest has no layer list")
        layers = []
    if not isinstance(files, list):
        errors.append("The manifest has an invalid file list")
        files = []
    instantiation = document.get("instantiation") or {}
    manifest = Manifest(
        reference=str(document.get("tag")),
        layers=tuple(layers),
        files=tuple(
            TemplatedFile(str(f.get("path")), tuple(f.get("variables") or ()))
            for f in files if isinstance(f, dict)
        ),
        instantiation=parse_variables(
            instantiation.get("arguments"), "instantiation", errors
        ),
        build=parse_stage(document.get("build"), "build", errors),
        deploy=parse_stage(document.get("deploy"), "deploy", errors),
        description=str(document.get("description") or ""),
        readme=str(document.get("readme") or ""),
    )
    if errors:
        raise ValidationError(errors)
    return manifest


def config_to_document(config: InstanceConfig) -> dict:
    """Write a ``config.template`` document.

    Args:
        config: Configuration to write.

    Returns:
        The document.
    """
    return {
        "template": {"id": config.template_id, "tag": config.reference},
        "instantiation": {
            "arguments": [variable_to_document(v) for v in config.instantiation]
        },
        "build": stage_to_document(config.build),
        "deploy": stage_to_document(config.deploy),
    }


def config_from_document(document) -> InstanceConfig:
    """Read a ``config.template`` document.

    The ``template`` and ``instantiation`` sections are optional, so files
    written by hand with only ``build`` and ``deploy`` still work.

    Args:
        document: Parsed YAML.

    Returns:
        The configuration.

    Raises:
        ValidationError: If the document is not valid.
    """
    if not isinstance(document, dict):
        raise ValidationError("config.template is not a mapping")
    errors = []
    template = document.get("template") or {}
    instantiation = document.get("instantiation") or {}
    config = InstanceConfig(
        template_id=template.get("id"),
        reference=str(template.get("tag") or ""),
        instantiation=parse_variables(
            instantiation.get("arguments"), "instantiation", errors
        ),
        build=parse_stage(document.get("build") or {}, "build", errors),
        deploy=parse_stage(document.get("deploy") or {}, "deploy", errors),
    )
    if errors:
        raise ValidationError(errors)
    return config
