import re


_DISALLOWED_IRI_CHARS = re.compile(r"[<>\"{}|^`\\\s]")
_IRI_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
_PREFIXED_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9._-]*:[A-Za-z_][A-Za-z0-9._-]*$")
_LOCAL_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9._-]*$")


def serialize_sparql_iri_or_prefixed_name(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("SPARQL term cannot be empty")

    if _PREFIXED_NAME.fullmatch(normalized):
        return normalized

    if not _IRI_SCHEME.match(normalized):
        raise ValueError(f"Unsupported SPARQL identifier: {value}")

    if _DISALLOWED_IRI_CHARS.search(normalized):
        raise ValueError(f"Invalid IRI for SPARQL term: {value}")

    return f"<{normalized}>"


def serialize_prefixed_ontology_local_name(local_name: str, prefix: str = "dici_onto") -> str:
    normalized = local_name.strip()
    if not _LOCAL_NAME.fullmatch(normalized):
        raise ValueError(f"Unsupported ontology local name: {local_name}")

    return f"{prefix}:{normalized}"
