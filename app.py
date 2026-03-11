import streamlit as st
import requests
import re
import time

st.set_page_config(page_title="Reverb Draft Tool")

st.title("Reverb Draft Creator")

if "api" not in st.session_state:
    st.session_state.api = None

# PAGE 1
if st.session_state.api is None:

    api = st.text_input("Enter Reverb API Key", type="password")

    if st.button("Connect"):
        st.session_state.api = api
        st.rerun()

# PAGE 2
else:

    st.header("Create Draft Listings")

    shipping_profile = st.text_input("Shipping Profile ID")

    links = st.text_area("Paste Sold Listing URLs (one per line)")

    if st.button("Create Draft Listings"):

        headers = {
            "Authorization": f"Token {st.session_state.api}",
            "Accept-Version": "3.0",
            "Content-Type": "application/json"
        }

        link_list = [l.strip() for l in links.split("\n") if l.strip()]

        success = 0

        for link in link_list:

            try:

                # استخراج ID من الرابط
                listing_id = re.search(r'/item/(\d+)', link).group(1)

                url = f"https://api.reverb.com/api/listings/{listing_id}"

                r = requests.get(url, headers=headers)

                if r.status_code != 200:
                    st.error(f"Cannot fetch listing {listing_id}")
                    continue

                data = r.json()["listing"]

                title = data["title"]
                description = data["description"]
                price = float(data["price"]["amount"])

                brand = data["make"]
                model = data["model"]

                images = data["photos"]

                new_price = round(price * 0.5, 2)

                draft = {
                    "title": title,
                    "description": description,
                    "price": new_price,
                    "currency": "USD",
                    "condition": "Excellent",
                    "make": brand,
                    "model": model,
                    "shipping_profile_id": shipping_profile
                }

                create = requests.post(
                    "https://api.reverb.com/api/listings",
                    headers=headers,
                    json=draft
                )

                if create.status_code in [200,201]:

                    new_listing_id = create.json()["listing"]["id"]

                    for img in images:

                        requests.post(
                            f"https://api.reverb.com/api/listings/{new_listing_id}/images",
                            headers=headers,
                            json={"url": img["image_url"]}
                        )

                    st.success(f"Draft created: {title}")

                    success += 1

                else:

                    st.error("Error creating listing")

                time.sleep(1)

            except Exception as e:

                st.error(f"Failed listing: {link}")

        st.success(f"{success} Draft Listings Created")