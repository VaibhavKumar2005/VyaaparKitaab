resource "random_string" "suffix" {
  length  = 6
  upper   = false
  special = false
}

data "azurerm_client_config" "current" {}

locals {
  name_prefix    = lower(var.project_name)
  resource_group = "rg-${local.name_prefix}-${var.environment}"
  suffix         = random_string.suffix.result
  app_env        = var.environment == "prod" ? "production" : var.app_env
  allowed_origins = join(
    ",",
    distinct(
      compact(
        concat(
          ["https://${azurerm_static_web_app.frontend.default_host_name}"],
          var.extra_allowed_origins,
        )
      )
    )
  )
  effective_backend_image = (
    var.backend_image != ""
    ? var.backend_image
    : "${azurerm_container_registry.main.login_server}/vyaaparkitaab-backend:latest"
  )
}

resource "azurerm_resource_group" "main" {
  name     = local.resource_group
  location = var.location
}

resource "azurerm_log_analytics_workspace" "main" {
  name                = "law-${local.name_prefix}-${local.suffix}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
}

resource "azurerm_application_insights" "main" {
  name                = "appi-${local.name_prefix}-${local.suffix}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  workspace_id        = azurerm_log_analytics_workspace.main.id
  application_type    = "web"
}

resource "azurerm_storage_account" "uploads" {
  name                     = replace("st${local.name_prefix}${local.suffix}", "-", "")
  resource_group_name      = azurerm_resource_group.main.name
  location                 = azurerm_resource_group.main.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  min_tls_version          = "TLS1_2"

  blob_properties {
    versioning_enabled = true
  }
}

resource "azurerm_storage_container" "documents" {
  name                  = "documents"
  storage_account_id    = azurerm_storage_account.uploads.id
  container_access_type = "private"
}

resource "azurerm_container_registry" "main" {
  name                = replace("acr${local.name_prefix}${local.suffix}", "-", "")
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "Basic"
  admin_enabled       = false
}

resource "azurerm_key_vault" "main" {
  name                       = replace("kv-${local.name_prefix}-${local.suffix}", "-", "")
  location                   = azurerm_resource_group.main.location
  resource_group_name        = azurerm_resource_group.main.name
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  purge_protection_enabled   = false
  soft_delete_retention_days = 7
  rbac_authorization_enabled = true
}

resource "azurerm_role_assignment" "deployer_key_vault" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = data.azurerm_client_config.current.object_id
}

resource "azurerm_key_vault_secret" "secret_key" {
  name         = "secret-key"
  value        = var.secret_key
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [azurerm_role_assignment.deployer_key_vault]
}

resource "azurerm_key_vault_secret" "encryption_key" {
  name         = "encryption-key"
  value        = var.encryption_key != "" ? var.encryption_key : var.secret_key
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [azurerm_role_assignment.deployer_key_vault]
}

resource "azurerm_key_vault_secret" "postgres_password" {
  name         = "postgres-password"
  value        = var.postgres_admin_password
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [azurerm_role_assignment.deployer_key_vault]
}

resource "azurerm_key_vault_secret" "database_url" {
  name         = "database-url"
  value        = "postgresql://${var.postgres_admin_username}:${urlencode(var.postgres_admin_password)}@${azurerm_postgresql_flexible_server.main.fqdn}:5432/${azurerm_postgresql_flexible_server_database.app.name}"
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [azurerm_role_assignment.deployer_key_vault]
}

resource "azurerm_key_vault_secret" "smtp_password" {
  count        = var.smtp_password != "" ? 1 : 0
  name         = "smtp-password"
  value        = var.smtp_password
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [azurerm_role_assignment.deployer_key_vault]
}

resource "azurerm_key_vault_secret" "payment_key_secret" {
  count        = var.payment_key_secret != "" ? 1 : 0
  name         = "payment-key-secret"
  value        = var.payment_key_secret
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [azurerm_role_assignment.deployer_key_vault]
}

resource "azurerm_key_vault_secret" "payment_webhook_secret" {
  count        = var.payment_webhook_secret != "" ? 1 : 0
  name         = "payment-webhook-secret"
  value        = var.payment_webhook_secret
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [azurerm_role_assignment.deployer_key_vault]
}

resource "azurerm_key_vault_secret" "gemini_api_key" {
  count        = var.gemini_api_key != "" ? 1 : 0
  name         = "gemini-api-key"
  value        = var.gemini_api_key
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [azurerm_role_assignment.deployer_key_vault]
}

resource "azurerm_postgresql_flexible_server" "main" {
  name                   = "psql-${local.name_prefix}-${local.suffix}"
  resource_group_name    = azurerm_resource_group.main.name
  location               = azurerm_resource_group.main.location
  version                = "16"
  sku_name               = "B_Standard_B1ms"
  storage_mb             = 32768
  administrator_login    = var.postgres_admin_username
  administrator_password = var.postgres_admin_password
  zone                   = "1"
}

resource "azurerm_postgresql_flexible_server_firewall_rule" "container_apps" {
  name             = "allow-azure-services"
  server_id        = azurerm_postgresql_flexible_server.main.id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}

resource "azurerm_postgresql_flexible_server_database" "app" {
  name      = "vyaaparkitaab"
  server_id = azurerm_postgresql_flexible_server.main.id
  charset   = "UTF8"
  collation = "en_US.utf8"
}

resource "azurerm_static_web_app" "frontend" {
  name                = "swa-${local.name_prefix}-${local.suffix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = var.static_web_app_location
  sku_tier            = "Free"
  sku_size            = "Free"
}

resource "azurerm_container_app_environment" "main" {
  name                       = "cae-${local.name_prefix}-${local.suffix}"
  location                   = azurerm_resource_group.main.location
  resource_group_name        = azurerm_resource_group.main.name
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id
}

resource "azurerm_user_assigned_identity" "backend" {
  name                = "id-${local.name_prefix}-${local.suffix}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
}

resource "azurerm_role_assignment" "backend_key_vault" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.backend.principal_id
}

resource "azurerm_role_assignment" "backend_acr_pull" {
  scope                = azurerm_container_registry.main.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.backend.principal_id
}

resource "azurerm_container_app" "backend" {
  name                         = "app-${local.name_prefix}-${local.suffix}"
  resource_group_name          = azurerm_resource_group.main.name
  container_app_environment_id = azurerm_container_app_environment.main.id
  revision_mode                = "Single"

  depends_on = [
    azurerm_role_assignment.backend_key_vault,
    azurerm_role_assignment.backend_acr_pull,
  ]

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.backend.id]
  }

  registry {
    server   = azurerm_container_registry.main.login_server
    identity = azurerm_user_assigned_identity.backend.id
  }

  secret {
    name                = "secret-key"
    key_vault_secret_id = azurerm_key_vault_secret.secret_key.versionless_id
    identity            = azurerm_user_assigned_identity.backend.id
  }

  secret {
    name                = "encryption-key"
    key_vault_secret_id = azurerm_key_vault_secret.encryption_key.versionless_id
    identity            = azurerm_user_assigned_identity.backend.id
  }

  secret {
    name                = "database-url"
    key_vault_secret_id = azurerm_key_vault_secret.database_url.versionless_id
    identity            = azurerm_user_assigned_identity.backend.id
  }

  dynamic "secret" {
    for_each = azurerm_key_vault_secret.smtp_password
    content {
      name                = "smtp-password"
      key_vault_secret_id = secret.value.versionless_id
      identity            = azurerm_user_assigned_identity.backend.id
    }
  }

  dynamic "secret" {
    for_each = azurerm_key_vault_secret.payment_key_secret
    content {
      name                = "payment-key-secret"
      key_vault_secret_id = secret.value.versionless_id
      identity            = azurerm_user_assigned_identity.backend.id
    }
  }

  dynamic "secret" {
    for_each = azurerm_key_vault_secret.payment_webhook_secret
    content {
      name                = "payment-webhook-secret"
      key_vault_secret_id = secret.value.versionless_id
      identity            = azurerm_user_assigned_identity.backend.id
    }
  }

  dynamic "secret" {
    for_each = azurerm_key_vault_secret.gemini_api_key
    content {
      name                = "gemini-api-key"
      key_vault_secret_id = secret.value.versionless_id
      identity            = azurerm_user_assigned_identity.backend.id
    }
  }

  template {
    container {
      name   = "backend"
      image  = local.effective_backend_image
      cpu    = var.container_cpu
      memory = var.container_memory

      env {
        name  = "ENV"
        value = local.app_env
      }

      env {
        name  = "ALLOWED_ORIGINS"
        value = local.allowed_origins
      }

      env {
        name        = "DATABASE_URL"
        secret_name = "database-url"
      }

      env {
        name        = "SECRET_KEY"
        secret_name = "secret-key"
      }

      env {
        name        = "ENCRYPTION_KEY"
        secret_name = "encryption-key"
      }

      env {
        name  = "OTP_PROVIDER"
        value = var.otp_provider
      }

      env {
        name  = "SMTP_HOST"
        value = var.smtp_host
      }

      env {
        name  = "SMTP_PORT"
        value = tostring(var.smtp_port)
      }

      env {
        name  = "SMTP_USER"
        value = var.smtp_user
      }

      env {
        name  = "SMTP_FROM_EMAIL"
        value = var.smtp_from_email
      }

      dynamic "env" {
        for_each = azurerm_key_vault_secret.smtp_password
        content {
          name        = "SMTP_PASSWORD"
          secret_name = "smtp-password"
        }
      }

      env {
        name  = "PAYMENT_GATEWAY"
        value = var.payment_gateway
      }

      env {
        name  = "PAYMENT_KEY_ID"
        value = var.payment_key_id
      }

      dynamic "env" {
        for_each = azurerm_key_vault_secret.payment_key_secret
        content {
          name        = "PAYMENT_KEY_SECRET"
          secret_name = "payment-key-secret"
        }
      }

      dynamic "env" {
        for_each = azurerm_key_vault_secret.payment_webhook_secret
        content {
          name        = "PAYMENT_WEBHOOK_SECRET"
          secret_name = "payment-webhook-secret"
        }
      }

      env {
        name  = "BANK_DATA_PROVIDER"
        value = var.bank_data_provider
      }

      env {
        name  = "OCR_DEFAULT_LANG"
        value = var.ocr_default_lang
      }

      env {
        name  = "OCR_GEMINI_MODEL"
        value = var.ocr_gemini_model
      }

      dynamic "env" {
        for_each = azurerm_key_vault_secret.gemini_api_key
        content {
          name        = "GEMINI_API_KEY"
          secret_name = "gemini-api-key"
        }
      }

      env {
        name  = "UPLOAD_CONTAINER"
        value = azurerm_storage_container.documents.name
      }

      liveness_probe {
        transport               = "HTTP"
        path                    = "/api/v1/health"
        port                    = 8000
        interval_seconds        = 30
        timeout                 = 5
        failure_count_threshold = 3
      }

      readiness_probe {
        transport               = "HTTP"
        path                    = "/api/v1/health"
        port                    = 8000
        interval_seconds        = 15
        timeout                 = 5
        success_count_threshold = 1
        failure_count_threshold = 3
      }
    }

    min_replicas = var.min_replicas
    max_replicas = 3
  }

  ingress {
    external_enabled = true
    target_port      = 8000
    transport        = "auto"

    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }
}

resource "azurerm_monitor_metric_alert" "backend_http_5xx" {
  name                = "alert-${local.name_prefix}-http5xx"
  resource_group_name = azurerm_resource_group.main.name
  scopes              = [azurerm_container_app.backend.id]
  description         = "Container App HTTP 5xx rate is elevated"
  severity            = 2
  frequency           = "PT1M"
  window_size         = "PT5M"

  criteria {
    metric_namespace = "Microsoft.App/containerApps"
    metric_name      = "Http5xx"
    aggregation      = "Total"
    operator         = "GreaterThan"
    threshold        = 5
  }
}

resource "azurerm_monitor_metric_alert" "backend_cpu" {
  name                = "alert-${local.name_prefix}-cpu"
  resource_group_name = azurerm_resource_group.main.name
  scopes              = [azurerm_container_app.backend.id]
  description         = "Container App CPU usage is elevated"
  severity            = 2
  frequency           = "PT1M"
  window_size         = "PT5M"

  criteria {
    metric_namespace = "Microsoft.App/containerApps"
    metric_name      = "CpuPercentage"
    aggregation      = "Average"
    operator         = "GreaterThan"
    threshold        = 80
  }
}
