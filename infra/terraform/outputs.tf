output "kube_context" {
  description = "kubectl context for the cluster. Pass it explicitly: kubectl --context <this>."
  value       = local.kube_context
  depends_on  = [terraform_data.cluster]
}

output "registry_push" {
  description = "Registry address to push images to from this machine."
  value       = "localhost:${var.registry_port}"
}

output "registry_cluster" {
  description = "Registry address the cluster pulls images from (use in image.repository)."
  value       = "${local.registry_name}:${var.registry_port}"
}

output "app_url" {
  description = "URL of the app once deployed."
  value       = var.http_port == 80 ? "http://${var.app_host}" : "http://${var.app_host}:${var.http_port}"
}

output "ingress_class" {
  description = "IngressClass installed by ingress-nginx."
  value       = "nginx"
}
