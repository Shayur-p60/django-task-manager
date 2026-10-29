# --- GitOps: Argo CD, Kyverno and the root Application ---------------------
#
# Argo CD syncs everything under gitops/ from git. Terraform only installs
# the controllers and the root Application; the app, its database and the
# admission policies are all managed by Argo CD from there.

resource "random_password" "argocd_admin" {
  length  = 32
  special = false
}

# Argo CD wants the time the admin password was set. Record it once, so
# the Helm values (and the release) don't change on every plan.
resource "terraform_data" "argocd_admin_password_mtime" {
  input = timestamp()

  lifecycle {
    ignore_changes = [input]
  }

  triggers_replace = [random_password.argocd_admin.id]
}

resource "helm_release" "argocd" {
  name             = "argocd"
  repository       = "https://argoproj.github.io/argo-helm"
  chart            = "argo-cd"
  version          = var.argocd_chart_version
  namespace        = "argocd"
  create_namespace = true
  wait             = true
  timeout          = 600

  values = [yamlencode({
    # Not needed here: no SSO, no notifications, no ApplicationSets.
    dex           = { enabled = false }
    notifications = { enabled = false }
    applicationSet = {
      replicas = 0
    }

    configs = {
      cm = {
        "exec.enabled"           = "false"
        "admin.enabled"          = "true"
        "timeout.reconciliation" = "60s"
        # Let the root app wait for each child Application to be healthy,
        # so sync waves (platform -> database -> app) are respected.
        "resource.customizations.health.argoproj.io_Application" = <<-LUA
          hs = {}
          hs.status = "Progressing"
          hs.message = ""
          if obj.status ~= nil and obj.status.health ~= nil then
            hs.status = obj.status.health.status
            if obj.status.health.message ~= nil then
              hs.message = obj.status.health.message
            end
          end
          return hs
        LUA
      }
      secret = {
        # A random password from the start, so the generated
        # argocd-initial-admin-secret is never needed.
        argocdServerAdminPassword      = random_password.argocd_admin.bcrypt_hash
        argocdServerAdminPasswordMtime = terraform_data.argocd_admin_password_mtime.output
      }
    }

    # Sized for a ~4 GB Docker Desktop VM.
    controller = {
      resources = {
        requests = { cpu = "100m", memory = "256Mi" }
        limits   = { memory = "512Mi" }
      }
    }
    repoServer = {
      resources = {
        requests = { cpu = "50m", memory = "128Mi" }
        limits   = { memory = "256Mi" }
      }
    }
    server = {
      # No Ingress: the UI is reached with kubectl port-forward only.
      ingress = { enabled = false }
      resources = {
        requests = { cpu = "25m", memory = "64Mi" }
        limits   = { memory = "192Mi" }
      }
    }
    redis = {
      resources = {
        requests = { cpu = "25m", memory = "32Mi" }
        limits   = { memory = "96Mi" }
      }
    }
  })]

  depends_on = [terraform_data.cluster]
}

# The admin password is set above, so the initial-admin secret shouldn't
# exist. Delete it anyway in case an earlier install created one.
resource "terraform_data" "argocd_initial_secret_removed" {
  triggers_replace = [helm_release.argocd.id, random_password.argocd_admin.id]

  provisioner "local-exec" {
    command = "kubectl --context '${local.kube_context}' -n argocd delete secret argocd-initial-admin-secret --ignore-not-found"
  }
}

resource "helm_release" "kyverno" {
  name             = "kyverno"
  repository       = "https://kyverno.github.io/kyverno"
  chart            = "kyverno"
  version          = var.kyverno_chart_version
  namespace        = "kyverno"
  create_namespace = true
  wait             = true
  timeout          = 600

  values = [yamlencode({
    # Only admission control is used (image signature verification), so
    # the background, cleanup and reports controllers are off.
    admissionController = {
      replicas = 1
      container = {
        resources = {
          requests = { cpu = "50m", memory = "128Mi" }
          limits   = { memory = "384Mi" }
        }
      }
    }
    backgroundController = { enabled = false }
    cleanupController    = { enabled = false }
    reportsController    = { enabled = false }
  })]

  depends_on = [terraform_data.cluster]
}

# Root Application (app-of-apps): syncs gitops/apps/, which defines the
# platform policies, the database and the app.
resource "helm_release" "argocd_root_app" {
  name       = "argocd-root-app"
  repository = "https://argoproj.github.io/argo-helm"
  chart      = "argocd-apps"
  version    = var.argocd_apps_chart_version
  namespace  = "argocd"
  wait       = true

  values = [yamlencode({
    applications = {
      root = {
        namespace  = "argocd"
        project    = "default"
        finalizers = ["resources-finalizer.argocd.argoproj.io"]
        source = {
          repoURL        = var.gitops_repo_url
          targetRevision = var.gitops_revision
          path           = "gitops/apps"
        }
        destination = {
          server    = "https://kubernetes.default.svc"
          namespace = "argocd"
        }
        syncPolicy = var.gitops_auto_sync ? {
          automated = { prune = true, selfHeal = true }
        } : {}
      }
    }
  })]

  # Kyverno's CRDs must exist before Argo CD syncs the policies.
  depends_on = [helm_release.argocd, helm_release.kyverno, helm_release.cloudnative_pg]
}
