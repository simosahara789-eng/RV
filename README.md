# Reverb Bulk Draft Creator (Streamlit)

A practical Streamlit tool to generate Reverb **draft** listings from sold Reverb item URLs in bulk.

## What this app does

### API-dependent (official Reverb API)
- Validate API key (`/shop`) 
- Create draft listings (`/listings`) 
- Apply shipping profile ID, price, quantity, condition, and core fields

### Scraping-dependent (public sold listing pages)
- Extract title, description, image URLs, brand/model hints, and sold price (best effort)
- If sold page returns 403/blocked, fallback to authenticated listing lookup by item ID
- Extract extra specs when present in page metadata/text

### Not 100% automatable/reliable
- Perfect 1:1 clone of every field across all listing types
- Guaranteed image re-attachment for every account/API behavior
- Automatic category UUID mapping for all categories without dedicated mapping endpoints/data

The app implements safe fallbacks and logs warnings when fields are missing.

---

## Project structure

- `app.py` – Streamlit UI with 2 pages (Settings, Bulk Draft Creator)
- `reverb_api.py` – Reverb API client (auth test, draft creation, rate-limit handling)
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
3. Open **Bulk Draft Creator**.
4. Paste sold URLs (1 per line), set shipping profile ID and discount.
5. Optionally set quantity, location, SKU prefix, sanitization options.
6. Choose:
   - **Preview only** (unchecked create box), or
   - **Create drafts immediately** (checked).
7. Watch progress + final table; download CSV report.

---

## Notes on limitations

- If sold price is missing even after API fallback, draft creation for that URL is skipped with an error row.
- If photos fail during API create, app retries without photos and reports warning.
- Category UUID may be unavailable from page data; app proceeds and flags warning.
