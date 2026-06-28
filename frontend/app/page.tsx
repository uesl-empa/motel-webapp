"use client";

import { Fragment, useEffect, useRef, useState, type ChangeEvent, type KeyboardEvent } from "react";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/+$/, "") || "http://localhost:8000";

interface ComponentNode {
  component: string;
  label: string;
  parent_component: string | null;
  is_leaf: boolean;
  has_instances: boolean;
  has_instance_descendant: boolean;
}

interface ComponentTreeNode extends ComponentNode {
  children: ComponentTreeNode[];
}

interface VisibleComponentNode extends ComponentTreeNode {
  depth: number;
  parentComponent: string | null;
}

interface LocationOption {
  iri: string;
  label: string;
}

interface CarrierOption {
  iri: string;
  label: string;
}

interface InstanceRow {
  instance?: string;
  [key: string]: string | undefined;
}

interface FilteredData {
  component: string;
  instances: InstanceRow[];
  error?: string;
}

interface TtlFileStatus {
  path: string;
  exists: boolean;
  generated_at: string | null;
  modified_at_unix: number | null;
  size_bytes: number | null;
}

interface DataStatusResponse {
  graphdb_repository: string;
  graphdb_url: string;
  repository_size: number;
  ttl_file: TtlFileStatus;
}

interface AttributeRangeInput {
  lower: string;
  upper: string;
}

interface FlowAttributeRow {
  att: string;
  att_label?: string;
  att_category: string;
  att_val: string;
  att_unit: string;
  unit_label: string;
  att_currency: string;
}

interface FlowRow {
  flow_iri: string;
  direction: "Input" | "Output";
  carrier: string;
  attributes: FlowAttributeRow[];
}

interface EmbeddedCarbonRow {
  ec_iri: string;
  lca_activity: string;
  lca_ref_product: string;
  period: string;
  location: string;
  lca_unit: string;
  ssp2_ndc: string;
  ssp2_pkbudg1000: string;
}

interface InstanceGroup {
  key: string;
  technologyIri: string | null;
  representativeRow: InstanceRow;
  rows: InstanceRow[];
}

const buildEmptyAttributeRanges = (
  attributes: string[]
): Record<string, AttributeRangeInput> =>
  Object.fromEntries(
    attributes.map((attribute) => [attribute, { lower: "", upper: "" }])
  );

const localName = (iri: string): string =>
  iri.replace(/[\/#]+$/g, "").split("/").pop()?.split("#").pop()?.split(":").pop() ?? iri;

const formatNumericValue = (value: string): string => {
  const num = Number(value);
  if (!Number.isNaN(num) && value.trim() !== "") {
    return Number.isInteger(num) ? String(num) : value;
  }
  return value;
};

const normalizeTechnologyIdentifier = (value: string): string =>
  localName(value).trim().toLowerCase();

const supportsTechnologyAssembly = (
  componentType: string | null | undefined,
  supportedComponentLocalNames: Set<string>
): boolean => {
  if (!componentType) {
    return false;
  }

  return supportedComponentLocalNames.has(localName(componentType).toLowerCase());
};

const getFilenameFromContentDisposition = (headerValue: string | null): string | null => {
  if (!headerValue) {
    return null;
  }

  const encodedMatch = headerValue.match(/filename\*=UTF-8''([^;]+)/i);
  if (encodedMatch?.[1]) {
    try {
      return decodeURIComponent(encodedMatch[1]);
    } catch {
      return encodedMatch[1];
    }
  }

  const plainMatch = headerValue.match(/filename="?([^";]+)"?/i);
  return plainMatch?.[1] ?? null;
};

const cloneComponentTreeNode = (node: ComponentTreeNode): ComponentTreeNode => ({
  ...node,
  children: node.children.map(cloneComponentTreeNode),
});

const buildComponentTree = (components: ComponentNode[]): ComponentTreeNode[] => {
  const nodesById = new Map<string, ComponentTreeNode>();

  for (const component of components) {
    nodesById.set(component.component, { ...component, children: [] });
  }

  const roots: ComponentTreeNode[] = [];
  for (const node of nodesById.values()) {
    const parentNode = node.parent_component ? nodesById.get(node.parent_component) : undefined;
    if (parentNode) {
      parentNode.children.push(node);
      continue;
    }

    roots.push(node);
  }

  const sortNodes = (nodes: ComponentTreeNode[]) => {
    nodes.sort((left, right) => left.label.localeCompare(right.label, undefined, { sensitivity: "base" }));
    nodes.forEach((node) => sortNodes(node.children));
  };

  sortNodes(roots);
  return roots;
};

const compressUnaryDisplayTree = (
  nodes: ComponentTreeNode[],
  selectedComponent: string,
): ComponentTreeNode[] =>
  nodes.flatMap((node) => {
    const compressedChildren = compressUnaryDisplayTree(node.children, selectedComponent);
    const shouldBypassNode =
      node.children.length === 1 &&
      !node.has_instances &&
      node.component !== selectedComponent;

    if (shouldBypassNode) {
      const fallbackChild = compressedChildren[0] ?? node.children[0];
      return fallbackChild ? [fallbackChild] : [];
    }

    return [{ ...node, children: compressedChildren }];
  });

const matchesComponentSearch = (component: ComponentTreeNode, searchTerm: string): boolean => {
  const normalizedSearch = searchTerm.trim().toLowerCase();
  if (!normalizedSearch) {
    return true;
  }

  const displayValue = `${component.label} ${component.component} ${localName(component.component)}`;
  return displayValue.toLowerCase().includes(normalizedSearch);
};

const filterComponentTree = (
  nodes: ComponentTreeNode[],
  searchTerm: string,
): ComponentTreeNode[] => {
  const normalizedSearch = searchTerm.trim();
  if (!normalizedSearch) {
    return nodes.map(cloneComponentTreeNode);
  }

  return nodes.flatMap((node) => {
    if (matchesComponentSearch(node, normalizedSearch)) {
      return [{ ...node, children: node.children.map(cloneComponentTreeNode) }];
    }

    const filteredChildren = filterComponentTree(node.children, normalizedSearch);
    if (filteredChildren.length === 0) {
      return [];
    }

    return [{ ...node, children: filteredChildren }];
  });
};

const flattenVisibleComponentTree = (
  nodes: ComponentTreeNode[],
  expandedComponentKeys: Set<string>,
  forceExpand: boolean,
  depth = 0,
  parentComponent: string | null = null,
): VisibleComponentNode[] => {
  const flattened: VisibleComponentNode[] = [];

  for (const node of nodes) {
    flattened.push({
      ...node,
      depth,
      parentComponent,
    });

    const shouldShowChildren = node.children.length > 0 && (forceExpand || expandedComponentKeys.has(node.component));
    if (!shouldShowChildren) {
      continue;
    }

    flattened.push(
      ...flattenVisibleComponentTree(
        node.children,
        expandedComponentKeys,
        forceExpand,
        depth + 1,
        node.component,
      )
    );
  }

  return flattened;
};

const getComponentAncestorPath = (
  components: ComponentNode[],
  componentId: string,
): string[] => {
  const componentLookup = new Map(
    components.map((component) => [component.component, component.parent_component])
  );
  const path: string[] = [];
  const visited = new Set<string>();
  let currentComponent = componentId;

  while (true) {
    const parentComponent = componentLookup.get(currentComponent);
    if (!parentComponent || visited.has(parentComponent)) {
      return path;
    }

    path.push(parentComponent);
    visited.add(parentComponent);
    currentComponent = parentComponent;
  }
};

export default function Home() {
  const [components, setComponents] = useState<ComponentNode[]>([]);
  const [dataStatus, setDataStatus] = useState<DataStatusResponse | null>(null);
  const [dataStatusLoading, setDataStatusLoading] = useState<boolean>(true);
  const [selectedComponent, setSelectedComponent] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(false);
  const [draftLoading, setDraftLoading] = useState<boolean>(false);
  const [yamlLoading, setYamlLoading] = useState<boolean>(false);
  const [exportLoading, setExportLoading] = useState<boolean>(false);
  const [csvExportLoading, setCsvExportLoading] = useState<boolean>(false);
  const [importLoading, setImportLoading] = useState<boolean>(false);
  const [activeTechnologyIri, setActiveTechnologyIri] = useState<string | null>(null);
  const [draftConfigId, setDraftConfigId] = useState<string | null>(null);
  const [draftCount, setDraftCount] = useState<number>(0);
  const [addedTechnologyIris, setAddedTechnologyIris] = useState<string[]>([]);
  const [draftImportFile, setDraftImportFile] = useState<File | null>(null);
  const [draftImportInputKey, setDraftImportInputKey] = useState<number>(0);
  const [yamlPreview, setYamlPreview] = useState<string>("");
  const [isYamlPanelOpen, setIsYamlPanelOpen] = useState<boolean>(false);
  const [isPreviewOpen, setIsPreviewOpen] = useState<boolean>(false);
  const [draftMessage, setDraftMessage] = useState<string>("");
  const [filterMessage, setFilterMessage] = useState<string>("");
  const [filteredData, setFilteredData] = useState<FilteredData | null>(null);
  const [isAdvancedFiltersCollapsed, setIsAdvancedFiltersCollapsed] = useState<boolean>(true);
  const [useAttributeRangeFilters, setUseAttributeRangeFilters] = useState<boolean>(false);
  const [attributesLoading, setAttributesLoading] = useState<boolean>(false);
  const [locationsLoading, setLocationsLoading] = useState<boolean>(false);
  const [availableFilterAttributes, setAvailableFilterAttributes] = useState<string[]>([]);
  const [availableLocations, setAvailableLocations] = useState<LocationOption[]>([]);
  const [selectedLocationIris, setSelectedLocationIris] = useState<string[]>([]);
  const [availableCarriers, setAvailableCarriers] = useState<CarrierOption[]>([]);
  const [selectedCarrierIris, setSelectedCarrierIris] = useState<string[]>([]);
  const [carriersLoading, setCarriersLoading] = useState<boolean>(false);
  const [expandedInstanceKeys, setExpandedInstanceKeys] = useState<string[]>([]);
  const [componentSearch, setComponentSearch] = useState<string>("");
  const [instanceSearchTerm, setInstanceSearchTerm] = useState<string>("");
  const [isComponentListOpen, setIsComponentListOpen] = useState<boolean>(false);
  const [expandedComponentKeys, setExpandedComponentKeys] = useState<string[]>([]);
  const [highlightedComponentKey, setHighlightedComponentKey] = useState<string | null>(null);
  const [supportedTechnologyAssemblyComponents, setSupportedTechnologyAssemblyComponents] = useState<Set<string>>(
    new Set(["converter", "energyconverter"])
  );
  const [attributeRanges, setAttributeRanges] = useState<Record<string, AttributeRangeInput>>(
    {}
  );
  const [conversionParamsCache, setConversionParamsCache] = useState<Record<string, FlowRow[]>>({});
  const [embeddedCarbonCache, setEmbeddedCarbonCache] = useState<Record<string, EmbeddedCarbonRow[]>>({});
  const [isDeveloperMode, setIsDeveloperMode] = useState<boolean>(false);
  const componentSelectorRef = useRef<HTMLDivElement | null>(null);

  const selectedComponentNode =
    components.find((component) => component.component === selectedComponent) ?? null;
  const componentTree = buildComponentTree(components);
  const displayComponentTree = compressUnaryDisplayTree(componentTree, selectedComponent);
  const filteredComponentTree = filterComponentTree(displayComponentTree, componentSearch);
  const forceExpandComponentTree = componentSearch.trim().length > 0;
  const visibleComponentNodes = flattenVisibleComponentTree(
    filteredComponentTree,
    new Set(expandedComponentKeys),
    forceExpandComponentTree,
  );

  // Fetch component options on mount
  useEffect(() => {
    const fetchDataStatus = async () => {
      setDataStatusLoading(true);
      try {
        const response = await fetch(`${API_BASE_URL}/api/filter/data-status`);
        if (!response.ok) {
          throw new Error(`Request failed with status ${response.status}`);
        }

        const data = await response.json();
        setDataStatus({
          graphdb_repository:
            typeof data.graphdb_repository === "string" ? data.graphdb_repository : "MOTEL",
          graphdb_url: typeof data.graphdb_url === "string" ? data.graphdb_url : "",
          repository_size:
            typeof data.repository_size === "number" ? data.repository_size : Number(data.repository_size ?? 0),
          ttl_file: {
            path: typeof data.ttl_file?.path === "string" ? data.ttl_file.path : "",
            exists: Boolean(data.ttl_file?.exists),
            generated_at:
              typeof data.ttl_file?.generated_at === "string" ? data.ttl_file.generated_at : null,
            modified_at_unix:
              typeof data.ttl_file?.modified_at_unix === "number" ? data.ttl_file.modified_at_unix : null,
            size_bytes: typeof data.ttl_file?.size_bytes === "number" ? data.ttl_file.size_bytes : null,
          },
        });
      } catch (error) {
        console.error("Error fetching TTL data status:", error);
        setDataStatus(null);
      } finally {
        setDataStatusLoading(false);
      }
    };

    const fetchSupportedAssemblyComponents = async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/api/technologies/supported-components`);
        if (!response.ok) {
          throw new Error(`Request failed with status ${response.status}`);
        }

        const data = await response.json();
        const supportedComponentsRaw: unknown[] = Array.isArray(data.supported_components)
          ? data.supported_components
          : [];
        const normalizedSupportedComponents = supportedComponentsRaw
          .filter((component): component is string => typeof component === "string")
          .map((component) => component.trim().toLowerCase())
          .filter((component) => component.length > 0);

        if (normalizedSupportedComponents.length > 0) {
          setSupportedTechnologyAssemblyComponents(new Set(normalizedSupportedComponents));
        }
      } catch (error) {
        console.error("Error fetching supported technology assembly components:", error);
      }
    };

    const fetchComponents = async () => {
      try {
        const componentsResponse = await fetch(`${API_BASE_URL}/api/filter/components`);

        if (componentsResponse.ok) {
          const data = await componentsResponse.json();
          const componentsRaw: unknown[] = Array.isArray(data.components) ? data.components : [];
          setComponents(
            componentsRaw.flatMap((component): ComponentNode[] => {
              if (typeof component !== "object" || component === null) {
                return [];
              }

              const candidate = component as {
                component?: unknown;
                label?: unknown;
                parent_component?: unknown;
                is_leaf?: unknown;
                has_instances?: unknown;
                has_instance_descendant?: unknown;
              };
              if (typeof candidate.component !== "string" || candidate.component.trim().length === 0) {
                return [];
              }

              return [
                {
                  component: candidate.component,
                  label:
                    typeof candidate.label === "string" && candidate.label.trim().length > 0
                      ? candidate.label
                      : localName(candidate.component),
                  parent_component:
                    typeof candidate.parent_component === "string" &&
                    candidate.parent_component.trim().length > 0
                      ? candidate.parent_component
                      : null,
                  is_leaf:
                    candidate.is_leaf === undefined
                      ? true
                      : candidate.is_leaf === true || candidate.is_leaf === "true",
                  has_instances:
                    candidate.has_instances === true || candidate.has_instances === "true",
                  has_instance_descendant:
                    candidate.has_instance_descendant === true ||
                    candidate.has_instance_descendant === "true",
                },
              ];
            })
          );
        }
      } catch (error) {
        console.error("Error fetching components:", error);
      }
    };

    fetchDataStatus();
    fetchSupportedAssemblyComponents();
    fetchComponents();
  }, []);

  useEffect(() => {
    if (!selectedComponent) {
      setComponentSearch("");
      return;
    }

    setComponentSearch(selectedComponentNode?.label ?? localName(selectedComponent));
  }, [selectedComponent, selectedComponentNode]);

  useEffect(() => {
    if (!selectedComponent) {
      return;
    }

    setExpandedComponentKeys((previous) =>
      Array.from(new Set([...previous, ...getComponentAncestorPath(components, selectedComponent)]))
    );
  }, [components, selectedComponent]);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (!componentSelectorRef.current?.contains(event.target as Node)) {
        setIsComponentListOpen(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, []);

  useEffect(() => {
    if (!isComponentListOpen) {
      return;
    }

    const visibleComponentKeys = visibleComponentNodes.map((component) => component.component);
    if (visibleComponentKeys.length === 0) {
      setHighlightedComponentKey(null);
      return;
    }

    if (highlightedComponentKey && visibleComponentKeys.includes(highlightedComponentKey)) {
      return;
    }

    if (selectedComponent && visibleComponentKeys.includes(selectedComponent)) {
      setHighlightedComponentKey(selectedComponent);
      return;
    }

    setHighlightedComponentKey(visibleComponentKeys[0]);
  }, [highlightedComponentKey, isComponentListOpen, selectedComponent, visibleComponentNodes]);

  useEffect(() => {
    if (!selectedComponent) {
      setAvailableFilterAttributes([]);
      setAvailableLocations([]);
      setSelectedLocationIris([]);
      setAvailableCarriers([]);
      setSelectedCarrierIris([]);
      setLocationsLoading(false);
      setUseAttributeRangeFilters(false);
      setAttributeRanges({});
      return;
    }

    const fetchLocationsForComponent = async () => {
      setLocationsLoading(true);
      setSelectedLocationIris([]);
      try {
        const response = await fetch(
          `${API_BASE_URL}/api/filter/locations/${encodeURIComponent(selectedComponent)}`
        );

        if (!response.ok) {
          throw new Error(`Request failed with status ${response.status}`);
        }

        const data = await response.json();
        const locationsRaw: unknown[] = Array.isArray(data.locations) ? data.locations : [];
        setAvailableLocations(
          locationsRaw
            .filter(
              (location): location is LocationOption =>
                typeof location === "object" &&
                location !== null &&
                typeof (location as { iri?: unknown }).iri === "string" &&
                typeof (location as { label?: unknown }).label === "string"
            )
            .map((location) => ({ iri: location.iri, label: location.label }))
        );
      } catch (error) {
        console.error("Error fetching locations for component:", error);
        setAvailableLocations([]);
      } finally {
        setLocationsLoading(false);
      }
    };

    const fetchAttributes = async () => {
      setAttributesLoading(true);
      try {
        const response = await fetch(
          `${API_BASE_URL}/api/filter/attributes/${encodeURIComponent(selectedComponent)}`
        );

        if (!response.ok) {
          throw new Error(`Request failed with status ${response.status}`);
        }

        const data = await response.json();
        const discoveredAttributes: string[] = Array.isArray(data.attributes)
          ? data.attributes
          : [];

        setAvailableFilterAttributes(discoveredAttributes);
        setAttributeRanges(buildEmptyAttributeRanges(discoveredAttributes));
        setUseAttributeRangeFilters(false);
      } catch (error) {
        console.error("Error fetching attributes:", error);
        setAvailableFilterAttributes([]);
        setUseAttributeRangeFilters(false);
        setAttributeRanges({});
      } finally {
        setAttributesLoading(false);
      }
    };

    fetchLocationsForComponent();
    fetchAttributes();

    const fetchCarriersForComponent = async () => {
      setCarriersLoading(true);
      setSelectedCarrierIris([]);
      try {
        const response = await fetch(
          `${API_BASE_URL}/api/filter/carriers/${encodeURIComponent(selectedComponent)}`
        );
        if (!response.ok) {
          throw new Error(`Request failed with status ${response.status}`);
        }
        const data = await response.json();
        const carriersRaw: unknown[] = Array.isArray(data.carriers) ? data.carriers : [];
        setAvailableCarriers(
          carriersRaw
            .filter(
              (c): c is CarrierOption =>
                typeof c === "object" &&
                c !== null &&
                typeof (c as { iri?: unknown }).iri === "string" &&
                typeof (c as { label?: unknown }).label === "string"
            )
            .map((c) => ({ iri: c.iri, label: c.label }))
        );
      } catch (error) {
        console.error("Error fetching carriers for component:", error);
        setAvailableCarriers([]);
      } finally {
        setCarriersLoading(false);
      }
    };

    fetchCarriersForComponent();
  }, [selectedComponent]);

  const showLocationFilter = selectedComponent.length > 0 && availableLocations.length > 0;
  const showCarrierFilter = selectedComponent.length > 0 && availableCarriers.length > 0;

  useEffect(() => {
    setExpandedInstanceKeys([]);
  }, [filteredData]);

  const handleComponentSelection = (component: ComponentNode) => {
    setSelectedComponent(component.component);
    setComponentSearch(component.label);
    setExpandedComponentKeys((previous) =>
      Array.from(new Set([...previous, ...getComponentAncestorPath(components, component.component)]))
    );
    setHighlightedComponentKey(component.component);
    setIsComponentListOpen(false);
  };

  const toggleComponentBranch = (componentId: string) => {
    setExpandedComponentKeys((previous) =>
      previous.includes(componentId)
        ? previous.filter((key) => key !== componentId)
        : [...previous, componentId]
    );
  };

  const handleComponentInputChange = (value: string) => {
    setComponentSearch(value);
    setIsComponentListOpen(true);

    if (!value.trim()) {
      setSelectedComponent("");
      setHighlightedComponentKey(null);
      return;
    }

    if (selectedComponentNode && value !== selectedComponentNode.label) {
      setSelectedComponent("");
    }

    setHighlightedComponentKey(null);
  };

  const moveHighlightedComponent = (direction: 1 | -1) => {
    if (visibleComponentNodes.length === 0) {
      return;
    }

    const currentIndex = visibleComponentNodes.findIndex(
      (component) => component.component === highlightedComponentKey
    );
    const nextIndex =
      currentIndex === -1
        ? direction === 1
          ? 0
          : visibleComponentNodes.length - 1
        : (currentIndex + direction + visibleComponentNodes.length) % visibleComponentNodes.length;

    setHighlightedComponentKey(visibleComponentNodes[nextIndex].component);
  };

  const handleComponentInputKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (!isComponentListOpen) {
        setIsComponentListOpen(true);
      }
      moveHighlightedComponent(1);
      return;
    }

    if (event.key === "ArrowUp") {
      event.preventDefault();
      if (!isComponentListOpen) {
        setIsComponentListOpen(true);
      }
      moveHighlightedComponent(-1);
      return;
    }

    if (event.key === "ArrowRight") {
      const highlightedComponent = visibleComponentNodes.find(
        (component) => component.component === highlightedComponentKey
      );
      if (!highlightedComponent || highlightedComponent.children.length === 0) {
        return;
      }

      event.preventDefault();
      setExpandedComponentKeys((previous) =>
        previous.includes(highlightedComponent.component)
          ? previous
          : [...previous, highlightedComponent.component]
      );
      setIsComponentListOpen(true);
      return;
    }

    if (event.key === "ArrowLeft") {
      const highlightedComponent = visibleComponentNodes.find(
        (component) => component.component === highlightedComponentKey
      );
      if (!highlightedComponent) {
        return;
      }

      event.preventDefault();
      if (expandedComponentKeys.includes(highlightedComponent.component)) {
        setExpandedComponentKeys((previous) =>
          previous.filter((key) => key !== highlightedComponent.component)
        );
        return;
      }

      if (highlightedComponent.parentComponent) {
        setHighlightedComponentKey(highlightedComponent.parentComponent);
      }
      return;
    }

    if (event.key === "Enter") {
      event.preventDefault();
      if (!isComponentListOpen) {
        setIsComponentListOpen(true);
        return;
      }

      const highlightedComponent = visibleComponentNodes.find(
        (component) => component.component === highlightedComponentKey
      );
      if (!highlightedComponent) {
        return;
      }

      handleComponentSelection(highlightedComponent);
      return;
    }

    if (event.key === "Escape") {
      event.preventDefault();
      setIsComponentListOpen(false);
    }
  };

  const handleFilter = async (
    options?: {
      attributeRangesOverride?: Record<string, AttributeRangeInput>;
      useAttributeRangeFiltersOverride?: boolean;
      locationIrisOverride?: string[];
      carrierIrisOverride?: string[];
    }
  ) => {
    if (!selectedComponent) return;

    setLoading(true);
    setFilteredData(null);
    setFilterMessage("");

    const attributeRangePayload: Record<string, { lower?: number; upper?: number }> = {};
    const shouldUseAttributeRangeFilters =
      options?.useAttributeRangeFiltersOverride ?? useAttributeRangeFilters;
    const activeAttributeRanges = options?.attributeRangesOverride ?? attributeRanges;
    const activeLocationIris = options?.locationIrisOverride ?? selectedLocationIris;
    const activeCarrierIris = options?.carrierIrisOverride ?? selectedCarrierIris;

    if (shouldUseAttributeRangeFilters) {
      for (const attribute of availableFilterAttributes) {
        const draftRange = activeAttributeRanges[attribute];
        if (!draftRange) {
          continue;
        }
        const hasLower = draftRange.lower.trim().length > 0;
        const hasUpper = draftRange.upper.trim().length > 0;

        if (!hasLower && !hasUpper) {
          continue;
        }

        const parsedLower = hasLower ? Number(draftRange.lower) : undefined;
        const parsedUpper = hasUpper ? Number(draftRange.upper) : undefined;

        if ((hasLower && Number.isNaN(parsedLower)) || (hasUpper && Number.isNaN(parsedUpper))) {
          setFilterMessage(`Invalid numeric range for ${attribute}`);
          setLoading(false);
          return;
        }

        if (parsedLower !== undefined && parsedUpper !== undefined && parsedLower > parsedUpper) {
          setFilterMessage(
            `Lower value must be less than or equal to upper value for ${attribute}`
          );
          setLoading(false);
          return;
        }

        attributeRangePayload[attribute] = {
          ...(parsedLower !== undefined ? { lower: parsedLower } : {}),
          ...(parsedUpper !== undefined ? { upper: parsedUpper } : {}),
        };
      }
    }

    try {
      const response = await fetch(
        `${API_BASE_URL}/api/filter/instances`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            type_label: selectedComponent,
            attribute_ranges: attributeRangePayload,
            ...(activeLocationIris.length > 0 ? { location_iris: activeLocationIris } : {}),
            ...(activeCarrierIris.length > 0 ? { carrier_iris: activeCarrierIris } : {}),
          }),
        }
      );

      if (!response.ok) {
        throw new Error(`Request failed with status ${response.status}`);
      }

      const data = await response.json();
      const instances: InstanceRow[] = data.instances ?? [];

      setFilteredData({
        component: selectedComponent,
        instances,
      });
      setDraftMessage("");
    } catch (error) {
      console.error("Error filtering data:", error);
      setFilterMessage("Failed to fetch instances");
      setFilteredData({
        component: selectedComponent,
        instances: [],
        error: "Failed to fetch instances",
      });
    } finally {
      setLoading(false);
    }
  };

  const handleClearAllFilters = () => {
    setSelectedLocationIris([]);
    setUseAttributeRangeFilters(false);
    setAttributeRanges(buildEmptyAttributeRanges(availableFilterAttributes));
    setFilterMessage("");
    setInstanceSearchTerm("");
  };

  const handleClearRangeFilters = () => {
    const clearedRanges = buildEmptyAttributeRanges(availableFilterAttributes);
    setAttributeRanges(clearedRanges);
    setFilterMessage("");
    void handleFilter({
      attributeRangesOverride: clearedRanges,
      useAttributeRangeFiltersOverride: true,
    });
  };

  const handleClearEverything = () => {
    setSelectedComponent("");
    setComponentSearch("");
    setHighlightedComponentKey(null);
    setIsComponentListOpen(false);
    setFilteredData(null);
    setIsAdvancedFiltersCollapsed(true);
    handleClearAllFilters();
  };

  const getTechnologyIri = (row: InstanceRow): string | null => {
    const techIri = row.tech;
    if (techIri && techIri.trim().length > 0) return techIri;

    const instanceIri = row.instance;
    if (instanceIri && instanceIri.trim().length > 0) return instanceIri;

    return null;
  };

  const isTechnologyAlreadyInDraft = (technologyIdentifier: string): boolean => {
    const normalizedIdentifier = normalizeTechnologyIdentifier(technologyIdentifier);
    return addedTechnologyIris.some(
      (value) => normalizeTechnologyIdentifier(value) === normalizedIdentifier
    );
  };

  const ensureDraft = async (): Promise<string> => {
    if (draftConfigId) return draftConfigId;

    const response = await fetch(`${API_BASE_URL}/api/technologies/drafts`, {
      method: "POST",
    });

    if (!response.ok) {
      throw new Error(`Failed to create draft (${response.status})`);
    }

    const data = await response.json();
    const newConfigId = data.config_id as string;
    setDraftConfigId(newConfigId);
    setDraftCount(0);
    setAddedTechnologyIris([]);
    return newConfigId;
  };

  const isSelectedComponentSupportedForAssembly = (): boolean =>
    supportsTechnologyAssembly(
      filteredData?.component ?? selectedComponent,
      supportedTechnologyAssemblyComponents
    );

  const handleDraftImportFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    const selectedFile = event.target.files?.[0] ?? null;
    if (!selectedFile) {
      setDraftImportFile(null);
      return;
    }

    const normalizedName = selectedFile.name.toLowerCase();
    if (!normalizedName.endsWith(".yaml") && !normalizedName.endsWith(".yml")) {
      setDraftImportFile(null);
      setDraftMessage("Please choose a .yaml or .yml file.");
      event.target.value = "";
      return;
    }

    setDraftImportFile(selectedFile);
    setDraftMessage("");
  };

  const handleImportDraftFile = async () => {
    if (!draftImportFile) {
      setDraftMessage("Choose a .yaml or .yml file first.");
      return;
    }

    setImportLoading(true);
    setDraftMessage("");

    try {
      const formData = new FormData();
      formData.append("file", draftImportFile);

      const response = await fetch(`${API_BASE_URL}/api/technologies/drafts/import`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const contentType = response.headers.get("content-type") || "";
        if (contentType.includes("application/json")) {
          const errorPayload = await response.json();
          const detail = errorPayload?.detail;

          if (typeof detail === "string") {
            throw new Error(detail);
          }

          const detailMessage = detail?.message;
          if (typeof detailMessage === "string") {
            throw new Error(detailMessage);
          }
        }

        throw new Error(`Failed to import draft (${response.status})`);
      }

      const data = await response.json();
      const newConfigId = data.config_id as string;
      const importedTechs: unknown[] = Array.isArray(data?.techs_config?.techs)
        ? data.techs_config.techs
        : [];

      const syncedTechnologyIris = importedTechs
        .map((tech): string | null => {
          if (typeof tech === "string") {
            return tech;
          }

          if (typeof tech === "object" && tech !== null) {
            const candidate = (
              tech as {
                technology_iri?: unknown;
                iri?: unknown;
                tech?: unknown;
                tech_id?: unknown;
              }
            ).technology_iri ??
              (tech as { iri?: unknown }).iri ??
              (tech as { tech?: unknown }).tech ??
              (tech as { tech_id?: unknown }).tech_id;

            return typeof candidate === "string" ? candidate : null;
          }

          return null;
        })
        .filter((iri): iri is string => iri !== null && iri.trim().length > 0);

      setDraftConfigId(newConfigId);
      setDraftCount(importedTechs.length);
      setAddedTechnologyIris(Array.from(new Set(syncedTechnologyIris)));
      setYamlPreview("");
      setIsPreviewOpen(false);
      setDraftImportFile(null);
      setDraftImportInputKey((previous) => previous + 1);
      setDraftMessage(`Imported ${importedTechs.length} technologies into draft ${newConfigId}.`);
    } catch (error) {
      setDraftMessage(error instanceof Error ? error.message : "Failed to import draft file");
    } finally {
      setImportLoading(false);
    }
  };

  const handleAddTechnology = async (row: InstanceRow) => {
    if (!isSelectedComponentSupportedForAssembly()) {
      setDraftMessage("Add technology is only available for supported component types.");
      return;
    }

    const technologyIri = getTechnologyIri(row);
    if (!technologyIri) {
      setDraftMessage("Selected row does not contain a technology IRI.");
      return;
    }

    if (isTechnologyAlreadyInDraft(technologyIri)) {
      setDraftMessage("Technology already added to draft.");
      return;
    }

    setDraftLoading(true);
    setActiveTechnologyIri(technologyIri);
    setDraftMessage("");

    try {
      const configId = await ensureDraft();
      const response = await fetch(
        `${API_BASE_URL}/api/technologies/drafts/${encodeURIComponent(configId)}/append-technology`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            config_id: configId,
            technology_iri: technologyIri,
          }),
        }
      );

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || `Failed to append technology (${response.status})`);
      }

      const data = await response.json();
      const techs = data?.techs_config?.techs;
      if (Array.isArray(techs)) {
        setDraftCount(techs.length);

        const syncedTechnologyIris = techs
          .map((tech): string | null => {
            if (typeof tech === "string") {
              return tech;
            }

            if (typeof tech === "object" && tech !== null) {
              const candidate = (
                tech as {
                  technology_iri?: unknown;
                  iri?: unknown;
                  tech?: unknown;
                  tech_id?: unknown;
                }
              ).technology_iri ??
                (tech as { iri?: unknown }).iri ??
                (tech as { tech?: unknown }).tech ??
                (tech as { tech_id?: unknown }).tech_id;

              return typeof candidate === "string" ? candidate : null;
            }

            return null;
          })
          .filter((iri): iri is string => iri !== null && iri.trim().length > 0);

        if (syncedTechnologyIris.length > 0) {
          setAddedTechnologyIris(Array.from(new Set(syncedTechnologyIris)));
        } else {
          setAddedTechnologyIris((previous) => {
            const isPresent = previous.some(
              (value) =>
                normalizeTechnologyIdentifier(value) ===
                normalizeTechnologyIdentifier(technologyIri)
            );
            return isPresent ? previous : [...previous, technologyIri];
          });
        }
      } else {
        setDraftCount((previous) => previous + 1);
        setAddedTechnologyIris((previous) => {
          const isPresent = previous.some(
            (value) =>
              normalizeTechnologyIdentifier(value) ===
              normalizeTechnologyIdentifier(technologyIri)
          );
          return isPresent ? previous : [...previous, technologyIri];
        });
      }
      setDraftMessage("Technology added to draft.");
    } catch (error) {
      setDraftMessage(error instanceof Error ? error.message : "Failed to add technology");
    } finally {
      setDraftLoading(false);
      setActiveTechnologyIri(null);
    }
  };

  const handleRemoveTechnology = async (row: InstanceRow) => {
    if (!isSelectedComponentSupportedForAssembly()) {
      setDraftMessage("Remove technology is only available for supported component types.");
      return;
    }

    const technologyIri = getTechnologyIri(row);
    if (!technologyIri) {
      setDraftMessage("Selected row does not contain a technology IRI.");
      return;
    }

    if (!draftConfigId) {
      setDraftMessage("Create a draft by adding a technology first.");
      return;
    }

    if (!isTechnologyAlreadyInDraft(technologyIri)) {
      setDraftMessage("Technology is not currently in the draft.");
      return;
    }

    setDraftLoading(true);
    setActiveTechnologyIri(technologyIri);
    setDraftMessage("");

    try {
      const response = await fetch(
        `${API_BASE_URL}/api/technologies/drafts/${encodeURIComponent(draftConfigId)}/remove-technology`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            config_id: draftConfigId,
            technology_iri: technologyIri,
          }),
        }
      );

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || `Failed to remove technology (${response.status})`);
      }

      const data = await response.json();
      const techs = data?.techs_config?.techs;

      if (Array.isArray(techs)) {
        setDraftCount(techs.length);
      } else {
        setDraftCount((previous) => Math.max(previous - 1, 0));
      }

      setAddedTechnologyIris((previous) =>
        previous.filter(
          (iri) =>
            normalizeTechnologyIdentifier(iri) !==
            normalizeTechnologyIdentifier(technologyIri)
        )
      );
      setDraftMessage("Technology removed from draft.");
    } catch (error) {
      setDraftMessage(error instanceof Error ? error.message : "Failed to remove technology");
    } finally {
      setDraftLoading(false);
      setActiveTechnologyIri(null);
    }
  };

  const handlePreviewYaml = async () => {
    if (!draftConfigId) {
      setDraftMessage("Create a draft by adding a technology first.");
      return;
    }

    setYamlLoading(true);
    setDraftMessage("");

    try {
      const response = await fetch(
        `${API_BASE_URL}/api/technologies/drafts/${encodeURIComponent(draftConfigId)}/yaml`
      );

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || `Failed to fetch YAML preview (${response.status})`);
      }

      const data = await response.json();
      setYamlPreview(data.yaml || "");
      setIsPreviewOpen(true);
    } catch (error) {
      setDraftMessage(error instanceof Error ? error.message : "Failed to preview YAML");
    } finally {
      setYamlLoading(false);
    }
  };

  const handleExportDraft = async () => {
    if (!draftConfigId) {
      setDraftMessage("Create a draft by adding a technology first.");
      return;
    }

    setExportLoading(true);
    setDraftMessage("");

    try {
      const response = await fetch(
        `${API_BASE_URL}/api/technologies/drafts/${encodeURIComponent(draftConfigId)}/export`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
        }
      );

      if (!response.ok) {
        const contentType = response.headers.get("content-type") || "";
        if (contentType.includes("application/json")) {
          const error = await response.json();
          throw new Error(error.detail || `Failed to export draft (${response.status})`);
        }

        const errorText = await response.text();
        throw new Error(errorText || `Failed to export draft (${response.status})`);
      }

      const blob = await response.blob();
      const filenameFromHeader = getFilenameFromContentDisposition(
        response.headers.get("Content-Disposition")
      );
      const filename =
        filenameFromHeader ||
        `techs-${draftConfigId.replace(/[^a-zA-Z0-9_-]/g, "_")}.yaml`;

      const url = window.URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.URL.revokeObjectURL(url);

      setDraftMessage(`Draft downloaded as ${filename}`);
    } catch (error) {
      setDraftMessage(error instanceof Error ? error.message : "Failed to export draft");
    } finally {
      setExportLoading(false);
    }
  };

  const handleExportDraftCsv = async () => {
    if (!draftConfigId) {
      setDraftMessage("Create a draft by adding a technology first.");
      return;
    }

    setCsvExportLoading(true);
    setDraftMessage("");

    try {
      const response = await fetch(
        `${API_BASE_URL}/api/technologies/drafts/${encodeURIComponent(draftConfigId)}/export-csv`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
        }
      );

      if (!response.ok) {
        const contentType = response.headers.get("content-type") || "";
        if (contentType.includes("application/json")) {
          const error = await response.json();
          throw new Error(error.detail || `Failed to export CSV draft (${response.status})`);
        }

        const errorText = await response.text();
        throw new Error(errorText || `Failed to export CSV draft (${response.status})`);
      }

      const blob = await response.blob();
      const filenameFromHeader = getFilenameFromContentDisposition(
        response.headers.get("Content-Disposition")
      );
      const filename =
        filenameFromHeader ||
        `techs-${draftConfigId.replace(/[^a-zA-Z0-9_-]/g, "_")}.csv`;

      const url = window.URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.URL.revokeObjectURL(url);

      setDraftMessage(`Draft downloaded as ${filename}`);
    } catch (error) {
      setDraftMessage(error instanceof Error ? error.message : "Failed to export CSV draft");
    } finally {
      setCsvExportLoading(false);
    }
  };

  const instanceBindings = filteredData?.instances ?? [];
  const canAddTechnology = isSelectedComponentSupportedForAssembly();
  const preferredAttributeColumns = [
    "att",
    "att_category",
    "att_val",
    "att_unit",
    "att_currency",
  ];
  const groupedSourceColumnKey = "__source";
  const referenceSourceColumns = ["ref_label", "ref_type", "ref_url"] as const;
  const hiddenColumns = new Set<string>([...["ref_label", "ref_type", "ref_url"], "att_label", "unit_label", "description"]);
  const referenceSourceColumnSet = new Set<string>(referenceSourceColumns);
  const discoveredAttributeColumns = Array.from(
    new Set(
      instanceBindings.flatMap((row) =>
        Object.keys(row).filter((column) => column !== "tech" && column !== "instance")
      )
    )
  );
  const hasReferenceSourceColumns = referenceSourceColumns.some((column) =>
    discoveredAttributeColumns.includes(column)
  );
  const attributeColumns = [
    ...preferredAttributeColumns.filter(
      (column) =>
        discoveredAttributeColumns.includes(column) && !hiddenColumns.has(column)
    ),
    ...discoveredAttributeColumns.filter(
      (column) =>
        !preferredAttributeColumns.includes(column) && !hiddenColumns.has(column)
    ),
  ];
  if (hasReferenceSourceColumns) {
    attributeColumns.push(groupedSourceColumnKey);
  }
  const localNameColumns = isDeveloperMode
    ? new Set<string>()
    : new Set(["att", "att_category", "att_unit", "att_currency", "ref_type"]);
  const instanceGroupMap = new Map<string, InstanceGroup>();
  instanceBindings.forEach((row, rowIndex) => {
    const technologyIri = getTechnologyIri(row);
    const key = technologyIri ?? `unknown-${rowIndex}`;
    const existingGroup = instanceGroupMap.get(key);

    if (existingGroup) {
      existingGroup.rows.push(row);
      return;
    }

    instanceGroupMap.set(key, {
      key,
      technologyIri,
      representativeRow: row,
      rows: [row],
    });
  });
  const instanceGroups = Array.from(instanceGroupMap.values());
  const normalizedInstanceSearch = instanceSearchTerm.trim().toLowerCase();
  const filteredInstanceGroups = normalizedInstanceSearch
    ? instanceGroups.filter((group) => {
        if (!group.technologyIri) {
          return false;
        }
        return localName(group.technologyIri)
          .toLowerCase()
          .includes(normalizedInstanceSearch);
      })
    : instanceGroups;

  const toggleInstanceExpansion = (groupKey: string, technologyIri: string | null) => {
    setExpandedInstanceKeys((previous) => {
      const isCurrentlyExpanded = previous.includes(groupKey);
      if (!isCurrentlyExpanded && technologyIri) {
        if (!(groupKey in conversionParamsCache)) {
          fetch(`${API_BASE_URL}/api/filter/conversion-params/${encodeURIComponent(technologyIri)}`)
            .then((res) => res.json())
            .then((data) => {
              const rows: FlowRow[] = Array.isArray(data.flows) ? data.flows : [];
              setConversionParamsCache((prev) => ({ ...prev, [groupKey]: rows }));
            })
            .catch(() => {
              setConversionParamsCache((prev) => ({ ...prev, [groupKey]: [] }));
            });
        }
        if (!(groupKey in embeddedCarbonCache)) {
          fetch(`${API_BASE_URL}/api/filter/embedded-carbon/${encodeURIComponent(technologyIri)}`)
            .then((res) => res.json())
            .then((data) => {
              const rows: EmbeddedCarbonRow[] = Array.isArray(data.embedded_carbon) ? data.embedded_carbon : [];
              setEmbeddedCarbonCache((prev) => ({ ...prev, [groupKey]: rows }));
            })
            .catch(() => {
              setEmbeddedCarbonCache((prev) => ({ ...prev, [groupKey]: [] }));
            });
        }
      }
      return isCurrentlyExpanded
        ? previous.filter((key) => key !== groupKey)
        : [...previous, groupKey];
    });
  };

  return (
    <main className="min-h-screen bg-zinc-50 dark:bg-black p-8">
      <div className="max-w-6xl mx-auto">
        <h1 className="mb-4 text-3xl font-bold tracking-tight text-black dark:text-zinc-50">
          MOTEL tool
        </h1>
        <div className="mb-4 rounded-md border border-zinc-200 bg-white px-4 py-3 text-sm text-zinc-700 shadow-sm dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200">
          {dataStatusLoading ? (
            <p>TTL status: loading backend/GraphDB data…</p>
          ) : dataStatus ? (
            <p>
              TTL status: loaded from repository <span className="font-medium">{dataStatus.graphdb_repository}</span>
              {" · "}
              TTL file created: <span className="font-medium">{dataStatus.ttl_file.generated_at ?? "unknown"}</span>
              {" · "}
              TTL file seen by backend:{" "}
              <span className="font-medium">
                {dataStatus.ttl_file.modified_at_unix
                  ? new Date(dataStatus.ttl_file.modified_at_unix * 1000).toLocaleString()
                  : "unknown"}
              </span>
              {" · "}
              Repository size: <span className="font-medium">{dataStatus.repository_size.toLocaleString()}</span>
            </p>
          ) : (
            <p>TTL status: unavailable</p>
          )}
        </div>
        {/* Filter Section */}
        <div className="bg-white dark:bg-zinc-900 rounded-lg shadow-sm p-6 mb-6">
          <h1 className="text-2xl font-semibold text-black dark:text-zinc-50 mb-6">
            Component Filter
          </h1>
          
          <div className="flex flex-col gap-2">
            <label className="text-sm font-medium text-black dark:text-zinc-50">
              Component Type
            </label>
            <div className="flex items-center gap-2">
              <div className="relative flex-1" ref={componentSelectorRef}>
                <input
                  type="text"
                  value={componentSearch}
                  onChange={(e) => handleComponentInputChange(e.target.value)}
                  onClick={() => setIsComponentListOpen(true)}
                  onFocus={() => setIsComponentListOpen(true)}
                  onKeyDown={handleComponentInputKeyDown}
                  placeholder="Search component types..."
                  role="combobox"
                  aria-autocomplete="list"
                  aria-expanded={isComponentListOpen}
                  aria-controls="component-type-list"
                  className="w-full px-4 py-2 pr-20 border border-zinc-300 rounded-md bg-white text-black dark:bg-zinc-800 dark:border-zinc-700 dark:text-zinc-50 focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                {componentSearch ? (
                  <button
                    type="button"
                    onClick={() => {
                      setComponentSearch("");
                      setSelectedComponent("");
                      setHighlightedComponentKey(null);
                      setIsComponentListOpen(false);
                    }}
                    className="absolute right-2 top-1/2 -translate-y-1/2 rounded-md px-2 py-1 text-xs font-medium text-zinc-600 transition-colors hover:bg-zinc-100 hover:text-zinc-900 dark:text-zinc-300 dark:hover:bg-zinc-700 dark:hover:text-zinc-50"
                  >
                    Clear
                  </button>
                ) : null}

                {isComponentListOpen ? (
                  <div
                    id="component-type-list"
                    className="absolute z-20 mt-1 max-h-80 w-full overflow-auto rounded-md border border-zinc-300 bg-white p-1 shadow-lg dark:border-zinc-700 dark:bg-zinc-900"
                  >
                    {visibleComponentNodes.length > 0 ? (
                      visibleComponentNodes.map((component) => {
                        const isExpanded =
                          forceExpandComponentTree || expandedComponentKeys.includes(component.component);
                        const isHighlighted = highlightedComponentKey === component.component;
                        const isSelected = selectedComponent === component.component;

                        return (
                          <div
                            key={component.component}
                            className="py-0.5"
                            style={{ paddingLeft: `${component.depth * 0.875}rem` }}
                          >
                            <div
                              className={[
                                "flex items-center gap-2 rounded-md px-2 py-2 text-sm",
                                isHighlighted
                                  ? "bg-blue-100 text-blue-950 dark:bg-blue-950/50 dark:text-blue-100"
                                  : isSelected
                                    ? "bg-zinc-200 text-zinc-950 dark:bg-zinc-700 dark:text-zinc-50"
                                    : "text-black dark:text-zinc-50",
                              ].join(" ")}
                              onMouseEnter={() => setHighlightedComponentKey(component.component)}
                            >
                              {component.children.length > 0 ? (
                                <button
                                  type="button"
                                  onClick={() => toggleComponentBranch(component.component)}
                                  className="flex h-5 w-5 flex-none items-center justify-center rounded border border-zinc-300 text-xs text-zinc-600 transition-colors hover:bg-zinc-100 hover:text-zinc-900 dark:border-zinc-600 dark:text-zinc-300 dark:hover:bg-zinc-800 dark:hover:text-zinc-50"
                                  aria-label={isExpanded ? "Collapse branch" : "Expand branch"}
                                >
                                  {isExpanded ? "-" : "+"}
                                </button>
                              ) : (
                                <span className="block h-5 w-5 flex-none" />
                              )}

                              <button
                                type="button"
                                onClick={() => handleComponentSelection(component)}
                                className={[
                                  "min-w-0 flex-1 truncate text-left",
                                  component.children.length > 0
                                    ? "cursor-pointer font-medium text-zinc-600 dark:text-zinc-300"
                                    : "cursor-pointer",
                                ].join(" ")}
                              >
                                {component.label}
                              </button>
                            </div>
                          </div>
                        );
                      })
                    ) : (
                      <p className="px-3 py-2 text-sm text-zinc-600 dark:text-zinc-400">
                        No component types match your search.
                      </p>
                    )}
                  </div>
                ) : null}
              </div>
              <button
                onClick={() => { void handleFilter(); }}
                disabled={loading || !selectedComponent}
                className="h-10 px-6 rounded-md bg-blue-600 text-white font-medium transition-colors hover:bg-blue-700 disabled:bg-zinc-400 disabled:cursor-not-allowed whitespace-nowrap"
              >
                {loading ? "Loading..." : "Apply Filter"}
              </button>
              <button
                type="button"
                onClick={handleClearEverything}
                disabled={loading}
                className="h-10 px-6 rounded-md border border-zinc-300 bg-orange-600 text-white font-medium transition-colors hover:bg-orange-700 disabled:bg-zinc-400 disabled:cursor-not-allowed dark:border-zinc-700 whitespace-nowrap"
              >
                Clear All
              </button>
            </div>
            <p className="text-xs text-zinc-600 dark:text-zinc-400">
              Search the hierarchy or browse by expanding branches by clicking (+). Parent and leaf component types can both be selected.
            </p>
          </div>

          <div className={`relative mt-5 border border-zinc-200 dark:border-zinc-700 rounded-md p-4 bg-zinc-50 dark:bg-zinc-800/40${!isAdvancedFiltersCollapsed ? " pb-16" : ""}`}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm font-medium text-black dark:text-zinc-50">
                Additional Filters
              </p>
              <button
                type="button"
                onClick={() => setIsAdvancedFiltersCollapsed((previous) => !previous)}
                className="h-8 px-3 rounded-md bg-zinc-200 text-zinc-900 text-xs font-medium transition-colors hover:bg-zinc-300 dark:bg-zinc-700 dark:text-zinc-100 dark:hover:bg-zinc-600"
              >
                {isAdvancedFiltersCollapsed ? "Show" : "Hide"}
              </button>
            </div>

            {!isAdvancedFiltersCollapsed ? (
              <>
                {locationsLoading && selectedComponent ? (
                  <p className="mt-4 mb-4 text-xs text-zinc-600 dark:text-zinc-400">
                    Loading location options for selected component...
                  </p>
                ) : null}

                {showLocationFilter ? (
                  <div className="mt-4 mb-4 flex flex-col gap-2">
                    <div className="flex items-center justify-between">
                      <label className="text-sm font-medium text-black dark:text-zinc-50">
                        Location (optional)
                      </label>
                      {selectedLocationIris.length > 0 ? (
                        <button
                          type="button"
                          onClick={() => setSelectedLocationIris([])}
                          className="text-xs text-zinc-500 hover:text-zinc-800 dark:text-zinc-400 dark:hover:text-zinc-200 underline"
                        >
                          Clear selection
                        </button>
                      ) : null}
                    </div>
                    <details className="group rounded-md border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-800">
                      <summary className="list-none cursor-pointer select-none px-3 py-2 text-sm text-black dark:text-zinc-50 [&::-webkit-details-marker]:hidden">
                        <span className="flex items-center justify-between gap-2">
                          <span>
                            {selectedLocationIris.length > 0
                              ? `${selectedLocationIris.length} location(s) selected`
                              : "All Locations"}
                          </span>
                          <span className="text-zinc-500 transition-transform group-open:rotate-180" aria-hidden="true">
                            <svg className="h-4 w-4" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
                              <path d="M6 8L10 12L14 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                            </svg>
                          </span>
                        </span>
                      </summary>
                      <div className="border-t border-zinc-200 dark:border-zinc-700 px-3 py-2 max-h-40 overflow-y-auto flex flex-col gap-1">
                        {availableLocations.map((location) => (
                          <label key={location.iri} className="inline-flex items-center gap-2 text-sm text-black dark:text-zinc-50 cursor-pointer">
                            <input
                              type="checkbox"
                              checked={selectedLocationIris.includes(location.iri)}
                              onChange={(e) => {
                                setSelectedLocationIris((previous) =>
                                  e.target.checked
                                    ? [...previous, location.iri]
                                    : previous.filter((iri) => iri !== location.iri)
                                );
                              }}
                              className="h-4 w-4 rounded border-zinc-300 text-blue-600 focus:ring-blue-500"
                            />
                            {location.label}
                          </label>
                        ))}
                      </div>
                    </details>
                    <p className="text-xs text-zinc-600 dark:text-zinc-400">
                      Select one or more locations to narrow results. Leave all unchecked to include all.
                    </p>
                  </div>
                ) : null}

                {carriersLoading && selectedComponent ? (
                  <p className="mt-4 mb-4 text-xs text-zinc-600 dark:text-zinc-400">
                    Loading energy / mass carrier options for selected component...
                  </p>
                ) : null}

                {showCarrierFilter ? (
                  <div className="mt-4 mb-4 flex flex-col gap-2">
                    <div className="flex items-center justify-between">
                      <label className="text-sm font-medium text-black dark:text-zinc-50">
                        Energy / Mass Carrier (optional)
                      </label>
                      {selectedCarrierIris.length > 0 ? (
                        <button
                          type="button"
                          onClick={() => setSelectedCarrierIris([])}
                          className="text-xs text-zinc-500 hover:text-zinc-800 dark:text-zinc-400 dark:hover:text-zinc-200 underline"
                        >
                          Clear selection
                        </button>
                      ) : null}
                    </div>
                    <details className="group rounded-md border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-800">
                      <summary className="list-none cursor-pointer select-none px-3 py-2 text-sm text-black dark:text-zinc-50 [&::-webkit-details-marker]:hidden">
                        <span className="flex items-center justify-between gap-2">
                          <span>
                            {selectedCarrierIris.length > 0
                              ? `${selectedCarrierIris.length} carrier(s) selected`
                              : "All Carriers"}
                          </span>
                          <span className="text-zinc-500 transition-transform group-open:rotate-180" aria-hidden="true">
                            <svg className="h-4 w-4" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
                              <path d="M6 8L10 12L14 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                            </svg>
                          </span>
                        </span>
                      </summary>
                      <div className="border-t border-zinc-200 dark:border-zinc-700 px-3 py-2 max-h-40 overflow-y-auto flex flex-col gap-1">
                        {availableCarriers.map((carrier) => (
                          <label key={carrier.iri} className="inline-flex items-center gap-2 text-sm text-black dark:text-zinc-50 cursor-pointer">
                            <input
                              type="checkbox"
                              checked={selectedCarrierIris.includes(carrier.iri)}
                              onChange={(e) => {
                                setSelectedCarrierIris((previous) =>
                                  e.target.checked
                                    ? [...previous, carrier.iri]
                                    : previous.filter((iri) => iri !== carrier.iri)
                                );
                              }}
                              className="h-4 w-4 rounded border-zinc-300 text-blue-600 focus:ring-blue-500"
                            />
                            {carrier.label}
                          </label>
                        ))}
                      </div>
                    </details>
                    <p className="text-xs text-zinc-600 dark:text-zinc-400">
                      Select one or more carriers to show only instances connected to those flows. Leave all unchecked to include all.
                    </p>
                  </div>
                ) : null}

                <div className="flex flex-wrap items-center gap-2">
                  <label className="inline-flex items-center gap-2 text-sm font-medium text-black dark:text-zinc-50">
                    <input
                      type="checkbox"
                      checked={useAttributeRangeFilters}
                      onChange={(e) => setUseAttributeRangeFilters(e.target.checked)}
                      disabled={attributesLoading || availableFilterAttributes.length === 0}
                      className="h-4 w-4 rounded border-zinc-300 text-blue-600 focus:ring-blue-500"
                    />
                    Use attribute range filters
                  </label>
                </div>
                <div className="absolute bottom-4 right-4 flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      onClick={() => { void handleFilter(); }}
                      disabled={loading || !selectedComponent}
                      className="h-9 px-4 rounded-md bg-blue-600 text-white text-sm font-medium transition-colors hover:bg-blue-700 disabled:bg-zinc-400 disabled:cursor-not-allowed"
                    >
                      {loading ? "Applying..." : "Apply additional filters"}
                    </button>
                    <button
                      type="button"
                      onClick={() => { handleClearAllFilters(); void handleFilter({ attributeRangesOverride: buildEmptyAttributeRanges(availableFilterAttributes), useAttributeRangeFiltersOverride: false, locationIrisOverride: [], carrierIrisOverride: [] }); }}
                      disabled={loading}
                      className="h-9 px-4 rounded-md border border-zinc-300 bg-orange-600 text-white text-sm font-medium transition-colors hover:bg-orange-700 disabled:bg-zinc-400 disabled:cursor-not-allowed dark:border-zinc-700"
                    >
                      Clear additional filters
                    </button>
                  </div>
                <p className="mt-1 text-xs text-zinc-600 dark:text-zinc-400">
                  {attributesLoading
                    ? "Loading available attributes for selected component..."
                    : availableFilterAttributes.length > 0
                      ? "Filters are optional. Enable this to set lower/upper limits per attribute."
                      : "No numeric attributes found for this component type."}
                </p>

                {useAttributeRangeFilters ? (
                  <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
                    {availableFilterAttributes.map((attribute) => (
                      <div
                        key={attribute}
                        className="rounded-md border border-zinc-200 dark:border-zinc-700 p-3 bg-white dark:bg-zinc-900"
                      >
                        <p className="text-sm font-medium text-black dark:text-zinc-50 mb-2">
                          {attribute}
                        </p>
                        <div className="grid grid-cols-2 gap-2">
                          <input
                            type="number"
                            value={attributeRanges[attribute]?.lower ?? ""}
                            onChange={(e) =>
                              setAttributeRanges((previous) => ({
                                ...previous,
                                [attribute]: {
                                  lower: e.target.value,
                                  upper: previous[attribute]?.upper ?? "",
                                },
                              }))
                            }
                            placeholder="Lower"
                            className="w-full px-2 py-1.5 border border-zinc-300 rounded-md bg-white text-black dark:bg-zinc-800 dark:border-zinc-700 dark:text-zinc-50 focus:outline-none focus:ring-2 focus:ring-blue-500"
                          />
                          <input
                            type="number"
                            value={attributeRanges[attribute]?.upper ?? ""}
                            onChange={(e) =>
                              setAttributeRanges((previous) => ({
                                ...previous,
                                [attribute]: {
                                  lower: previous[attribute]?.lower ?? "",
                                  upper: e.target.value,
                                },
                              }))
                            }
                            placeholder="Upper"
                            className="w-full px-2 py-1.5 border border-zinc-300 rounded-md bg-white text-black dark:bg-zinc-800 dark:border-zinc-700 dark:text-zinc-50 focus:outline-none focus:ring-2 focus:ring-blue-500"
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                ) : null}
              </>
            ) : null}
          </div>

          {filterMessage ? (
            <p className="mt-3 text-sm text-red-600 dark:text-red-400">{filterMessage}</p>
          ) : null}
        </div>

        {/* Filtered Data Display Area */}
        <div className="bg-white dark:bg-zinc-900 rounded-lg shadow-sm p-6 min-h-[400px]">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-semibold text-black dark:text-zinc-50">
              Filtered Results
            </h2>
            <button
              type="button"
              onClick={() => setIsDeveloperMode((prev) => !prev)}
              className={[
                "h-8 px-3 rounded-md text-xs font-medium transition-colors",
                isDeveloperMode
                  ? "bg-amber-500 text-white hover:bg-amber-600"
                  : "bg-zinc-200 text-zinc-700 hover:bg-zinc-300 dark:bg-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-600",
              ].join(" ")}
            >
              {isDeveloperMode ? "Developer mode: ON" : "Developer mode: OFF"}
            </button>
          </div>
          
          {filteredData ? (
            <div className="text-zinc-700 dark:text-zinc-300">
              <p className="mb-2">
                <span className="font-medium">Component:</span>{" "}
                {isDeveloperMode ? filteredData.component : localName(filteredData.component)}
              </p>
              <p className="text-zinc-600 dark:text-zinc-400 mb-3">
                Instances received: {instanceGroups.length}
              </p>
              {normalizedInstanceSearch ? (
                <p className="text-zinc-600 dark:text-zinc-400 mb-3">
                  Matching instances: {filteredInstanceGroups.length}
                </p>
              ) : null}
              <p className="text-zinc-600 dark:text-zinc-400 mb-3">
                Attribute rows received: {instanceBindings.length}
              </p>

              <div className="mb-4 p-3 border border-zinc-200 dark:border-zinc-700 rounded-md bg-zinc-50 dark:bg-zinc-800/40">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-sm font-medium text-black dark:text-zinc-50">
                    Import/Export YAML
                  </p>
                  <button
                    type="button"
                    onClick={() =>
                      setIsYamlPanelOpen((previous) => {
                        if (previous) {
                          setIsPreviewOpen(false);
                        }
                        return !previous;
                      })
                    }
                    className="h-8 px-3 rounded-md bg-zinc-200 text-zinc-900 text-xs font-medium transition-colors hover:bg-zinc-300 dark:bg-zinc-700 dark:text-zinc-100 dark:hover:bg-zinc-600"
                  >
                    {isYamlPanelOpen ? "Hide" : "Show"}
                  </button>
                </div>

                {isYamlPanelOpen ? (
                  <div className="mt-3 space-y-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <div className="h-9 min-w-[260px] max-w-full rounded-md border border-zinc-300 bg-white px-2 text-sm dark:border-zinc-600 dark:bg-zinc-900">
                        <label
                          htmlFor="draft-yaml-file-input"
                          className="flex h-full cursor-pointer items-center gap-2"
                        >
                          <span className="rounded border border-zinc-300 bg-zinc-100 px-2 py-1 text-xs font-medium text-zinc-800 dark:border-zinc-500 dark:bg-zinc-800 dark:text-zinc-100">
                            Choose YAML File
                          </span>
                          <span className="truncate text-zinc-600 dark:text-zinc-300">
                            {draftImportFile ? draftImportFile.name : "No file selected"}
                          </span>
                        </label>
                        <input
                          id="draft-yaml-file-input"
                          key={draftImportInputKey}
                          type="file"
                          accept=".yaml,.yml,application/x-yaml,text/yaml,text/x-yaml"
                          onChange={handleDraftImportFileChange}
                          className="sr-only"
                        />
                      </div>
                      <button
                        type="button"
                        onClick={handleImportDraftFile}
                        disabled={!draftImportFile || importLoading}
                        className="h-9 px-3 rounded-md bg-indigo-600 text-white text-sm font-medium transition-colors hover:bg-indigo-700 disabled:bg-zinc-400 disabled:cursor-not-allowed"
                      >
                        {importLoading ? "Importing..." : "Import YAML Draft"}
                      </button>
                    </div>

                    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-zinc-200 pt-3 dark:border-zinc-700">
                      <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
                        <p className="text-sm text-zinc-700 dark:text-zinc-300">
                          <span className="font-medium">Draft:</span> {draftConfigId ? draftConfigId : "none"}
                        </p>
                        <p className="text-sm text-zinc-700 dark:text-zinc-300">
                          <span className="font-medium">Technologies:</span> {draftCount}
                        </p>
                      </div>

                      <div className="flex flex-wrap items-center gap-2">
                        <button
                          type="button"
                          onClick={handlePreviewYaml}
                          disabled={!draftConfigId || yamlLoading}
                          className="h-9 px-3 rounded-md bg-zinc-700 text-white text-sm font-medium transition-colors hover:bg-zinc-800 disabled:bg-zinc-400 disabled:cursor-not-allowed"
                        >
                          {yamlLoading ? "Loading YAML..." : "Generate YAML"}
                        </button>
                        <button
                          type="button"
                          onClick={handleExportDraft}
                          disabled={!draftConfigId || exportLoading}
                          className="h-9 px-3 rounded-md bg-blue-600 text-white text-sm font-medium transition-colors hover:bg-blue-700 disabled:bg-zinc-400 disabled:cursor-not-allowed"
                        >
                          {exportLoading ? "Downloading..." : "Download YAML"}
                        </button>
                        <button
                          type="button"
                          onClick={handleExportDraftCsv}
                          disabled={!draftConfigId || csvExportLoading}
                          className="h-9 px-3 rounded-md bg-emerald-600 text-white text-sm font-medium transition-colors hover:bg-emerald-700 disabled:bg-zinc-400 disabled:cursor-not-allowed"
                        >
                          {csvExportLoading ? "Downloading CSV..." : "Download CSV"}
                        </button>
                        <button
                          type="button"
                          onClick={() => setIsPreviewOpen((previous) => !previous)}
                          className="h-9 px-3 rounded-md bg-zinc-200 text-zinc-900 text-sm font-medium transition-colors hover:bg-zinc-300 dark:bg-zinc-700 dark:text-zinc-100 dark:hover:bg-zinc-600"
                        >
                          {isPreviewOpen ? "Hide Preview" : "Show Preview"}
                        </button>
                      </div>
                    </div>
                  </div>
                ) : null}
                {draftMessage ? (
                  <p className="mt-2 text-sm text-zinc-700 dark:text-zinc-300">{draftMessage}</p>
                ) : null}
              </div>

              {filteredData.error ? (
                <p className="text-red-600 dark:text-red-400 mb-3">{filteredData.error}</p>
              ) : null}

              <div className="mt-6 relative">
                {instanceGroups.length > 0 ? (
                  <>
                    <h3 className="text-lg font-medium text-black dark:text-zinc-50 mb-3">
                      Instances
                    </h3>
                    <div className="mb-3 max-w-md">
                      <label className="text-xs font-medium text-zinc-600 dark:text-zinc-300">
                        Search instance label
                      </label>
                      <div className="relative mt-1">
                        <input
                          type="text"
                          value={instanceSearchTerm}
                          onChange={(event) => setInstanceSearchTerm(event.target.value)}
                          placeholder="Type to filter instance labels..."
                          className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2 pr-16 text-sm text-black shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-50"
                        />
                        {instanceSearchTerm ? (
                          <button
                            type="button"
                            onClick={() => setInstanceSearchTerm("")}
                            className="absolute right-2 top-1/2 -translate-y-1/2 rounded-md px-2 py-1 text-xs font-medium text-zinc-600 transition-colors hover:bg-zinc-100 hover:text-zinc-900 dark:text-zinc-300 dark:hover:bg-zinc-700 dark:hover:text-zinc-50"
                            aria-label="Clear instance search"
                          >
                            X
                          </button>
                        ) : null}
                      </div>
                    </div>
                    <div className="overflow-auto border border-zinc-200 dark:border-zinc-700 rounded-md">
                      <table className="min-w-full text-sm">
                        <thead className="bg-zinc-100 dark:bg-zinc-800">
                          <tr>
                            <th className="text-left px-3 py-2 font-medium text-zinc-800 dark:text-zinc-100 whitespace-nowrap">
                              #
                            </th>
                            {canAddTechnology ? (
                              <th className="text-left px-3 py-2 font-medium text-zinc-800 dark:text-zinc-100 whitespace-nowrap">
                                Action
                              </th>
                            ) : null}
                            <th className="text-left px-3 py-2 font-medium text-zinc-800 dark:text-zinc-100 whitespace-nowrap">
                              Instance
                            </th>
                            <th className="text-left px-3 py-2 font-medium text-zinc-800 dark:text-zinc-100 whitespace-nowrap">
                              Attributes
                            </th>
                            <th className="text-left px-3 py-2 font-medium text-zinc-800 dark:text-zinc-100 whitespace-nowrap">
                              Details
                            </th>
                          </tr>
                        </thead>
                        <tbody>
                          {filteredInstanceGroups.map((group, rowIndex) => {
                            const isExpanded = expandedInstanceKeys.includes(group.key);
                            const isAlreadyAdded =
                              group.technologyIri !== null &&
                              isTechnologyAlreadyInDraft(group.technologyIri);

                            return (
                              <Fragment key={group.key}>
                                <tr className="border-t border-zinc-200 dark:border-zinc-700">
                                  <td className="px-3 py-2 text-zinc-700 dark:text-zinc-300 align-top whitespace-nowrap">
                                    {rowIndex + 1}
                                  </td>
                                  {canAddTechnology ? (
                                    <td className="px-3 py-2 align-top whitespace-nowrap">
                                      {group.technologyIri ? (
                                        isAlreadyAdded ? (
                                          <button
                                            type="button"
                                            onClick={() => handleRemoveTechnology(group.representativeRow)}
                                            disabled={
                                              draftLoading && activeTechnologyIri === group.technologyIri
                                            }
                                            className="h-8 px-3 rounded-md bg-red-600 text-white text-xs font-medium transition-colors hover:bg-red-700 disabled:bg-zinc-400 disabled:cursor-not-allowed"
                                          >
                                            {draftLoading && activeTechnologyIri === group.technologyIri
                                              ? "Removing..."
                                              : "Remove"}
                                          </button>
                                        ) : (
                                          <button
                                            type="button"
                                            onClick={() => handleAddTechnology(group.representativeRow)}
                                            disabled={
                                              draftLoading && activeTechnologyIri === group.technologyIri
                                            }
                                            className="h-8 px-3 rounded-md bg-blue-600 text-white text-xs font-medium transition-colors hover:bg-blue-700 disabled:bg-zinc-400 disabled:cursor-not-allowed"
                                          >
                                            {draftLoading && activeTechnologyIri === group.technologyIri
                                              ? "Adding..."
                                              : "Add"}
                                          </button>
                                        )
                                      ) : (
                                        <span className="text-zinc-400">-</span>
                                      )}
                                    </td>
                                  ) : null}
                                  <td className="px-3 py-2 text-zinc-700 dark:text-zinc-300 align-top break-all">
                                    {group.technologyIri ? (
                                      <div>
                                        <p className="font-medium text-zinc-900 dark:text-zinc-100">
                                          {localName(group.technologyIri)}
                                        </p>
                                        {isDeveloperMode && (
                                          <p className="text-xs text-zinc-500 dark:text-zinc-400">
                                            {group.technologyIri}
                                          </p>
                                        )}
                                      </div>
                                    ) : (
                                      "Unknown instance"
                                    )}
                                  </td>
                                  <td className="px-3 py-2 text-zinc-700 dark:text-zinc-300 align-top whitespace-nowrap">
                                    {group.rows.length}
                                  </td>
                                  <td className="px-3 py-2 align-top whitespace-nowrap">
                                    <button
                                      type="button"
                                      onClick={() => toggleInstanceExpansion(group.key, group.technologyIri)}
                                      className="h-8 px-3 rounded-md bg-zinc-200 text-zinc-900 text-xs font-medium transition-colors hover:bg-zinc-300 dark:bg-zinc-700 dark:text-zinc-100 dark:hover:bg-zinc-600"
                                    >
                                      {isExpanded ? "Hide" : "Expand"}
                                    </button>
                                  </td>
                                </tr>
                                {isExpanded ? (
                                  <tr className="border-t border-zinc-200 dark:border-zinc-700 bg-zinc-50/80 dark:bg-zinc-800/50">
                                    <td
                                      colSpan={canAddTechnology ? 5 : 4}
                                      className="px-3 py-3"
                                    >
                                      <div className="flex flex-col gap-4">
                                        {group.representativeRow.description ? (
                                          <div>
                                            <p className="text-xs font-semibold text-zinc-700 dark:text-zinc-200 mb-3 uppercase tracking-wide">
                                              Description
                                            </p>
                                            <div className="rounded-md border border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900 px-3 py-3">
                                              <p className="text-sm text-zinc-700 dark:text-zinc-300 whitespace-pre-wrap">
                                                {group.representativeRow.description}
                                              </p>
                                            </div>
                                          </div>
                                        ) : null}

                                        {/* Technical parameters */}
                                        <div>
                                          <p className="text-xs font-semibold text-zinc-700 dark:text-zinc-200 mb-3 uppercase tracking-wide">
                                            Technical parameters
                                          </p>
                                          {attributeColumns.length > 0 ? (
                                            <div className="overflow-auto border border-zinc-200 dark:border-zinc-700 rounded-md bg-white dark:bg-zinc-900">
                                              <table className="min-w-full text-xs">
                                                <thead className="bg-zinc-100 dark:bg-zinc-800">
                                                  <tr>
                                                    <th className="text-left px-2 py-1.5 font-medium text-zinc-800 dark:text-zinc-100 whitespace-nowrap">#</th>
                                                    {attributeColumns.map((column) => (
                                                      <th key={`${group.key}-${column}`} className="text-left px-2 py-1.5 font-medium text-zinc-800 dark:text-zinc-100 whitespace-nowrap">
                                                        {column === groupedSourceColumnKey ? "Source" : ({att: "Attribute", att_label: "Attribute", att_category: "Category", att_val: "Value", att_unit: "Unit", att_currency: "Currency"} as Record<string, string>)[column] ?? column}
                                                      </th>
                                                    ))}
                                                  </tr>
                                                </thead>
                                                <tbody>
                                                  {group.rows.map((attributeRow, attributeRowIndex) => (
                                                    <tr key={`${group.key}-${attributeRow.att ?? attributeRowIndex}`} className="border-t border-zinc-200 dark:border-zinc-700">
                                                      <td className="px-2 py-1.5 text-zinc-700 dark:text-zinc-300 align-top whitespace-nowrap">{attributeRowIndex + 1}</td>
                                                      {attributeColumns.map((column) => (
                                                        <td key={`${group.key}-${attributeRowIndex}-${column}`} className="px-2 py-1.5 text-zinc-700 dark:text-zinc-300 align-top break-all">
                                                          {(() => {
                                                            if (column === groupedSourceColumnKey) {
                                                              const sourceLabel = attributeRow.ref_label;
                                                              const sourceType = attributeRow.ref_type;
                                                              const sourceUrl = attributeRow.ref_url;
                                                              if (!sourceLabel && !sourceType && !sourceUrl) return "-";
                                                              return (
                                                                <div className="flex flex-col gap-0.5">
                                                                  {sourceLabel ? <span>{sourceLabel}</span> : null}
                                                                  {sourceUrl ? (
                                                                    sourceType ? (
                                                                      <span>
                                                                        {localName(sourceType)}:{" "}
                                                                        <a href={sourceUrl} target="_blank" rel="noopener noreferrer" className="text-blue-700 underline dark:text-blue-300">{sourceUrl}</a>
                                                                      </span>
                                                                    ) : (
                                                                      <a href={sourceUrl} target="_blank" rel="noopener noreferrer" className="text-blue-700 underline dark:text-blue-300">{sourceUrl}</a>
                                                                    )
                                                                  ) : sourceType ? <span>{localName(sourceType)}</span> : null}
                                                                </div>
                                                              );
                                                            }
                                                            const value = attributeRow[column];
                                                            if (!value) return "-";
                                                            if (column === "att") {
                                                              const labelValue = attributeRow.att_label;
                                                              return labelValue || (isDeveloperMode ? value : localName(value));
                                                            }
                                                            if (localNameColumns.has(column)) return localName(value);
                                                            if (column === "att_val") return formatNumericValue(value);
                                                            return value;
                                                          })()}
                                                        </td>
                                                      ))}
                                                    </tr>
                                                  ))}
                                                </tbody>
                                              </table>
                                            </div>
                                          ) : (
                                            <p className="text-sm text-zinc-600 dark:text-zinc-400">No attribute columns found for this instance.</p>
                                          )}
                                        </div>

                                        {/* Energy flows */}
                                        {(() => {
                                          const flows = conversionParamsCache[group.key];
                                          if (flows === undefined) return null;
                                          return (
                                            <div>
                                              <p className="text-xs font-semibold text-zinc-700 dark:text-zinc-200 mb-3 uppercase tracking-wide">
                                                Flows
                                              </p>
                                              {flows.length > 0 ? (
                                                <div className="overflow-auto border border-zinc-200 dark:border-zinc-700 rounded-md bg-white dark:bg-zinc-900">
                                                  <table className="min-w-full text-xs">
                                                    <thead className="bg-zinc-100 dark:bg-zinc-800">
                                                      <tr>
                                                        <th className="text-left px-3 py-1.5 font-medium text-zinc-800 dark:text-zinc-100 whitespace-nowrap">#</th>
                                                        <th className="text-left px-3 py-1.5 font-medium text-zinc-800 dark:text-zinc-100 whitespace-nowrap">Instance</th>
                                                        <th className="text-left px-3 py-1.5 font-medium text-zinc-800 dark:text-zinc-100 whitespace-nowrap">Direction</th>
                                                        <th className="text-left px-3 py-1.5 font-medium text-zinc-800 dark:text-zinc-100 whitespace-nowrap">Carrier</th>
                                                        <th className="text-left px-3 py-1.5 font-medium text-zinc-800 dark:text-zinc-100 whitespace-nowrap">Main</th>
                                                        <th className="text-left px-3 py-1.5 font-medium text-zinc-800 dark:text-zinc-100 whitespace-nowrap">Attribute</th>
                                                        <th className="text-left px-3 py-1.5 font-medium text-zinc-800 dark:text-zinc-100 whitespace-nowrap">Value</th>
                                                        <th className="text-left px-3 py-1.5 font-medium text-zinc-800 dark:text-zinc-100 whitespace-nowrap">Unit</th>
                                                      </tr>
                                                    </thead>
                                                    <tbody>
                                                      {flows.map((flow, flowIndex) => {
                                                        const flowKey = `${group.key}::${flow.flow_iri}`;
                                                        const sortedAttrs = flow.attributes
                                                          .filter((a) => {
                                                            const name = localName(a.att);
                                                            return name !== "IsMainInput" && name !== "IsMainOutput";
                                                          })
                                                          .sort((a, b) => a.att.localeCompare(b.att));
                                                        const attrCount = Math.max(sortedAttrs.length, 1);
                                                        const isMain = flow.attributes.some(
                                                          (a) => {
                                                            const name = localName(a.att);
                                                            return (name === "IsMainInput" || name === "IsMainOutput") &&
                                                              (a.att_val === "1" || a.att_val === "1.0");
                                                          }
                                                        );
                                                        return sortedAttrs.length > 0 ? (
                                                          sortedAttrs.map((attr, attrIndex) => (
                                                            <tr key={`${flowKey}-${attrIndex}`} className={attrIndex === 0 ? "border-t border-zinc-200 dark:border-zinc-700" : ""}>
                                                              {attrIndex === 0 && (
                                                                <>
                                                                  <td rowSpan={attrCount} className="px-3 py-1.5 text-zinc-700 dark:text-zinc-300 align-top whitespace-nowrap">{flowIndex + 1}</td>
                                                                  <td rowSpan={attrCount} className="px-3 py-1.5 text-zinc-900 dark:text-zinc-100 align-top font-medium">
                                                                    {isDeveloperMode ? flow.flow_iri : localName(flow.flow_iri)}
                                                                  </td>
                                                                  <td rowSpan={attrCount} className="px-3 py-1.5 align-top whitespace-nowrap">
                                                                    <span className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-semibold ${flow.direction === "Input" ? "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300" : "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300"}`}>
                                                                      {flow.direction}
                                                                    </span>
                                                                  </td>
                                                                  <td rowSpan={attrCount} className="px-3 py-1.5 text-zinc-700 dark:text-zinc-300 align-top">
                                                                    {isDeveloperMode ? flow.carrier : localName(flow.carrier)}
                                                                  </td>
                                                                  <td rowSpan={attrCount} className="px-3 py-1.5 text-center align-top">
                                                                    {isMain && <span className="text-emerald-600 dark:text-emerald-400 font-bold text-sm">✓</span>}
                                                                  </td>
                                                                </>
                                                              )}
                                                              <td className="px-3 py-1.5 text-zinc-700 dark:text-zinc-300 align-top font-medium">{isDeveloperMode ? attr.att : localName(attr.att)}</td>
                                                              <td className="px-3 py-1.5 text-zinc-700 dark:text-zinc-300 align-top">{attr.att_val ? formatNumericValue(attr.att_val) : "-"}</td>
                                                              <td className="px-3 py-1.5 text-zinc-700 dark:text-zinc-300 align-top">{isDeveloperMode ? (attr.att_unit || "-") : (attr.att_unit ? localName(attr.att_unit) : "-")}</td>
                                                            </tr>
                                                          ))
                                                        ) : (
                                                          <tr key={flowKey} className="border-t border-zinc-200 dark:border-zinc-700">
                                                            <td className="px-3 py-1.5 text-zinc-700 dark:text-zinc-300 align-top whitespace-nowrap">{flowIndex + 1}</td>
                                                            <td className="px-3 py-1.5 text-zinc-900 dark:text-zinc-100 align-top font-medium">
                                                              {isDeveloperMode ? flow.flow_iri : localName(flow.flow_iri)}
                                                            </td>
                                                            <td className="px-3 py-1.5 align-top whitespace-nowrap">
                                                              <span className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-semibold ${flow.direction === "Input" ? "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300" : "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300"}`}>
                                                                {flow.direction}
                                                              </span>
                                                            </td>
                                                            <td className="px-3 py-1.5 text-zinc-700 dark:text-zinc-300 align-top">
                                                              {isDeveloperMode ? flow.carrier : localName(flow.carrier)}
                                                            </td>
                                                            <td colSpan={4} className="px-3 py-1.5 text-zinc-500 dark:text-zinc-400 italic">No attributes</td>
                                                          </tr>
                                                        );
                                                      })}
                                                    </tbody>
                                                  </table>
                                                </div>
                                              ) : (
                                                <p className="text-sm text-zinc-600 dark:text-zinc-400">No energy flows found for this instance.</p>
                                              )}
                                            </div>
                                          );
                                        })()}

                                        {/* Embedded Carbon */}
                                        {(() => {
                                          const ecList = embeddedCarbonCache[group.key];
                                          if (ecList === undefined) return null;
                                          return (
                                            <div>
                                              <p className="text-xs font-semibold text-zinc-700 dark:text-zinc-200 mb-3 uppercase tracking-wide">
                                                Embedded Carbon
                                              </p>
                                              {ecList.length > 0 ? (
                                                <div className="overflow-auto border border-zinc-200 dark:border-zinc-700 rounded-md bg-white dark:bg-zinc-900">
                                                  <table className="min-w-full text-xs">
                                                    <thead className="bg-zinc-100 dark:bg-zinc-800">
                                                      <tr>
                                                        <th className="text-left px-3 py-1.5 font-medium text-zinc-800 dark:text-zinc-100 whitespace-nowrap">#</th>
                                                        <th className="text-left px-3 py-1.5 font-medium text-zinc-800 dark:text-zinc-100 whitespace-nowrap">Instance</th>
                                                        <th className="text-left px-3 py-1.5 font-medium text-zinc-800 dark:text-zinc-100 whitespace-nowrap">LCA Activity</th>
                                                        <th className="text-left px-3 py-1.5 font-medium text-zinc-800 dark:text-zinc-100 whitespace-nowrap">Ref. Product</th>
                                                        <th className="text-left px-3 py-1.5 font-medium text-zinc-800 dark:text-zinc-100 whitespace-nowrap">Period</th>
                                                        <th className="text-left px-3 py-1.5 font-medium text-zinc-800 dark:text-zinc-100 whitespace-nowrap">Location</th>
                                                        <th className="text-left px-3 py-1.5 font-medium text-zinc-800 dark:text-zinc-100 whitespace-nowrap">LCA Unit</th>
                                                        <th className="text-left px-3 py-1.5 font-medium text-zinc-800 dark:text-zinc-100 whitespace-nowrap">ssp2 NDC</th>
                                                        <th className="text-left px-3 py-1.5 font-medium text-zinc-800 dark:text-zinc-100 whitespace-nowrap">ssp2 PkBudg1000</th>
                                                      </tr>
                                                    </thead>
                                                    <tbody>
                                                      {ecList.map((ec, ecIndex) => (
                                                        <tr key={`${group.key}::ec::${ec.ec_iri}`} className="border-t border-zinc-200 dark:border-zinc-700">
                                                          <td className="px-3 py-1.5 text-zinc-700 dark:text-zinc-300 align-top whitespace-nowrap">{ecIndex + 1}</td>
                                                          <td className="px-3 py-1.5 text-zinc-900 dark:text-zinc-100 align-top font-medium">
                                                            {isDeveloperMode ? ec.ec_iri : localName(ec.ec_iri)}
                                                          </td>
                                                          <td className="px-3 py-1.5 text-zinc-700 dark:text-zinc-300 align-top">{ec.lca_activity || "-"}</td>
                                                          <td className="px-3 py-1.5 text-zinc-700 dark:text-zinc-300 align-top">{ec.lca_ref_product || "-"}</td>
                                                          <td className="px-3 py-1.5 text-zinc-700 dark:text-zinc-300 align-top whitespace-nowrap">
                                                            {ec.period ? (isDeveloperMode ? ec.period : localName(ec.period)) : "-"}
                                                          </td>
                                                          <td className="px-3 py-1.5 text-zinc-700 dark:text-zinc-300 align-top whitespace-nowrap">
                                                            {ec.location ? (isDeveloperMode ? ec.location : localName(ec.location)) : "-"}
                                                          </td>
                                                          <td className="px-3 py-1.5 text-zinc-700 dark:text-zinc-300 align-top">{ec.lca_unit || "-"}</td>
                                                          <td className="px-3 py-1.5 text-zinc-700 dark:text-zinc-300 align-top">{ec.ssp2_ndc ? formatNumericValue(ec.ssp2_ndc) : "-"}</td>
                                                          <td className="px-3 py-1.5 text-zinc-700 dark:text-zinc-300 align-top">{ec.ssp2_pkbudg1000 ? formatNumericValue(ec.ssp2_pkbudg1000) : "-"}</td>
                                                        </tr>
                                                      ))}
                                                    </tbody>
                                                  </table>
                                                </div>
                                              ) : (
                                                <p className="text-sm text-zinc-600 dark:text-zinc-400">No embedded carbon data found for this instance.</p>
                                              )}
                                            </div>
                                          );
                                        })()}
                                      </div>
                                    </td>
                                  </tr>
                                ) : null}
                              </Fragment>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </>
                ) : null}

                {isPreviewOpen ? (
                  <aside className="absolute top-12 right-2 z-20 w-fit max-w-[calc(100vw-1rem)] md:right-4 md:max-w-[calc(100vw-2rem)] xl:max-w-[48%] border border-zinc-200 dark:border-zinc-700 rounded-md bg-white/95 dark:bg-zinc-900/95 p-3 shadow-xl backdrop-blur-sm">
                    <div className="flex items-center justify-between mb-2">
                      <h3 className="text-lg font-medium text-black dark:text-zinc-50">
                        YAML Preview
                      </h3>
                      <button
                        type="button"
                        onClick={() => setIsPreviewOpen(false)}
                        className="h-8 px-3 rounded-md bg-zinc-200 text-zinc-900 text-xs font-medium transition-colors hover:bg-zinc-300 dark:bg-zinc-700 dark:text-zinc-100 dark:hover:bg-zinc-600"
                      >
                        Collapse
                      </button>
                    </div>
                    {yamlPreview ? (
                      <pre className="p-3 bg-zinc-100 dark:bg-zinc-950 rounded text-xs overflow-auto max-h-[70vh] xl:max-h-[420px]">
                        {yamlPreview}
                      </pre>
                    ) : (
                      <p className="text-sm text-zinc-600 dark:text-zinc-400">
                        Click &quot;Generate YAML&quot; to load content.
                      </p>
                    )}
                  </aside>
                ) : null}
              </div>
            </div>
          ) : (
            <p className="text-zinc-500 dark:text-zinc-500 italic">
              Select a component and apply filter to see results
            </p>
          )}
        </div>
      </div>
    </main>
  );
}
