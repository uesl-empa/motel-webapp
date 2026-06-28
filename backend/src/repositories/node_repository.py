from abc import ABC, abstractmethod
import pandas as pd
from backend.src.db.queries import (
    ALL_TYPES,
    ASSEMBLY_SUPPORT_FOR_TECHNOLOGY,
    AVAILABLE_CARRIERS_FOR_TYPE,
    AVAILABLE_LOCATIONS_FOR_TYPE,
    COMPONENTS,
    EMBEDDED_CARBON_PARAMS,
    ENERGY_CARRIER_PARAMS,
    FILTERABLE_ATTRIBUTES_FOR_TYPE,
    INSTANCES_WITH_ATTRIBUTES,
    SUPPORTED_ASSEMBLY_COMPONENT_TYPES,
    TECH_PARAMS,
    TECHNOLOGY_TYPES,
)
from backend.src.constants.technology_attributes import get_tech_attribute_filter_values
from backend.src.utils.sparql_terms import serialize_sparql_iri_or_prefixed_name

class NodeRepository(ABC):
    @abstractmethod
    def get_all_types(self) -> pd.DataFrame:
        pass

    def get_components(self) -> pd.DataFrame:
        pass

    def get_tech_params(self, id: str, supported_component_roots: list[str] | None = None) -> pd.DataFrame:
        pass

    def get_technology_types(self, id: str) -> pd.DataFrame:
        pass

    def is_technology_supported_for_assembly(self, id: str, supported_component_roots: list[str]) -> bool:
        pass

    def get_supported_assembly_component_types(self, supported_component_roots: list[str]) -> pd.DataFrame:
        pass

    def get_instances_with_attributes(
        self,
        tech_type: str,
        range_filters: str = "",
        location_filter: str = "",
        carrier_filter: str = "",
    ) -> pd.DataFrame:
        pass

    def get_available_carriers_for_type(self, tech_type: str) -> pd.DataFrame:
        pass

    def get_filterable_attributes_for_type(self, tech_type: str) -> pd.DataFrame:
        pass

    def get_energy_carriers(self, energy_conv_id: str) -> pd.DataFrame:
        pass

    def get_embedded_carbon(self, tech_id: str) -> pd.DataFrame:
        pass

    def get_available_locations_for_type(self, tech_type: str) -> pd.DataFrame:
        pass

class GraphDBNodeRepository(NodeRepository):
    def __init__(self, client):
        self.client = client

    def get_all_types(self) -> pd.DataFrame:
        query = ALL_TYPES
        results = self.client.sparql_query(query)
        return results
    
    # Returns component classes with parent links and a direct-instance flag.
    # Inference stays disabled so direct `a ?component` matches remain explicit.
    def get_components(self) -> pd.DataFrame:
        query = COMPONENTS
        results = self.client.sparql_query(query, replace_namespaces=True, infer=False)
        return results
    
    def get_tech_params(self, id: str, supported_component_roots: list[str] | None = None) -> pd.DataFrame:
        normalized_supported_component_roots = supported_component_roots or [
            "dici_onto:Converter",
            "dici_onto:EnergyConverter",
        ]
        query = TECH_PARAMS.format(
            tech_id_term=serialize_sparql_iri_or_prefixed_name(id),
            tech_attribute_filter_values=get_tech_attribute_filter_values(),
            supported_component_roots="\n        ".join(
                serialize_sparql_iri_or_prefixed_name(root)
                for root in normalized_supported_component_roots
            ),
        )
        results = self.client.sparql_query(query)
        return results

    def get_technology_types(self, id: str) -> pd.DataFrame:
        query = TECHNOLOGY_TYPES.format(
            tech_id_term=serialize_sparql_iri_or_prefixed_name(id),
        )
        results = self.client.sparql_query(query, replace_namespaces=True)
        return results

    def is_technology_supported_for_assembly(self, id: str, supported_component_roots: list[str]) -> bool:
        if not supported_component_roots:
            return False

        query = ASSEMBLY_SUPPORT_FOR_TECHNOLOGY.format(
            tech_id_term=serialize_sparql_iri_or_prefixed_name(id),
            supported_component_roots="\n        ".join(
                serialize_sparql_iri_or_prefixed_name(root)
                for root in supported_component_roots
            ),
        )
        results = self.client.sparql_query(query)
        if results.empty or "match_count" not in results.columns:
            return False

        value = results.iloc[0]["match_count"]
        try:
            return int(float(str(value))) > 0
        except (TypeError, ValueError):
            return False

    def get_supported_assembly_component_types(self, supported_component_roots: list[str]) -> pd.DataFrame:
        if not supported_component_roots:
            return pd.DataFrame(columns=["component"])

        query = SUPPORTED_ASSEMBLY_COMPONENT_TYPES.format(
            supported_component_roots="\n        ".join(
                serialize_sparql_iri_or_prefixed_name(root)
                for root in supported_component_roots
            ),
        )
        results = self.client.sparql_query(query, replace_namespaces=True)
        return results
    
    def get_instances_with_attributes(
        self,
        tech_type: str,
        range_filters: str = "",
        location_filter: str = "",
        carrier_filter: str = "",
    ) -> pd.DataFrame:
        query = INSTANCES_WITH_ATTRIBUTES.format(
            tech_type_term=serialize_sparql_iri_or_prefixed_name(tech_type),
            range_filters=range_filters,
            location_filter=location_filter,
            carrier_filter=carrier_filter,
        )
        results = self.client.sparql_query(query)
        return results

    def get_available_carriers_for_type(self, tech_type: str) -> pd.DataFrame:
        query = AVAILABLE_CARRIERS_FOR_TYPE.format(
            tech_type_term=serialize_sparql_iri_or_prefixed_name(tech_type)
        )
        results = self.client.sparql_query(query)
        return results

    def get_filterable_attributes_for_type(self, tech_type: str) -> pd.DataFrame:
        query = FILTERABLE_ATTRIBUTES_FOR_TYPE.format(
            tech_type_term=serialize_sparql_iri_or_prefixed_name(tech_type)
        )
        results = self.client.sparql_query(query, replace_namespaces=True)
        return results
    
    def get_energy_carriers(self, energy_conv_id: str) -> pd.DataFrame:
        query = ENERGY_CARRIER_PARAMS.format(
            energy_conv_id_term=serialize_sparql_iri_or_prefixed_name(energy_conv_id)
        )
        results = self.client.sparql_query(query)
        return results

    def get_embedded_carbon(self, tech_id: str) -> pd.DataFrame:
        query = EMBEDDED_CARBON_PARAMS.format(
            tech_id_term=serialize_sparql_iri_or_prefixed_name(tech_id)
        )
        results = self.client.sparql_query(query)
        return results

    def get_available_locations_for_type(self, tech_type: str) -> pd.DataFrame:
        query = AVAILABLE_LOCATIONS_FOR_TYPE.format(
            tech_type_term=serialize_sparql_iri_or_prefixed_name(tech_type)
        )
        results = self.client.sparql_query(query)
        return results