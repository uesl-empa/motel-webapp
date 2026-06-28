def parse_type(technology_type: str | None) -> str | None:
    if not technology_type:
        return None

    normalized_type = technology_type.strip().lower()

    return {
        "converter": "conversion",
        "energyconverter": "conversion",
        "storage": "storage",
    }.get(normalized_type)
