# Postman API Spec Syncing

- **What it does**: Scans `specs/**/*.y*ml`, infers spec names, deletes any prior spec with the same name in the target Postman workspace, creates a new spec, generates/keeps the collection (replaces any same-name collection), attaches a client-credentials JWT pre-request script, and ensures Dev/QA/UAT/Prod environments exist with `base_url`.

- **Key functions (ingest_spec.py)**:
  - `_load_env()`: Loads `.env` if present when python-dotenv is missing.
  - `get_spec_name(path)`: Reads OpenAPI `info.title` (fallback to filename) for naming specs/collections.
  - `list_spec_files()`: Finds spec files under `specs/`.
  - `create_spec()` / `get_spec_id()`: Create a spec from a file; pull its ID.
  - `generate_collection()` / `wait_for_generated_collection()`: Generate a collection and poll until the ID is available.
  - `list_specs()` / `delete_spec()`: Clean up older specs with the same name.
  - `list_collections()` / `delete_collection()`: Replace any existing collection with the same name.
  - `set_prerequest_script()` / `check_prerequest_script()`: Apply the client-credentials pre-request script that fetches and caches a JWT.
  - `upsert_environment()`: Create/update Dev/QA/UAT/Prod environments with `base_url`.

- **Triggers (GitHub Actions)**: `.github/workflows/Sync API to Postman.yml` runs on `push` to `specs/**` (and manual dispatch). Uses Python 3.11 and `requirements.txt`.

- **Env vars / secrets**:
  - `POSTMAN_API_KEY`
  - `WORKSPACE_ID`
  - Postman environment values used by the pre-request script: `client_id`, `client_secret`, `token_url`.

- **Run locally**:
  ```bash
  python -m pip install -r requirements.txt
  POSTMAN_API_KEY=... WORKSPACE_ID=... python ingest_spec.py
  ```

- **Run via GitHub Actions**:
  - Set repo secrets `POSTMAN_API_KEY` and `POSTMAN_WORKSPACE_ID`.
  - Push changes under `specs/` or use the “Run workflow” button. The Action installs deps from `requirements.txt` and executes `python ingest_spec.py`.

**Business Value**
- Problem: Integrating a single refund API took 47 minutes (6 systems, 3 dead ends, personal workspace fallback). Typical internal API discovery takes 2–4 hours because specs, collections, environments, and auth are fragmented or inconsistent.
- Outcome: The workflow programmatically uploads OpenAPI specs, regenerates collections, injects a JWT client-credentials flow, upserts all environments, deduplicates old specs/collections, and enforces naming/structure/auth. CloudFormation export → GitHub → Postman means engineers start with a working, authenticated request in seconds instead of hours.

**ROI**
- Baseline savings from the 47-minute effort: 0.78 hours × 14 engineers = 10.92 hours/week → ~$1,638/week at $150/hr → ~$85,176/year.
- Broader impact: applies across ~47 APIs, cutting discovery-to-first-call from 2–4 hours to seconds; reduces onboarding/testing/integration time and reliance on tribal knowledge.

**Scaling Strategy**
- CloudFormation monitors API Gateway and auto-exports OpenAPI YAML to GitHub.
- GitHub Actions + ingestion script handle: spec creation, duplicate removal, collection regeneration, JWT pre-request dumped in and environment creation (if not already created)
- No per-API customization needed; new/updated APIs will flow into Postman consistently.

**Workspace Consolidation**
- Current state: hundreds of shared workspaces, inconsistent naming/ownership, scattered collections.
- Approach: adopt Postman team merge/governance; shift to domain workspaces (Payments, Auth, Risk, Ledger, etc.); move existing collections/specs into domain workspaces; treat ingestion automation as the source of truth; assign clear owners (eng lead + PM).
- Result: reduced sprawl, better coverage, predictable discovery paths for every internal API.
