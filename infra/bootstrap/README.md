# Terraform Bootstrap

This folder provisions the Azure storage resources needed to store Terraform remote state for the main VyaparKitaab infrastructure.

Run this stack first with local state, then configure the main `infra/terraform` stack to use the created storage account and container.

Planned resources:
- Resource group
- Storage account for Terraform state
- Private blob container for the state file