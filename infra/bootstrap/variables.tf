variable "project_name" {
  description = "Prefix used for the bootstrap resources."
  type        = string
  default     = "vyaaparkitaab"
}

variable "location" {
  description = "Azure region for the bootstrap resources."
  type        = string
  default     = "centralindia"
}

variable "environment" {
  description = "Deployment environment name."
  type        = string
  default     = "dev"
}

variable "state_container_name" {
  description = "Blob container name used for Terraform state."
  type        = string
  default     = "tfstate"
}