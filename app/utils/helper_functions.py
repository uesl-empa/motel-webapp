"""Helper functions for managing ontology data uploads and queries to GraphDB."""

from pathlib import Path
from typing import Dict, List, Optional, Tuple


def get_graph_name_for_file(file_path: Path, data_dir: Path) -> str:
    """
    Determine the named graph URI for a given TTL file based on its location.

    Named Graph Convention:
    - Core ontology (data/00_ontology/core/): http://digicities_core_ont
    - Extensions (data/00_ontology/extensions/): http://digicities_ont_ext_<name>
    - External ontologies (data/00_ontology/external/): http://ext_ont_<name>
    - Classes & Attributes (data/01_classes_and_attributes/): http://cls_atr_<name>
    - Scenarios (data/02_scenarios/): http://scenarios_<name>

    Args:
        file_path: Path to the TTL file
        data_dir: Path to the data directory

    Returns:
        Named graph URI string
    """
    rel_path = file_path.relative_to(data_dir)
    parts = rel_path.parts
    name = file_path.stem  # filename without extension

    if parts[0] == "00_ontology":
        if parts[1] == "core":
            return "http://digicities_core_ont"
        elif parts[1] == "extensions":
            return f"http://digicities_ont_ext_{name}"
        elif parts[1] == "external":
            return f"http://ext_ont_{name}"
    elif parts[0] == "01_classes_and_attributes":
        # Remove 'cls_atr_' prefix if present for cleaner naming
        if name.startswith("cls_atr_"):
            name = name[8:]  # Remove 'cls_atr_' prefix
        return f"http://cls_atr_{name}"
    elif parts[0] == "02_scenarios":
        return f"http://scenarios_{name}"

    # Fallback
    return f"http://data_{name}"


def upload_to_named_graph(client, file_path: Path, data_dir: Path, replace: bool = True):
    """
    Upload a TTL file to its corresponding named graph.

    Args:
        client: GraphDBClient instance
        file_path: Path to the TTL file
        data_dir: Path to the data directory
        replace: If True, replace existing data. If False, append to existing data.
    """
    graph_name = get_graph_name_for_file(file_path, data_dir)
    mode = "REPLACE" if replace else "APPEND"
    print(f"[{mode}] {file_path.name} -> <{graph_name}>")

    client.upload_ttl(
        ttl_file_path=str(file_path),
        graph_name=graph_name,
        replace_existing=replace
    )


def discover_data_files(data_dir: Path):
    """
    Discover all TTL files in the data directory and show their target graphs.

    Args:
        data_dir: Path to the data directory

    Returns:
        List of Path objects for all discovered TTL files
    """
    print("Discovered data files:\n")

    categories = {
        "Core Ontology": data_dir / "00_ontology" / "core",
        "Extensions": data_dir / "00_ontology" / "extensions",
        "External Ontologies": data_dir / "00_ontology" / "external",
        "Classes & Attributes": data_dir / "01_classes_and_attributes",
        "Scenarios": data_dir / "02_scenarios"
    }

    all_files = []
    for category, path in categories.items():
        if path.exists():
            files = list(path.glob("*.ttl"))
            if files:
                print(f"{category}:")
                for f in files:
                    graph = get_graph_name_for_file(f, data_dir)
                    print(f"  {f.name} -> <{graph}>")
                    all_files.append(f)
                print()

    return all_files


def load_all_data(client, data_dir: Path, replace: bool = True):
    """
    Load all TTL files from the data directory into their respective named graphs.

    Args:
        client: GraphDBClient instance
        data_dir: Path to the data directory
        replace: If True, replace existing data. If False, append to existing data.
    """
    all_files = discover_data_files(data_dir)

    print("Loading all data files...\n")
    for f in all_files:
        upload_to_named_graph(client, f, data_dir, replace=replace)

    print(f"\nDone! Repository now contains {client.get_repository_size()} statements")


def show_graph_status(client):
    """
    Display the current status of all named graphs in the repository.

    Args:
        client: GraphDBClient instance
    """
    print(f"Repository contains {client.get_repository_size()} statements")
    print("\nNamed graphs:")

    graphs = client.list_graphs()
    if graphs.empty:
        print("  (none)")
    else:
        for g in graphs['g'].tolist():
            graph_size = client.get_graph_size(g)
            print(f"  <{g}> ({graph_size} statements)")


# =============================================================================
# Query Management Functions
# =============================================================================

def discover_query_categories(queries_dir: Path) -> List[str]:
    """
    Discover all query categories (subdirectories) in the queries directory.

    Args:
        queries_dir: Path to the queries directory (e.g., data/03_queries)

    Returns:
        List of category names (directory names)
    """
    if not queries_dir.exists():
        return []

    categories = [d.name for d in queries_dir.iterdir() if d.is_dir()]
    return sorted(categories)


def discover_queries_in_category(queries_dir: Path, category: str) -> Dict[int, Tuple[str, Path]]:
    """
    Discover all SPARQL query files in a specific category.

    Args:
        queries_dir: Path to the queries directory
        category: Name of the category subdirectory

    Returns:
        Dictionary mapping query number to (query_name, query_path)
    """
    category_path = queries_dir / category
    if not category_path.exists():
        return {}

    queries = {}
    query_files = sorted(category_path.glob("*.sparql"))

    for idx, query_file in enumerate(query_files, start=1):
        query_name = query_file.stem  # filename without extension
        queries[idx] = (query_name, query_file)

    return queries


def load_query(query_path: Path) -> str:
    """
    Load a SPARQL query from a file.

    Args:
        query_path: Path to the .sparql file

    Returns:
        Query string
    """
    with open(query_path, 'r', encoding='utf-8') as f:
        return f.read()


def list_queries(queries_dir: Path, category: str) -> Dict[int, Tuple[str, Path]]:
    """
    List all queries in a category with their numbers.

    Args:
        queries_dir: Path to the queries directory
        category: Name of the category

    Returns:
        Dictionary mapping query number to (query_name, query_path)
    """
    queries = discover_queries_in_category(queries_dir, category)

    if not queries:
        print(f"No queries found in category '{category}'")
        return {}

    print(f"\nQueries in '{category}':")
    print("-" * 50)
    for num, (name, path) in queries.items():
        print(f"  [{num}] {name}")
    print("-" * 50)

    return queries


def run_query_by_number(client, queries: Dict[int, Tuple[str, Path]], query_num: int,
                        show_query: bool = False):
    """
    Run a query by its number and return results as DataFrame.

    Args:
        client: GraphDBClient instance
        queries: Dictionary from list_queries()
        query_num: The query number to run
        show_query: If True, print the query before running

    Returns:
        DataFrame with query results, or None if query not found
    """
    if query_num not in queries:
        print(f"Query #{query_num} not found. Available: {list(queries.keys())}")
        return None

    query_name, query_path = queries[query_num]
    query_text = load_query(query_path)

    print(f"\nRunning: {query_name}")

    if show_query:
        print("\nQuery:")
        print("-" * 50)
        print(query_text)
        print("-" * 50)

    result = client.sparql_query(query_text)
    print(f"Results: {len(result)} rows")

    return result


class QueryEngine:
    """
    Interactive query engine for managing and running SPARQL queries.
    """

    def __init__(self, client, queries_dir: Path):
        """
        Initialize the query engine.

        Args:
            client: GraphDBClient instance
            queries_dir: Path to the queries directory
        """
        self.client = client
        self.queries_dir = queries_dir
        self.current_category = None
        self.current_queries = {}
        self.last_result = None

    def categories(self) -> List[str]:
        """List available query categories."""
        cats = discover_query_categories(self.queries_dir)
        print("\nAvailable query categories:")
        for cat in cats:
            print(f"  - {cat}")
        return cats

    def select_category(self, category: str):
        """
        Select a category and list its queries.

        Args:
            category: Name of the category to select
        """
        self.current_category = category
        self.current_queries = list_queries(self.queries_dir, category)
        return self.current_queries

    def run(self, query_num: int, show_query: bool = False):
        """
        Run a query by number from the current category.

        Args:
            query_num: Query number to run
            show_query: If True, display the query text

        Returns:
            DataFrame with results
        """
        if not self.current_queries:
            print("No category selected. Use select_category() first.")
            return None

        self.last_result = run_query_by_number(
            self.client,
            self.current_queries,
            query_num,
            show_query=show_query
        )
        return self.last_result

    def show_last_query(self, query_num: int):
        """Display the text of a query without running it."""
        if query_num not in self.current_queries:
            print(f"Query #{query_num} not found.")
            return

        query_name, query_path = self.current_queries[query_num]
        query_text = load_query(query_path)

        print(f"\nQuery: {query_name}")
        print("-" * 50)
        print(query_text)
        print("-" * 50)
