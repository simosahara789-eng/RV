# Reverb Bulk Draft Creator (Streamlit)

A practical Streamlit tool to generate and manage Reverb drafts from sold Reverb item URLs.

## What this app does

### API-dependent (official Reverb API)
- Validate API key (`/shop`)
- Create draft listings (`/listings`)
- Fetch your draft listings (best effort, endpoint/permission dependent)
- Publish a draft by listing ID (best effort, endpoint/permission dependent)

### Scraping-dependent (public sold listing pages)
- Extract title, description, image URLs, brand/model hints, and sold price (best effort)
- If sold page returns 403/blocked, fallback to authenticated listing lookup by item ID
- Extract extra specs when present in page metadata/text

### Not 100% automatable/reliable
- Perfect 1:1 clone of every field across all listing types
- Guaranteed image re-attachment for every account/API behavior
- Automatic category UUID mapping for all categories without dedicated mapping endpoints/data

---

## Project structure

- `app.py` – Streamlit UI with 2 pages (`Settings`, `Draft Tools`)
- `reverb_api.py` – Reverb API client (auth test, draft creation, draft fetch/publish, rate-limit handling)
- `scraper.py` – Sold page extraction logic
- `parser.py` – URL/item parsing + price/discount helpers
- `utils.py` – sanitization, retry, logging, report helpers
- `requirements.txt` – dependencies

---

## Local setup

1. Create and activate a virtual environment.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Provide API key via environment variable (recommended):
   ```bash
   export REVERB_API_KEY="your_api_key_here"
   ```
4. Run app:
   ```bash
   streamlit run app.py
   ```

---

## Streamlit Cloud deployment

1. Push this repo to GitHub.
2. In Streamlit Cloud, create app from the repo.
3. Set `app.py` as entry point.
4. Add secret in **App settings → Secrets**:
   ```toml
   REVERB_API_KEY = "your_api_key_here"
   ```
5. Deploy.

---

## `.env` or secrets examples

### `.env` example
```env
REVERB_API_KEY=your_api_key_here
LOG_LEVEL=INFO
```

### `.streamlit/secrets.toml` example
```toml
REVERB_API_KEY = "your_api_key_here"
LOG_LEVEL = "INFO"
```

---

## Usage flow

1. Open **Settings** page.
2. Enter API key and click **Test API key**.
3. Open **Draft Tools** page.
4. Choose action:
   - **Publish New Drafts**: create drafts from sold URLs in bulk.
   - **See My Drafts**: list current drafts and optionally publish a draft by ID.

### Publish New Drafts mode
1. Paste sold URLs (one per line).
2. Enter shipping profile ID and discount.
3. Optionally set quantity, location, and SKU prefix.
4. Click **Publish New Drafts**.
5. Watch per-item lifecycle (`pending`, `processing`, `success`/`failed`) and download CSV report.

### See My Drafts mode
1. Click **Refresh My Drafts** to fetch drafts.
2. Optionally enter a draft ID and click **Publish Draft**.

---

## Notes on limitations

- If sold price is missing even after API fallback, draft creation for that URL is skipped with an error row.
- If photos fail during API create, app retries without photos and reports warning.
- Category UUID may be unavailable from page data; app proceeds and flags warning.
- Some seller accounts may not have permission for draft-list or draft-publish endpoints.
