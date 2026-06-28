FIELD_LIFETIME = "lifetime"
FIELD_TRL = "trl"
FIELD_INTEREST_RATE = "interest_rate"
FIELD_CAPEX = "capex"
FIELD_CAPEX_PER_CAP = "capex_per_rated_power"
FIELD_OPEX = "opex"
FIELD_OPEX_CAP = "opex_cap"
FIELD_OPEX_ENERGY = "opex_energy"
FIELD_CO2_CAP = "co2_cap"
FIELD_INTRODUCED = "introduced"

# Currently in use
LIFETIME_ATTRIBUTE = "Lifetime"
TRL_ATTRIBUTE = "TRL"
CAPEX_POWER_ATTRIBUTE = "CAPEX_power" # can be used for capex_per_cap
OPEX_POWER_ATTRIBUTE = "OPEX_power" # can be used for opex_per_cap
OPEX_ENERGY_ATTRIBUTE = "OPEX_energy" # used for opex_per_energy
CAPEX_MASSRATE_ATTRIBUTE = "CAPEX_massrate" # can be used for capex_per_cap
OPEX_MASSRATE_ATTRIBUTE = "OPEX_massrate" # can be used for opex_per_cap
OPEX_PRODUCTION_ATTRIBUTE = "OPEX_production" # can be used for opex_per_cap

INTRODUCED = "Introduced" # Year of technology used for trl

# Not currently in use, but defined in the ontology and potentially useful to have as constants.
INTEREST_RATE_ATTRIBUTE = "InterestRate"
CAPEX_ATTRIBUTE = "CAPEX"
OPEX_ATTRIBUTE = "OPEX"
OPEX_CAP_ATTRIBUTE = "OPEX_CAP"
CO2_CAP_ATTRIBUTE = "CO2_CAP"
CAPEX_PER_RATED_POWER_ATTRIBUTE = "CAPEXperRatedPower"
CAPEX_ONE_TIME_ATTRIBUTE = "CAPEXOneTime"
CAPEX_PER_CAPACITY_ATTRIBUTE = "CAPEXPerCapacity"
OPEX_ONE_TIME_ATTRIBUTE = "OPEXOneTime"
OPEX_PER_CAPACITY_ATTRIBUTE = "OPEXPerCapacity"
OPEX_PER_ENERGY_ATTRIBUTE = "OPEXPerEnergy"


# Update this dictionary to change canonical ontology attribute local names.
TECH_ATTRIBUTE_NAME_BY_FIELD = {
    FIELD_LIFETIME: LIFETIME_ATTRIBUTE,
    FIELD_TRL: TRL_ATTRIBUTE,
    FIELD_INTEREST_RATE: INTEREST_RATE_ATTRIBUTE,
    FIELD_CAPEX: CAPEX_ATTRIBUTE,
    FIELD_CAPEX_PER_CAP: CAPEX_PER_RATED_POWER_ATTRIBUTE,
    FIELD_OPEX: OPEX_ATTRIBUTE,
    FIELD_OPEX_CAP: OPEX_CAP_ATTRIBUTE,
    FIELD_OPEX_ENERGY: OPEX_ENERGY_ATTRIBUTE,
    FIELD_CO2_CAP: CO2_CAP_ATTRIBUTE,
    FIELD_INTRODUCED: INTRODUCED,
}

# Optional fallback local names per semantic field.
# Keep these empty or extend them when attribute names are migrated in GraphDB.
TECH_ATTRIBUTE_ALIASES_BY_FIELD = {
    FIELD_LIFETIME: (),
    FIELD_TRL: (),
    FIELD_INTEREST_RATE: (),
    FIELD_CAPEX: (CAPEX_ONE_TIME_ATTRIBUTE,),
    FIELD_CAPEX_PER_CAP: (CAPEX_POWER_ATTRIBUTE, CAPEX_MASSRATE_ATTRIBUTE, CAPEX_PER_CAPACITY_ATTRIBUTE),
    FIELD_OPEX: (OPEX_ONE_TIME_ATTRIBUTE,),
    FIELD_OPEX_CAP: (OPEX_POWER_ATTRIBUTE, OPEX_MASSRATE_ATTRIBUTE, OPEX_PRODUCTION_ATTRIBUTE, OPEX_PER_CAPACITY_ATTRIBUTE),
    FIELD_OPEX_ENERGY: (OPEX_PER_ENERGY_ATTRIBUTE,),
    FIELD_CO2_CAP: (),
    FIELD_INTRODUCED: (),
}


def get_attribute_names_for_field(field_key: str) -> tuple[str, ...]:
    canonical_name = TECH_ATTRIBUTE_NAME_BY_FIELD[field_key]
    alias_names = TECH_ATTRIBUTE_ALIASES_BY_FIELD.get(field_key, ())
    return tuple(dict.fromkeys((canonical_name, *alias_names)))


def get_tech_attribute_local_names() -> tuple[str, ...]:
    names: list[str] = []
    seen: set[str] = set()
    for field_key in TECH_ATTRIBUTE_NAME_BY_FIELD:
        for name in get_attribute_names_for_field(field_key):
            if name in seen:
                continue
            seen.add(name)
            names.append(name)
    return tuple(names)


def get_tech_attribute_filter_values() -> str:
    return ",\n        ".join(
        f"dici_onto:{attribute_name}" for attribute_name in get_tech_attribute_local_names()
    )


TECH_ATTRIBUTE_TYPES = get_tech_attribute_local_names()
TECH_ATTRIBUTE_IRIS = tuple(f"dici_onto:{attribute}" for attribute in TECH_ATTRIBUTE_TYPES)
TECH_ATTRIBUTE_FILTER_VALUES = get_tech_attribute_filter_values()
