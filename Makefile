# Local Kubernetes platform for the task manager (k3d + Helm).
# Every kubectl/helm call names the k3d context explicitly, so other
# contexts in your kubeconfig (e.g. a cloud cluster) are never touched.

CLUSTER          ?= tasks
CONTEXT          := k3d-$(CLUSTER)
NAMESPACE        ?= task-manager
HOST             ?= tasks.localhost
HTTP_PORT        ?= 80
REGISTRY_PORT    ?= 5111
REGISTRY_PUSH    ?= localhost:$(REGISTRY_PORT)
REGISTRY_CLUSTER ?= k3d-$(CLUSTER)-registry.localhost:$(REGISTRY_PORT)
IMAGE            ?= task-manager

# Image tag: the git commit, plus "-dirty" when the working tree has
# uncommitted or untracked changes, so a tag never claims to be a commit
# it isn't.
GIT_SHA := $(shell git rev-parse --short=12 HEAD)
DIRTY   := $(shell [ -z "$$(git status --porcelain)" ] || echo -dirty)
TAG     ?= $(GIT_SHA)$(DIRTY)

TF_DIR     := infra/terraform
CHART_APP  := deploy/helm/task-manager
CHART_DB   := deploy/helm/task-manager-db
SECRET_KEY_SECRET := task-manager-secret-key

KUBECTL := kubectl --context $(CONTEXT)
HELM    := helm --kube-context $(CONTEXT)
CURL    := curl --silent --show-error --resolve $(HOST):$(HTTP_PORT):127.0.0.1
BASE_URL := http://$(HOST)$(if $(filter-out 80,$(HTTP_PORT)),:$(HTTP_PORT))

KUBECONFORM := kubeconform -strict -summary \
	-schema-location default \
	-schema-location 'https://raw.githubusercontent.com/datreeio/CRDs-catalog/main/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json'

.DEFAULT_GOAL := help
.PHONY: help cluster-up cluster-down kube-context-check build-push deploy undeploy \
	smoke-test status logs lint tf-check helm-check

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  %-20s %s\n", $$1, $$2}'

# --- Cluster ---------------------------------------------------------------

cluster-up: ## Create the k3d cluster, registry, ingress-nginx and CloudNativePG (Terraform)
	terraform -chdir=$(TF_DIR) init -input=false
	terraform -chdir=$(TF_DIR) apply -input=false -auto-approve

cluster-down: ## Delete the cluster and registry (Terraform destroy)
	terraform -chdir=$(TF_DIR) destroy -input=false -auto-approve

kube-context-check: ## Fail unless the k3d cluster's context exists and answers
	@kubectl config get-contexts -o name | grep -qx '$(CONTEXT)' || { \
		echo "ERROR: kube context '$(CONTEXT)' not found. Run 'make cluster-up' first." >&2; exit 1; }
	@$(KUBECTL) get --raw /readyz >/dev/null 2>&1 || { \
		echo "ERROR: cluster for context '$(CONTEXT)' is not reachable. Is Docker running?" >&2; exit 1; }
	@echo "Using kube context $(CONTEXT)"

# --- Image -----------------------------------------------------------------

build-push: ## Build the image and push it to the k3d registry, tagged with the git SHA
	docker build -t $(REGISTRY_PUSH)/$(IMAGE):$(TAG) .
	docker push $(REGISTRY_PUSH)/$(IMAGE):$(TAG)
	@echo "Pushed $(REGISTRY_PUSH)/$(IMAGE):$(TAG) (cluster pulls it as $(REGISTRY_CLUSTER)/$(IMAGE):$(TAG))"

# --- Deploy ----------------------------------------------------------------

deploy: kube-context-check ## Install/upgrade the database and the app
	@$(CURL) --fail -o /dev/null http://$(REGISTRY_PUSH)/v2/$(IMAGE)/manifests/$(TAG) \
		-H 'Accept: application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.v2+json, application/vnd.docker.distribution.manifest.list.v2+json' \
		|| { echo "ERROR: image $(IMAGE):$(TAG) is not in the registry. Run 'make build-push' first." >&2; exit 1; }
	$(KUBECTL) create namespace $(NAMESPACE) --dry-run=client -o yaml | $(KUBECTL) apply -f -
	@# Placeholder secret management: generate SECRET_KEY once and keep it.
	@# The value is piped in, so it never appears in values, args or the repo.
	@$(KUBECTL) -n $(NAMESPACE) get secret $(SECRET_KEY_SECRET) >/dev/null 2>&1 \
		&& echo "Secret $(SECRET_KEY_SECRET) already exists" \
		|| { python3 -c 'import secrets, sys; sys.stdout.write(secrets.token_urlsafe(50))' \
			| $(KUBECTL) -n $(NAMESPACE) create secret generic $(SECRET_KEY_SECRET) --from-file=SECRET_KEY=/dev/stdin; }
	$(HELM) upgrade --install task-manager-db $(CHART_DB) -n $(NAMESPACE) --wait --timeout 5m
	$(KUBECTL) -n $(NAMESPACE) wait --for=condition=Ready cluster.postgresql.cnpg.io/task-manager-db --timeout=300s
	$(HELM) upgrade --install task-manager $(CHART_APP) -n $(NAMESPACE) \
		--set image.repository=$(REGISTRY_CLUSTER)/$(IMAGE) \
		--set image.tag=$(TAG) \
		--set host=$(HOST) \
		--wait --timeout 10m

undeploy: kube-context-check ## Remove the app and database releases (keeps the namespace)
	-$(HELM) uninstall task-manager -n $(NAMESPACE)
	-$(HELM) uninstall task-manager-db -n $(NAMESPACE)

# --- Checks ----------------------------------------------------------------

smoke-test: kube-context-check ## curl /healthz/ through the ingress
	@for i in $$(seq 1 30); do \
		if body=$$($(CURL) --fail $(BASE_URL)/healthz/ 2>/dev/null); then \
			echo "OK $(BASE_URL)/healthz/ -> $$body"; exit 0; fi; \
		sleep 2; \
	done; \
	echo "ERROR: $(BASE_URL)/healthz/ did not return 200" >&2; \
	$(CURL) -i $(BASE_URL)/healthz/ >&2; exit 1

status: kube-context-check ## Show the app's Kubernetes resources
	$(KUBECTL) -n $(NAMESPACE) get pods,svc,ingress,jobs,hpa,pdb,clusters.postgresql.cnpg.io

logs: kube-context-check ## Tail the web pods' logs
	$(KUBECTL) -n $(NAMESPACE) logs -l app.kubernetes.io/name=task-manager --all-containers --prefix -f --tail=50

lint: tf-check helm-check ## Run the same infra checks as CI

tf-check: ## terraform fmt -check and validate
	terraform -chdir=$(TF_DIR) fmt -check -recursive -diff
	terraform -chdir=$(TF_DIR) init -backend=false -input=false >/dev/null
	terraform -chdir=$(TF_DIR) validate

helm-check: ## helm lint and helm template | kubeconform for both charts
	helm lint $(CHART_DB)
	helm lint $(CHART_APP) --set image.tag=ci
	helm template task-manager-db $(CHART_DB) | $(KUBECONFORM)
	helm template task-manager $(CHART_APP) --set image.tag=ci | $(KUBECONFORM)
	helm template task-manager $(CHART_APP) --set image.tag=ci --set autoscaling.enabled=false | $(KUBECONFORM)
