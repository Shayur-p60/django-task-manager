terraform {
  required_version = ">= 1.6"

  required_providers {
    helm = {
      source  = "hashicorp/helm"
      version = "~> 3.3"
    }
    local = {
      source  = "hashicorp/local"
      version = "~> 2.9"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.9"
    }
  }

  # State stays on this machine for now. To share it later, replace this
  # block with a remote backend (e.g. "s3", "gcs", "azurerm" or
  # Terraform Cloud) and run `terraform init -migrate-state`. Nothing else
  # in this configuration depends on where the state lives.
  backend "local" {
    path = "terraform.tfstate"
  }
}
