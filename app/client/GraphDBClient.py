import requests
import pandas
import urllib.parse
import rdflib


def df_from_json(query_out):
    """Convert SPARQL JSON results to pandas DataFrame."""
    cols = query_out["head"]["vars"]
    out = []
    for row in query_out["results"]["bindings"]:
        item = []
        for c in cols:
            item.append(row.get(c, {}).get("value"))
        out.append(item)
    return pandas.DataFrame(out, columns=cols)


def dict_from_json(query_out):
    """Convert SPARQL JSON results to a list of dictionaries (one per row)."""
    cols = query_out["head"]["vars"]
    rows_out = []
    for row in query_out["results"]["bindings"]:
        row_out = {}
        for c in cols:
            row_out[c] = row.get(c, {}).get("value")
        rows_out.append(row_out)
    return rows_out


def split_graph(graph, split_size):
    """Split a graph into subgraphs for uploading large datasets.

    Args:
        graph: An rdflib graph
        split_size: The number of triples per split

    Returns:
        A list of subgraphs
    """
    subgraphs = []
    triples_list = list(graph.triples((None, None, None)))
    for i in range(0, len(triples_list), split_size):
        subgraph = rdflib.Graph()
        for triple in triples_list[i : i + split_size]:
            subgraph.add(triple)
        subgraphs.append(subgraph)
    return subgraphs


class GraphDBClient:
    """Client for interacting with a local GraphDB instance."""

    default_graph_name = "<https://digicities.info>"

    def __init__(self, repository, host="http://localhost:7200"):
        """Initialize the GraphDB client.

        Args:
            repository: Name of the GraphDB repository
            host: GraphDB host URL (default: http://localhost:7200)
        """
        self.repository = repository
        self.host = host.rstrip("/")
        print(f"GraphDBClient initialized for repository '{repository}' at {self.host}")

    def get_namespaces(self):
        """Retrieve namespaces used in the repository.

        Returns:
            DataFrame of namespaces and their corresponding URIs
        """
        url = f"{self.host}/repositories/{self.repository}/namespaces"
        headers = {"Accept": "application/sparql-results+json"}

        response = requests.get(url, headers=headers)
        response.raise_for_status()

        namespace_df = df_from_json(response.json())
        namespace_df["prefix"] = namespace_df["prefix"] + ":"
        self.namespaces = namespace_df.set_index("namespace")["prefix"].to_dict()

        return namespace_df

    def sparql_query(self, query, infer=True, out_format="df", replace_namespaces=False):
        """Execute a SPARQL SELECT query.

        Args:
            query: SPARQL query string
            infer: Whether to use inference (default: True)
            out_format: Output format - "df", "dict", or "response" (default: "df")
            replace_namespaces: Replace URIs with namespace prefixes (default: False)

        Returns:
            Query results in specified format
        """
        out_format_options = ["df", "dict", "response"]
        if out_format not in out_format_options:
            raise ValueError(f"'out_format' must be one of {out_format_options}")

        url = f"{self.host}/repositories/{self.repository}"
        headers = {"Accept": "application/sparql-results+json"}
        params = {
            "query": query,
            "infer": "true" if infer else "false"
        }

        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()

        if out_format == "df":
            result = df_from_json(response.json())
            if replace_namespaces:
                result = self.replace_namespaces(result)
        elif out_format == "dict":
            result = dict_from_json(response.json())
        elif out_format == "response":
            result = response.content

        return result

    def replace_namespaces(self, df):
        """Replace URIs with namespace prefixes in a DataFrame.

        Args:
            df: DataFrame with URIs

        Returns:
            Modified DataFrame with namespace prefixes
        """
        if not hasattr(self, "namespaces"):
            self.get_namespaces()
        return df.replace(self.namespaces, regex=True)

    def sparql_update(self, statement):
        """Execute a SPARQL UPDATE statement.

        Args:
            statement: SPARQL UPDATE statement

        Returns:
            Response object
        """
        update_url = urllib.parse.quote(statement)
        update_url = update_url.replace("%0A", "")
        url = f"{self.host}/repositories/{self.repository}/statements?update={update_url}"
        headers = {"Accept": "application/sparql-results+json"}

        response = requests.post(url, headers=headers)
        response.raise_for_status()

        return response

    def upload_ttl(self, ttl_str=None, ttl_file_path=None, graph_name=None,
                   replace_existing=False, split_size=None):
        """Upload Turtle data to the repository.

        Args:
            ttl_str: Turtle data as string (mutually exclusive with ttl_file_path)
            ttl_file_path: Path to Turtle file (mutually exclusive with ttl_str)
            graph_name: Named graph to upload to (optional)
            replace_existing: Replace existing data in graph (default: False)
            split_size: Split large graphs into chunks of this size (optional)

        Returns:
            Response object
        """
        if (ttl_str is None and ttl_file_path is None) or \
           (ttl_str is not None and ttl_file_path is not None):
            raise ValueError("Provide exactly one of ttl_str or ttl_file_path")

        if graph_name:
            # GraphDB requires angle brackets around the URI
            graph_uri = f"<{graph_name}>"
            graph_name_encoded = urllib.parse.quote(graph_uri)
            url = f"{self.host}/repositories/{self.repository}/statements?context={graph_name_encoded}"
        else:
            url = f"{self.host}/repositories/{self.repository}/statements"

        headers = {"Content-Type": "text/turtle", "Accept": "application/json"}
        request_type = "PUT" if replace_existing else "POST"

        if split_size is not None:
            graph = rdflib.Graph()
            if ttl_file_path is not None:
                graph.parse(source=ttl_file_path)
            else:
                graph.parse(data=ttl_str, format="turtle")

            graph_splits = split_graph(graph=graph, split_size=split_size)
            for graph_split in graph_splits:
                serialized = graph_split.serialize(format="turtle", encoding="utf-8")
                response = requests.request(request_type, url, headers=headers, data=serialized)
                response.raise_for_status()
                if response.status_code == 204:
                    print(f"Uploaded split ({split_size} triples)")
                    request_type = "POST"  # Subsequent splits should append
                else:
                    print("Upload failed, check response")

            print(f"Total: {len(list(graph.triples((None, None, None))))} triples uploaded")
        else:
            if ttl_file_path is not None:
                graph = rdflib.Graph()
                graph.parse(source=ttl_file_path)
                serialized = graph.serialize(format="turtle", encoding="utf-8")
            else:
                serialized = ttl_str

            response = requests.request(request_type, url, headers=headers, data=serialized)
            response.raise_for_status()

            if response.status_code == 204:
                print("Data uploaded successfully")
            else:
                print("Upload failed, check response")

        return response

    def upload_rdf_file(self, rdf_file_path, graph_name=None, replace_existing=False):
        """Upload an RDF file to the repository.

        Args:
            rdf_file_path: Path to RDF file
            graph_name: Named graph to upload to (optional)
            replace_existing: Replace existing data (default: False)

        Returns:
            Response object
        """
        if graph_name:
            graph_uri = f"<{graph_name}>"
        else:
            graph_uri = f"<{GraphDBClient.default_graph_name}>"
        graph_name_encoded = urllib.parse.quote(graph_uri)

        url = f"{self.host}/repositories/{self.repository}/statements?context={graph_name_encoded}"
        headers = {"Content-Type": "application/xhtml+xml", "Accept": "application/json"}
        request_type = "PUT" if replace_existing else "POST"

        with open(rdf_file_path, "rb") as rdf_file:
            response = requests.request(request_type, url, headers=headers, data=rdf_file)

        if response.status_code == 413:
            print(f"{rdf_file_path}: File too large, splitting into chunks")
            self.upload_ttl(
                ttl_file_path=rdf_file_path,
                graph_name=graph_name,
                replace_existing=replace_existing,
                split_size=10000,
            )
        else:
            response.raise_for_status()

        return response

    def get_repository_size(self):
        """Get the number of statements in the repository.

        Returns:
            Number of statements (int)
        """
        url = f"{self.host}/repositories/{self.repository}/size"
        response = requests.get(url)
        response.raise_for_status()
        return int(response.text)

    def clear_repository(self):
        """Clear all statements from the repository.

        Returns:
            Response object
        """
        url = f"{self.host}/repositories/{self.repository}/statements"
        response = requests.delete(url)
        response.raise_for_status()
        print("Repository cleared")
        return response

    def list_graphs(self):
        """List all named graphs in the repository.

        Returns:
            DataFrame with graph URIs
        """
        query = "SELECT DISTINCT ?g WHERE { GRAPH ?g { ?s ?p ?o } }"
        return self.sparql_query(query)

    def clear_graph(self, graph_name):
        """Clear all statements from a specific named graph.

        Args:
            graph_name: URI of the named graph to clear

        Returns:
            Response object
        """
        graph_uri = f"<{graph_name}>"
        graph_name_encoded = urllib.parse.quote(graph_uri)
        url = f"{self.host}/repositories/{self.repository}/statements?context={graph_name_encoded}"
        response = requests.delete(url)
        response.raise_for_status()
        print(f"Graph <{graph_name}> cleared")
        return response

    def get_graph_size(self, graph_name):
        """Get the number of statements in a specific named graph.

        Args:
            graph_name: URI of the named graph

        Returns:
            Number of statements (int)
        """
        query = f"SELECT (COUNT(*) as ?count) WHERE {{ GRAPH <{graph_name}> {{ ?s ?p ?o }} }}"
        results = self.sparql_query(query, out_format="dict")
        first_row = results[0] if results else {}
        return int(first_row.get("count", 0))


if __name__ == "__main__":
    # Test the client
    client = GraphDBClient(repository="MOTEL")

    print("\n--- Testing get_namespaces ---")
    try:
        namespaces = client.get_namespaces()
        print(namespaces.head())
    except Exception as e:
        print(f"Error: {e}")

    print("\n--- Testing sparql_query ---")
    try:
        query = "SELECT * WHERE { ?s ?p ?o } LIMIT 5"
        result = client.sparql_query(query)
        print(result)
    except Exception as e:
        print(f"Error: {e}")

    print("\n--- Testing get_repository_size ---")
    try:
        size = client.get_repository_size()
        print(f"Repository size: {size} statements")
    except Exception as e:
        print(f"Error: {e}")

    print("\nAll tests completed")
