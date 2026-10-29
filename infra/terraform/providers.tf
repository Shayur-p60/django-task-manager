# Always target the k3d cluster's context explicitly, never the current
# kubectl context, so other clusters in the same kubeconfig can't be
# touched by mistake.
provider "helm" {
  kubernetes = {
    config_path    = pathexpand(var.kubeconfig_path)
    config_context = local.kube_context
  }
}
