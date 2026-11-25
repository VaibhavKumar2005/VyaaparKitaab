variable "project_name" {
  description = "Prefix used for all Azure resource names."
  type        = string
  default     = "vyaaparkitaab"
}

variable "location" {
  description = "Azure region for backend, Postgres, ACR, and Key Vault."
  type        = string
  default     = "centralindia"
}

variable "static_web_app_location" {
  description = "Azure Static Web Apps region (closest supported region to India is eastasia)."
  type        = string
  default     = "eastasia"
}

variable "environment" {
  description = "Deployment environment label (dev, staging, prod)."
  type        = string
  default     = "prod"
}

variable "app_env" {
  description = "Application ENV setting passed to FastAPI (production or development)."
  type        = string
  default     = "production"
}

variable "backend_image" {
  description = "Container image for the FastAPI backend. Leave empty to use the ACR image built by scripts/deploy_azure.sh, or pass a public bootstrap image like ghcr.io/vaibhavkumar2005/vyaaparkitaab-backend:latest."
  type        = string
  default     = "ghcr.io/vaibhavkumar2005/vyaaparkitaab-backend:latest"
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

variable "secret_key" {
  description = "Strong JWT signing secret (>= 32 chars) stored in Key Vault."
  type        = string
  sensitive   = true
}

variable "encryption_key" {
  description = "Dedicated Fernet/PII encryption key stored in Key Vault (defaults to secret_key if omitted)."
  type        = string
  default     = ""
  sensitive   = true
}

variable "extra_allowed_origins" {
  description = "Additional CORS origins besides the Azure Static Web App HTTPS hostname."
  type        = list(string)
  default     = ["http://localhost:5173"]
}

variable "otp_provider" {
  description = "OTP provider: smtp_email, twilio_verify, twilio_sms, or sandbox."
  type        = string
  default     = "smtp_email"
}

variable "smtp_host" {
  description = "SMTP host for email OTP & receipts."
  type        = string
  default     = "smtp.gmail.com"
}

variable "smtp_port" {
  description = "SMTP TLS port."
  type        = number
  default     = 587
}

variable "smtp_user" {
  description = "SMTP login email address."
  type        = string
  default     = ""
}

variable "smtp_from_email" {
  description = "Sender address for transactional OTP & receipt emails."
  type        = string
  default     = ""
}

variable "smtp_password" {
  description = "SMTP App Password stored in Azure Key Vault."
  type        = string
  default     = ""
  sensitive   = true
}

variable "payment_gateway" {
  description = "Payment gateway mode: razorpay or sandbox."
  type        = string
  default     = "sandbox"
}

variable "payment_key_id" {
  description = "Razorpay Key ID (public)."
  type        = string
  default     = ""
}

variable "payment_key_secret" {
  description = "Razorpay Key Secret stored in Azure Key Vault."
  type        = string
  default     = ""
  sensitive   = true
}

variable "payment_webhook_secret" {
  description = "Razorpay Webhook Secret stored in Azure Key Vault."
  type        = string
  default     = ""
  sensitive   = true
}

variable "bank_data_provider" {
  description = "Account Aggregator provider: mock or setu_aa."
  type        = string
  default     = "mock"
}

variable "ocr_default_lang" {
  description = "Default Tesseract OCR language mode (auto, hin+eng, eng)."
  type        = string
  default     = "auto"
}

variable "ocr_gemini_model" {
  description = "Gemini model used for optional handwritten Hindi bill OCR."
  type        = string
  default     = "gemini-2.5-flash"
}

variable "gemini_api_key" {
  description = "Optional Gemini API Key stored in Azure Key Vault for handwritten Hindi OCR."
  type        = string
  default     = ""
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

variable "min_replicas" {
  description = "Minimum Container App replicas (1 avoids webhook cold starts and keeps warm memory state)."
  type        = number
  default     = 1
}
