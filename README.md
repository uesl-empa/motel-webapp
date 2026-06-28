MOTEL Webapp
============

What This Repository Is For
---------------------------

This repository contains the MOTEL web application stack for exploring MOTEL technology data through a knowledge graph.

It brings together:

- a GraphDB knowledge graph
- a FastAPI backend API
- a Next.js frontend

This repo is part of the broader MOTEL project.

- Project website: https://bartonchentw.github.io/motel-platform/
- Data processing repository: https://github.com/BartonChenTW/motel-platform

If you want the fuller deployment and developer setup, including GraphDB reload steps and Kubernetes manifests, see [docs/full-setup.md](docs/full-setup.md).

Project Structure
-----------------

- `frontend/`: Next.js user interface
- `backend/`: FastAPI service and GraphDB query logic
- `app/`: ontology files, generated TTL data, notebooks, and helper scripts
- `k8s/`: Kubernetes manifests for Empa server setup only
- `docker-compose.yml`: local stack for running the app

Run Locally
-----------

For most GitHub users, the easiest way to run this project is with Docker Compose. You do not need to install GraphDB separately because it runs as a container in the local stack.

Before you start, install:

- Git
- Docker Desktop, with Docker Compose enabled

Then download this repository and start the app:

```bash
git clone https://github.com/<your-user>/motel-webapp.git
cd motel-webapp
docker compose up -d --build
```

This starts:

- the Next.js frontend
- the FastAPI backend
- a local GraphDB container

After startup, open:

- Frontend: http://localhost:3000
- Backend health: http://localhost:8000/api/filter/health
- GraphDB workbench: http://localhost:7200

Quick Start
-----------

For local use, start the full stack with Docker Compose:

```bash
docker compose up -d --build
```

Then open:

- Frontend: http://localhost:3000
- Backend health: http://localhost:8000/api/filter/health
- GraphDB workbench: http://localhost:7200

Useful notes:

- `docker compose down` keeps GraphDB data
- `docker compose down -v` removes volumes and triggers a fresh seed next time

More Setup
----------

See [docs/full-setup.md](docs/full-setup.md) for:

- developer workflow
- TTL refresh and GraphDB reseeding
- environment variables
- Kubernetes-related files in this repo
