from collections.abc import Mapping

from backend.src.utils.sparql_terms import serialize_prefixed_ontology_local_name
from backend.src.utils.sparql_terms import serialize_sparql_iri_or_prefixed_name

NumericRange = tuple[float | None, float | None]


def build_range_filter_fragment(attribute_ranges: Mapping[str, NumericRange]) -> str:
    if not attribute_ranges:
        return ""

    fragments: list[str] = []
    for idx, (attribute_name, bounds) in enumerate(attribute_ranges.items()):
        lower, upper = bounds
        conditions: list[str] = []
        if lower is not None:
            conditions.append(f"?range_num_{idx} >= {lower:g}")
        if upper is not None:
            conditions.append(f"?range_num_{idx} <= {upper:g}")

        if not conditions:
            continue

        fragments.append(
            "\n".join(
                [
                    "FILTER EXISTS {",
                    f"  ?tech dici_onto:hasAttribute ?range_att_{idx} .",
                    f"  ?range_att_{idx} a {serialize_prefixed_ontology_local_name(attribute_name)} .",
                    f"  ?range_att_{idx} dici_onto:hasAttributeValue ?range_val_{idx} .",
                    (
                        f"  BIND(IF(datatype(?range_val_{idx}) = xsd:gYear, "
                        f"xsd:double(REPLACE(STR(?range_val_{idx}), \"^(-?[0-9]+).*$\", \"$1\")), "
                        f"xsd:double(?range_val_{idx})) AS ?range_num_{idx}) ."
                    ),
                    f"  FILTER({' && '.join(conditions)}) .",
                    "}",
                ]
            )
        )

    return "\n\n    ".join(fragments)


def build_location_filter_fragment(location_iris: list[str]) -> str:
    if not location_iris:
        return ""

    trimmed = [iri.strip() for iri in location_iris if iri.strip()]
    if not trimmed:
        return ""

    terms = ", ".join(serialize_sparql_iri_or_prefixed_name(iri) for iri in trimmed)

    return "\n".join(
        [
            "FILTER EXISTS {",
            f"  ?tech dici_onto:locatedIn ?loc_filter .",
            f"  FILTER(?loc_filter IN ({terms})) .",
            "}",
        ]
    )


def build_carrier_filter_fragment(carrier_iris: list[str]) -> str:
    if not carrier_iris:
        return ""

    terms = ", ".join(
        serialize_sparql_iri_or_prefixed_name(iri.strip())
        for iri in carrier_iris
        if iri.strip()
    )
    if not terms:
        return ""

    return "\n".join(
        [
            "FILTER EXISTS {",
            "  ?tech (dici_onto:feeds|dici_onto:fedBy|^dici_onto:feeds|^dici_onto:fedBy) ?_carrier_flow .",
            "  VALUES ?_carrier_flow_type { dici_onto:Flow dici_onto:EnergyCarrierFlow dici_onto:MaterialFlow }",
            "  ?_carrier_flow a ?_carrier_flow_type .",
            "  ?_carrier_flow dici_onto:contains ?_carrier_iri .",
            f"  FILTER(?_carrier_iri IN ({terms})) .",
            "}",
        ]
    )
