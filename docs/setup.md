# Setup Guide

## Prerequisites

- Python 3.10+
- Node.js 18+
- npm or yarn

## Backend Setup

### 1. Create virtual environment

```bash
cd backend
python -m venv .venv
```

### 2. Activate environment

**Windows:**
```bash
.venv\Scripts\activate
```

**macOS/Linux:**
```bash
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Set environment variables (optional)

Create a `.env` file in `backend/`:

```bash
DATAHUB_BASE_URL=http://localhost:8080
DATAH_TOKEN=your_token_here
USE_MOCK_DATAHUB=true
API_BASE_URL=http://localhost:8000
ENV=development
```

### 5. Run the backend

```bash
uvicorn app.main:app --reload --port 8000
```

Verify at: http://localhost:8000/health

---

## Frontend Setup

### 1. Install dependencies

```bash
cd frontend
npm install
```

### 2. Set environment variables

Create `frontend/.env.local`:

```bash
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

### 3. Run the frontend

```bash
npm run dev
```

Verify at: http://localhost:3000

---

## Running in Mock Mode

By default, the app runs in **mock mode** using simulated metadata data. This is useful for:

- Local development
- Demo preparation
- Testing without external connector access

The mock data is defined in:
- `backend/app/services/mock_store.py`
- `frontend/lib/mock.ts`

---

## Connecting to Real DataHub

To use a real DataHub instance:

### 1. Set environment variables

```bash
export DATAHUB_BASE_URL=http://your-datahub:8080
export DATAHUB_TOKEN=your_gms_token
export USE_MOCK_DATAHUB=false
```

### 2. Update the datahub_client

Replace the mock methods in `backend/app/services/datahub_client.py` with real DataHub API calls using:

- DataHub MCP Server, or
- DataHub Agent Context Kit, or
- Direct GMS API calls

Example:

```python
def get_asset(self, urn: str) -> Dict[str, Any]:
    # Call DataHub GMS API
    response = requests.get(
        f"{self.base_url}/entities/{urn}",
        headers={"Authorization": f"Bearer {self.token}"}
    )
    response.raise_for_status()
    return parse_datahub_entity(response.json())
```

---

## Running Tests

### Backend tests

```bash
cd backend
pytest -v
```

### Frontend tests

```bash
cd frontend
npm run test
```

---

## Troubleshooting

### Backend won't start

- Check Python version: `python --version` (needs 3.10+)
- Ensure virtual environment is activated
- Check port 8000 is not in use

### Frontend won't start

- Check Node.js version: `node --version` (needs 18+)
- Run `npm install` again
- Check port 3000 is not in use

### API calls fail

- Verify backend is running at http://localhost:8000
- Check `NEXT_PUBLIC_API_BASE_URL` in frontend `.env.local`
- Try disabling mock mode to test real backend

### Write-back log not created

- Ensure `backend/data/` directory exists
- Check file permissions
- The log is created on first write

---

## Project Structure

```
datahub-incident-autopilot/
├── backend/
│   ├── app/
│   │   ├── api/           # API routers
│   │   ├── core/          # Config
│   │   ├── models/        # Pydantic models
│   │   ├── services/      # Business logic
│   │   ├── main.py        # FastAPI app
│   │   └── tests/         # Tests
│   ├── data/              # Writeback log
│   └── requirements.txt
├── frontend/
│   ├── app/               # Next.js pages
│   ├── components/        # React components
│   ├── lib/               # API client, types, mock
│   └── package.json
├── examples/              # Sample scenarios, artifacts, writebacks
├── docs/                  # Architecture, demo script, setup
└── README.md
```