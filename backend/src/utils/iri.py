def local_name(iri_or_prefixed: str | None) -> str | None:
    if not iri_or_prefixed:
        return iri_or_prefixed

    return iri_or_prefixed.rstrip("/#").split("/")[-1].split("#")[-1].split(":")[-1]
