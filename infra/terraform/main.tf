locals {
  kube_context  = "k3d-${var.cluster_name}"
  registry_name = "k3d-${var.cluster_name}-registry.localhost"
  config_file   = "${path.module}/.generated/k3d-${var.cluster_name}.yaml"
}

# --- k3d cluster + registry ------------------------------------------------
#
# Created with the k3d CLI rather than a Terraform provider: there is no
# official k3d provider, and the community ones lag behind k3d releases.
# The CLI is driven from a config file that Terraform generates, so the
# cluster's shape still lives in variables, and `terraform destroy`
# removes it. See infra/README.md.

resource "local_file" "k3d_config" {
  filename        = local.config_file
  file_permission = "0644"
  content = templatefile("${path.module}/templates/k3d-config.yaml.tftpl", {
    cluster_name  = var.cluster_name
    agents        = var.agents
    k3s_image     = var.k3s_image
    http_port     = var.http_port
    https_port    = var.https_port
    registry_name = local.registry_name
    registry_port = var.registry_port
  })
}

resource "terraform_data" "cluster" {
  # Recreate the cluster when its configuration changes.
  triggers_replace = [local_file.k3d_config.content]

  # Destroy-time provisioners can only read `self`, so keep what they need here.
  input = {
    cluster_name  = var.cluster_name
    registry_name = local.registry_name
  }

  provisioner "local-exec" {
    command = "k3d cluster create --config '${local_file.k3d_config.filename}' --wait --timeout 300s"
  }

  provisioner "local-exec" {
    when    = destroy
    command = "k3d cluster delete '${self.input.cluster_name}' && (k3d registry delete '${self.input.registry_name}' 2>/dev/null || true)"
  }
}

# --- Cluster add-ons --------------------------------------------------------

resource "helm_release" "ingress_nginx" {
  name             = "ingress-nginx"
  repository       = "https://kubernetes.github.io/ingress-nginx"
  chart            = "ingress-nginx"
  version          = var.ingress_nginx_chart_version
  namespace        = "ingress-nginx"
  create_namespace = true
  wait             = true
  timeout          = 600

  values = [yamlencode({
    controller = {
      # k3s's built-in service load balancer exposes this on every node;
      # k3d forwards the host's ports to it.
      service = { type = "LoadBalancer" }
      ingressClassResource = {
        name    = "nginx"
        default = true
      }
      config = {
        # Overwrite (don't trust) X-Forwarded-* headers sent by clients,
        # since the app trusts X-Forwarded-Proto.
        "use-forwarded-headers" = "false"
      }
      resources = {
        requests = { cpu = "50m", memory = "96Mi" }
      }
    }
  })]

  depends_on = [terraform_data.cluster]
}

resource "helm_release" "cloudnative_pg" {
  name             = "cnpg"
  repository       = "https://cloudnative-pg.github.io/charts"
  chart            = "cloudnative-pg"
  version          = var.cloudnative_pg_chart_version
  namespace        = "cnpg-system"
  create_namespace = true
  wait             = true
  timeout          = 600

  values = [yamlencode({
    resources = {
      requests = { cpu = "50m", memory = "96Mi" }
    }
  })]

  depends_on = [terraform_data.cluster]
}
