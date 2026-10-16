"""Mask provider-visible operation descriptions and schemas with the turn map."""

from dataclasses import replace


def masked_structure(value, pseudonymizer):
    if isinstance(value, str):
        return pseudonymizer.mask(value)
    if isinstance(value, dict):
        return {pseudonymizer.mask(key): masked_structure(item, pseudonymizer)
                for key, item in value.items()}
    if isinstance(value, list):
        return [masked_structure(item, pseudonymizer) for item in value]
    return value


def masked_schema(schema, pseudonymizer):
    if not isinstance(schema, dict):
        return schema
    result = {}
    for key, value in schema.items():
        if key in {"description", "title", "default", "enum", "const", "examples", "$comment"}:
            result[key] = masked_structure(value, pseudonymizer)
        elif key in {"properties", "$defs", "definitions", "dependentSchemas"} and isinstance(value, dict):
            result[key] = {pseudonymizer.mask(name): masked_schema(child, pseudonymizer)
                           for name, child in value.items()}
        elif key == "required" and isinstance(value, list):
            result[key] = [pseudonymizer.mask(name) for name in value]
        elif isinstance(value, dict):
            result[key] = masked_schema(value, pseudonymizer)
        elif isinstance(value, list):
            result[key] = [masked_schema(item, pseudonymizer) for item in value]
        else:
            # Validation keywords and their structural values (type, format,
            # regex, references) are protocol, not natural-language content.
            result[key] = value
    return result


def masked_spec(spec, pseudonymizer):
    # The routing name is an opaque protocol identifier; it must stay stable.
    return replace(spec, description=pseudonymizer.mask(spec.description),
                   parameters=masked_schema(spec.parameters, pseudonymizer))
