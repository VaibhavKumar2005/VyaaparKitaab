# Terraform Infrastructure

This folder contains the Azure Terraform scaffold for VyaparKitaab.

Planned resources:

- Resource group
- Log Analytics and monitoring
- Storage for uploads
- Azure Container Registry
- Azure Database for PostgreSQL Flexible Server
- Azure Container Apps environment
- Containerized backend app

The stack is intentionally kept practical for a student showcase while still looking enterprise-ready.

## How to Use

1. Apply the bootstrap stack in `infra/bootstrap` first to create the Terraform state storage account and container.
2. Use the outputs from that bootstrap stack to initialize the main stack in `infra/terraform`.
3. Configure the GitHub Actions workflow in `.github/workflows/terraform.yml` for CI checks and manual Azure deployment.

## Workflow Notes

- The CI job runs `terraform init -backend=false`, `fmt`, and `validate` on pull requests and pushes.
- The deploy job is triggered manually with `workflow_dispatch` and asks for the Azure OIDC values plus the Terraform state backend details.
- The backend is configured through Azure Blob Storage, which gives the project remote state and state locking.
