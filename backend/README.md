## Backend startup

```bash
python -m backend.src.server
```

## Environment configuration

- `BACKEND_HOST`: bind host for backend startup. Defaults to `0.0.0.0`.
- `BACKEND_PORT`: bind port for backend startup. Defaults to `8000`.
- `BACKEND_CORS_ALLOWED_ORIGINS`: comma-separated list of allowed frontend origins. Defaults to `http://localhost:3000,http://127.0.0.1:3000`.
- `GRAPHDB_URL`: GraphDB base URL used by backend queries. Defaults to `http://localhost:7200`.
- `GRAPHDB_REPOSITORY`: GraphDB repository name. Defaults to `MOTEL`.
- `BACKEND_DRAFTS_DB_PATH`: optional absolute/relative path for the SQLite draft database. If unset, defaults to `backend/output/drafts.sqlite`.

## Draft persistence

- Technology draft configs are persisted in SQLite at `backend/output/drafts.sqlite` by default.
- Draft cleanup runs automatically and removes drafts older than 30 days.
- Cleanup is checked at most once per hour during normal draft API usage.

## Build Docker image

Build from repository root so both `app/` and `backend/` packages are included:

```bash
docker build -f backend/Dockerfile -t motel-backend:local .
```

Smoke test locally:

```bash
docker run --rm -p 8000:8000 \
	-e BACKEND_PORT=8000 \
	-e GRAPHDB_URL=http://host.docker.internal:7200 \
	-e GRAPHDB_REPOSITORY=MOTEL \
	motel-backend:local
```

Then check `http://localhost:8000/api/filter/health`.

## Local compose stack

The root `docker-compose.yml` now includes:
- a persisted GraphDB home volume,
- a one-shot `graphdb-seed` service that loads ontology data from `app/data` when the repository is empty,
- the `backend` service, which waits for GraphDB seeding to complete.

```bash
docker compose up -d --build
```

Quick checks:

```bash
docker compose ps
curl http://localhost:8000/api/filter/health
```

Notes:
- Normal `docker compose down` keeps the GraphDB and backend named volumes, so you do not need to reload data on the next `up`.
- `docker compose down -v` removes volumes and will trigger a fresh repository seed on the next startup.
- You can force reseeding of an existing repository by setting `GRAPHDB_SEED_REPLACE=true` for the `graphdb-seed` service.
- The seed job loads TTL files from `app/data` in this repository.

## Kubernetes deployment

Manifests are in `k8s/backend` (backend resources) and `k8s/shared` (shared resources).

1. Update image in `k8s/backend/deployment.yaml` to your registry/tag.
2. Update CORS (`BACKEND_CORS_ALLOWED_ORIGINS`) and GraphDB URL/repository env vars.
3. Ensure the `motel-backend-data` PVC fits your storage class or adjust/remove persistence settings.
4. Update hostnames/TLS secret in `k8s/backend/ingress.yaml`.

Apply manifests:

```bash
kubectl apply -f k8s/shared/namespace.yaml
kubectl apply -f k8s/backend/pvc.yaml
kubectl apply -f k8s/backend/deployment.yaml
kubectl apply -f k8s/backend/service.yaml
kubectl apply -f k8s/backend/ingress.yaml
```

Verify rollout:

```bash
kubectl -n motel rollout status deployment/motel-backend
kubectl -n motel get pods -l app=motel-backend
kubectl -n motel get svc motel-backend
kubectl -n motel get ingress motel-backend
```
