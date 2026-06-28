from collections import defaultdict

from backend.src.repositories.node_repository import GraphDBNodeRepository
from backend.src.utils.iri import local_name


def get_filterable_attribute_names_for_type(
    node_repository: GraphDBNodeRepository,
    type_label: str,
) -> set[str]:
    discovered = node_repository.get_filterable_attributes_for_type(type_label)
    if discovered.empty or "attribute_type" not in discovered.columns:
        return set()

    discovered_names = {
        local_name(str(attribute))
        for attribute in discovered["attribute_type"].dropna().astype(str)
    }
    return {name for name in discovered_names if name is not None}


def get_available_location_iris(
    node_repository: GraphDBNodeRepository,
    type_label: str,
) -> set[str]:
    discovered = node_repository.get_available_locations_for_type(type_label)

    if discovered.empty or "location" not in discovered.columns:
        return set()

    return {
        str(location)
        for location in discovered["location"].dropna().astype(str)
        if str(location).strip()
    }


def get_available_carrier_iris(
    node_repository: GraphDBNodeRepository,
    type_label: str,
) -> set[str]:
    discovered = node_repository.get_available_carriers_for_type(type_label)

    if discovered.empty or "carrier" not in discovered.columns:
        return set()

    return {
        str(carrier)
        for carrier in discovered["carrier"].dropna().astype(str)
        if str(carrier).strip()
    }


# Restricts the component tree to subtrees rooted at these component local names.
# To re-enable other top-level categories, add their local names here:
#   "energycarrier"
#   "flow"
#   "material"
_ENABLED_ROOT_COMPONENT_LOCAL_NAMES: set[str] = {
    "energyconverter",
    "energystorage",
}


def get_component_hierarchy(node_repository: GraphDBNodeRepository) -> list[dict[str, object]]:
    discovered = node_repository.get_components()

    if discovered.empty or "component" not in discovered.columns:
        return []

    direct_parents_by_component: dict[str, set[str]] = defaultdict(set)
    children_by_component: dict[str, set[str]] = defaultdict(set)
    all_components: set[str] = set()
    instance_bearing_components: set[str] = set()

    for row in discovered.to_dict(orient="records"):
        component = _normalize_optional_string(row.get("component"))
        if component is None:
            continue

        all_components.add(component)

        if _coerce_bool(row.get("has_instances")):
            instance_bearing_components.add(component)

        parent_component = _normalize_optional_string(row.get("parent"))
        if parent_component is not None:
            direct_parents_by_component[component].add(parent_component)
            children_by_component[parent_component].add(component)

    relevant_components = _collect_relevant_components(
        instance_bearing_components,
        direct_parents_by_component,
    )

    if not relevant_components:
        return []

    if _ENABLED_ROOT_COMPONENT_LOCAL_NAMES:
        relevant_components = _filter_to_enabled_roots(
            relevant_components,
            children_by_component,
        )

    parent_by_component = {
        component: _pick_preferred_parent(
            component,
            direct_parents_by_component,
            relevant_components,
        )
        for component in relevant_components
    }

    relevant_children_by_component: dict[str, set[str]] = defaultdict(set)
    for component, parent_component in parent_by_component.items():
        if parent_component is not None:
            relevant_children_by_component[parent_component].add(component)

    has_instance_descendant = {
        component: _has_instance_descendant(
            component,
            instance_bearing_components,
            children_by_component,
        )
        for component in relevant_components
    }

    return [
        {
            "component": component,
            "label": local_name(component) or component,
            "parent_component": parent_by_component.get(component),
            "is_leaf": component not in relevant_children_by_component,
            "has_instances": component in instance_bearing_components,
            "has_instance_descendant": has_instance_descendant.get(component, False),
        }
        for component in sorted(
            relevant_components,
            key=lambda value: (local_name(value) or value).lower(),
        )
    ]


def _coerce_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False

    return str(value).strip().lower() in {"true", "1"}


def _normalize_optional_string(value: object) -> str | None:
    if value is None:
        return None

    normalized = str(value).strip()
    if not normalized or normalized.lower() == "nan":
        return None

    return normalized


def _collect_relevant_components(
    instance_bearing_components: set[str],
    direct_parents_by_component: dict[str, set[str]],
) -> set[str]:
    relevant_components = set(instance_bearing_components)
    stack = list(instance_bearing_components)

    while stack:
        component = stack.pop()
        for parent_component in direct_parents_by_component.get(component, ()): 
            if parent_component in relevant_components:
                continue

            relevant_components.add(parent_component)
            stack.append(parent_component)

    return relevant_components


def _filter_to_enabled_roots(
    relevant_components: set[str],
    children_by_component: dict[str, set[str]],
) -> set[str]:
    """Keep only components that are an enabled root or a descendant of one."""
    seed_roots = {
        component
        for component in relevant_components
        if (local_name(component) or "").strip().lower() in _ENABLED_ROOT_COMPONENT_LOCAL_NAMES
    }

    if not seed_roots:
        # Avoid hiding the entire tree when namespace formatting differs unexpectedly.
        return relevant_components

    allowed: set[str] = set()
    stack = list(seed_roots)

    while stack:
        component = stack.pop()
        if component in allowed:
            continue
        allowed.add(component)
        stack.extend(children_by_component.get(component, ()))

    return relevant_components & allowed


def _pick_preferred_parent(
    component: str,
    direct_parents_by_component: dict[str, set[str]],
    relevant_components: set[str],
) -> str | None:
    candidates = sorted(
        parent
        for parent in direct_parents_by_component.get(component, ())
        if parent in relevant_components
    )
    return candidates[0] if candidates else None


def _has_instance_descendant(
    component: str,
    instance_bearing_components: set[str],
    children_by_component: dict[str, set[str]],
) -> bool:
    stack = list(children_by_component.get(component, ()))
    visited: set[str] = set()

    while stack:
        child_component = stack.pop()
        if child_component in visited:
            continue

        visited.add(child_component)
        if child_component in instance_bearing_components:
            return True

        stack.extend(children_by_component.get(child_component, ()))

    return False
