import os
import time
from pathlib import Path

from app.client.GraphDBClient import GraphDBClient
from app.utils.helper_functions import load_all_data


def _as_bool(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def wait_for_repository(client: GraphDBClient, timeout_seconds: int, interval_seconds: float) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None

    while time.monotonic() < deadline:
        try:
            client.get_repository_size()
            return
        except Exception as exc:
            last_error = exc
            print(f"Waiting for GraphDB repository '{client.repository}' at {client.host}...")
            time.sleep(interval_seconds)

    raise RuntimeError(
        f"Timed out waiting for repository '{client.repository}' at {client.host}"
    ) from last_error


def main() -> None:
    graphdb_url = os.getenv("GRAPHDB_URL", "http://graphdb:7200").rstrip("/")
    repository_name = os.getenv("GRAPHDB_REPOSITORY", "MOTEL")
    replace_existing = _as_bool(os.getenv("GRAPHDB_SEED_REPLACE"))
    timeout_seconds = int(os.getenv("GRAPHDB_WAIT_TIMEOUT_SECONDS", "120"))
    interval_seconds = float(os.getenv("GRAPHDB_WAIT_INTERVAL_SECONDS", "2"))
    data_dir = Path(os.getenv("GRAPHDB_DATA_DIR", Path(__file__).resolve().parents[1] / "data"))

    if not data_dir.exists():
        raise FileNotFoundError(f"GraphDB seed data directory not found: {data_dir}")

    client = GraphDBClient(repository=repository_name, host=graphdb_url)
    wait_for_repository(client, timeout_seconds=timeout_seconds, interval_seconds=interval_seconds)

    repository_size = client.get_repository_size()
    if repository_size > 0 and not replace_existing:
        print(
            f"Repository '{repository_name}' already contains {repository_size} statements; skipping seed."
        )
        return

    if replace_existing and repository_size > 0:
        print(f"Repository '{repository_name}' already contains data; replacing existing graphs.")
    else:
        print(f"Repository '{repository_name}' is empty; loading ontology data.")

    load_all_data(client, data_dir, replace=True)


if __name__ == "__main__":
    main()
