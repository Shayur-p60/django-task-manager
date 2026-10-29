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
