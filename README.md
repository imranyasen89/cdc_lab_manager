# Centralized Pathology Sample Tracking & Lab Workflow System

A Flask-based pathology laboratory network tracking system designed for managing the complete lifecycle of sample collections, dispatching couriers, processing specimens at the G-8 Main Lab, entering HIMS diagnostic summaries, verifying reports, and recording deliveries to branches or patients.

---

## 1. Core Architecture

The system features:
*   **Workflow Engine (`app/services/workflow_service.py`)**: A state machine that enforces correct workflow transitions and role authorizations using transactional row locks.
*   **TAT Service (`app/services/tat_service.py`)**: Automatically computes diagnostic response times and compares actual stage durations against rules to flag delays dynamically.
*   **Interactive Maps**: Plotting hubs, riders, and route checkpoints via Leaflet + OpenStreetMap (no keys required; modular for Google Maps).
*   **QR Code Ready**: Automatically renders client-side QR codes linking back to each specimen's live tracking timeline page.
*   **Audit Logger**: Logs all state changes, actors, locations, and IPs in an immutable audit ledger.

---

## 2. Fast Setup & Launch

Run the following commands in your shell to get started:

### Step A: Set up Virtual Environment & Install
```bash
# Create virtual environment
python -m venv .venv

# Activate virtual environment
# On Windows (PowerShell):
.venv\Scripts\Activate.ps1
# On macOS / Linux:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Step B: Launch and Auto-Seed
When starting the server, it will automatically detect if the database has been created and populate it with seed hubs, employees, priorities, and 9 specimen requests in different statuses.
```bash
python run.py
```
Open your browser and navigate to: **`http://localhost:5000`**

### Step C: Run Unit Tests
```bash
python -m unittest tests/test_workflow.py
```

---

## 3. Seeded Accounts & Credentials

Use the following seeded accounts to test the dashboard view transitions:

| Employee Role | Username | Password | Context |
| :--- | :--- | :--- | :--- |
| **Super Admin** | `admin` | `admin123` | Users CRUD and audit trail logs |
| **Lab Manager** | `manager` | `manager123` | View performance averages and daily reports |
| **Lab Supervisor** | `supervisor` | `supervisor123` | Assign couriers to pending pickup requests |
| **Branch Staff** | `branch11` | `branch123` | Create dispatches (G-11 Hub) |
| **Lab Technologist** | `tech` | `tech123` | Receive, process, and enter results at G-8 |
| **Medical Verifier** | `verifier` | `verifier123` | Review, approve or reject reports |
| **Courier (Rider 1)** | `rider1` | `rider123` | Ahmed Courier (G-11 route) |
| **Courier (Rider 2)** | `rider2` | `rider123` | Bilal Courier (G-10 route) |
| **Courier (Rider 3)** | `rider3` | `rider123` | Hamza Courier (G-13 route) |
