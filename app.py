"""Streamlit app for bulk Reverb draft creation from sold listing URLs."""

from __future__ import annotations

import os
from decimal import Decimal

import streamlit as st

from parser import apply_discount, flatten_specs
from reverb_api import ReverbAPIClient, condition_to_uuid
from scraper import extract_listing_data
from utils import (
    ResultRow,
    dataframe_to_csv_bytes,
    parse_bulk_urls,
    sanitize_text,
    setup_logging,
    results_to_dataframe,
)

logger = setup_logging()

st.set_page_config(page_title="Reverb Bulk Draft Creator", layout="wide")
st.title("🎸 Reverb Bulk Draft Creator")

if "api_key" not in st.session_state:
    st.session_state.api_key = os.getenv("REVERB_API_KEY", "")

if "api_tested" not in st.session_state:
    st.session_state.api_tested = False

with st.expander("Workflow analysis: API vs scraping vs limitations", expanded=False):
    st.markdown(
        """
### A) Official API capabilities (best effort, account-permission dependent)
- Validate API key and account access.
- Create **draft** listings (`POST /listings`).
- Set core listing fields (title, description, make/brand, model, price, condition, shipping profile, quantity, sku, location).

### B) Data that usually requires sold-page extraction
- Sold item URLs, historical sold price, and page-level metadata.
- Public listing description and image URLs.
- Page specs that are not guaranteed in a single API response.

### C) Things not fully reliable to automate end-to-end
- Perfectly cloning every private/internal listing field.
- Guaranteed image migration in one request for all seller accounts/API versions.
- Category UUID inference from arbitrary text with 100% accuracy without extra mapping/endpoints.

This app uses robust fallbacks: create draft first, include warnings for missing fields, and continue processing instead of failing silently.
        """
    )

page = st.sidebar.radio("Navigate", ["Settings", "Bulk Draft Creator"])

if page == "Settings":
    st.subheader("API Settings")
    st.caption("Your API key is stored in Streamlit session (and optional env/secrets), never hardcoded.")

    api_key_input = st.text_input(
        "Reverb API Key",
        value=st.session_state.api_key,
        type="password",
        placeholder="REVERB_API_KEY",
    )

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Save key", use_container_width=True):
            st.session_state.api_key = api_key_input.strip()
            st.session_state.api_tested = False
            st.success("API key saved to current session.")
    with c2:
        if st.button("Test API key", use_container_width=True):
            key = api_key_input.strip()
            if not key:
                st.error("Please provide an API key first.")
            else:
                client = ReverbAPIClient(key, logger)
                ok, message = client.test_api_key()
                st.session_state.api_tested = ok
                if ok:
                    st.success(message)
                else:
                    st.error(message)

else:
    st.subheader("Bulk Draft Creator")
    if not st.session_state.api_key:
        st.warning("Go to Settings first and save/test your API key.")
        st.stop()

    with st.form("bulk_form"):
        url_text = st.text_area(
            "Sold Reverb URLs (one per line)",
            height=220,
            placeholder="https://reverb.com/item/94975758-fender-deluxe-reverb-1966-serviced?show_sold=true",
        )

        col1, col2, col3 = st.columns(3)
        with col1:
            shipping_profile_id = st.text_input("Shipping profile ID", placeholder="114252")
        with col2:
            discount_percent = st.number_input("Discount %", min_value=0.0, max_value=95.0, value=15.0, step=0.5)
        with col3:
            inventory_qty = st.number_input("Default quantity", min_value=1, max_value=999, value=1, step=1)

        col4, col5, col6 = st.columns(3)
        with col4:
            location = st.text_input("Location (optional)")
        with col5:
            sku_prefix = st.text_input("SKU prefix (optional)")
        with col6:
            trim_length = st.number_input("Trim description length (0 = off)", min_value=0, max_value=10000, value=0)

        remove_special = st.checkbox("Remove emojis / unusual characters", value=False)
        create_now = st.checkbox("Create drafts immediately", value=False)

        submitted = st.form_submit_button("Start processing", use_container_width=True)

    if submitted:
        urls = parse_bulk_urls(url_text)
        if not urls:
            st.error("No valid Reverb item URLs found.")
            st.stop()
        if not shipping_profile_id.strip().isdigit():
            st.error("Shipping profile ID must be numeric.")
            st.stop()

        client = ReverbAPIClient(st.session_state.api_key, logger)

        progress_bar = st.progress(0)
        status_placeholder = st.empty()
        table_placeholder = st.empty()

        results: list[ResultRow] = [
            ResultRow(source_url=source_url, status="pending", action="pending") for source_url in urls
        ]
        total = len(urls)

        for idx, url in enumerate(urls, start=1):
            status_placeholder.info(f"Processing {idx}/{total}: {url}")
            row = results[idx - 1]
            row.status = "processing"
            row.action = "processing"
            table_placeholder.dataframe(results_to_dataframe(results), use_container_width=True)

            try:
                extracted = extract_listing_data(url, api_client=client)
                price = Decimal(extracted.price_amount) if extracted.price_amount else None
                if price is None:
                    raise ValueError("Sold price unavailable after HTML + API fallback; cannot calculate discounted draft price.")
                discounted = apply_discount(price, discount_percent)
                display_currency = extracted.price_currency or "USD"

                title = sanitize_text(extracted.title, remove_special=remove_special, trim_length=160)
                description = sanitize_text(
                    extracted.description,
                    remove_special=remove_special,
                    trim_length=(trim_length if trim_length > 0 else None),
                )

                payload = {
                    "title": title,
                    "description": description or title,
                    "price": {"amount": f"{discounted}", "currency": extracted.price_currency or "USD"},
                    "shipping_profile_id": int(shipping_profile_id),
                    "make": extracted.brand or "Unknown",
                    "model": extracted.model or "Unknown",
                    "condition": {"uuid": condition_to_uuid(extracted.condition)},
                    "quantity": int(inventory_qty),
                }

                if location.strip():
                    payload["location"] = sanitize_text(location, remove_special=remove_special, trim_length=80)
                if sku_prefix.strip():
                    payload["sku"] = f"{sanitize_text(sku_prefix, remove_special=True)}-{idx}"
                if extracted.images:
                    payload["photos"] = extracted.images
                if extracted.category_uuid:
                    payload["category_uuid"] = extracted.category_uuid

                warnings = list(extracted.warnings)
                if extracted.specs:
                    warnings.append(flatten_specs(extracted.specs))

                if create_now:
                    success, _response_json, action_message = client.create_draft(payload)
                    if success:
                        row.status = "success"
                        row.title = title
                        row.sold_price = f"{price} {display_currency}"
                        row.discounted_price = f"{discounted} {display_currency}"
                        row.action = "draft created"
                        row.warnings = " | ".join(warnings + ([action_message] if action_message else []))
                    else:
                        row.status = "failed"
                        row.title = title
                        row.sold_price = f"{price} {display_currency}"
                        row.discounted_price = f"{discounted} {display_currency}"
                        row.action = "failed"
                        row.error = action_message
                        row.warnings = " | ".join(warnings)
                else:
                    row.status = "preview"
                    row.title = title
                    row.sold_price = f"{price} {display_currency}"
                    row.discounted_price = f"{discounted} {display_currency}"
                    row.action = "preview only"
                    row.warnings = " | ".join(warnings)

            except Exception as exc:
                logger.exception("Failed processing URL: %s", url)
                row.status = "failed"
                row.action = "failed"
                row.error = str(exc)

            progress_bar.progress(idx / total)
            table_placeholder.dataframe(results_to_dataframe(results), use_container_width=True)

        status_placeholder.success("Bulk run completed.")
        report_df = results_to_dataframe(results)
        st.markdown("### Final report")
        st.dataframe(report_df, use_container_width=True)
        st.download_button(
            "Download CSV report",
            data=dataframe_to_csv_bytes(report_df),
            file_name="reverb_bulk_draft_report.csv",
            mime="text/csv",
            use_container_width=True,
        )
