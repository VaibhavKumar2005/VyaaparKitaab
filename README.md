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

VyaparKitaab aims to bring bookkeeping, inventory, customer management, invoicing, payments, analytics, and AI-powered insights into a single cloud platform.

---

## 🎯 Problem Statement

Small businesses often struggle with:

- 📒 Paper-based bookkeeping
- 📦 Inventory tracking
- 🧾 Invoice management
- 👥 Customer records
- 💳 Payment and transaction management
- 📊 Business analytics
- 📈 Sales forecasting

Most existing solutions are either expensive, overly complex, or fragmented across multiple applications.

---

# ✨ Vision

Build an intelligent business operating system that helps MSMEs spend less time managing records and more time growing their business, while giving customers a secure and transparent view of their transactions and spending.

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
- Transaction and payment tracking

---

## 🔐 Secure Transaction Flow

VyaparKitaab is designed to support a secure purchase flow in which customer KYC can be handled by a dedicated KYC application, while OTP-based authentication provides an additional verification step before payment authorization.

A successful transaction can automatically generate a transactional email or message containing the purchase/receipt information.

```text
KYC Application
      │
      ▼
Customer Verification
      │
      ▼
Store Dashboard (B)
      │
      ▼
OTP Authentication
      │
      ▼
Payment Authorization
      │
      ▼
Transaction Recorded
      │
      ├── Store transaction status
      └── Customer purchase notification
```

---

## 🖥️ Dual Dashboard Model

### B — Store / Business Dashboard

The store-facing dashboard focuses on day-to-day transaction operations:

- Cash and digital payment records
- Orders and purchases
- Discounts applied
- Payment status
- Transaction history
- Refund/transaction records
- Business-side analytics

### C — Customer Dashboard

The customer-facing dashboard focuses on personal transaction visibility:

- Purchase history
- Payments made
- Discounts received/saved
- Transaction details
- Spending overview
- Category and subcategory-wise spending analysis

Spending can be organized hierarchically, for example:

```text
Spending
├── Food
│   ├── Restaurants
│   ├── Grocery
│   └── Delivery
├── Shopping
│   ├── Electronics
│   ├── Clothing
│   └── Household
└── Transport
    ├── Fuel
    ├── Cab
    └── Public Transport
```

This allows customers to understand **where their money is being spent**, rather than only viewing a flat list of transactions.

---

## 🤖 AI Features

- Invoice OCR
- Demand forecasting
- Customer segmentation
- Sales analytics
- Business anomaly detection
- Natural language business assistant
- Transaction/spending classification

Example:

> "How much profit did I make this month?"

> "Which products should I restock?"

> "How much did I spend on food this month?"

---

## 📊 Analytics Dashboard

- Revenue trends
- Monthly profit
- Inventory insights
- Top customers
- Fast-moving products
- Business KPIs
- Customer spending summaries
- Category-wise transaction analysis

---

# 🏗️ Proposed Architecture

```text
                 React + TypeScript
                         │
          ┌──────────────┴──────────────┐
          ▼                             ▼
   Store Dashboard (B)          Customer Dashboard (C)
          │                             │
          └──────────────┬──────────────┘
                         ▼
                   FastAPI Backend
                         │
       ┌─────────────────┼──────────────────┐
       ▼                 ▼                  ▼
 PostgreSQL       Payment Services    Authentication
       │                 │                  │
       │                 ▼                  ▼
       │          Transaction Flow     OTP Verification
       │
       └───────────────┬───────────────────┘
                       ▼
                 AI/ML Services
                       │
      ┌────────────────┼────────────────┐
      ▼                ▼                ▼
 Invoice OCR     Forecasting     Transaction Classification
                       │
                 Databricks
                       │
                  Delta Lake
                       │
                    MLflow
```

KYC is intended to be handled by a **separate KYC application/service**, rather than making the store dashboard responsible for full identity verification.

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

```text
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
├── database/
├── docker/
├── docs/
│   ├── README.md
│   └── SYNOPSIS.md
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
- [ ] Store dashboard
- [ ] Customer dashboard
- [ ] Transaction recording

---

## Phase 2 — Secure Payments & AI Integration

- [ ] KYC application integration
- [ ] OTP-based transaction authentication
- [ ] Payment integration
- [ ] Automated purchase notifications
- [ ] Invoice OCR
- [ ] Demand forecasting
- [ ] AI business insights
- [ ] Transaction classification
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
- Android application
- Regional language support
- Multi-store management
- Supplier analytics
- Advanced forecasting

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

---

## Quick Start (docker-compose)

This repository includes a minimal `docker-compose.yml` to run a Postgres database and the backend.

Start the stack:

```bash
docker-compose up --build
```

Open `http://localhost:8000` to see the simple frontend and `http://localhost:8000/health` for the API health.
