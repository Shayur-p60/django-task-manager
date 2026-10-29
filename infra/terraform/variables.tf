variable "cluster_name" {
  description = "Name of the k3d cluster. The kube context will be k3d-<name>."
  type        = string
  default     = "tasks"
}

variable "agents" {
  description = "Number of k3d agent (worker) nodes."
  type        = number
  default     = 2
}

variable "k3s_image" {
  description = "k3s node image. Empty uses the default for the installed k3d version."
  type        = string
  default     = ""
}

variable "http_port" {
  description = "Port on this machine that forwards to the ingress controller (HTTP)."
  type        = number
  default     = 80
}

variable "https_port" {
  description = "Port on this machine that forwards to the ingress controller (HTTPS)."
  type        = number
  default     = 443
}

variable "registry_port" {
  description = "Port on this machine for the local image registry."
  type        = number
  default     = 5111
}

variable "kubeconfig_path" {
  description = "Kubeconfig that k3d writes the cluster's context into."
  type        = string
  default     = "~/.kube/config"
}

variable "ingress_nginx_chart_version" {
  description = "ingress-nginx Helm chart version."
  type        = string
  default     = "4.15.1"
}

variable "cloudnative_pg_chart_version" {
  description = "CloudNativePG operator Helm chart version."
  type        = string
  default     = "0.29.1"
}

variable "app_host" {
  description = "Host name the app is served on through the ingress."
  type        = string
  default     = "tasks.localhost"
}

variable "argocd_chart_version" {
  description = "Argo CD Helm chart version."
  type        = string
  default     = "10.11.6"
}

variable "argocd_apps_chart_version" {
  description = "argocd-apps Helm chart version (creates the root Application)."
  type        = string
  default     = "2.0.7"
}

variable "kyverno_chart_version" {
  description = "Kyverno Helm chart version."
  type        = string
  default     = "3.9.2"
}

variable "gitops_repo_url" {
  description = "Git repository Argo CD syncs from."
  type        = string
  default     = "https://github.com/Shayur-p60/django-task-manager.git"
}

variable "gitops_revision" {
  description = <<-EOT
    Branch the root Application tracks. Keep "main"; override only to try
    work in progress, e.g. -var gitops_revision=feature/gitops. The child
    Applications in gitops/apps/ must track main to merge (checked in CI).
  EOT
  type        = string
  default     = "main"
}
