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

output "argocd_admin_password" {
  description = "Argo CD admin password. Read it with: terraform output -raw argocd_admin_password"
  value       = random_password.argocd_admin.result
  sensitive   = true
}

output "argocd_ui" {
  description = "How to open the Argo CD UI (not exposed via ingress)."
  value       = "kubectl --context ${local.kube_context} -n argocd port-forward svc/argocd-server 8443:443, then https://localhost:8443 (user: admin)"
}
