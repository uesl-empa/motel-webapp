MOTEL Ontology
===============

What This Repository Is For
---------------------------

This repository is the working home of the MOTEL knowledge graph, GraphDB loading flow, backend API, and demo web application.

At a high level, it helps turn structured technology data into something people can explore more easily:

- an ontology that defines the meaning of technologies, attributes, flows, and related concepts
- a knowledge graph that stores those data in a connected form
- a web interface that lets users browse, filter, and inspect the technology data

In practical terms, this repo is used to:

- store ontology files and imported MOTEL TTL files
- load those files into GraphDB
- serve the data through a backend API
- show the results in a simple frontend for exploration and demo use

You do not need to be a programmer to think of it this way:
this project is a data-to-knowledge-to-web-app pipeline for the MOTEL technology dataset.

This repository contains the MOTEL knowledge graph stack: GraphDB, a FastAPI backend, and a Next.js frontend.

TTL Generation Note
-------------------

The motel-db to TTL export step lives in a separate repository.

Important:
`app/data/01_classes_and_attributes/cls_atr_motel.ttl` is not authored or generated in this repository. It is an imported artifact produced in the separate motel-db export repository and then copied here for loading into GraphDB and use by the backend/frontend.

This repository consumes those generated files, especially:

- `app/data/01_classes_and_attributes/cls_atr_motel.ttl`

Typical workflow across the two repositories:

1. Generate or refresh the MOTEL TTL in the upstream motel-db export repository.
2. Copy the refreshed TTL output into `app/data/` in this repository.
3. Run the local enrichment step below.
4. Reload GraphDB from this repository.

Before reloading GraphDB, run the local enrichment step here so unit-based cost attributes expose frontend-visible units and capacity-basis metadata:

```bash
.venv\Scripts\python.exe app\ttl_creation\from_motel_db\enrich_unit_based_costs.py app\data\01_classes_and_attributes\cls_atr_motel.ttl app\data\temp\cls_atr_motel.ttl
```

Quick Start (Local Users)
-------------------------

Local users run the full stack with Docker Compose and do not modify the code.

1) Start everything:

```bash
docker compose up -d --build
```

2) Open the services:

- Frontend: http://localhost:3000
- Backend health: http://localhost:8000/api/filter/health
- GraphDB workbench: http://localhost:7200

Notes:

- `docker compose down` keeps GraphDB data.
- `docker compose down -v` clears volumes and will trigger a fresh seed on next startup.

Developer Workflow
------------------

Developers run GraphDB via Docker Compose and start backend and frontend locally.

1) Start GraphDB (plus repo setup and seed job):

```bash
docker compose up -d graphdb graphdb-setup graphdb-seed
```

2) Start the backend:

```bash
conda create -n motel python=3.13
conda activate motel
python -m pip install -r backend/requirements.txt
python -m backend.src.server
```

3) Start the frontend:

```bash
cd frontend
npm install
npm run dev
```

Service URLs remain the same as in the quick start section.

Reloading GraphDB
-----------------

If you update TTL files under `app/data` and want GraphDB to reload them into the existing `MOTEL` repository, run:

```bash
docker compose build backend graphdb-seed
docker compose run --rm -e GRAPHDB_SEED_REPLACE=true graphdb-seed
docker compose up -d --force-recreate backend frontend
```

Why all three steps matter:

- `build` updates the Docker images, because both `backend` and `graphdb-seed` copy `app/` into the image at build time.
- `graphdb-seed` reloads GraphDB from the TTL files inside the freshly built image.
- `--force-recreate` replaces the running backend container so its TTL status endpoint sees the same refreshed file version as the seed image.

If you skip the rebuild, GraphDB may reload an older baked-in TTL file. If you only restart the backend, the UI may still show TTL metadata from an older backend container image.

If GraphDB is not running yet, start it first:

```bash
docker compose up -d graphdb graphdb-setup
docker compose build backend graphdb-seed
docker compose run --rm -e GRAPHDB_SEED_REPLACE=true graphdb-seed
docker compose up -d --force-recreate backend frontend
```

For a full reset of persisted GraphDB data:

```bash
docker compose down -v
docker compose up -d
```

Be careful: `docker compose down -v` removes the stored GraphDB volume.

Environment Notes
-----------------

Common backend environment variables (optional overrides):

- `BACKEND_HOST` (default `0.0.0.0`)
- `BACKEND_PORT` (default `8000`)
- `BACKEND_CORS_ALLOWED_ORIGINS` (default `http://localhost:3000,http://127.0.0.1:3000`)
- `GRAPHDB_URL` (default `http://localhost:7200`)
- `GRAPHDB_REPOSITORY` (default `MOTEL`)

Repository Layout
-----------------

- `backend/`: FastAPI service and GraphDB query logic
- `frontend/`: Next.js web app
- `app/`: notebooks, ontology data, generated TTL files, and helper scripts
- `docker-compose.yml`: full local stack
