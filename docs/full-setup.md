MOTEL Webapp Full Setup
=======================

Overview
--------

This repository is the working home of the MOTEL knowledge graph application stack.

At a high level, it supports:

- ontology-based TTL files used by the MOTEL knowledge graph
- loading those files into GraphDB
- serving the graph through a backend API
- exploring the result through a frontend web application

This repo is part of the wider MOTEL project:

- Project website: https://bartonchentw.github.io/motel-platform/
- Data processing repository: https://github.com/BartonChenTW/motel-platform

The upstream data processing and export pipeline now lives in the separate `motel-platform` repository. This repository consumes the generated outputs and focuses on the web application, graph loading, and deployment setup.

TTL Generation Note
-------------------

The motel-db to TTL export step now lives in a separate repository.

This repository consumes those generated files, especially:

- `app/data/01_classes_and_attributes/cls_atr_motel.ttl`

When the upstream export changes, copy the refreshed TTL output into `app/data/` here and then reload GraphDB.

Quick Start
-----------

For local users who want to run the full stack without changing code:

```bash
docker compose up -d --build
```

Services:

- Frontend: http://localhost:3000
- Backend health: http://localhost:8000/api/filter/health
- GraphDB workbench: http://localhost:7200

Notes:

- `docker compose down` keeps GraphDB data
- `docker compose down -v` clears volumes and triggers a fresh seed on next startup

Developer Workflow
------------------

Developers can run GraphDB in Docker and start backend and frontend locally.

1. Start GraphDB and setup jobs:

```bash
docker compose up -d graphdb graphdb-setup graphdb-seed
```

2. Start the backend:

```bash
conda create -n motel python=3.13
conda activate motel
python -m pip install -r backend/requirements.txt
python -m backend.src.server
```

3. Start the frontend:

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
docker compose restart backend frontend
```

The rebuild step matters because both `backend` and `graphdb-seed` copy `app/` into the Docker image at build time. If you skip the rebuild, GraphDB may reload an older baked-in TTL file.

If GraphDB is not running yet, start it first:

```bash
docker compose up -d graphdb graphdb-setup
docker compose build backend graphdb-seed
docker compose run --rm -e GRAPHDB_SEED_REPLACE=true graphdb-seed
docker compose up -d backend frontend
```

For a full reset of persisted GraphDB data:

```bash
docker compose down -v
docker compose up -d
```

Be careful: `docker compose down -v` removes the stored GraphDB volume.

Environment Notes
-----------------

Common backend environment variables:

- `BACKEND_HOST` default: `0.0.0.0`
- `BACKEND_PORT` default: `8000`
- `BACKEND_CORS_ALLOWED_ORIGINS` default: `http://localhost:3000,http://127.0.0.1:3000`
- `GRAPHDB_URL` default: `http://localhost:7200`
- `GRAPHDB_REPOSITORY` default: `MOTEL`

Repository Layout
-----------------

- `backend/`: FastAPI service and GraphDB query logic
- `frontend/`: Next.js web app
- `app/`: notebooks, ontology data, generated TTL files, and helper scripts
- `docker-compose.yml`: full local stack
- `k8s/`: Kubernetes manifests for deployment-related setup

Kubernetes
----------

This repository also contains Kubernetes manifests under `k8s/`, including shared resources plus backend, frontend, and GraphDB deployment configuration.

These files support the fuller deployment setup and are intentionally kept out of the short top-level README so the main entry point stays focused on local usage.
