output "resource_group_name" {
  value = azurerm_resource_group.main.name
}

output "container_app_url" {
  value = azurerm_container_app.backend.latest_revision_fqdn
}

output "postgres_fqdn" {
  value = azurerm_postgresql_flexible_server.main.fqdn
}

output "storage_account_name" {
  value = azurerm_storage_account.uploads.name
}

output "container_registry_login_server" {
  value = azurerm_container_registry.main.login_server
}