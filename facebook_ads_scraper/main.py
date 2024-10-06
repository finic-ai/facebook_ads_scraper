from playwright.sync_api import sync_playwright, Page
import json
from dotenv import load_dotenv
import os
from bs4 import BeautifulSoup
from typing import List, Optional
from pydantic import BaseModel
import json
import platform
from finic import Finic
load_dotenv()

API_KEY = os.getenv("API_KEY")
BROWSER_CDP_URL = f"wss://browser-521298051240.us-central1.run.app/ws?api_key={API_KEY}&browser_id=test_browser"
# BROWSER_CDP_URL = f"ws://localhost:8000/ws?api_key={API_KEY}&browser_id=test_browser"

class FacebookAd(BaseModel):
    library_id: Optional[str] = None
    start_date: Optional[str] = None
    status: Optional[str] = None
    partner_name: Optional[str] = None
    partner_url: Optional[str] = None
    advertiser_name: Optional[str] = None
    advertiser_url: Optional[str] = None
    advertiser_description: Optional[str] = None
    ad_text: Optional[str] = None
    ad_links: Optional[List[str]] = []
    image_urls: Optional[List[str]] = []
    video_urls: Optional[List[str]] = []

def main():
    finic_client = Finic()
    
    with open('input.json', 'r', encoding='utf-8') as f:
        input_data = json.load(f)
    urls = input_data.get("ad_urls", [])
    
    results = []

    print("Connecting to Browser...")

    # Returns a playwright BrowserContext
    context = finic_client.launch_browser_sync(headless=False, slow_mo=500)
    
    page = context.new_page()
    for url in urls:

        page.goto(url)
        page.wait_for_load_state("domcontentloaded", timeout=10000)

        ### GET ADVERTISER INFO ###
        about_button = page.locator("//div[@role='link' and normalize-space(text())='About']")
        about_button.click()
        page.wait_for_timeout(1000)

        advertiser_description = page.locator("//div[normalize-space(text())='Page transparency']/following-sibling::span[1]").inner_text()
        advertiser_name_element = page.locator("//a[./div[@role='heading']]").first
        advertiser_name = advertiser_name_element.inner_text()
        advertiser_url = advertiser_name_element.get_attribute("href")
        ### GET AD DETAILS ###
        page.reload()
        page.wait_for_load_state("domcontentloaded", timeout=10000)
        
        # Scroll to load all ads
        last_height = page.evaluate("document.body.scrollHeight")
        while True:
            # Scroll down to bottom
            page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
            
            # Wait for page to load
            page.wait_for_load_state("networkidle", timeout=10000)
            page.wait_for_load_state("load", timeout=10000)
            
            # Calculate new scroll height and compare with last scroll height
            new_height = page.evaluate("document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height

        # Wait a bit more to ensure all content is loaded
        page.wait_for_timeout(2000)
        ads_selector = "//div[normalize-space(text())='See summary details' or normalize-space(text())='See ad details']/ancestor::*[6]"
        ads = page.locator(ads_selector)
        print(f"Found {ads.count()} ads")

        for i in range(ads.count()):
            ad = ads.nth(i)
            facebook_ad = FacebookAd()

            # Extract ad status
            status_elem = ad.locator("//span[normalize-space(text())='Active' or normalize-space(text())='Inactive']")
            if status_elem.is_visible():
                facebook_ad.status = status_elem.inner_text()

            # Extract ad information
            facebook_ad.advertiser_name = advertiser_name
            facebook_ad.advertiser_url = advertiser_url
            facebook_ad.advertiser_description = advertiser_description
            
            # Extract library ID
            library_id_elem = ad.locator("//span[contains(text(), 'Library ID:')]")
            if library_id_elem.is_visible():
                facebook_ad.library_id = library_id_elem.inner_text().split(":")[1].strip()
            
            # Take screenshot of the ad
            initial_styles = ad.evaluate("""(element) => {
                return {
                    zIndex: element.style.zIndex,
                    position: element.style.position,
                    bottom: element.style.bottom,
                    left: element.style.left
                };
            }""")

            # Take screenshot of the ad
            finic_client.screenshot(page, f"({ads_selector})[{i+1}]", f"screenshots/{facebook_ad.advertiser_name}_{facebook_ad.library_id}.png")

            # Extract start date
            start_date_elem = ad.locator("//span[contains(text(), 'Started running on')]")
            if start_date_elem.is_visible():
                facebook_ad.start_date = start_date_elem.inner_text().replace("Started running on ", "")

            # Extract ad text
            ad_text_elem = ad.locator("div[style*='white-space: pre-wrap;']").first
            if ad_text_elem.is_visible():
                facebook_ad.ad_text = ad_text_elem.inner_text()
            
            # Extract ad links
            ad_link_elems = ad.locator("//div[@role='button' and parent::*[@role='none'] and not(.//text()[normalize-space()='See ad details' or normalize-space()='See summary details'])]").all()
            for ad_link_elem in ad_link_elems:
                if ad_link_elem.is_visible():
                    with page.expect_popup() as popup_info:
                        ad_link_elem.click()
                        page.wait_for_timeout(2000)

                    popup = popup_info.value
                    ad_url = popup.url
                    facebook_ad.ad_links.append(ad_url)
                    popup.close()

            # Extract image URLs (if available)
            image_elems = ad.locator("img").all()[1:]
            for image_elem in image_elems:
                if image_elem.is_visible():
                    src = image_elem.get_attribute("src")
                    if src:
                        facebook_ad.image_urls.append(src)
            
            # Extract video URL (if available)
            video_elems = ad.locator("video").all()
            for video_elem in video_elems:
                if video_elem.is_visible():
                    src = video_elem.get_attribute("src")
                    if src:
                        facebook_ad.video_urls.append(src)
            
            # Extract partner name and url
            ad_title = ad.locator("//img[1]/following-sibling::div[1]//span[1]").first
            ad_title_text = ad_title.inner_text()
            if "with" in ad_title_text:
                facebook_ad.partner_name = ad_title_text.split("with")[0].strip()
                facebook_ad.partner_url = ad_title.locator("xpath=.//a[1]").first.get_attribute("href")
            
            # Add the extracted ad to results
            results.append(facebook_ad.dict())

            print(f"Processed ad {i+1}/{ads.count()}")

    # Save results to JSON file
    with open('results.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=4)

    print(f"Scraped {len(results)} ads. Results saved to results.json")

    context.close()
