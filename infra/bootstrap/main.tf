resource "random_string" "suffix" {
  length  = 6
  upper   = false
  special = false
}

locals {
  name_prefix        = lower(var.project_name)
  resource_group_name = "rg-${local.name_prefix}-${var.environment}-state"
  storage_account_name = substr(lower(replace("st${local.name_prefix}${random_string.suffix.result}tf", "-", "")), 0, 24)
}

resource "azurerm_resource_group" "state" {
  name     = local.resource_group_name
  location = var.location
}

resource "azurerm_storage_account" "state" {
  name                     = local.storage_account_name
  resource_group_name      = azurerm_resource_group.state.name
  location                 = azurerm_resource_group.state.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  min_tls_version          = "TLS1_2"

  blob_properties {
    versioning_enabled = true
  }
}

resource "azurerm_storage_container" "state" {
  name                  = var.state_container_name
  storage_account_id    = azurerm_storage_account.state.id
  container_access_type = "private"
}