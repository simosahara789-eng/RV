import streamlit as st
import requests
import re
import html as html_lib

st.set_page_config(page_title="Reverb Draft Creator")

API_BASE = "https://api.reverb.com/api"

st.title("Reverb Draft Creator")

if "api" not in st.session_state:
    st.session_state.api = None


def clean_text(value: str) -> str:
    if not value:
        return ""
    value = html_lib.unescape(value)
    value = value.replace("\\/", "/").replace("\\n", "\n").replace('\\"', '"')
    return value.strip()


def extract_first(pattern: str, text: str, flags=0, default=None):
    match = re.search(pattern, text, flags)
    if not match:
        return default
    return match.group(1)


if st.session_state.api is None:
    api = st.text_input("Enter Reverb API Key", type="password")

    if st.button("Connect"):
        st.session_state.api = api.strip()
        st.rerun()

else:
    st.header("Create Draft Listings")

    shipping_profile = st.text_input("Shipping Profile ID")
    links = st.text_area("Paste Sold Listing URLs (one per line)")

    if st.button("Create Draft Listings"):
        headers = {
            "Authorization": f"Bearer {st.session_state.api}",
            "Accept-Version": "3.0",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0",
        }

        link_list = [l.strip() for l in links.split("\n") if l.strip()]
        success = 0

        for link in link_list:
            try:
                page_resp = requests.get(
                    link,
                    headers={"User-Agent": "Mozilla/5.0"},
                    timeout=30,
                )
                page_resp.raise_for_status()
                page_html = page_resp.text

                title = extract_first(r"<h1[^>]*>(.*?)</h1>", page_html, re.S | re.I)
                title = clean_text(title)

                amount = extract_first(r'"amount":\s*([0-9.]+)', page_html)
                description = extract_first(r'"description":"(.*?)"', page_html, re.S)
                make = extract_first(r'"make":"(.*?)"', page_html, re.S)
                model = extract_first(r'"model":"(.*?)"', page_html, re.S)

                image_urls = re.findall(r'"image_url":"(.*?)"', page_html, re.S)
                image_urls = [clean_text(x) for x in image_urls if x][:6]

                if not title or not amount:
                    st.error(f"Could not read title or price: {link}")
                    continue

                price = float(amount)
                new_price = round(price * 0.5, 2)

                description = clean_text(description) or title
                make = clean_text(make) or "Unknown"
                model = clean_text(model) or title

                draft = {
                    "title": title,
                    "description": description,
                    "make": make,
                    "model": model,
                    "price": {
                        "amount": f"{new_price:.2f}",
                        "currency": "USD",
                    },
                    "shipping_profile_id": int(shipping_profile) if shipping_profile else None,
                    "photos": image_urls,
                }

                create_resp = requests.post(
                    f"{API_BASE}/listings",
                    headers=headers,
                    json=draft,
                    timeout=30,
                )

                if create_resp.status_code in (200, 201):
                    success += 1
                    st.success(f"Draft created: {title}")
                else:
                    st.error(
                        f"Create failed for {title}: "
                        f"{create_resp.status_code} - {create_resp.text}"
                    )

            except Exception as e:
                st.error(f"Failed listing: {link} | {e}")

        st.success(f"{success} Draft Listings Created")