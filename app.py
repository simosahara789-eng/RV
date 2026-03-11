import streamlit as st
import requests
import json

API_BASE = "https://api.reverb.com/api"

# Official Reverb condition UUIDs from docs
CONDITIONS = {
    "Excellent": "df268ad1-c462-4ba6-b6db-e007e23922ea",
    "Very Good": "ae4d9114-1bd7-4ec5-a4ba-6653af5ac84d",
    "Good": "f7a3f48c-972a-44c6-b01a-0cd27488d3f6",
    "Fair": "98777886-76d0-44c8-865e-bb40e669e934",
    "Poor": "6a9dfcad-600b-46c8-9e08-ce6e5057921e",
    "Mint": "ac5b9c1e-dc78-466d-b0b3-7cf712967a48",
    "Brand New": "7c3f45de-2ae0-4c81-8400-fdb6b1d74890",
}

st.set_page_config(page_title="Reverb Draft Creator", layout="centered")
st.title("Reverb Draft Creator")

if "api_key" not in st.session_state:
    st.session_state.api_key = None

def api_headers(api_key: str) -> dict:
    return {
        "Authorization": f"Bearer {api_key}",
        "Accept-Version": "3.0",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

def get_shipping_profiles(api_key: str):
    resp = requests.get(f"{API_BASE}/shop", headers=api_headers(api_key), timeout=30)
    if resp.status_code != 200:
        return None, f"Failed to fetch shop: {resp.status_code} - {resp.text}"
    data = resp.json()
    profiles = data.get("shipping_profiles", [])
    return profiles, None

def create_draft(api_key: str, payload: dict):
    resp = requests.post(
        f"{API_BASE}/listings",
        headers=api_headers(api_key),
        json=payload,
        timeout=60,
    )
    return resp

# Page 1
if st.session_state.api_key is None:
    api = st.text_input("Enter Reverb API Key", type="password")
    if st.button("Connect"):
        st.session_state.api_key = api.strip()
        st.rerun()

# Page 2
else:
    st.subheader("Create Draft Listing")

    profiles, profile_error = get_shipping_profiles(st.session_state.api_key)

    if profile_error:
        st.error(profile_error)
    else:
        if profiles:
            options = {
                f'{p.get("name", "Profile")} ({p.get("id")})': str(p.get("id"))
                for p in profiles
            }
            selected = st.selectbox("Shipping Profile", list(options.keys()))
            shipping_profile_id = options[selected]
        else:
            shipping_profile_id = st.text_input("Shipping Profile ID")

        title = st.text_input("Title")
        make = st.text_input("Brand / Make")
        model = st.text_input("Model")
        description = st.text_area("Description")
        price = st.number_input("Price USD", min_value=0.0, step=1.0, value=100.0)
        discount_percent = st.number_input("Discount %", min_value=0, max_value=90, value=50)
        condition_name = st.selectbox("Condition", list(CONDITIONS.keys()), index=0)
        photos_text = st.text_area(
            "Photo URLs (one per line)",
            help="ضع كل رابط صورة في سطر"
        )

        if st.button("Create Draft"):
            if not title or not make or not model:
                st.error("Title, Make, and Model are required.")
            else:
                discounted = round(price * (1 - discount_percent / 100), 2)
                photo_urls = [x.strip() for x in photos_text.splitlines() if x.strip()]

                payload = {
                    "title": title,
                    "make": make,
                    "model": model,
                    "description": description or title,
                    "price": {
                        "amount": f"{discounted:.2f}",
                        "currency": "USD",
                    },
                    "condition": {
                        "uuid": CONDITIONS[condition_name]
                    },
                    "shipping_profile_id": int(shipping_profile_id) if shipping_profile_id else None,
                    "photos": photo_urls,
                }

                resp = create_draft(st.session_state.api_key, payload)

                if resp.status_code in (200, 201):
                    st.success("Draft created successfully.")
                    st.code(json.dumps(resp.json(), indent=2), language="json")
                else:
                    st.error(f"Create failed: {resp.status_code}")
                    st.code(resp.text)