variable "project_name" {
  description = "Prefix used for all Azure resource names."
  type        = string
  default     = "vyaaparkitaab"
}

variable "location" {
  description = "Azure region for the deployment."
  type        = string
  default     = "centralindia"
}

variable "environment" {
  description = "Deployment environment name."
  type        = string
  default     = "dev"
}

variable "backend_image" {
  description = "Container image for the FastAPI backend."
  type        = string
  default     = "ghcr.io/your-org/vyaaparkitaab-backend:latest"
}

variable "postgres_admin_username" {
  description = "Admin username for PostgreSQL Flexible Server."
  type        = string
  default     = "vyaaparadmin"
}

variable "postgres_admin_password" {
  description = "Admin password for PostgreSQL Flexible Server."
  type        = string
  sensitive   = true
}

variable "container_cpu" {
  description = "CPU units for the backend container app."
  type        = number
  default     = 0.5
}

variable "container_memory" {
  description = "Memory for the backend container app."
  type        = string
  default     = "1Gi"
}