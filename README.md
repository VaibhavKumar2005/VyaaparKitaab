# 📒 VyaparKitaab

> A Cloud-Based Intelligent Business Notebook for Indian MSMEs

![Status](https://img.shields.io/badge/Status-In%20Development-orange)
![License](https://img.shields.io/badge/License-MIT-blue)
![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react)
![FastAPI](https://img.shields.io/badge/FastAPI-0.116-009688?logo=fastapi)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-17-4169E1?logo=postgresql)
![Docker](https://img.shields.io/badge/Docker-Enabled-2496ED?logo=docker)
![OCI](https://img.shields.io/badge/Cloud-Oracle%20Cloud-F80000)

---

## 📖 Overview

**VyaparKitaab** is an AI-powered digital business notebook designed specifically for **Indian Micro, Small and Medium Enterprises (MSMEs)**.

Many small businesses still depend on paper registers, WhatsApp chats, Excel sheets, and disconnected software to manage their daily operations. This often leads to manual errors, duplicate work, and poor visibility into business performance.

VyaparKitaab aims to bring bookkeeping, inventory, customer management, invoicing, analytics, and AI-powered insights into a single cloud platform.

---

## 🎯 Problem Statement

Small businesses often struggle with:

- 📒 Paper-based bookkeeping
- 📦 Inventory tracking
- 🧾 Invoice management
- 👥 Customer records
- 📊 Business analytics
- 📈 Sales forecasting

Most existing solutions are either expensive, overly complex, or fragmented across multiple applications.

---

# ✨ Vision

Build an intelligent business operating system that helps MSMEs spend less time managing records and more time growing their business.

---

# 🚀 Planned Features

## 📚 Business Management

- Digital bookkeeping
- Customer management
- Product catalog
- Inventory management
- Sales tracking
- Purchase tracking
- Invoice generation

---

## 🤖 AI Features

- Invoice OCR
- Demand forecasting
- Customer segmentation
- Sales analytics
- Business anomaly detection
- Natural language business assistant

Example:

> "How much profit did I make this month?"

> "Which products should I restock?"

---

## 📊 Analytics Dashboard

- Revenue trends
- Monthly profit
- Inventory insights
- Top customers
- Fast-moving products
- Business KPIs

---

# 🏗️ Proposed Architecture

```
                React + TypeScript
                       │
                       ▼
                 FastAPI Backend
                       │
     ┌─────────────────┼──────────────────┐
     ▼                 ▼                  ▼
PostgreSQL      AI/ML Services      Authentication
                     │
      ┌──────────────┼───────────────┐
      ▼              ▼               ▼
 Invoice OCR   Forecasting      LLM Assistant
                     │
               Databricks
                     │
                Delta Lake
                     │
                  MLflow
```

---

# 🛠 Tech Stack

## Frontend

- React
- TypeScript
- Tailwind CSS

## Backend

- FastAPI
- SQLAlchemy
- Pydantic

## Database

- PostgreSQL

## AI & ML

- PyTorch
- Scikit-learn
- OCR
- LLM APIs

## Data Engineering

- Databricks
- Delta Lake
- MLflow

## Cloud

- Oracle Cloud Infrastructure (OCI)

## DevOps

- Docker
- GitHub Actions

---

# 📂 Project Structure

```
VyaparKitaab
│
├── frontend/
├── backend/
│   ├── app/
│   ├── routers/
│   ├── models/
│   ├── schemas/
│   ├── services/
│   └── core/
│
├── ai/
│
├── database/
│
├── docker/
│
├── docs/
│
├── .github/
│   └── workflows/
│
├── README.md
└── LICENSE
```

---

# 🛣️ Development Roadmap

## Phase 1 — MVP

- [ ] Project setup
- [ ] User authentication
- [ ] Inventory management
- [ ] Customer management
- [ ] Invoice generation
- [ ] Dashboard

---

## Phase 2 — AI Integration

- [ ] Invoice OCR
- [ ] Demand forecasting
- [ ] AI business insights
- [ ] LLM assistant

---

## Phase 3 — Cloud Deployment

- [ ] OCI deployment
- [ ] Docker
- [ ] CI/CD
- [ ] Monitoring

---

## Phase 4 — Future Enhancements

- WhatsApp integration

---

## Quick Start

Run the FastAPI backend with Docker (recommended):

```bash
docker build -t vyaaparkitaab-backend -f docker/Dockerfile .
docker run --env-file .env.example -p 8000:8000 vyaaparkitaab-backend
```

Or run locally with Uvicorn:

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Contributing

See `CONTRIBUTING.md` for guidelines on setting up a development environment, coding style, and submitting pull requests.
- Android application
- Regional language support
- Multi-store management
- Supplier analytics
- Advanced forecasting

---

# 📸 Screenshots

Coming soon.

---

# 📊 Project Status

🚧 **Currently under active development**

This repository documents the complete development journey of VyaparKitaab—from project planning to a working AI-powered prototype.

---

# 👥 Team

**Vaibhav Kumar**

B.Tech CSE (AI & ML)

GLA University

---

**Jagriti Gupta**

B.Tech CSE (AI & ML)

GLA University

---

# 📜 License

This project is licensed under the MIT License.

---

# ⭐ Support

If you found this project interesting, consider giving it a ⭐ on GitHub.
