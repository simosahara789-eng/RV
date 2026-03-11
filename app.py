import streamlit as st
import requests
import re
import time
from playwright.sync_api import sync_playwright

st.set_page_config(page_title="Reverb Pro Tool")

st.title("Reverb Auto Draft Creator")

# PAGE 1
if "api" not in st.session_state:
    st.session_state.api = None

if st.session_state.api is None:

    api = st.text_input("Enter Reverb API Key")

    if st.button("Connect"):
        st.session_state.api = api
        st.rerun()

# PAGE 2
else:

    st.header("Create Draft Listings")

    shipping_profile = st.text_input("Shipping Profile ID", "114252")

    discount = st.slider("Discount %", 0, 80, 50)

    max_listings = st.slider("Number of Listings", 1, 100, 10)

    links = st.text_area("Paste Sold Listing URLs (one per line)")

    if st.button("Create Draft Listings"):

        headers = {
            "Authorization": f"Token {st.session_state.api}",
            "Accept-Version": "3.0",
            "Content-Type": "application/json"
        }

        link_list = [l.strip() for l in links.split("\n") if l.strip()]

        success = 0

        with sync_playwright() as p:

            browser = p.chromium.launch(headless=True)

            page = browser.new_page()

            for link in link_list[:max_listings]:

                try:

                    page.goto(link)

                    title = page.locator("h1").first.inner_text()

                    description = page.locator(".listing-description").inner_text()

                    price_text = page.locator('[itemprop="price"]').first.inner_text()

                    price = float(re.sub(r"[^\d.]", "", price_text))

                    brand = page.locator('[itemprop="brand"]').first.inner_text()

                    model = page.locator('[itemprop="model"]').first.inner_text()

                    images = page.locator("img").all()

                    image_urls = []

                    for img in images[:6]:

                        src = img.get_attribute("src")

                        if src and "reverb.com" in src:

                            image_urls.append(src)

                    new_price = round(price * (1 - discount/100), 2)

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

                    r = requests.post(
                        "https://api.reverb.com/api/listings",
                        headers=headers,
                        json=draft
                    )

                    if r.status_code in [200,201]:

                        listing_id = r.json()["listing"]["id"]

                        for img in image_urls:

                            requests.post(
                                f"https://api.reverb.com/api/listings/{listing_id}/images",
                                headers=headers,
                                json={"url": img}
                            )

                        st.success(f"Draft created: {title}")

                        success += 1

                    else:

                        st.error("Error creating listing")

                    time.sleep(2)

                except:

                    st.error(f"Failed listing: {link}")

            browser.close()

        st.success(f"{success} Draft Listings Created")