ALL_TYPES = """
PREFIX dici_onto: <https://digicities.info/ontology#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
select distinct ?type where {{
    ?object a ?type .
}} limit 100
"""

COMPONENTS = """
PREFIX dici_onto: <https://digicities.info/ontology#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT DISTINCT ?component ?parent ?has_instances

WHERE {{
    ?component rdfs:subClassOf+ dici_onto:Component .
    OPTIONAL {{
        ?component rdfs:subClassOf ?parent .
        ?parent rdfs:subClassOf* dici_onto:Component .
        FILTER(?parent != dici_onto:Component)
    }}
    BIND(EXISTS {{
        ?i a ?component .
    }} AS ?has_instances)
}}
ORDER BY ?component ?parent
"""

TECH_PARAMS = """
PREFIX dici_onto: <https://digicities.info/ontology#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?tech_id ?tech_type ?assembly_root ?attr ?attr_type ?value ?unit_label ?att_currency
WHERE {{
    BIND ({tech_id_term} AS ?tech_id) .

    ?tech_id rdf:type ?tech_type .
    VALUES ?assembly_root {{
        {supported_component_roots}
    }}
    ?tech_type rdfs:subClassOf* ?assembly_root .

    ?tech_id dici_onto:hasAttribute ?attr .
    ?attr rdf:type ?attr_type .
    ?attr dici_onto:hasAttributeValue ?value .
    OPTIONAL {{ ?attr dici_onto:hasUnitLabel ?unit_label }}
    OPTIONAL {{ ?attr dici_onto:currency ?att_currency }}
    
    FILTER(?attr_type IN (
        {tech_attribute_filter_values}
    ))
}}
"""

TECHNOLOGY_TYPES = """
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>

SELECT DISTINCT ?tech_type
WHERE {{
    BIND ({tech_id_term} AS ?tech_id) .
    ?tech_id rdf:type ?tech_type .
}}
"""

ASSEMBLY_SUPPORT_FOR_TECHNOLOGY = """
PREFIX dici_onto: <https://digicities.info/ontology#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT (COUNT(*) AS ?match_count)
WHERE {{
    BIND ({tech_id_term} AS ?tech_id) .
    ?tech_id rdf:type ?tech_type .
    VALUES ?supported_root {{
        {supported_component_roots}
    }}
    ?tech_type rdfs:subClassOf* ?supported_root .
}}
"""

SUPPORTED_ASSEMBLY_COMPONENT_TYPES = """
PREFIX dici_onto: <https://digicities.info/ontology#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT DISTINCT ?component
WHERE {{
    VALUES ?supported_root {{
        {supported_component_roots}
    }}
    ?component rdfs:subClassOf* ?supported_root .
    ?component rdfs:subClassOf* dici_onto:Component .
}}
ORDER BY ?component
"""

INSTANCES_WITH_ATTRIBUTES = """
PREFIX dici_onto: <https://digicities.info/ontology#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX qudt: <http://qudt.org/schema/qudt/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
PREFIX prov: <http://www.w3.org/ns/prov#>
PREFIX schema: <https://schema.org/>
 
#namespaces for clearer output
PREFIX cur: <http://qudt.org/vocab/currency/>
prefix unit: <http://qudt.org/vocab/unit/> 
PREFIX itm: <https://digicities.info/proj/MOTEL/EnergyConverter/>
 
SELECT ?tech ?description ?att ?att_label ?att_category ?att_val ?att_unit ?unit_label ?att_currency ?ref_label ?ref_type ?ref_url WHERE {{
    ?tech a {tech_type_term} .
    OPTIONAL {{ ?tech rdfs:description ?description }}
    ?tech dici_onto:hasAttribute ?att.
    OPTIONAL {{ ?att rdfs:label ?att_instance_label }}
    ?att a ?att_category.
    OPTIONAL {{
        ?att a ?att_type .
        FILTER(STRSTARTS(STR(?att_type), "https://digicities.info/ontology#"))
        FILTER(?att_type NOT IN (
            dici_onto:DynamicAttribute,
            dici_onto:ResourceAttribute,
            dici_onto:SimpleValueAttribute,
            dici_onto:CustomPhysicalRatioAttribute,
            dici_onto:EventAttribute,
            dici_onto:CategoricalAttribute,
            dici_onto:CurveAttribute,
            dici_onto:SimpleCostAttribute,
            dici_onto:UnitBasedCostAttribute,
            dici_onto:PhysicalAttribute
        ))
        FILTER NOT EXISTS {{
            ?att a ?more_specific_type .
            FILTER(?more_specific_type != ?att_type)
            FILTER(STRSTARTS(STR(?more_specific_type), "https://digicities.info/ontology#"))
            ?more_specific_type rdfs:subClassOf+ ?att_type .
        }}
        OPTIONAL {{ ?att_type rdfs:label ?att_type_label }}
    }}
    BIND(COALESCE(?att_instance_label, ?att_type_label) AS ?att_label)
    ?att dici_onto:hasAttributeValue ?att_val.
    OPTIONAL {{ ?att qudt:unit ?att_unit }}
    OPTIONAL {{ ?att dici_onto:hasUnitLabel ?unit_label }}
    OPTIONAL {{ ?att dici_onto:currency ?att_currency }}
    OPTIONAL {{ 
        ?att prov:wasDerivedFrom ?ref.
        ?ref a dici_onto:Reference;
            rdfs:label ?ref_label.
        OPTIONAL {{ ?ref dici_onto:hasReferenceType ?ref_type }}
        OPTIONAL {{ ?ref schema:url ?ref_url }}
    }}
 
    # Whitelist: Only property-type attributes (not domain-type)
    FILTER(?att_category IN (
        dici_onto:DynamicAttribute,
        dici_onto:ResourceAttribute,
        dici_onto:SimpleValueAttribute,
        dici_onto:CustomPhysicalRatioAttribute,
        dici_onto:EventAttribute,
        dici_onto:CategoricalAttribute,
        dici_onto:CurveAttribute,
        dici_onto:SimpleCostAttribute,
        dici_onto:UnitBasedCostAttribute,
        dici_onto:PhysicalAttribute
    ))

    # Embedded carbon is rendered by the dedicated Embedded Carbon query/table,
    # never as an ordinary technology attribute.
    FILTER NOT EXISTS {{ ?att a dici_onto:Embedded_Carbon }}
    FILTER NOT EXISTS {{ ?att a dici_onto:EmbeddedCarbon }}

    {location_filter}

    {carrier_filter}

    {range_filters}
}} ORDER BY ?tech ?att LIMIT 2000
"""

ENERGY_CARRIER_PARAMS = """
PREFIX dici_onto: <https://digicities.info/ontology#>
PREFIX qudt: <http://qudt.org/schema/qudt/>

SELECT DISTINCT ?flow ?direction ?carrier ?att ?att_category ?att_val ?att_unit ?unit_label ?att_currency WHERE {{
    BIND({energy_conv_id_term} as ?energy_conv)
    {{
        BIND("Output" AS ?direction)
        ?energy_conv (dici_onto:feeds|^dici_onto:fedBy) ?flow .
        VALUES ?flow_type {{ dici_onto:Flow dici_onto:EnergyCarrierFlow dici_onto:MaterialFlow }}
        ?flow a ?flow_type .
        ?flow dici_onto:contains ?carrier .
        ?flow dici_onto:hasAttribute ?att .
        {{
            ?att a dici_onto:PhysicalAttribute .
            BIND(dici_onto:PhysicalAttribute AS ?att_category)
            OPTIONAL {{ ?att dici_onto:hasAttributeValue ?hav }}
            OPTIONAL {{ ?att qudt:value ?qv }}
            BIND(COALESCE(?hav, ?qv) AS ?att_val)
            FILTER(BOUND(?att_val))
        }} UNION {{
            ?att a dici_onto:SimpleValueAttribute .
            FILTER NOT EXISTS {{ ?att a dici_onto:PhysicalAttribute }}
            BIND(dici_onto:SimpleValueAttribute AS ?att_category)
            ?att dici_onto:hasAttributeValue ?att_val
        }}
        OPTIONAL {{ ?att qudt:unit ?att_unit }}
        OPTIONAL {{ ?att dici_onto:hasUnitLabel ?unit_label }}
        OPTIONAL {{ ?att dici_onto:currency ?att_currency }}
    }}
    UNION {{
        BIND("Input" AS ?direction)
        ?energy_conv (dici_onto:fedBy|^dici_onto:feeds) ?flow .
        VALUES ?flow_type {{ dici_onto:Flow dici_onto:EnergyCarrierFlow dici_onto:MaterialFlow }}
        ?flow a ?flow_type .
        ?flow dici_onto:contains ?carrier .
        ?flow dici_onto:hasAttribute ?att .
        {{
            ?att a dici_onto:PhysicalAttribute .
            BIND(dici_onto:PhysicalAttribute AS ?att_category)
            OPTIONAL {{ ?att dici_onto:hasAttributeValue ?hav }}
            OPTIONAL {{ ?att qudt:value ?qv }}
            BIND(COALESCE(?hav, ?qv) AS ?att_val)
            FILTER(BOUND(?att_val))
        }} UNION {{
            ?att a dici_onto:SimpleValueAttribute .
            FILTER NOT EXISTS {{ ?att a dici_onto:PhysicalAttribute }}
            BIND(dici_onto:SimpleValueAttribute AS ?att_category)
            ?att dici_onto:hasAttributeValue ?att_val
        }}
        OPTIONAL {{ ?att qudt:unit ?att_unit }}
        OPTIONAL {{ ?att dici_onto:hasUnitLabel ?unit_label }}
        OPTIONAL {{ ?att dici_onto:currency ?att_currency }}
    }}
}} ORDER BY ?direction ?flow ?att"""

EMBEDDED_CARBON_PARAMS = """
PREFIX dici_onto: <https://digicities.info/ontology#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX qudt: <http://qudt.org/schema/qudt/>

SELECT ?ec_iri ?lca_activity ?lca_ref_product ?period ?location ?lca_unit ?ssp2_ndc ?ssp2_pkbudg1000 WHERE {{
    BIND({tech_id_term} AS ?tech_id) .
    ?ec_iri a dici_onto:EmbeddedCarbon .
    ?ec_iri (dici_onto:linksComponent|^dici_onto:linksComponent) ?tech_id .
    OPTIONAL {{ ?ec_iri rdfs:LCA_activity ?lca_activity }}
    OPTIONAL {{ ?ec_iri rdfs:LCA_ref_product ?lca_ref_product }}
    OPTIONAL {{ ?ec_iri dici_onto:occursDuring ?period }}
    OPTIONAL {{ ?ec_iri dici_onto:locatedIn ?location }}
    OPTIONAL {{
        ?ec_iri dici_onto:hasAttribute ?u .
        ?u a dici_onto:LCA_unit .
        ?u dici_onto:hasAttributeValue ?lca_unit
    }}
    OPTIONAL {{
        ?ec_iri dici_onto:hasAttribute ?n .
        ?n a dici_onto:ssp2_NDC .
        ?n qudt:value ?ssp2_ndc
    }}
    OPTIONAL {{
        ?ec_iri dici_onto:hasAttribute ?p .
        ?p a dici_onto:ssp2_PkBudg1000 .
        ?p qudt:value ?ssp2_pkbudg1000
    }}
}} ORDER BY ?ec_iri
"""

FILTERABLE_ATTRIBUTES_FOR_TYPE = """
PREFIX dici_onto: <https://digicities.info/ontology#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT DISTINCT ?attribute_type
WHERE {{
    ?tech a {tech_type_term} .
    ?tech dici_onto:hasAttribute ?att .
    ?att a ?attribute_type .
    ?att dici_onto:hasAttributeValue ?att_val .

    # Only expose attributes that can be used in numeric/year range filters.
    FILTER(isNumeric(?att_val) || datatype(?att_val) = xsd:gYear)

    FILTER(STRSTARTS(STR(?attribute_type), "https://digicities.info/ontology#"))
    FILTER(?attribute_type NOT IN (
        dici_onto:DynamicAttribute,
        dici_onto:ResourceAttribute,
        dici_onto:SimpleValueAttribute,
        dici_onto:CustomPhysicalRatioAttribute,
        dici_onto:EventAttribute,
        dici_onto:CategoricalAttribute,
        dici_onto:CurveAttribute,
        dici_onto:SimpleCostAttribute,
        dici_onto:UnitBasedCostAttribute,
        dici_onto:PhysicalAttribute
    ))

    # Keep only the most specific discovered type for each attribute node.
    FILTER NOT EXISTS {{
        ?att a ?more_specific_type .
        FILTER(?more_specific_type != ?attribute_type)
        FILTER(STRSTARTS(STR(?more_specific_type), "https://digicities.info/ontology#"))
        ?more_specific_type rdfs:subClassOf+ ?attribute_type .
    }}
}}
ORDER BY ?attribute_type
"""

AVAILABLE_LOCATIONS_FOR_TYPE = """
PREFIX dici_onto: <https://digicities.info/ontology#>

SELECT DISTINCT ?location WHERE {{
    ?tech a {tech_type_term} .
    ?tech dici_onto:locatedIn ?location .
}}
ORDER BY ?location
"""

AVAILABLE_CARRIERS_FOR_TYPE = """
PREFIX dici_onto: <https://digicities.info/ontology#>

SELECT DISTINCT ?carrier WHERE {{
    ?tech a {tech_type_term} .
    ?tech (dici_onto:feeds|dici_onto:fedBy|^dici_onto:feeds|^dici_onto:fedBy) ?flow .
    VALUES ?flow_type {{ dici_onto:Flow dici_onto:EnergyCarrierFlow dici_onto:MaterialFlow }}
    ?flow a ?flow_type .
    ?flow dici_onto:contains ?carrier .
}}
ORDER BY ?carrier
"""
