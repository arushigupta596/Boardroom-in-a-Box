# Boardroom-in-a-Box

AI-powered retail analytics boardroom with autonomous agents for executive decision-making.

## Overview

Boardroom-in-a-Box simulates a C-suite executive meeting where AI agents (CEO, CFO, CMO, CIO) analyze retail data, identify insights, flag risks, and make recommendations. An Evaluator agent scores decisions and detects conflicts.

```
┌─────────────────────────────────────────────────────────────┐
│                    BOARDROOM-IN-A-BOX                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   👔 CEO ──→ 💰 CFO ──→ 📊 CMO ──→ 🔧 CIO ──→ ⚖️ Evaluator │
│                                                             │
│   Each agent:                                               │
│   • Queries their allowed data views (SQL guardrails)       │
│   • Generates KPIs and insights                             │
│   • Flags risks and concerns                                │
│   • Hands off to next agent with context                    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Features

### Agent System
- **CEO Agent**: Strategic overview - revenue, margin, growth, regional performance
- **CFO Agent**: Financial metrics - margin analysis, costs, discounts, inventory value
- **CMO Agent**: Marketing metrics - sales, customers, promotions, basket analysis
- **CIO Agent**: Data quality - freshness, health checks, coverage, integrity
- **Evaluator**: Scores decisions, detects conflicts, enforces constraints

### Security & Guardrails
- **Role-based views**: Each agent only sees their allowed data
- **SQL guardrails**: Allowlist enforcement, JOIN limits, row limits
- **No raw table access**: Agents query views, not base tables
- **Audit trail**: Full logging of queries and decisions

### LLM Integration (OpenRouter)
- **Intent Router**: Natural language → flow selection
- **SQL Analyst**: Questions → SQL with guardrails
- **Conflict Detector**: Finds soft conflicts between agents

### Flows
| Flow | Description | Agents |
|------|-------------|--------|
| KPI Review | General performance check | CEO → CFO → CMO → CIO → Evaluator |
| Trade-off | CFO vs CMO debate | CFO ↔ CMO → Evaluator |
| Scenario | What-if analysis | CFO → CMO → Evaluator |
| Root Cause | Why did X happen? | CIO → CFO → CMO → Evaluator |

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- OpenRouter API key (for LLM features)
- Supabase account (for cloud database) or PostgreSQL 14+ (for local)

### 1. Database Setup

**Option A: Supabase (Recommended for deployment)**

The project uses [Supabase](https://supabase.com) as the cloud database:

1. Create a Supabase project at https://supabase.com
2. Run the schema SQL in Supabase SQL Editor:
   ```sql
   -- Copy contents from supabase_schema.sql
   ```
3. Load data using the API loader:
   ```bash
   python load_to_supabase.py
   ```

**Option B: Local PostgreSQL**

```bash
# Create database
createdb retail_erp

# Load schema and data
python setup_retail_db.py
```

### 2. Backend Setup

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your settings:
#   - OPENROUTER_API_KEY (required for LLM features)
#   - DB_HOST, DB_USER, DB_PASSWORD (for Supabase or local DB)

# Start API server
cd api && uvicorn main:app --reload --port 8000
```

### 3. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

### 4. Open App

Navigate to **http://localhost:3000**

## Usage

### Web UI

1. Select a **Flow Type** (KPI Review, Trade-off, Scenario, Root Cause)
2. Select a **Display Mode** (Summary, Debate, Operator, Audit)
3. Click **Run Analysis**
4. Watch agents process in realtime
5. Click on any agent to see their conversation/insights
6. Review evaluation results and recommendations

### CLI

```bash
# Run KPI Review
python run_boardroom_v3.py --flow kpi-review --mode summary

# Run Trade-off debate
python run_boardroom_v3.py --flow trade-off

# Check data confidence only
python run_boardroom_v3.py --confidence-only

# Export board memo
python run_boardroom_v3.py --export memo --output memo.md
```

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check |
| `/api/flows/stream/{flow}` | GET | SSE streaming flow execution |
| `/api/flows/kpi-review` | POST | Run KPI Review |
| `/api/flows/trade-off` | POST | Run Trade-off debate |
| `/api/ask` | POST | Natural language question (LLM) |
| `/api/query` | POST | Natural language SQL (LLM) |
| `/api/confidence` | GET | Data confidence check |
| `/api/sessions/{id}` | GET | Get session details |
| `/api/sessions/{id}/memo` | GET | Get board memo |

### Natural Language (requires OpenRouter API key)

```bash
# Ask a question
curl -X POST http://localhost:8000/api/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "How are we doing this quarter?"}'

# Generate SQL from question
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What is revenue by category?", "agent": "CEO"}'
```

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                           Frontend                                │
│                      (Next.js + React)                           │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │FlowTimeline │  │  KPICards   │  │   EvaluatorScore        │  │
│  │(realtime)   │  │             │  │   ConflictPanel         │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
                              │ SSE
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│                         API Layer                                 │
│                    (FastAPI + Uvicorn)                           │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │/api/flows/* │  │  /api/ask   │  │    /api/sessions/*      │  │
│  │(streaming)  │  │  (LLM)      │  │    (audit)              │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│                      Agent Layer                                  │
│  ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐  ┌───────────┐  │
│  │  CEO   │  │  CFO   │  │  CMO   │  │  CIO   │  │ Evaluator │  │
│  │Agent   │  │Agent   │  │Agent   │  │Agent   │  │           │  │
│  └────────┘  └────────┘  └────────┘  └────────┘  └───────────┘  │
│       │           │           │           │             │        │
│       └───────────┴───────────┴───────────┴─────────────┘        │
│                              │                                    │
│                    ┌─────────▼─────────┐                         │
│                    │   SQL Guardrails  │                         │
│                    │  (view allowlist) │                         │
│                    └─────────┬─────────┘                         │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│                        Database                                   │
│                (Supabase / PostgreSQL)                           │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ ceo_views │ cfo_views │ cmo_views │ cio_views │ eval_views  │ │
│  └─────────────────────────────────────────────────────────────┘ │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                    retail schema                             │ │
│  │  pos_transaction │ product │ store │ inventory │ customer   │ │
│  └─────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
```

## Project Structure

```
boardroom-agents-for-retail/
├── agents/                    # Agent implementations
│   ├── base_agent.py         # Base class with guardrails
│   ├── ceo_agent_v2.py       # CEO agent
│   ├── cfo_agent_v2.py       # CFO agent
│   ├── cmo_agent_v2.py       # CMO agent
│   ├── cio_agent_v2.py       # CIO agent
│   ├── evaluator_v2.py       # Evaluator with scoring
│   ├── flow_orchestrator.py  # Flow execution
│   ├── confidence_engine.py  # Data confidence
│   ├── sql_guardrails.py     # Query validation
│   ├── intent_router.py      # LLM intent routing
│   ├── sql_analyst.py        # LLM SQL generation
│   ├── conflict_detector.py  # LLM conflict detection
│   └── llm_client.py         # OpenRouter client
├── api/                       # FastAPI backend
│   └── main.py
├── frontend/                  # Next.js frontend
│   ├── app/
│   │   └── page.tsx
│   └── components/
│       ├── FlowTimeline.tsx
│       ├── KPICard.tsx
│       ├── EvaluatorScore.tsx
│       └── ...
├── schema/                    # Database schema
├── data/                      # Sample data (Excel)
├── .env.example              # Environment template
├── requirements.txt          # Python dependencies
└── run_boardroom_v3.py       # CLI runner
```

## Configuration

### Environment Variables

```bash
# Required for LLM features
OPENROUTER_API_KEY=sk-or-v1-your-key

# Database - Supabase (recommended)
DB_HOST=db.your-project.supabase.co
DB_PORT=5432
DB_NAME=postgres
DB_USER=postgres
DB_PASSWORD=your-supabase-password
DB_SSLMODE=require

# Database - Local PostgreSQL (alternative)
# DB_HOST=localhost
# DB_PORT=5432
# DB_NAME=retail_erp
# DB_USER=your_user
# DB_PASSWORD=

# API
API_PORT=8000
```

### Supabase Setup

1. Create a project at [supabase.com](https://supabase.com)
2. Run `supabase_schema.sql` in the SQL Editor
3. Run `python load_to_supabase.py` to load data
4. Copy your database credentials to `.env`

## Data Model

The system uses a retail ERP data model with the following core entities:

### Core Tables (retail schema)

```
┌─────────────────────────────────────────────────────────────────────┐
│                         RETAIL DATA MODEL                           │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────┐    ┌──────────────────┐    ┌─────────────────────┐   │
│  │  store   │    │  pos_transaction │    │ pos_transaction_line│   │
│  ├──────────┤    ├──────────────────┤    ├─────────────────────┤   │
│  │store_id  │◄───│store_id          │    │txn_id               │   │
│  │name      │    │txn_id            │◄───│sku_id               │   │
│  │region    │    │customer_id       │    │qty                  │   │
│  │format    │    │txn_ts            │    │unit_price           │   │
│  └──────────┘    │payment_method    │    │discount             │   │
│                  │total_amount      │    │line_total           │   │
│                  └──────────────────┘    └─────────────────────┘   │
│                           │                        │               │
│                           ▼                        ▼               │
│  ┌──────────┐    ┌──────────────────┐    ┌─────────────────────┐   │
│  │ customer │    │     product      │    │   store_inventory   │   │
│  ├──────────┤    ├──────────────────┤    ├─────────────────────┤   │
│  │cust_id   │    │sku_id            │    │store_id             │   │
│  │segment   │    │product_name      │    │sku_id               │   │
│  │join_date │    │category          │    │on_hand_qty          │   │
│  │region    │    │subcategory       │    │unit_cost            │   │
│  └──────────┘    │brand             │    │last_updated         │   │
│                  │unit_cost         │    └─────────────────────┘   │
│                  │list_price        │                              │
│                  └──────────────────┘                              │
│                                                                     │
│  ┌──────────────────┐    ┌──────────────────┐    ┌──────────────┐  │
│  │  purchase_order  │    │  goods_receipt   │    │transfer_order│  │
│  ├──────────────────┤    ├──────────────────┤    ├──────────────┤  │
│  │po_id             │◄───│po_id             │    │to_id         │  │
│  │supplier_id       │    │grn_id            │    │from_dc_id    │  │
│  │dc_id             │    │received_date     │    │to_store_id   │  │
│  │order_date        │    │status            │    │ship_date     │  │
│  │expected_date     │    └──────────────────┘    │status        │  │
│  │status            │                            └──────────────┘  │
│  └──────────────────┘                                              │
└─────────────────────────────────────────────────────────────────────┘
```

### Sample Data

| Table | Records | Description |
|-------|---------|-------------|
| `store` | 20 | Retail stores across 4 regions |
| `product` | 180 | SKUs across 6 categories |
| `customer` | 5,000 | Customer profiles with segments |
| `pos_transaction` | ~9,000 | Point-of-sale transactions |
| `pos_transaction_line` | ~90,000 | Line items (10 per transaction avg) |
| `store_inventory` | ~3,600 | Current inventory by store/SKU |
| `purchase_order` | 450 | POs to suppliers |
| `goods_receipt` | 256 | Received shipments |
| `transfer_order` | 600 | Inter-store transfers |

### Data Characteristics

- **Time Period**: Rolling 90-day window (updated to current date)
- **Regions**: North, South, East, West
- **Categories**: Electronics, Apparel, Home & Garden, Sports, Beauty, Food & Beverage
- **Store Formats**: Flagship, Standard, Express, Outlet

---

## Decision Constraints

The Evaluator enforces hard constraints that cannot be violated. These represent non-negotiable business rules.

### Hard Constraints

| Constraint | Threshold | Operator | Description |
|------------|-----------|----------|-------------|
| **Margin Floor** | 18% | ≥ | Minimum acceptable gross margin. Recommendations that would push margin below this are blocked. |
| **Max Discount Cap** | 12% | ≤ | Maximum average discount rate. Prevents excessive promotional discounting. |
| **Inventory Days Min** | 30 days | ≥ | Minimum days of inventory. Below this risks stockouts. |
| **Inventory Days Max** | 90 days | ≤ | Maximum days of inventory. Above this indicates overstock/cash flow risk. |

### Constraint Violations

When a constraint is violated:
1. The Evaluator flags it as **VIOLATED**
2. A conflict is created with resolution guidance
3. Recommendations are adjusted or blocked
4. Risk level is elevated

Example violation:
```
Constraint: Inventory Days Max (90 days)
Actual: 144.3 days
Status: VIOLATED
Resolution: Run clearance promotions on slow movers
```

### Soft Signals (LLM-Detected)

In addition to hard constraints, the LLM Conflict Detector identifies soft signals:

| Signal Type | Example | Severity |
|-------------|---------|----------|
| **Contradictory Recommendations** | CFO: "Cut promos" vs CMO: "Increase promos" | High |
| **Priority Misalignment** | CEO focuses growth, CFO focuses cost cutting | Medium |
| **Missing Assumptions** | CMO assumes inventory availability | Low |
| **Time Horizon Conflict** | Short-term revenue vs long-term brand | Medium |

---

## Evaluation Scoring

The Evaluator scores decisions across 5 dimensions:

| Dimension | Weight | What It Measures |
|-----------|--------|------------------|
| **Profitability Safety** | 30% | Margin protection, cost control |
| **Growth Impact** | 25% | Revenue growth, market expansion |
| **Inventory Health** | 20% | Stock levels, turnover, cash flow |
| **Operational Risk** | 15% | Execution complexity, conflicts |
| **Data Confidence** | 10% | Data freshness, quality, coverage |

### Score Interpretation

| Score | Risk Level | Meaning |
|-------|------------|---------|
| 8.0 - 10.0 | Low | Safe to proceed with recommendations |
| 6.0 - 7.9 | Medium | Review flagged items before proceeding |
| 4.0 - 5.9 | High | Significant concerns, manual review required |
| 0.0 - 3.9 | Critical | Do not proceed, blocking issues present |

---

## Data Confidence Engine

Before running any analysis, the CIO's Confidence Engine validates data quality.

### Confidence Factors

| Factor | Weight | What It Checks |
|--------|--------|----------------|
| **Data Freshness** | 30% | How recent is the data? (target: ≤1 day old) |
| **Health Checks** | 25% | Are data quality rules passing? |
| **Data Quality** | 20% | Missing values, invalid records |
| **Coverage** | 15% | Do we have data for all expected entities? |
| **Integrity** | 10% | Referential integrity, orphan records |

### Confidence Levels

| Level | Score | Can Proceed? |
|-------|-------|--------------|
| **High** | 80-100 | Yes - full confidence |
| **Medium** | 60-79 | Yes - with warnings |
| **Low** | 40-59 | No - blocking issues |
| **Critical** | 0-39 | No - data unreliable |

### Health Checks Run

1. **Orphan SKUs** - SKUs in transactions but not in product master
2. **Bad Transaction Prices** - Null or negative prices
3. **Negative Inventory** - On-hand quantity < 0
4. **Orphan Transactions** - Transactions without matching store
5. **Data Freshness** - Transactions in last 30 days
6. **PO Line Integrity** - PO lines with invalid SKU references

## LLM Models (via OpenRouter)

| Model | Use Case |
|-------|----------|
| Claude Haiku | Intent routing (fast) |
| Claude Haiku | SQL generation (fast) |
| Claude Haiku | Conflict detection |

To change models, edit `agents/llm_client.py`.

## Development

### Run Tests

```bash
python -m pytest tests/ -v
```

### Add New Agent

1. Create `agents/new_agent_v2.py` extending `BaseAgent`
2. Define `ALLOWED_VIEWS` for the agent
3. Implement `analyze()` method
4. Add to `flow_orchestrator.py`

### Add New View

1. Create view in PostgreSQL under appropriate schema
2. Add to agent's `ALLOWED_VIEWS`
3. Update `sql_analyst.py` schema definitions

## License

MIT
