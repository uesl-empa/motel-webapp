# Frontend

This frontend is a Next.js application deployed as a containerized web service.

## Local development

```bash
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 npm run dev
```

If `NEXT_PUBLIC_API_BASE_URL` is not set, the app falls back to `http://localhost:8000`.

## Build Docker image

`NEXT_PUBLIC_API_BASE_URL` is used at build time for browser-side API calls.

```bash
docker build \
	--build-arg NEXT_PUBLIC_API_BASE_URL=https://PLACEHOLDER:PORT \
	-t motel-frontend:local \
	./frontend
```

Smoke test locally:

```bash
docker run --rm -p 3000:3000 motel-frontend:local
```

Then open `http://localhost:3000`.

## Publish image to GitLab Container Registry

Set your values:

```bash
export CI_REGISTRY=gitlab.empa.ch
export CI_REGISTRY_IMAGE=gitlab.empa.ch/ues-lab/team-mes/motel/motel_ontology
export IMAGE_NAME=frontend
export IMAGE_TAG=$(git rev-parse --short HEAD)
export API_BASE_URL=https://PLACEHOLDER:PORT
```

Authenticate Docker to GitLab registry (use a GitLab token with `read_registry` and `write_registry` scopes):

```bash
echo <gitlab-token> | docker login $CI_REGISTRY -u <gitlab-username> --password-stdin
```

Build and push:

```bash
docker build \
	--build-arg NEXT_PUBLIC_API_BASE_URL=$API_BASE_URL \
	-t $CI_REGISTRY_IMAGE/$IMAGE_NAME:$IMAGE_TAG \
	-t $CI_REGISTRY_IMAGE/$IMAGE_NAME:latest \
	./frontend

docker push $CI_REGISTRY_IMAGE/$IMAGE_NAME:$IMAGE_TAG
docker push $CI_REGISTRY_IMAGE/$IMAGE_NAME:latest
```

## Kubernetes deployment

Manifests are in `k8s/frontend` (frontend resources) and `k8s/shared` (shared resources).

### 1) Update placeholders

Before applying manifests:

1. Update image in `k8s/frontend/deployment.yaml` to your GitLab registry path/tag.
2. Keep or remove `imagePullSecrets` based on repository visibility.
3. Update `host` in `k8s/frontend/ingress.yaml` from `app.example.com` to your real domain.
4. Update TLS secret name if your cert manager creates a different secret.
5. Update `ingressClassName` if your cluster is not using nginx.

### 2) Apply manifests

```bash
kubectl apply -f k8s/shared/namespace.yaml
kubectl apply -f k8s/frontend/deployment.yaml
kubectl apply -f k8s/frontend/service.yaml
kubectl apply -f k8s/frontend/ingress.yaml
```

### 3) Verify rollout

```bash
kubectl -n motel get pods
kubectl -n motel rollout status deployment/motel-frontend
kubectl -n motel get svc motel-frontend
kubectl -n motel get ingress motel-frontend
```

### 4) (Optional) GitLab registry pull secret for private images

```bash
kubectl -n motel create secret docker-registry gitlab-registry-secret \
	--docker-server=gitlab.empa.ch \
	--docker-username=<gitlab-username> \
	--docker-password=<gitlab-token>
```

Then uncomment the `imagePullSecrets` block in `k8s/frontend/deployment.yaml`.

## Production checklist

1. Use a real production backend URL for `NEXT_PUBLIC_API_BASE_URL` during image build.
2. Ensure backend CORS allows your frontend origin via `BACKEND_CORS_ALLOWED_ORIGINS`.
3. Ensure DNS points the frontend hostname to your Ingress controller.
4. Ensure TLS certificate provisioning is configured for the Ingress host.
