# WealthOS - Mutual Fund CAS Import

This project parses CAMS/KFintech Consolidated Account Statements (CAS) in PDF format to build a local portfolio dashboard. It extracts mutual fund transactions, matches them against a local database of AMFI schemes, and calculates current valuations, XIRR, and asset allocation.

## Prerequisites

- **Backend**: Python 3.10+
- **Frontend**: Node.js 18+

## Setup Instructions

### 1. Backend Setup

The backend is a FastAPI application that handles PDF parsing (via `pdfplumber`), database storage (SQLite via SQLAlchemy), and portfolio calculations.

```bash
cd backend

# Create and activate virtual environment (Windows)
python -m venv .venv
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the backend server (starts on http://localhost:8000)
uvicorn app.main:app --reload
```

### 2. Frontend Setup

The frontend is a Vite + Vanilla TypeScript SPA that provides a premium dashboard for your portfolio.

```bash
cd frontend

# Install dependencies
npm install

# Start the development server (starts on http://localhost:5173)
npm run dev
```

## CAS Request Instructions

To use this application, you need a detailed CAS PDF from CAMS or KFintech.

1. Go to [CAMS Online CAS Request](https://www.camsonline.com/Investors/Statements/Consolidated-Account-Statement) or [KFintech CAS](https://mfs.kfintech.com/investor/General/ConsolidatedAccountStatement).
2. Select **Detailed** statement type.
3. Choose a specific date range (from the beginning of your investments to today).
4. Enter your registered email address and a password.
5. You will receive an encrypted PDF in your email. Use this PDF and the password you provided on the Upload page.

## Testing & Fixture Guidance

When developing or running tests, you can use mock CAS files to verify the parser without exposing real financial data.

1. **Running Tests**: The backend uses `pytest`. Run tests via:
   ```bash
   cd backend
   pytest
   ```
2. **Generating Fixtures**: If you want to add new test fixtures for edge cases (e.g., SIP reversals, splits), create a dummy PDF using a PDF generator or heavily redact an existing one, then place it in `backend/tests/fixtures/`.
3. **Mocking Data**: The `/api/portfolio/summary` and other endpoints return standard JSON structures as defined in `schemas.py`.

## Features

- **Drag-and-Drop Upload**: Secure, local parsing of your encrypted PDF.
- **Import Review**: Intelligent matching of your PDF schemes with the AMFI database.
- **Dashboard**:
  - Live summary of Investment, Current Value, Gains, and XIRR.
  - Interactive Donut chart for Asset Allocation (using Chart.js).
  - Area chart for Portfolio Valuation History over time.
  - Sortable holdings table for detailed drill-downs.
- **Import History**: Keep track of previous imports and transaction additions.
