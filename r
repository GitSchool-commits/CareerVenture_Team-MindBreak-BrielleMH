# Career Venture Lab — TEAM-MINDBREAK (Pathway PSY-3 | AP Calculus)

**Student Owner:** Brielle Monroe-Holland  
**Pathway:** `PSY-3` — Psychology / Behavioral Science (Study Habits and Wellness Education Studio)  
**Course & Level:** AP Calculus (Advanced)  
**Status:** Stage 1 Build (Deterministic Core, Dated Event Ledger, AP Calculus Panel, Save/Restore JSON, Acceptance Tests)

> *Simulation Only: Fictional business, customers, transactions, and funding for educational purposes. Nonclinical educational workshops only.*

## Repository Structure

```text
├── app.py                 # Main Streamlit application (Stage 1)
├── requirements.txt       # Python dependencies for local & Render deployment
├── README.md              # Setup, testing, and deployment instructions
└── sample_data/
    └── monthly_fixture.csv # Exact PSY 3-month verification fixture
```

## Quick Start (Local)

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Launch the Streamlit app:
   ```bash
   streamlit run app.py
   ```
3. Open **Tab 5 (Stage 1 Acceptance Tests)** and click **Run All Stage 1 Acceptance Tests** to verify all checks pass, then click **Reset to Post-Startup Opening State ($3,000 Cash)** on **Tab 1** before starting Round 1.

## Render Deployment Command

```bash
streamlit run app.py --server.address 0.0.0.0 --server.port $PORT
```
