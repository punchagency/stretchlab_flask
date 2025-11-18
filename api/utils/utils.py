from jsonschema import validate, ValidationError
import os
from playwright.sync_api import sync_playwright
from playwright.async_api import (
    async_playwright,
    TimeoutError as PlaywrightTimeoutError,
)
import asyncio
import secrets
import string
import bcrypt
import random
from dotenv import load_dotenv
from ..database.database import (
    save_flexology_data,
    get_user_details,
    update_user_bookings,
    get_bookings_if_not_expired,
)
import base64
from ..ai.aianalysis import extract_booking_data_from_html
import jwt
import logging
import time
from io import BytesIO
import uuid
import boto3

load_dotenv()
s3 = boto3.client("s3")


# Initilaizing variables with the env values
INITIAL_URL = os.getenv("INITIAL_URL")
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
ERROR_IMAGE_BUCKET_NAME = "stretchnoteerrorimagelog"


class BrowserContextManager:
    """Context manager for handling browser operations with automatic cleanup"""

    def __init__(self, playwright, headless=True):
        self.playwright = playwright
        self.headless = headless
        self.browser = None

    async def __aenter__(self):
        self.browser = await self.playwright.chromium.launch(headless=self.headless)
        return self.browser

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.browser:
            try:
                await self.browser.close()
            except Exception as e:
                logging.error(f"Error closing browser: {e}")


def save_error_image_to_s3(
    image_data, image_name, content_type="image/jpeg", region_name="eu-north-1"
):
    try:
        s3.upload_fileobj(
            Fileobj=image_data,
            Bucket=ERROR_IMAGE_BUCKET_NAME,
            Key=image_name,
            ExtraArgs={
                "ContentType": content_type,
                # "ACL": "public-read",
            },
        )

        image_url = f"https://{ERROR_IMAGE_BUCKET_NAME}.s3.{region_name}.amazonaws.com/{image_name}"
        return {"status": "success", "url": image_url}

    except Exception as e:
        logging.error(f"Error saving error image to S3: {str(e)}")
        return {"status": "error", "message": str(e)}


def validate_request(data, schema):
    try:
        validate(instance=data, schema=schema)
        return data
    except ValidationError as e:
        raise ValueError(f"Invalid request data: {e.message}")


def hash_credentials(username, password):
    prefix = username + "_"
    suffix = "_lab"
    full_string = prefix + password + suffix
    string_bytes = full_string.encode("utf-8")
    key = username.encode("utf-8")
    encrypted = bytes(s ^ key[i % len(key)] for i, s in enumerate(string_bytes))
    return base64.b64encode(encrypted).decode("utf-8")


def reverse_hash_credentials(username, hashed_password):
    prefix = username + "_"
    suffix = "_lab"

    try:
        encrypted = base64.b64decode(hashed_password)
        key = username.encode("utf-8")
        decrypted = bytes(e ^ key[i % len(key)] for i, e in enumerate(encrypted))
        full_string = decrypted.decode("utf-8")

        if full_string.startswith(prefix) and full_string.endswith(suffix):
            return full_string[len(prefix) : -len(suffix)]
        else:
            raise ValueError("Invalid hashed password format")
    except Exception as e:
        raise ValueError(f"Failed to decrypt password: {str(e)}")


def clubready_login(data):
    playwright = None
    browser = None
    context = None
    page = None

    try:
        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        page.goto(INITIAL_URL)
        page.fill("input[name='uid']", data["username"])
        page.fill("input[name='pw']", data["password"])
        page.click("input[type='submit']")
        page.wait_for_load_state("networkidle")

        current_url = page.url
        if "invalidlogin" in current_url:
            raise ValueError("Invalid Username or Password")

        if "Dashboard" in current_url:
            hashed_password = hash_credentials(data["username"], data["password"])
            page.query_selector("#account-avatar").click(force=True)
            profile_menu = page.wait_for_selector("#logout-div", state="attached")
            full_name = profile_menu.query_selector(
                "ul li:nth-child(1) td .regtxt2"
            ).inner_text()
            profile_info = profile_menu.query_selector(
                "ul li:nth-child(1) td .text2"
            ).inner_text()

            location_id = profile_info.split("-")[0]
            user_id = profile_info.split("-")[1]
            return {
                "status": True,
                "hashed_password": hashed_password,
                "location_id": location_id,
                "user_id": user_id,
                "full_name": full_name,
            }

        elif "selectlogin" in current_url:
            hashed_password = hash_credentials(data["username"], data["password"])
            page.wait_for_selector("select[name='stores']")
            select_element = page.query_selector("select[name='stores']")
            option_elements = select_element.query_selector_all("option")
            option_elements[0].click()
            page.click("input[name='Submit2']")
            page.wait_for_load_state("networkidle")
            current_url = page.url
            if "Dashboard" in current_url:

                page.query_selector("#account-avatar").click(force=True)
                profile_menu = page.wait_for_selector("#logout-div", state="attached")
                full_name = profile_menu.query_selector(
                    "ul li:nth-child(1) td .regtxt2"
                ).inner_text()
                profile_info = profile_menu.query_selector(
                    "ul li:nth-child(1) td .text2"
                ).inner_text()

                location_id = profile_info.split("-")[0]
                user_id = profile_info.split("-")[1]
                return {
                    "status": True,
                    "hashed_password": hashed_password,
                    "location_id": location_id,
                    "user_id": user_id,
                    "full_name": full_name,
                }

        else:
            raise ValueError("Unexpected URL after login")

    except Exception as e:
        logging.error(f"An error occurred during login: {str(e)}")
        raise
    finally:
        if page:
            page.close()
        if context:
            context.close()
        if browser:
            browser.close()
        if playwright:
            playwright.stop()


def clubready_admin_login(data):
    playwright = None
    browser = None
    context = None
    page = None

    try:
        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        page.goto(INITIAL_URL)
        page.fill("input[name='uid']", data["username"])
        page.fill("input[name='pw']", data["password"])
        page.click("input[type='submit']")
        page.wait_for_load_state("networkidle")

        current_url = page.url
        if "invalidlogin.asp" in current_url:
            logging.error("Invalid Username or Password")
            return {
                "status": False,
                "message": "Invalid Username or Password",
            }
        if "Dashboard" in current_url:
            hashed_password = hash_credentials(data["username"], data["password"])
            page.goto("https://scheduling.clubready.com/day")
            page.wait_for_selector(".spinner-background", state="hidden", timeout=40000)
            root_div = page.query_selector("div[id='root']")
            location_name = root_div.query_selector(
                "#menu-location .location-name"
            ).inner_text()
            locations = [location_name]
            return {
                "status": True,
                "hashed_password": hashed_password,
                "locations": locations,
                "message": "Clubready credentials verified successfully",
            }

        if "chain" in current_url:
            hashed_password = hash_credentials(data["username"], data["password"])

            page.wait_for_selector("div[id='theclubs']")
            select_element = page.query_selector("div[id='theclubs']")
            option_elements = select_element.query_selector_all(".clubtext")
            locations = [
                option.inner_text().split(",")[0] for option in option_elements
            ]

            return {
                "status": True,
                "hashed_password": hashed_password,
                "locations": locations,
                "message": "Clubready credentials verified successfully",
            }

        if "selectlogin" in current_url:
            hashed_password = hash_credentials(data["username"], data["password"])

            page.wait_for_selector("select[name='stores']")
            select_element = page.query_selector("select[name='stores']")
            option_elements = select_element.query_selector_all("option")
            locations = [
                option.inner_text()
                for option in option_elements
                if option.get_attribute("value")
            ]

            return {
                "status": True,
                "hashed_password": hashed_password,
                "locations": locations,
                "message": "Clubready credentials verified successfully",
            }
        else:
            raise ValueError("Unexpected URL after login")

    except Exception as e:
        logging.error(f"An error occurred during login: {str(e)}")
        raise
    finally:
        if page:
            page.close()
        if context:
            context.close()
        if browser:
            browser.close()
        if playwright:
            playwright.stop()


# async def fetch_bookings_for_location(page, base_url, location_text, semaphore):
#     async with semaphore:
#         all_bookings = []
#         try:
#             print(f"Processing location: {location_text}")
#             await page.goto(base_url)
#             await page.wait_for_load_state("networkidle", timeout=0)

#             await page.wait_for_selector("select[name='stores']", timeout=10000)
#             select_element = await page.query_selector("select[name='stores']")
#             if not select_element:
#                 print(f"Select element not found for location: {location_text}")
#                 return []

#             options = await select_element.query_selector_all("option")
#             option = None
#             for opt in options:
#                 if (await opt.inner_text()).strip() == location_text.strip():
#                     option = opt
#                     break

#             if not option:
#                 print(f"No option found with text: {location_text}")
#                 return []

#             await option.click()
#             await page.click("input[name='Submit2']")
#             await page.wait_for_load_state("networkidle", timeout=0)
#             await page.goto("https://scheduling.clubready.com/day")
#             await page.wait_for_load_state("networkidle", timeout=0)

#             await page.wait_for_selector(
#                 ".spinner-background", state="hidden", timeout=40000
#             )

#             await page.click("#dropdown-button")
#             await page.wait_for_selector(
#                 ".sidebar-events-filter-menu", state="visible", timeout=2000
#             )
#             my_filter = await page.query_selector(".dropdown--item:has(input#only-me)")
#             if not my_filter:
#                 print(f"No 'only-me' filter found for location: {location_text}")
#                 return []

#             await page.click(".dropdown--item:has(input#only-me)")
#             container = await page.query_selector_all(".sidebar-section-content")

#             all_div_selectors = []
#             for cont in container:
#                 div_selector = await cont.query_selector_all(
#                     "div[class*='sidebar-event-card']"
#                 )
#                 all_div_selectors.extend(div_selector)

#             print(f"Total event cards found: {len(all_div_selectors)}")
#             await page.click("#dropdown-button")
#             await page.wait_for_selector(
#                 ".sidebar-events-filter-menu", state="hidden", timeout=2000
#             )

#             if all_div_selectors:
#                 print(
#                     f"Found {len(all_div_selectors)} event cards for location: {location_text}"
#                 )

#                 for div in all_div_selectors:
#                     event_date = await (
#                         await div.query_selector(".event-date")
#                     ).inner_text()
#                     past = "previous-event" in await div.get_attribute("id")
#                     await div.click()
#                     modal_details = await page.wait_for_selector(
#                         ".booking-panel", state="visible"
#                     )
#                     await page.wait_for_function(
#                         expression="""
#                         (element) => {
#                             const loaders = element.querySelectorAll('[class*="spinner"]');
#                             return element && element.offsetParent !== null && loaders.length === 0;
#                         }
#                         """,
#                         arg=modal_details,
#                         timeout=20000,
#                     )
#                     first_timer = (
#                         "YES"
#                         if await modal_details.query_selector(
#                             ".booking-header-tags .text-first-visit"
#                         )
#                         else "NO"
#                     )
#                     if await modal_details.query_selector(
#                         ".client-membership-tags .container-active"
#                     ):
#                         active = "YES"
#                     else:
#                         lead_type_elem = await modal_details.query_selector(
#                             ".membership-info .lead-type"
#                         )
#                         if (
#                             lead_type_elem
#                             and await lead_type_elem.inner_text() == "Employee"
#                         ):
#                             active = "YES"
#                         else:
#                             future_bookings_elem = await modal_details.query_selector(
#                                 ".future-bookings .details-info"
#                             )
#                             if future_bookings_elem:
#                                 try:
#                                     if int(await future_bookings_elem.inner_text()) > 0:
#                                         active = "YES"
#                                     else:
#                                         active = "NO"
#                                 except ValueError:
#                                     active = "NO"
#                     client_name_elem = await modal_details.query_selector(
#                         "#client-name"
#                     )
#                     client_name = (
#                         await client_name_elem.inner_text()
#                         if client_name_elem
#                         else "N/A"
#                     )

#                     booking_number_elem = await modal_details.query_selector(
#                         ".details-tab .details-row"
#                     )
#                     booking_number = (
#                         await booking_number_elem.inner_text()
#                         if booking_number_elem
#                         else "N/A"
#                     )
#                     booking_id = (
#                         booking_number.lower().split("booking: #")[1].strip()
#                         if "booking: #" in booking_number.lower()
#                         else "N/A"
#                     )

#                     workout_type_elem = await modal_details.query_selector(
#                         ".booking-title"
#                     )
#                     workout_type = (
#                         await workout_type_elem.inner_text()
#                         if workout_type_elem
#                         else "N/A"
#                     )

#                     flexologist_name_elem = await modal_details.query_selector(
#                         ".avatar-name-container .name-container .name"
#                     )
#                     flexologist_name = (
#                         await flexologist_name_elem.inner_text()
#                         if flexologist_name_elem
#                         else "N/A"
#                     )

#                     phone_elem = await modal_details.query_selector(
#                         "#selected-phone-button .text"
#                     )
#                     phone = await phone_elem.inner_text() if phone_elem else "N/A"

#                     booking_time_elem = await modal_details.query_selector(
#                         ".datetime-value .time-value"
#                     )
#                     booking_time = (
#                         await booking_time_elem.inner_text()
#                         if booking_time_elem
#                         else "N/A"
#                     )
#                     result = {
#                         "client_name": client_name,
#                         "booking_id": booking_id,
#                         "workout_type": workout_type,
#                         "flexologist_name": flexologist_name,
#                         "phone": phone,
#                         "booking_time": booking_time,
#                         "event_date": event_date,
#                         "past": past,
#                         "first_timer": first_timer,
#                         "active": active,
#                         "location": location_text,
#                     }
#                     all_bookings.append(result)

#                     close_btn = await modal_details.query_selector("#header-close")
#                     if close_btn:
#                         await close_btn.wait_for_element_state("visible")
#                         await close_btn.wait_for_element_state("stable")
#                         await close_btn.click()
#                         await page.wait_for_selector(".booking-panel", state="hidden")
#                     else:
#                         print("Close button not found")

#             return all_bookings

#         except PlaywrightTimeoutError as e:
#             print(f"Timeout error for location {location_text}: {e}")
#             raise e
#         except Exception as e:
#             print(f"Error processing location {location_text}: {e}")
#             raise e


# async def get_user_bookings_from_clubready(user_details, max_concurrency=3):
#     username = user_details["Username"]
#     password = user_details["Password"]
#     password = reverse_hash_credentials(username, password)
#     print(username, password)
#     async with async_playwright() as p:
#         # Use custom browser context manager for automatic cleanup
#         async with BrowserContextManager(p, headless=True) as browser:
#             try:
#                 # Use context context manager for automatic cleanup
#                 async with await browser.new_context() as context:
#                     async with await context.new_page() as page:
#                         await page.goto(INITIAL_URL)
#                         await page.fill("input[name='uid']", username)
#                         await page.fill("input[name='pw']", password)
#                         await page.click("input[type='submit']")
#                         await page.wait_for_load_state("networkidle", timeout=0)
#                         current_url = page.url
#                         if "invalidlogin" in current_url:
#                             print("Invalid Username or Password")
#                             return {
#                                 "status": False,
#                                 "message": "Invalid Username or Password",
#                                 "bookings": [],
#                             }

#                         all_bookings = []
#                         failed_locations = []
#                         location = None
#                         if "Dashboard" in current_url:
#                             await page.goto("https://scheduling.clubready.com/day")
#                             await page.wait_for_load_state("networkidle", timeout=0)

#                             await page.wait_for_selector(
#                                 ".spinner-background", state="hidden", timeout=40000
#                             )
#                             location_element = await page.query_selector(
#                                 "#menu-location .location-name"
#                             )
#                             location = await location_element.inner_text()

#                             await page.click("#dropdown-button")
#                             await page.wait_for_selector(
#                                 ".sidebar-events-filter-menu",
#                                 state="visible",
#                                 timeout=2000,
#                             )

#                             await page.click(".dropdown--item:has(input#only-me)")
#                             container = await page.query_selector_all(
#                                 ".sidebar-section-content"
#                             )

#                             all_div_selectors = []
#                             for cont in container:
#                                 div_selector = await cont.query_selector_all(
#                                     "div[class*='sidebar-event-card']"
#                                 )
#                                 all_div_selectors.extend(div_selector)

#                             await page.click("#dropdown-button")
#                             await page.wait_for_selector(
#                                 ".sidebar-events-filter-menu",
#                                 state="hidden",
#                                 timeout=2000,
#                             )

#                             if all_div_selectors:
#                                 print(f"Found {len(all_div_selectors)} event cards")
#                                 for div in all_div_selectors:
#                                     event_date = await (
#                                         await div.query_selector(".event-date")
#                                     ).inner_text()
#                                     past = "previous-event" in await div.get_attribute(
#                                         "id"
#                                     )
#                                     await div.click()
#                                     modal_details = await page.wait_for_selector(
#                                         ".booking-panel", state="visible"
#                                     )
#                                     await page.wait_for_function(
#                                         expression="""
#                                     (element) => {
#                                         const loaders = element.querySelectorAll('[class*="spinner"]');
#                                         return element && element.offsetParent !== null && loaders.length === 0;
#                                     }
#                                     """,
#                                         arg=modal_details,
#                                         timeout=20000,
#                                     )
#                                     first_timer = (
#                                         "YES"
#                                         if await modal_details.query_selector(
#                                             ".booking-header-tags .text-first-visit"
#                                         )
#                                         else "NO"
#                                     )
#                                     if await modal_details.query_selector(
#                                         ".client-membership-tags .container-active"
#                                     ):
#                                         active = "YES"
#                                     else:
#                                         lead_type_elem = (
#                                             await modal_details.query_selector(
#                                                 ".membership-info .lead-type"
#                                             )
#                                         )
#                                         if (
#                                             lead_type_elem
#                                             and await lead_type_elem.inner_text()
#                                             == "Employee"
#                                         ):
#                                             active = "YES"
#                                         else:
#                                             future_bookings_elem = (
#                                                 await modal_details.query_selector(
#                                                     ".future-bookings .details-info"
#                                                 )
#                                             )
#                                             if future_bookings_elem:
#                                                 try:
#                                                     if (
#                                                         int(
#                                                             await future_bookings_elem.inner_text()
#                                                         )
#                                                         > 0
#                                                     ):
#                                                         active = "YES"
#                                                     else:
#                                                         active = "NO"
#                                                 except ValueError:
#                                                     active = "NO"

#                                     client_name_elem = (
#                                         await modal_details.query_selector(
#                                             "#client-name"
#                                         )
#                                     )
#                                     client_name = (
#                                         await client_name_elem.inner_text()
#                                         if client_name_elem
#                                         else "N/A"
#                                     )

#                                     booking_number_elem = (
#                                         await modal_details.query_selector(
#                                             ".details-tab .details-row"
#                                         )
#                                     )
#                                     booking_number = (
#                                         await booking_number_elem.inner_text()
#                                         if booking_number_elem
#                                         else "N/A"
#                                     )
#                                     booking_id = (
#                                         booking_number.lower()
#                                         .split("booking: #")[1]
#                                         .strip()
#                                         if "booking: #" in booking_number.lower()
#                                         else "N/A"
#                                     )

#                                     workout_type_elem = (
#                                         await modal_details.query_selector(
#                                             ".booking-title"
#                                         )
#                                     )
#                                     workout_type = (
#                                         await workout_type_elem.inner_text()
#                                         if workout_type_elem
#                                         else "N/A"
#                                     )

#                                     flexologist_name_elem = await modal_details.query_selector(
#                                         ".avatar-name-container .name-container .name"
#                                     )
#                                     flexologist_name = (
#                                         await flexologist_name_elem.inner_text()
#                                         if flexologist_name_elem
#                                         else "N/A"
#                                     )

#                                     phone_elem = await modal_details.query_selector(
#                                         "#selected-phone-button .text"
#                                     )
#                                     phone = (
#                                         await phone_elem.inner_text()
#                                         if phone_elem
#                                         else "N/A"
#                                     )

#                                     booking_time_elem = (
#                                         await modal_details.query_selector(
#                                             ".datetime-value .time-value"
#                                         )
#                                     )
#                                     booking_time = (
#                                         await booking_time_elem.inner_text()
#                                         if booking_time_elem
#                                         else "N/A"
#                                     )
#                                     result = {
#                                         "client_name": client_name,
#                                         "booking_id": booking_id,
#                                         "workout_type": workout_type,
#                                         "flexologist_name": flexologist_name,
#                                         "phone": phone,
#                                         "booking_time": booking_time,
#                                         "event_date": event_date,
#                                         "past": past,
#                                         "first_timer": first_timer,
#                                         "active": active,
#                                         "location": location,
#                                     }
#                                     all_bookings.append(result)

#                                     close_btn = await modal_details.query_selector(
#                                         "#header-close"
#                                     )
#                                     if close_btn:
#                                         await close_btn.click()
#                                         await page.wait_for_selector(
#                                             ".booking-panel", state="hidden"
#                                         )
#                                         print("Close button clicked")
#                                     else:
#                                         print("Close button not found")
#                         else:
#                             await page.wait_for_selector("select[name='stores']")
#                             select_element = await page.query_selector(
#                                 "select[name='stores']"
#                             )
#                             option_elements = await select_element.query_selector_all(
#                                 "option"
#                             )
#                             location_texts = [
#                                 await opt.inner_text() for opt in option_elements
#                             ]

#                             if not location_texts:
#                                 print("No locations found in dropdown")
#                                 return {
#                                     "status": False,
#                                     "message": "No locations found",
#                                     "bookings": [],
#                                 }

#                             print(
#                                 f"Found {len(location_texts)} locations: {location_texts}"
#                             )

#                             semaphore = asyncio.Semaphore(max_concurrency)
#                             tasks = []

#                             # Create a list to track contexts for cleanup
#                             contexts_to_cleanup = []

#                             try:
#                                 # Create tasks with location tracking
#                                 location_tasks = []
#                                 for location_text in location_texts:
#                                     # Use context managers for each location's browser context
#                                     new_context = await browser.new_context()
#                                     contexts_to_cleanup.append(new_context)

#                                     new_page = await new_context.new_page()
#                                     await new_page.goto(INITIAL_URL)
#                                     await new_page.fill("input[name='uid']", username)
#                                     await new_page.fill("input[name='pw']", password)
#                                     await new_page.click("input[type='submit']")
#                                     await new_page.wait_for_load_state(
#                                         "networkidle", timeout=0
#                                     )

#                                     task = asyncio.create_task(
#                                         fetch_bookings_for_location(
#                                             new_page,
#                                             current_url,
#                                             location_text,
#                                             semaphore,
#                                         )
#                                     )
#                                     # Store task with its location for tracking
#                                     location_tasks.append((location_text, task))

#                                 # Wait for all tasks to complete and handle failures
#                                 results = await asyncio.gather(
#                                     *[task for _, task in location_tasks],
#                                     return_exceptions=True,
#                                 )

#                                 # Process results and track failures
#                                 successful_bookings = []

#                                 for (location_text, _), result in zip(
#                                     location_tasks, results
#                                 ):
#                                     if isinstance(result, Exception):
#                                         print(
#                                             f"Task failed for location {location_text}: {result}"
#                                         )
#                                         failed_locations.append(location_text)
#                                     else:
#                                         # Check if result is a genuine empty array or actual bookings
#                                         if result is not None and isinstance(
#                                             result, list
#                                         ):
#                                             successful_bookings.extend(result)
#                                         else:
#                                             print(
#                                                 f"Unexpected result for location {location_text}: {result}"
#                                             )
#                                             failed_locations.append(location_text)

#                                 all_bookings.extend(successful_bookings)

#                                 # Retry failed locations up to 2 times
#                                 if failed_locations:
#                                     print(
#                                         f"Retrying {len(failed_locations)} failed locations..."
#                                     )
#                                     retry_successful = []
#                                     still_failed = []

#                                     for location_text in failed_locations:
#                                         success = False
#                                         for retry_attempt in range(
#                                             2
#                                         ):  # Try up to 2 times
#                                             try:
#                                                 print(
#                                                     f"Retry attempt {retry_attempt + 1} for location: {location_text}"
#                                                 )

#                                                 # Create new context and page for retry
#                                                 retry_context = (
#                                                     await browser.new_context()
#                                                 )
#                                                 retry_page = (
#                                                     await retry_context.new_page()
#                                                 )
#                                                 await retry_page.goto(INITIAL_URL)
#                                                 await retry_page.fill(
#                                                     "input[name='uid']", username
#                                                 )
#                                                 await retry_page.fill(
#                                                     "input[name='pw']", password
#                                                 )
#                                                 await retry_page.click(
#                                                     "input[type='submit']"
#                                                 )
#                                                 await retry_page.wait_for_load_state(
#                                                     "networkidle", timeout=0
#                                                 )

#                                                 # Fetch bookings for this location
#                                                 retry_bookings = (
#                                                     await fetch_bookings_for_location(
#                                                         retry_page,
#                                                         current_url,
#                                                         location_text,
#                                                         semaphore,
#                                                     )
#                                                 )

#                                                 # Clean up retry context
#                                                 await retry_context.close()

#                                                 # Check if retry was successful
#                                                 if (
#                                                     retry_bookings is not None
#                                                     and isinstance(retry_bookings, list)
#                                                 ):
#                                                     all_bookings.extend(retry_bookings)
#                                                     retry_successful.append(
#                                                         location_text
#                                                     )
#                                                     success = True
#                                                     print(
#                                                         f"Retry successful for location: {location_text}"
#                                                     )
#                                                     break
#                                                 else:
#                                                     print(
#                                                         f"Retry returned empty result for location: {location_text}"
#                                                     )

#                                             except Exception as e:
#                                                 print(
#                                                     f"Retry attempt {retry_attempt + 1} failed for {location_text}: {e}"
#                                                 )
#                                                 # Clean up on exception
#                                                 try:
#                                                     await retry_context.close()
#                                                 except:
#                                                     pass

#                                         if not success:
#                                             still_failed.append(location_text)
#                                             print(
#                                                 f"Location {location_text} failed after all retry attempts"
#                                             )

#                                     failed_locations = (
#                                         still_failed  # Update failed locations list
#                                     )

#                             finally:
#                                 # Ensure all contexts are cleaned up
#                                 for ctx in contexts_to_cleanup:
#                                     try:
#                                         await ctx.close()
#                                     except Exception as e:
#                                         print(f"Error closing context: {e}")

#                         # Return results with failed locations for retry
#                         if failed_locations:
#                             message = (
#                                 f"Bookings fetched successfully. {len(failed_locations)} locations failed "
#                                 f"after retry attempts (2 retries each)."
#                             )
#                         else:
#                             message = "Bookings fetched successfully (including retries for failed locations)."

#                         response = {
#                             "status": len(failed_locations) == 0,  # True if no failures
#                             "message": message,
#                             "bookings": all_bookings,
#                             "failed_locations": failed_locations,
#                             "successful_locations": (
#                                 [location]
#                                 if "Dashboard" in current_url
#                                 else [
#                                     loc
#                                     for loc in location_texts
#                                     if loc not in failed_locations
#                                 ]
#                             ),
#                         }
#                         return response

#             except PlaywrightTimeoutError as e:
#                 print(f"Timeout error: {e}")
#                 raise e
#             except Exception as e:
#                 print(f"Error fetching bookings: {e}")
#                 raise e


# def submit_notes(username, password, period, notes, location=None, client_name=None):
#     password = reverse_hash_credentials(username, password)
#     playwright = None
#     browser = None
#     context = None
#     page = None
#     modal_details = None
#     same_client_booking = None
#     same_client_period = None

#     try:
#         playwright = sync_playwright().start()
#         browser = playwright.chromium.launch(headless=True)
#         context = browser.new_context()
#         page = context.new_page()

#         page.goto(INITIAL_URL)
#         page.fill("input[name='uid']", username)
#         page.fill("input[name='pw']", password)
#         page.click("input[type='submit']")
#         page.wait_for_load_state("networkidle", timeout=0)
#         base_url = page.url
#         if "Dashboard" in base_url:
#             page.goto("https://scheduling.clubready.com/day")
#             page.wait_for_load_state("networkidle", timeout=0)
#             page.wait_for_selector(".spinner-background", state="hidden", timeout=40000)

#             page.click("#dropdown-button")
#             page.wait_for_selector(
#                 ".sidebar-events-filter-menu",
#                 state="visible",
#                 timeout=2000,
#             )

#             page.click(".dropdown--item:has(input#only-me)")
#             container = page.query_selector(".sidebar-today-events")
#             page.click("#dropdown-button")
#             page.wait_for_selector(
#                 ".sidebar-events-filter-menu",
#                 state="hidden",
#                 timeout=2000,
#             )
#             unpaid_modal = None
#             if container:
#                 div_selector = container.query_selector_all(
#                     "div[class*='sidebar-event-card']"
#                 )
#                 if len(div_selector) > 0:
#                     print("Table with class starting with 'ids' found.")
#                     print(div_selector)

#                     matching_booking = None
#                     matching_index = -1

#                     for i, div in enumerate(div_selector):
#                         event_date = div.query_selector(".event-date").inner_text()
#                         if event_date == period:
#                             matching_booking = div
#                             matching_index = i
#                             break

#                     if (
#                         matching_booking
#                         and matching_index >= 0
#                         and matching_index + 1 < len(div_selector)
#                     ):
#                         check_client = (
#                             div_selector[matching_index + 1]
#                             .query_selector(".event-customer")
#                             .inner_text()
#                             .lower()
#                         )
#                         if check_client == client_name:
#                             same_client_booking = div_selector[matching_index + 1]
#                             same_client_period = same_client_booking.query_selector(
#                                 ".event-date"
#                             ).inner_text()
#                             print(
#                                 f"Found next booking for same client at index {matching_index + 1}"
#                             )
#                         else:
#                             print(
#                                 f"Found next booking for different client at index {matching_index + 1}"
#                             )

#                     if matching_booking:
#                         matching_booking.click()
#                         modal_details = page.wait_for_selector(
#                             ".booking-panel", state="visible"
#                         )
#                         page.wait_for_function(
#                             """
#                                                     (element) => {
#                                                         const loaders = element.querySelectorAll('[class*="spinner"]');
#                                                         return element && element.offsetParent !== null && loaders.length === 0;
#                                                     }
#                                                     """,
#                             arg=modal_details,
#                             timeout=20000,
#                         )

#                         open_notes_btn = modal_details.query_selector(
#                             "button[id='make-note-footer']"
#                         )

#                         if open_notes_btn:
#                             open_notes_btn.click()

#                             note_modal = page.wait_for_selector(
#                                 "div[class='desktop-modal add-note']",
#                                 state="visible",
#                                 timeout=10000,
#                             )
#                             if note_modal:
#                                 subject_input = note_modal.query_selector(
#                                     "input[id='subject']"
#                                 )
#                                 notes_textarea = note_modal.query_selector(
#                                     "textarea[id='text']"
#                                 )
#                                 if subject_input and notes_textarea:
#                                     note_modal.query_selector("#tag-0").click()
#                                     subject_input.fill("Session Notes")
#                                     notes_textarea.fill(notes)

#                                     submit_btn = note_modal.query_selector(
#                                         "button[id='add-note-btn']"
#                                     )
#                                     if submit_btn:

#                                         submit_btn.click()
#                                         page.wait_for_selector(
#                                             ".spinner-background",
#                                             state="hidden",
#                                             timeout=40000,
#                                         )

#                                 else:
#                                     print("Subject input or notes textarea not found")
#                                 close_btn = note_modal.query_selector(
#                                     "div[class='desktop-modal-header-close']"
#                                 )
#                                 if close_btn:
#                                     close_btn.click()

#                                 modal_details.query_selector(
#                                     "button[id='log-status-show']"
#                                 ).click()

#                                 try:
#                                     unpaid_modal = page.wait_for_selector(
#                                         ".log-as-completed",
#                                         state="visible",
#                                         timeout=10000,
#                                     )
#                                     if unpaid_modal:
#                                         unpaid_text_area = unpaid_modal.query_selector(
#                                             "textarea[id='optional-internal-note-mobile']"
#                                         )
#                                         if unpaid_text_area:
#                                             unpaid_text_area.fill(
#                                                 "Unpaid session logged off"
#                                             )
#                                             unpaid_modal.query_selector(
#                                                 "button[id='log-and-go-to-pos-button']"
#                                             ).click()
#                                             page.wait_for_timeout(500)
#                                             spinner = page.query_selector(
#                                                 ".spinner-background"
#                                             )
#                                             if spinner:
#                                                 page.wait_for_selector(
#                                                     ".spinner-background",
#                                                     state="hidden",
#                                                     timeout=40000,
#                                                 )
#                                         # unpaid_modal.query_selector(
#                                         #     "button[id='log-and-go-to-pos-button']"
#                                         # ).click()
#                                         # page.wait_for_timeout(500)
#                                         # unpaid_modal.query_selector(
#                                         #     ".desktop-modal-header-close"
#                                         # ).click()
#                                 except:
#                                     page.wait_for_selector(
#                                         ".spinner-background",
#                                         state="hidden",
#                                         timeout=40000,
#                                     )

#                     else:
#                         print("No matching booking found")

#                     if modal_details:
#                         close_btn = modal_details.query_selector("#header-close")
#                         if close_btn:
#                             close_btn.click()
#                             page.wait_for_selector(
#                                 ".booking-panel",
#                                 state="hidden",
#                             )
#                             print("close button clicked")
#                         else:
#                             print("Close button not found")

#                     if same_client_booking:
#                         same_client_booking.click()
#                         modal_details = page.wait_for_selector(
#                             ".booking-panel", state="visible"
#                         )
#                         page.wait_for_function(
#                             """
#                                 (element) => {
#                                     const loaders = element.querySelectorAll('[class*="spinner"]');
#                                     return element && element.offsetParent !== null && loaders.length === 0;
#                                 }
#                                 """,
#                             arg=modal_details,
#                             timeout=20000,
#                         )
#                         modal_details.query_selector(
#                             "button[id='log-status-show']"
#                         ).click()
#                         try:
#                             unpaid_modal = page.wait_for_selector(
#                                 ".log-as-completed",
#                                 state="visible",
#                                 timeout=10000,
#                             )
#                             if unpaid_modal:
#                                 unpaid_text_area = unpaid_modal.query_selector(
#                                     "textarea[id='optional-internal-note-mobile']"
#                                 )
#                                 if unpaid_text_area:
#                                     unpaid_text_area.fill("Unpaid session logged off")
#                                     unpaid_modal.query_selector(
#                                         "button[id='log-and-go-to-pos-button']"
#                                     ).click()
#                                     page.wait_for_timeout(500)
#                                     spinner = page.query_selector(".spinner-background")
#                                     if spinner:
#                                         page.wait_for_selector(
#                                             ".spinner-background",
#                                             state="hidden",
#                                             timeout=40000,
#                                         )
#                                 # unpaid_modal.query_selector(
#                                 #     ".desktop-modal-header-close"
#                                 # ).click()
#                         except:
#                             page.wait_for_selector(
#                                 ".spinner-background",
#                                 state="hidden",
#                                 timeout=40000,
#                             )
#                         close_btn = modal_details.query_selector("#header-close")
#                         if close_btn:
#                             close_btn.click()
#                             page.wait_for_selector(
#                                 ".booking-panel",
#                                 state="hidden",
#                             )
#                             print("close button clicked")
#                         else:
#                             print("Close button not found")

#                 else:
#                     print("No bookings found")
#             else:
#                 print("No container found")
#             # remove_notes(user_id, all_bookings)
#             return {
#                 "status": True,
#                 "same_client_period": same_client_period,
#                 "message": (
#                     "Heads Up - Session was logged off, but unpaid.  Ask front desk team to process payment"
#                     if unpaid_modal
#                     else "Notes submitted successfully"
#                 ),
#             }
#         else:
#             print(location, "location")
#             page.wait_for_selector("select[name='stores']")
#             select_element = page.query_selector("select[name='stores']")
#             options = select_element.query_selector_all("option")
#             option = None
#             for opt in options:
#                 if opt.inner_text().lower() == location.lower():
#                     option = opt
#                     break
#             if option:
#                 option.click()
#                 page.click("input[name='Submit2']")
#                 page.wait_for_load_state("networkidle", timeout=0)
#                 page.goto("https://scheduling.clubready.com/day")
#                 page.wait_for_load_state("networkidle", timeout=0)
#                 page.wait_for_selector(
#                     ".spinner-background", state="hidden", timeout=40000
#                 )

#                 page.click("#dropdown-button")
#                 page.wait_for_selector(
#                     ".sidebar-events-filter-menu",
#                     state="visible",
#                     timeout=2000,
#                 )

#                 page.click(".dropdown--item:has(input#only-me)")
#                 container = page.query_selector(".sidebar-today-events")
#                 page.click("#dropdown-button")
#                 page.wait_for_selector(
#                     ".sidebar-events-filter-menu",
#                     state="hidden",
#                     timeout=2000,
#                 )
#                 unpaid_modal = None
#                 if container:
#                     div_selector = container.query_selector_all(
#                         "div[class*='sidebar-event-card']"
#                     )
#                     if len(div_selector) > 0:
#                         print("Table with class starting with 'ids' found.")
#                         print(div_selector)

#                         # matching_booking = None
#                         # for div in div_selector:
#                         #     event_date = div.query_selector(".event-date").inner_text()
#                         #     if event_date == period:
#                         #         matching_booking = div
#                         #         break
#                         matching_booking = None
#                         print(period, "period")
#                         matching_index = -1
#                         for i, div in enumerate(div_selector):
#                             event_date = div.query_selector(".event-date").inner_text()
#                             print(event_date, "event_date")
#                             if event_date == period:
#                                 matching_booking = div
#                                 matching_index = i
#                                 break

#                         if (
#                             matching_booking
#                             and matching_index >= 0
#                             and matching_index + 1 < len(div_selector)
#                         ):
#                             check_client = (
#                                 div_selector[matching_index + 1]
#                                 .query_selector(".event-customer")
#                                 .inner_text()
#                                 .lower()
#                             )
#                             if check_client == client_name:
#                                 same_client_booking = div_selector[matching_index + 1]
#                                 same_client_period = same_client_booking.query_selector(
#                                     ".event-date"
#                                 ).inner_text()
#                                 print(
#                                     f"Found next booking for same client at index {matching_index + 1}"
#                                 )
#                             else:
#                                 print(
#                                     f"Found next booking for different client at index {matching_index + 1}"
#                                 )

#                         if matching_booking:
#                             matching_booking.click()
#                             modal_details = page.wait_for_selector(
#                                 ".booking-panel", state="visible"
#                             )
#                             page.wait_for_function(
#                                 """
#                                                         (element) => {
#                                                             const loaders = element.querySelectorAll('[class*="spinner"]');
#                                                             return element && element.offsetParent !== null && loaders.length === 0;
#                                                         }
#                                                         """,
#                                 arg=modal_details,
#                                 timeout=20000,
#                             )

#                             open_notes_btn = modal_details.query_selector(
#                                 "button[id='make-note-footer']"
#                             )

#                             if open_notes_btn:
#                                 open_notes_btn.click()
#                                 note_modal = page.wait_for_selector(
#                                     "div[class='desktop-modal add-note']",
#                                     state="visible",
#                                     timeout=10000,
#                                 )
#                                 if note_modal:
#                                     subject_input = note_modal.query_selector(
#                                         "input[id='subject']"
#                                     )
#                                     notes_textarea = note_modal.query_selector(
#                                         "textarea[id='text']"
#                                     )
#                                     if subject_input and notes_textarea:
#                                         note_modal.query_selector("#tag-0").click()
#                                         subject_input.fill("Session Notes")
#                                         notes_textarea.fill(notes)

#                                         submit_btn = note_modal.query_selector(
#                                             "button[id='add-note-btn']"
#                                         )
#                                         if submit_btn:

#                                             submit_btn.click()
#                                             page.wait_for_selector(
#                                                 ".spinner-background",
#                                                 state="hidden",
#                                                 timeout=40000,
#                                             )

#                                     else:
#                                         print(
#                                             "Subject input or notes textarea not found"
#                                         )
#                                     close_btn = note_modal.query_selector(
#                                         "div[class='desktop-modal-header-close']"
#                                     )
#                                     if close_btn:
#                                         close_btn.click()

#                                         modal_details.query_selector(
#                                             "button[id='log-status-show']"
#                                         ).click()

#                                     try:
#                                         unpaid_modal = page.wait_for_selector(
#                                             ".log-as-completed",
#                                             state="visible",
#                                             timeout=10000,
#                                         )
#                                         if unpaid_modal:
#                                             unpaid_text_area = unpaid_modal.query_selector(
#                                                 "textarea[id='optional-internal-note-mobile']"
#                                             )
#                                             if unpaid_text_area:
#                                                 unpaid_text_area.fill(
#                                                     "Unpaid session logged off"
#                                                 )
#                                                 unpaid_modal.query_selector(
#                                                     "button[id='log-and-go-to-pos-button']"
#                                                 ).click()
#                                                 page.wait_for_timeout(500)
#                                                 spinner = page.query_selector(
#                                                     ".spinner-background"
#                                                 )
#                                                 if spinner:
#                                                     page.wait_for_selector(
#                                                         ".spinner-background",
#                                                         state="hidden",
#                                                         timeout=40000,
#                                                     )
#                                             # page.wait_for_timeout(500)
#                                             # unpaid_modal.query_selector(
#                                             #     ".desktop-modal-header-close"
#                                             # ).click()
#                                     except:
#                                         page.wait_for_selector(
#                                             ".spinner-background",
#                                             state="hidden",
#                                             timeout=40000,
#                                         )

#                         else:
#                             return {
#                                 "status": False,
#                                 "message": "No matching booking found",
#                             }

#                         if modal_details:
#                             close_btn = modal_details.query_selector("#header-close")
#                             if close_btn:
#                                 close_btn.click()
#                                 page.wait_for_selector(
#                                     ".booking-panel",
#                                     state="hidden",
#                                 )
#                             else:
#                                 print("Close button not found")

#                         if same_client_booking:
#                             same_client_booking.click()
#                             modal_details = page.wait_for_selector(
#                                 ".booking-panel", state="visible"
#                             )
#                             page.wait_for_function(
#                                 """
#                                 (element) => {
#                                     const loaders = element.querySelectorAll('[class*="spinner"]');
#                                     return element && element.offsetParent !== null && loaders.length === 0;
#                                 }
#                                 """,
#                                 arg=modal_details,
#                                 timeout=20000,
#                             )
#                             modal_details.query_selector(
#                                 "button[id='log-status-show']"
#                             ).click()
#                             try:
#                                 unpaid_modal = page.wait_for_selector(
#                                     ".log-as-completed",
#                                     state="visible",
#                                     timeout=10000,
#                                 )
#                                 if unpaid_modal:
#                                     unpaid_text_area = unpaid_modal.query_selector(
#                                         "textarea[id='optional-internal-note-mobile']"
#                                     )
#                                     if unpaid_text_area:
#                                         unpaid_text_area.fill(
#                                             "Unpaid session logged off"
#                                         )
#                                         unpaid_modal.query_selector(
#                                             "button[id='log-and-go-to-pos-button']"
#                                         ).click()
#                                         page.wait_for_timeout(500)
#                                         spinner = page.query_selector(
#                                             ".spinner-background"
#                                         )
#                                         if spinner:
#                                             page.wait_for_selector(
#                                                 ".spinner-background",
#                                                 state="hidden",
#                                                 timeout=40000,
#                                             )
#                                     # unpaid_modal.query_selector(
#                                     #     "button[id='log-and-go-to-pos-button']"
#                                     # ).click()
#                                     # page.wait_for_timeout(500)
#                                     # unpaid_modal.query_selector(
#                                     #     ".desktop-modal-header-close"
#                                     # ).click()
#                             except:
#                                 page.wait_for_selector(
#                                     ".spinner-background",
#                                     state="hidden",
#                                     timeout=40000,
#                                 )
#                             close_btn = modal_details.query_selector("#header-close")
#                             if close_btn:
#                                 close_btn.click()
#                                 page.wait_for_selector(
#                                     ".booking-panel",
#                                     state="hidden",
#                                 )
#                                 print("close button clicked")
#                             else:
#                                 print("Close button not found")
#                     else:
#                         print("No bookings found")
#                 else:
#                     print("No container found")
#                 # remove_notes(user_id, all_bookings)
#                 print(unpaid_modal, "unpaid_modal")
#                 return {
#                     "status": True,
#                     "same_client_period": same_client_period,
#                     "message": (
#                         "Heads Up - Session was logged off, but unpaid.  Ask front desk team to process payment"
#                         if unpaid_modal
#                         else "Notes submitted successfully"
#                     ),
#                 }

#     except Exception as e:
#         print(f"An error occurred during submitting notes: {str(e)}")
#         raise
#     finally:
#         if page:
#             page.close()
#         if context:
#             context.close()
#         if browser:
#             browser.close()
#         if playwright:
#             playwright.stop()


async def fetch_bookings_for_location(page, base_url, location_text, semaphore):
    async with semaphore:
        all_bookings = []
        try:
            print(f"Processing location: {location_text}")
            await page.goto(base_url)
            await page.wait_for_load_state("networkidle", timeout=0)

            await page.wait_for_selector("select[name='stores']", timeout=10000)
            select_element = await page.query_selector("select[name='stores']")
            if not select_element:
                print(f"Select element not found for location: {location_text}")
                return []

            options = await select_element.query_selector_all("option")
            option = None
            for opt in options:
                if (await opt.inner_text()).strip() == location_text.strip():
                    option = opt
                    break

            if not option:
                print(f"No option found with text: {location_text}")
                return []

            await option.click()
            await page.click("input[name='Submit2']")
            await page.wait_for_load_state("networkidle", timeout=0)
            await page.goto("https://app.clubready.com/admin/schedulingdayview.asp")

            await page.wait_for_load_state("networkidle", timeout=0)

            print(location_text)

            my_booking_tab = await page.wait_for_selector(
                "#dvtab1", state="visible", timeout=40000
            )
            await my_booking_tab.click()

            all_bookings_cards = []

            all_bookings_cards = (
                await page.query_selector_all("table[class*='bookby']")
                if await page.query_selector_all("table[class*='bookby']")
                else []
            )

            if not all_bookings_cards:
                return []

            print(f"Found {len(all_bookings_cards)} bookings")
            for table in all_bookings_cards:
                check_group = await table.query_selector(
                    "td[onclick*='cl_selectclass']"
                )

                if check_group:
                    details = await table.query_selector("table tbody tr td")

                    details_text = await details.inner_text()
                    parts = details_text.split(":")
                    event_date = parts[0] + ":" + parts[1] + ":" + parts[2]
                    workout_type = parts[3].strip()
                    flexologist_name = parts[4].strip()

                    print(
                        event_date,
                        workout_type,
                        flexologist_name,
                        "event date",
                    )

                    await details.click()
                    await page.wait_for_selector(
                        ".fancybox-skin",
                        state="visible",
                        timeout=10000,
                    )
                    booking_list_elem = await page.query_selector("#BookingList")
                    booking_list_html = (
                        await booking_list_elem.inner_html()
                        if booking_list_elem
                        else ""
                    )
                    if booking_list_html.strip() == "":
                        continue

                    iframe = page.frame_locator("iframe[src*='common/scheduling']")

                    await iframe.get_by_role("table").first.wait_for(
                        state="visible", timeout=20000
                    )
                    booking_tables = await iframe.locator("table").all()

                    # This line removes the first table from the list of booking_tables as this is the parent table,
                    booking_tables = booking_tables[1:]

                    for booking_table in booking_tables:
                        client_name = await booking_table.locator(
                            "a[href*='selectcust']"
                        ).inner_text()
                        booking_id = await booking_table.locator(
                            "a[href*='calldetails']"
                        ).first.inner_text()
                        first_timer = (
                            "YES"
                            if booking_table.locator(
                                "span[title*='first time visitor']"
                            )
                            else "NO"
                        )
                        active = "YES"
                        profile_image = (
                            "https://app.clubready.com/images/nouserphoto.png"
                        )
                        result = {
                            "client_name": client_name,
                            "booking_id": booking_id,
                            "workout_type": workout_type,
                            "flexologist_name": flexologist_name.lower(),
                            "phone": "",
                            "booking_time": (event_date.split("-")[0].strip()),
                            "event_date": event_date.strip(),
                            "past": False,
                            "first_timer": first_timer,
                            "active": active,
                            "location": location_text,
                            "profile_image": profile_image,
                            "group_booking": True,
                        }
                        all_bookings.append(result)
                else:
                    first_timer = (
                        "YES"
                        if await table.query_selector(
                            "table tbody tr td:nth-child(3) span[title='first time visitor']"
                        )
                        else "NO"
                    )
                    active = "YES"

                    client_name_elem = await table.query_selector(
                        "table tbody tr td:nth-child(3) a strong"
                    )
                    client_name = (
                        await client_name_elem.inner_text()
                        if client_name_elem
                        else "N/A"
                    )

                    booking_number_elem = await table.query_selector(
                        "table tbody tr td:nth-child(2) div:nth-child(4) span strong a"
                    )
                    booking_number = (
                        await booking_number_elem.inner_text()
                        if booking_number_elem
                        else "N/A"
                    )
                    booking_id = (
                        booking_number.lower().split("#")[1].strip()
                        if "#" in booking_number.lower()
                        else "N/A"
                    )
                    print(booking_id, "booking_id")

                    workout_type_elem = await table.query_selector(
                        "table tbody tr td:nth-child(2) div:nth-child(2) strong"
                    )
                    workout_type = (
                        await workout_type_elem.inner_text()
                        if workout_type_elem
                        else "N/A"
                    )

                    flexologist_name_elem = await table.query_selector(
                        "table tbody tr td:nth-child(2) div:nth-child(3) strong"
                    )
                    flexologist_name = (
                        await flexologist_name_elem.inner_text()
                        if flexologist_name_elem
                        else "N/A"
                    )

                    phone_elem = await table.query_selector(
                        "table tbody tr td:nth-child(3) .regtxt2"
                    )
                    phone_text = await phone_elem.inner_text() if phone_elem else "N/A"
                    if ":" in phone_text:
                        phone = phone_text.split(":")[1].strip()
                    else:
                        phone = phone_text

                    print(phone, "phone")

                    event_date_elem = await table.query_selector(
                        "table tbody tr td:nth-child(2) .headertxt"
                    )
                    event_date = (
                        await event_date_elem.inner_text() if event_date_elem else "N/A"
                    )
                    profile_elem = await table.query_selector(
                        "table tbody tr td:first-child img"
                    )
                    profile_image = (
                        await profile_elem.get_attribute("src")
                        if profile_elem
                        else "N/A"
                    )
                    if profile_image != "N/A":
                        if "nouser" in profile_image:
                            profile_image = (
                                "https://app.clubready.com/images/nouserphoto.png"
                            )
                        else:
                            profile_image = f"https://clubready.blob.core.windows.net/{profile_image}"

                    result = {
                        "client_name": client_name,
                        "booking_id": booking_id,
                        "workout_type": workout_type,
                        "flexologist_name": flexologist_name.split("with")[1]
                        .strip()
                        .lower(),
                        "phone": phone,
                        "booking_time": (
                            event_date.split("-")[0].strip()
                            if event_date != "N/A"
                            else "N/A"
                        ),
                        "event_date": event_date,
                        "past": False,
                        "first_timer": first_timer,
                        "active": active,
                        "location": location_text,
                        "profile_image": profile_image,
                        "group_booking": False,
                    }
                    all_bookings.append(result)

            return all_bookings

        except PlaywrightTimeoutError as e:
            print(f"Timeout error for location {location_text}: {e}")
            raise e
        except Exception as e:
            print(f"Error processing location {location_text}: {e}")
            raise e


async def get_user_bookings_from_clubready(user_details, max_concurrency=3):
    username = user_details["Username"]
    password = user_details["Password"]
    password = reverse_hash_credentials(username, password)
    print(username, password)
    async with async_playwright() as p:
        # Use custom browser context manager for automatic cleanup
        async with BrowserContextManager(p, headless=True) as browser:
            try:
                # Use context context manager for automatic cleanup
                async with await browser.new_context() as context:
                    async with await context.new_page() as page:
                        await page.goto(INITIAL_URL)
                        await page.fill("input[name='uid']", username)
                        await page.fill("input[name='pw']", password)
                        await page.click("input[type='submit']")
                        await page.wait_for_load_state("networkidle", timeout=0)
                        current_url = page.url
                        if "invalidlogin" in current_url:
                            print("Invalid Username or Password")
                            return {
                                "status": False,
                                "message": "Invalid Username or Password",
                                "bookings": [],
                            }

                        all_bookings = []
                        failed_locations = []
                        location = None
                        if "Dashboard" in current_url:
                            await page.goto(
                                "https://app.clubready.com/admin/schedulingdayview.asp"
                            )
                            await page.wait_for_load_state("networkidle", timeout=0)

                            location_element = await page.query_selector(
                                "#smalltopmenu .club-name"
                            )
                            if location_element:
                                location = await location_element.inner_text()
                                print(location, "here")
                            else:
                                new_page = await context.new_page()
                                try:
                                    await new_page.goto(
                                        "https://scheduling.clubready.com/day"
                                    )
                                    await new_page.wait_for_load_state(
                                        "networkidle", timeout=0
                                    )
                                    location_element = await new_page.query_selector(
                                        ".location-name"
                                    )
                                    if location_element:
                                        location = (
                                            await location_element.inner_text()
                                        ).strip()
                                        print(location, "location")
                                finally:
                                    await new_page.close()

                            my_booking_tab = await page.wait_for_selector(
                                "#dvtab1", state="visible", timeout=40000
                            )
                            await my_booking_tab.click()

                            all_bookings_cards = []

                            all_bookings_cards = (
                                await page.query_selector_all("table[class*='bookby']")
                                if await page.query_selector_all(
                                    "table[class*='bookby']"
                                )
                                else []
                            )

                            if not all_bookings_cards:
                                return {
                                    "status": True,
                                    "message": "No bookings found",
                                    "bookings": [],
                                    "failed_locations": [],
                                    "successful_locations": [location],
                                }

                            print(f"Found {len(all_bookings_cards)} bookings")
                            for table in all_bookings_cards:
                                # cl_selectclass(88575149, '111819068', 11/17/2025)
                                check_group = await table.query_selector(
                                    "td[onclick*='cl_selectclass']"
                                )

                                if check_group:
                                    print("great")

                                    details = await table.query_selector(
                                        "table tbody tr td"
                                    )

                                    details_text = await details.inner_text()
                                    parts = details_text.split(":")
                                    event_date = (
                                        parts[0] + ":" + parts[1] + ":" + parts[2]
                                    )
                                    workout_type = parts[3].strip()
                                    flexologist_name = parts[4].strip()

                                    print(
                                        event_date,
                                        workout_type,
                                        flexologist_name,
                                        "event date",
                                    )

                                    await details.click()
                                    await page.wait_for_selector(
                                        ".fancybox-skin",
                                        state="visible",
                                        timeout=10000,
                                    )

                                    booking_list_elem = await page.query_selector(
                                        "#BookingList"
                                    )
                                    booking_list_html = (
                                        await booking_list_elem.inner_html()
                                        if booking_list_elem
                                        else ""
                                    )
                                    if booking_list_html.strip() == "":
                                        continue

                                    iframe = page.frame_locator(
                                        "iframe[src*='common/scheduling']"
                                    )

                                    await iframe.get_by_role("table").first.wait_for(
                                        state="visible", timeout=20000
                                    )
                                    booking_tables = await iframe.locator("table").all()

                                    # This line removes the first table from the list of booking_tables as this is the parent table,
                                    booking_tables = booking_tables[1:]

                                    for booking_table in booking_tables:
                                        client_name = await booking_table.locator(
                                            "a[href*='selectcust']"
                                        ).inner_text()
                                        booking_id = await booking_table.locator(
                                            "a[href*='calldetails']"
                                        ).first.inner_text()
                                        first_timer = (
                                            "YES"
                                            if booking_table.locator(
                                                "span[title*='first time visitor']"
                                            )
                                            else "NO"
                                        )
                                        active = "YES"
                                        profile_image = "https://app.clubready.com/images/nouserphoto.png"
                                        result = {
                                            "client_name": client_name,
                                            "booking_id": booking_id,
                                            "workout_type": workout_type,
                                            "flexologist_name": flexologist_name.lower(),
                                            "phone": "",
                                            "booking_time": (
                                                event_date.split("-")[0].strip()
                                            ),
                                            "event_date": event_date.strip(),
                                            "past": False,
                                            "first_timer": first_timer,
                                            "active": active,
                                            "location": location,
                                            "profile_image": profile_image,
                                            "group_booking": True,
                                        }
                                        all_bookings.append(result)
                                else:

                                    first_timer = (
                                        "YES"
                                        if await table.query_selector(
                                            "table tbody tr td:nth-child(3) span[title='first time visitor']"
                                        )
                                        else "NO"
                                    )
                                    active = "YES"

                                    client_name_elem = await table.query_selector(
                                        "table tbody tr td:nth-child(3) a strong"
                                    )
                                    client_name = (
                                        await client_name_elem.inner_text()
                                        if client_name_elem
                                        else "N/A"
                                    )

                                    booking_number_elem = await table.query_selector(
                                        "table tbody tr td:nth-child(2) div:nth-child(4) span strong a"
                                    )
                                    booking_number = (
                                        await booking_number_elem.inner_text()
                                        if booking_number_elem
                                        else "N/A"
                                    )
                                    booking_id = (
                                        booking_number.lower().split("#")[1].strip()
                                        if "#" in booking_number.lower()
                                        else "N/A"
                                    )

                                    workout_type_elem = await table.query_selector(
                                        "table tbody tr td:nth-child(2) div:nth-child(2) strong"
                                    )
                                    workout_type = (
                                        await workout_type_elem.inner_text()
                                        if workout_type_elem
                                        else "N/A"
                                    )

                                    flexologist_name_elem = await table.query_selector(
                                        "table tbody tr td:nth-child(2) div:nth-child(3) strong"
                                    )
                                    flexologist_name = (
                                        await flexologist_name_elem.inner_text()
                                        if flexologist_name_elem
                                        else "N/A"
                                    )

                                    phone_elem = await table.query_selector(
                                        "table tbody tr td:nth-child(3) .regtxt2"
                                    )
                                    phone_text = (
                                        await phone_elem.inner_text()
                                        if phone_elem
                                        else "N/A"
                                    )
                                    if ":" in phone_text:
                                        phone = phone_text.split(":")[1].strip()
                                    else:
                                        phone = phone_text

                                    event_date_elem = await table.query_selector(
                                        "table tbody tr td:nth-child(2) .headertxt"
                                    )
                                    event_date = (
                                        await event_date_elem.inner_text()
                                        if event_date_elem
                                        else "N/A"
                                    )
                                    profile_elem = await table.query_selector(
                                        "table tbody tr td:first-child img"
                                    )
                                    profile_image = (
                                        await profile_elem.get_attribute("src")
                                        if profile_elem
                                        else "N/A"
                                    )

                                    if profile_image != "N/A":
                                        if "nouser" in profile_image:
                                            profile_image = "https://app.clubready.com/images/nouserphoto.png"
                                        else:
                                            profile_image = f"https://clubready.blob.core.windows.net/{profile_image}"

                                    # if profile_image != "N/A":
                                    #     if profile_image.includes("")

                                    result = {
                                        "client_name": client_name,
                                        "booking_id": booking_id,
                                        "workout_type": workout_type,
                                        "flexologist_name": flexologist_name.split(
                                            "with"
                                        )[1]
                                        .strip()
                                        .lower(),
                                        "phone": phone,
                                        "booking_time": (
                                            event_date.split("-")[0].strip()
                                            if event_date != "N/A"
                                            else "N/A"
                                        ),
                                        "event_date": event_date,
                                        "past": False,
                                        "first_timer": first_timer,
                                        "active": active,
                                        "location": location,
                                        "profile_image": profile_image,
                                        "group_booking": False,
                                    }
                                    all_bookings.append(result)

                        else:
                            await page.wait_for_selector("select[name='stores']")
                            select_element = await page.query_selector(
                                "select[name='stores']"
                            )
                            option_elements = await select_element.query_selector_all(
                                "option"
                            )
                            location_texts = [
                                await opt.inner_text() for opt in option_elements
                            ]

                            if not location_texts:
                                print("No locations found in dropdown")
                                return {
                                    "status": False,
                                    "message": "No locations found",
                                    "bookings": [],
                                }

                            print(
                                f"Found {len(location_texts)} locations: {location_texts}"
                            )

                            semaphore = asyncio.Semaphore(max_concurrency)
                            tasks = []

                            # Create a list to track contexts for cleanup
                            contexts_to_cleanup = []

                            try:
                                # Create tasks with location tracking
                                location_tasks = []
                                for location_text in location_texts:
                                    # Use context managers for each location's browser context
                                    new_context = await browser.new_context()
                                    contexts_to_cleanup.append(new_context)
                                    print(username, password)

                                    new_page = await new_context.new_page()
                                    await new_page.goto(INITIAL_URL)
                                    await new_page.fill("input[name='uid']", username)
                                    await new_page.fill("input[name='pw']", password)
                                    await new_page.click("input[type='submit']")
                                    await new_page.wait_for_load_state(
                                        "networkidle", timeout=0
                                    )

                                    task = asyncio.create_task(
                                        fetch_bookings_for_location(
                                            new_page,
                                            current_url,
                                            location_text,
                                            semaphore,
                                        )
                                    )
                                    # Store task with its location for tracking
                                    location_tasks.append((location_text, task))

                                # Wait for all tasks to complete and handle failures
                                results = await asyncio.gather(
                                    *[task for _, task in location_tasks],
                                    return_exceptions=True,
                                )

                                # Process results and track failures
                                successful_bookings = []

                                for (location_text, _), result in zip(
                                    location_tasks, results
                                ):
                                    if isinstance(result, Exception):
                                        print(
                                            f"Task failed for location {location_text}: {result}"
                                        )
                                        failed_locations.append(location_text)
                                    else:
                                        # Check if result is a genuine empty array or actual bookings
                                        if result is not None and isinstance(
                                            result, list
                                        ):
                                            successful_bookings.extend(result)
                                        else:
                                            print(
                                                f"Unexpected result for location {location_text}: {result}"
                                            )
                                            failed_locations.append(location_text)

                                all_bookings.extend(successful_bookings)

                                # Retry failed locations up to 2 times
                                if failed_locations:
                                    print(
                                        f"Retrying {len(failed_locations)} failed locations..."
                                    )
                                    retry_successful = []
                                    still_failed = []

                                    for location_text in failed_locations:
                                        success = False
                                        for retry_attempt in range(
                                            2
                                        ):  # Try up to 2 times
                                            try:
                                                print(
                                                    f"Retry attempt {retry_attempt + 1} for location: {location_text}"
                                                )

                                                # Create new context and page for retry
                                                retry_context = (
                                                    await browser.new_context()
                                                )
                                                retry_page = (
                                                    await retry_context.new_page()
                                                )
                                                await retry_page.goto(INITIAL_URL)
                                                await retry_page.fill(
                                                    "input[name='uid']", username
                                                )
                                                await retry_page.fill(
                                                    "input[name='pw']", password
                                                )
                                                await retry_page.click(
                                                    "input[type='submit']"
                                                )
                                                await retry_page.wait_for_load_state(
                                                    "networkidle", timeout=0
                                                )

                                                # Fetch bookings for this location
                                                retry_bookings = (
                                                    await fetch_bookings_for_location(
                                                        retry_page,
                                                        current_url,
                                                        location_text,
                                                        semaphore,
                                                    )
                                                )

                                                # Clean up retry context
                                                await retry_context.close()

                                                # Check if retry was successful
                                                if (
                                                    retry_bookings is not None
                                                    and isinstance(retry_bookings, list)
                                                ):
                                                    all_bookings.extend(retry_bookings)
                                                    retry_successful.append(
                                                        location_text
                                                    )
                                                    success = True
                                                    print(
                                                        f"Retry successful for location: {location_text}"
                                                    )
                                                    break
                                                else:
                                                    print(
                                                        f"Retry returned empty result for location: {location_text}"
                                                    )

                                            except Exception as e:
                                                print(
                                                    f"Retry attempt {retry_attempt + 1} failed for {location_text}: {e}"
                                                )
                                                # Clean up on exception
                                                try:
                                                    await retry_context.close()
                                                except:
                                                    pass

                                        if not success:
                                            still_failed.append(location_text)
                                            print(
                                                f"Location {location_text} failed after all retry attempts"
                                            )

                                    failed_locations = (
                                        still_failed  # Update failed locations list
                                    )

                            finally:
                                # Ensure all contexts are cleaned up
                                for ctx in contexts_to_cleanup:
                                    try:
                                        await ctx.close()
                                    except Exception as e:
                                        print(f"Error closing context: {e}")

                        # Return results with failed locations for retry
                        if failed_locations:
                            message = (
                                f"Bookings fetched successfully. {len(failed_locations)} locations failed "
                                f"after retry attempts (2 retries each)."
                            )
                        else:
                            message = "Bookings fetched successfully (including retries for failed locations)."

                        response = {
                            "status": len(failed_locations) == 0,  # True if no failures
                            "message": message,
                            "bookings": all_bookings,
                            "failed_locations": failed_locations,
                            "successful_locations": (
                                [location]
                                if "Dashboard" in current_url
                                else [
                                    loc
                                    for loc in location_texts
                                    if loc not in failed_locations
                                ]
                            ),
                        }
                        return response

            except PlaywrightTimeoutError as e:
                print(f"Timeout error: {e}")
                raise e
            except Exception as e:
                print(f"Error fetching bookings: {e}")
                raise e


def submit_notes(
    username,
    password,
    period,
    notes,
    location=None,
    client_name=None,
    group_booking=False,
):
    password = reverse_hash_credentials(username, password)
    playwright = None
    browser = None
    context = None
    page = None

    def capture_and_upload_screenshot(local_page, label):
        try:
            png_bytes = local_page.screenshot(full_page=True)
            image_name = f"errors/{int(time.time())}_{uuid.uuid4().hex}_{label}.png"

            result = save_error_image_to_s3(
                BytesIO(png_bytes), image_name, content_type="image/png"
            )
            if isinstance(result, dict) and result.get("status") == "success":
                return result.get("url")
            else:
                logging.error(
                    f"S3 upload failed: {result.get('message', 'Unknown error')}"
                )
                return None
        except Exception as _s3e:
            logging.error(f"Failed to capture/upload screenshot: {_s3e}")
            return None

    def get_bookings(page):
        my_booking_tab = page.wait_for_selector(
            "#dvtab1", state="visible", timeout=40000
        )
        my_booking_tab.click()
        all_bookings_cards = []

        all_bookings_cards = (
            page.query_selector_all("table[class*='bookby']")
            if page.query_selector_all("table[class*='bookby']")
            else []
        )
        return all_bookings_cards

    def handle_submission(page, all_bookings_cards):
        unpaid_modal = False
        modal_details = None
        same_client_booking = None
        same_client_period = None
        matching_booking = None
        matching_index = -1
        event_date = None

        for i, div in enumerate(all_bookings_cards):
            if group_booking:
                details = div.query_selector("table tbody tr td")
                details_text = details.inner_text()
                parts = details_text.split(":")
                event_date = parts[0] + ":" + parts[1] + ":" + parts[2]
                event_date = event_date.strip()
            else:
                header_element = div.query_selector(
                    "table tbody tr td:nth-child(2) .headertxt"
                )
                if header_element:
                    event_date = header_element.inner_text()
                else:
                    continue
            print(event_date, period)
            print(event_date == period)
            if event_date == period:
                matching_booking = div
                matching_index = i
                break

        if (
            matching_booking
            and matching_index >= 0
            and matching_index + 1 < len(all_bookings_cards)
            and not group_booking
        ):
            check_client = (
                all_bookings_cards[matching_index + 1]
                .query_selector("table tbody tr td:nth-child(3) a strong")
                .inner_text()
                .lower()
            )
            if check_client == client_name:
                same_client_booking = all_bookings_cards[matching_index + 1]
                same_client_period = same_client_booking.query_selector(
                    "table tbody tr td:nth-child(2) .headertxt"
                ).inner_text()
                print(
                    f"Found next booking for same client at index {matching_index + 1}"
                )
            else:
                print(
                    f"Found next booking for different client at index {matching_index + 1}"
                )

        if matching_booking:
            if group_booking:
                details = matching_booking.query_selector("table tbody tr td")
                details.click()
                page.wait_for_selector(
                    ".fancybox-skin",
                    state="visible",
                    timeout=10000,
                )

                iframe = page.frame_locator("iframe[src*='common/scheduling']")

                iframe.get_by_role("table").first.wait_for(
                    state="visible", timeout=20000
                )
                booking_tables = iframe.locator("table").all()

                # This line removes the first table from the list of booking_tables as this is the parent table,
                booking_tables = booking_tables[1:]

                for booking_table in booking_tables:
                    check_name = booking_table.locator(
                        "a[href*='selectcust']"
                    ).inner_text()
                    if check_name.lower().strip() == client_name:
                        booking_table.locator("a[href*='calldetails']").first.click()
                        break

            else:
                booking_number_elem = matching_booking.query_selector(
                    "table tbody tr td:nth-child(2) div:nth-child(4) span strong a"
                )
                booking_number_elem.wait_for_element_state("visible", timeout=10000)
                booking_number_elem.wait_for_element_state("stable", timeout=10000)
                booking_number_elem.click()

            more_modal = page.wait_for_selector(
                ".fancybox-skin",
                state="visible",
                timeout=10000,
            )
            log_off_tab = more_modal.query_selector("#subnav2 li:last-child")
            log_off_tab.wait_for_element_state("visible", timeout=10000)
            log_off_tab.wait_for_element_state("stable", timeout=10000)
            log_off_tab.click()
            page.wait_for_function("element => !element.isConnected", arg=log_off_tab)
            page.wait_for_selector("#subnav2 li.activesublink2", timeout=10000)
            form_details = page.wait_for_selector(
                "#bkdetailform", state="visible", timeout=40000
            )
            page.wait_for_function(
                "element => element.isConnected && element.offsetParent !== null",
                arg=form_details,
            )

            booking_successful = page.query_selector(".baseline #lg_stat5")
            if booking_successful:
                booking_successful.wait_for_element_state("visible", timeout=10000)
                booking_successful.wait_for_element_state("stable", timeout=10000)
                booking_successful.click()
                page.wait_for_function(
                    "element => element.getAttribute('src') === '/images/bookingstatus5.png'",
                    arg=booking_successful,
                    timeout=10000,
                )

                text_area = page.query_selector("#bkdetailform textarea#note")
                if text_area:
                    text_area.fill(notes)
                else:
                    screenshot_url = capture_and_upload_screenshot(page, "no_text_area")
                    raise Exception(
                        f"No text area found in the booking{f' | screenshot: {screenshot_url}' if screenshot_url else ''}"
                    )

                log_off_btn = page.query_selector("#logbutton input:first-child")
                log_off_btn.wait_for_element_state("visible", timeout=10000)
                log_off_btn.wait_for_element_state("stable", timeout=10000)

                log_off_btn.click()
                page.wait_for_timeout(1000)
                unpaid_modal = (
                    True
                    if matching_booking.query_selector(
                        "table tbody tr td:nth-child(2) div:nth-child(5)"
                    )
                    else False
                )
            else:
                list_items = page.query_selector_all("#subnav2 li")
                if len(list_items) >= 3:
                    mid_div = page.query_selector("#bkdetailform .infobox")
                    if "session logged as completed" in mid_div.inner_text().lower():
                        notes_tab = page.query_selector(
                            ".fancybox-skin #subnav2 li:nth-child(2)"
                        )
                        notes_tab.wait_for_element_state("visible", timeout=10000)
                        notes_tab.wait_for_element_state("stable", timeout=10000)
                        notes_tab.click()
                        page.wait_for_function(
                            "element => !element.isConnected", arg=notes_tab
                        )
                        page.wait_for_selector(
                            "#subnav2 li.activesublink2", timeout=10000
                        )
                        form_details = page.wait_for_selector(
                            "#bkdetailform", state="visible", timeout=40000
                        )
                        page.wait_for_function(
                            "element => element.isConnected && element.offsetParent !== null",
                            arg=form_details,
                        )
                        page.select_option(
                            "select[id='bookingnoteclassifyID']",
                            label="Fitness Related",
                        )
                        textarea = page.query_selector("#bookingnotetext")
                        if textarea:
                            textarea.fill(notes)
                        else:
                            # come here and ad dthe screen capture to follow it bro
                            screenshot_url = capture_and_upload_screenshot(
                                page, "no_text_area"
                            )
                            raise Exception(
                                f"No text area found in the booking{f' | screenshot: {screenshot_url}' if screenshot_url else ''}"
                            )

                        submit_btn = page.query_selector("input[onclick*='addnote']")
                        submit_btn.click()
                        same_client_booking = None
                        page.wait_for_timeout(1000)
                else:
                    if len(list_items) < 3:
                        notes_tab = page.query_selector(
                            ".fancybox-skin #subnav2 li:nth-child(2)"
                        )
                        notes_tab.wait_for_element_state("visible", timeout=10000)
                        notes_tab.wait_for_element_state("stable", timeout=10000)
                        notes_tab.click()
                        page.wait_for_function(
                            "element => !element.isConnected", arg=notes_tab
                        )
                        page.wait_for_selector(
                            "#subnav2 li.activesublink2", timeout=10000
                        )
                        form_details = page.wait_for_selector(
                            "#bkdetailform", state="visible", timeout=40000
                        )
                        page.wait_for_function(
                            "element => element.isConnected && element.offsetParent !== null",
                            arg=form_details,
                        )
                        page.select_option(
                            "select[id='bookingnoteclassifyID']",
                            label="Fitness Related",
                        )
                        textarea = page.query_selector("#bookingnotetext")
                        if textarea:
                            textarea.fill(notes)
                        else:
                            # come here and ad dthe screen capture to follow it bro
                            screenshot_url = capture_and_upload_screenshot(
                                page, "no_text_area"
                            )
                            raise Exception(
                                f"No text area found in the booking{f' | screenshot: {screenshot_url}' if screenshot_url else ''}"
                            )

                        submit_btn = page.query_selector("input[onclick*='addnote']")
                        submit_btn.click()
                        same_client_booking = None
                        page.wait_for_timeout(1000)

                    else:
                        screenshot_url = capture_and_upload_screenshot(
                            page, "no_session_logged"
                        )
                        raise Exception(
                            f"No session logged{f' | screenshot: {screenshot_url}' if screenshot_url else ''}"
                        )

        else:
            screenshot_url = capture_and_upload_screenshot(page, "no_matching_booking")
            raise Exception(
                f"No matching booking found{f' | screenshot: {screenshot_url}' if screenshot_url else ''}"
            )

        if same_client_booking:
            all_bookings = page.query_selector_all("table[class*='bookby']")
            same_client_booking = all_bookings[matching_index + 1]
            booking_number_elem = same_client_booking.query_selector(
                "table tbody tr td:nth-child(2) div:nth-child(4) span strong a"
            )
            booking_number_elem.wait_for_element_state("visible", timeout=10000)
            booking_number_elem.wait_for_element_state("stable", timeout=10000)
            booking_number_elem.click()

            more_modal = page.wait_for_selector(
                ".fancybox-skin",
                state="visible",
                timeout=10000,
            )
            log_off_tab = more_modal.query_selector("#subnav2 li:last-child")
            log_off_tab.wait_for_element_state("visible", timeout=10000)
            log_off_tab.wait_for_element_state("stable", timeout=10000)
            log_off_tab.click()
            page.wait_for_function("element => !element.isConnected", arg=log_off_tab)
            page.wait_for_selector("#subnav2 li.activesublink2", timeout=10000)
            form_details = page.wait_for_selector(
                "#bkdetailform", state="visible", timeout=40000
            )
            page.wait_for_function(
                "element => element.isConnected && element.offsetParent !== null",
                arg=form_details,
            )

            booking_successful = page.query_selector(".baseline #lg_stat5")
            if booking_successful:
                booking_successful.wait_for_element_state("visible", timeout=10000)
                booking_successful.wait_for_element_state("stable", timeout=10000)
                booking_successful.click()
                page.wait_for_function(
                    "element => element.getAttribute('src') === '/images/bookingstatus5.png'",
                    arg=booking_successful,
                    timeout=10000,
                )
            text_area = page.query_selector("#bkdetailform textarea#note")
            if text_area:
                text_area.fill(notes)
            else:
                screenshot_url = capture_and_upload_screenshot(page, "no_text_area")
                raise Exception(
                    f"No text area found{f' | screenshot: {screenshot_url}' if screenshot_url else ''}"
                )

            log_off_btn = page.query_selector("#logbutton input:first-child")
            log_off_btn.wait_for_element_state("visible", timeout=10000)
            log_off_btn.wait_for_element_state("stable", timeout=10000)

            log_off_btn.click()
            page.wait_for_timeout(600)
            unpaid_modal = (
                True
                if matching_booking.query_selector(
                    "table tbody tr td:nth-child(2) div:nth-child(5)"
                )
                else False
            )
        return same_client_period, unpaid_modal

    try:
        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        page.goto(INITIAL_URL)
        page.fill("input[name='uid']", username)
        page.fill("input[name='pw']", password)
        page.click("input[type='submit']")
        page.wait_for_load_state("networkidle", timeout=0)
        base_url = page.url
        if "Dashboard" in base_url:
            page.goto("https://app.clubready.com/admin/schedulingdayview.asp")
            page.wait_for_load_state("networkidle", timeout=0)

            all_bookings_cards = get_bookings(page)

            if len(all_bookings_cards) > 0:
                same_client_period, unpaid_modal = handle_submission(
                    page, all_bookings_cards
                )
            else:
                screenshot_url = capture_and_upload_screenshot(page, "no_container")
                raise Exception(
                    f"No container found{f' | screenshot: {screenshot_url}' if screenshot_url else ''}"
                )
            # remove_notes(user_id, all_bookings)

        else:
            print(location, "location")
            page.wait_for_selector("select[name='stores']")
            select_element = page.query_selector("select[name='stores']")
            options = select_element.query_selector_all("option")
            option = None
            for opt in options:
                if opt.inner_text().lower() == location.lower():
                    option = opt
                    break
            if option:
                option.click()
                page.click("input[name='Submit2']")
                page.wait_for_load_state("networkidle", timeout=0)
                page.goto("https://app.clubready.com/admin/schedulingdayview.asp")
                page.wait_for_load_state("networkidle", timeout=0)

                all_bookings_cards = get_bookings(page)

                if len(all_bookings_cards) > 0:
                    same_client_period, unpaid_modal = handle_submission(
                        page, all_bookings_cards
                    )
                else:
                    screenshot_url = capture_and_upload_screenshot(page, "no_container")
                    raise Exception(
                        f"No container found{f' | screenshot: {screenshot_url}' if screenshot_url else ''}"
                    )

        return {
            "status": True,
            "same_client_period": same_client_period,
            "message": (
                "Heads Up - Session was logged off, but unpaid.  Ask front desk team to process payment"
                if unpaid_modal
                else "Notes submitted successfully"
            ),
        }

    except Exception as e:
        print(f"An error occurred during submitting notes: {str(e)}")
        screenshot_url = capture_and_upload_screenshot(page, "no_container")
        raise Exception(
            f"{str(e)}{f' | screenshot: {screenshot_url}' if screenshot_url else ''}"
        )
    finally:
        if page:
            page.close()
        if context:
            context.close()
        if browser:
            browser.close()
        if playwright:
            playwright.stop()


def submit_after_log_off(
    username, password, period, notes, location=None, client_name=None
):
    password = reverse_hash_credentials(username, password)
    playwright = None
    browser = None
    context = None
    page = None
    modal_details = None
    same_client_booking = None
    same_client_period = None

    def capture_and_upload_screenshot(local_page, label):
        try:
            png_bytes = local_page.screenshot(full_page=True)
            image_name = f"errors/{int(time.time())}_{uuid.uuid4().hex}_{label}.png"

            result = save_error_image_to_s3(
                BytesIO(png_bytes), image_name, content_type="image/png"
            )
            if isinstance(result, dict) and result.get("status") == "success":
                return result.get("url")
            else:
                logging.error(
                    f"S3 upload failed: {result.get('message', 'Unknown error')}"
                )
                return None
        except Exception as _s3e:
            logging.error(f"Failed to capture/upload screenshot: {_s3e}")
            return None

    def get_bookings(page):
        my_booking_tab = page.wait_for_selector(
            "#dvtab1", state="visible", timeout=40000
        )
        my_booking_tab.click()
        all_bookings_cards = []

        all_bookings_cards = (
            page.query_selector_all("table[class*='bookby']")
            if page.query_selector_all("table[class*='bookby']")
            else []
        )
        return all_bookings_cards

    def handle_submission(page, all_bookings_cards):
        unpaid_modal = False
        modal_details = None
        same_client_booking = None
        same_client_period = None
        matching_booking = None
        matching_index = -1
        print(f"Bookings found for location: {location} {len(all_bookings_cards)}")

        matching_booking = None
        matching_index = -1

        for i, div in enumerate(all_bookings_cards):
            event_date = div.query_selector(
                "table tbody tr td:nth-child(2) .headertxt"
            ).inner_text()
            print(event_date, period)
            print(event_date == period)
            if event_date == period:
                matching_booking = div
                matching_index = i
                break

        if (
            matching_booking
            and matching_index >= 0
            and matching_index + 1 < len(all_bookings_cards)
        ):
            check_client = (
                all_bookings_cards[matching_index + 1]
                .query_selector("table tbody tr td:nth-child(3) a strong")
                .inner_text()
                .lower()
            )
            if check_client == client_name:
                same_client_booking = all_bookings_cards[matching_index + 1]
                same_client_period = same_client_booking.query_selector(
                    "table tbody tr td:nth-child(2) .headertxt"
                ).inner_text()
                print(
                    f"Found next booking for same client at index {matching_index + 1}"
                )
            else:
                print(
                    f"Found next booking for different client at index {matching_index + 1}"
                )

        if matching_booking:
            booking_number_elem = matching_booking.query_selector(
                "table tbody tr td:nth-child(2) div:nth-child(4) span strong a"
            )
            booking_number_elem.wait_for_element_state("visible", timeout=10000)
            booking_number_elem.wait_for_element_state("stable", timeout=10000)
            booking_number_elem.click()

            more_modal = page.wait_for_selector(
                ".fancybox-skin",
                state="visible",
                timeout=10000,
            )
            notes_tab = more_modal.query_selector("#subnav2 li:nth-child(2)")
            notes_tab.wait_for_element_state("visible", timeout=10000)
            notes_tab.wait_for_element_state("stable", timeout=10000)
            notes_tab.click()
            page.wait_for_function("element => !element.isConnected", arg=notes_tab)
            page.wait_for_selector("#subnav2 li.activesublink2", timeout=10000)
            form_details = page.wait_for_selector(
                "#bkdetailform", state="visible", timeout=40000
            )
            page.wait_for_function(
                "element => element.isConnected && element.offsetParent !== null",
                arg=form_details,
            )
            page.select_option(
                "select[id='bookingnoteclassifyID']", label="Fitness Related"
            )
            textarea = page.query_selector("#bookingnotetext")
            if textarea:
                textarea.fill(notes)
            else:
                # come here and ad dthe screen capture to follow it bro
                screenshot_url = capture_and_upload_screenshot(page, "no_text_area")
                raise Exception(
                    f"No text area found in the booking{f' | screenshot: {screenshot_url}' if screenshot_url else ''}"
                )

            submit_btn = page.query_selector("input[onclick*='addnote']")
            submit_btn.click()
            page.wait_for_timeout(1000)

        else:
            screenshot_url = capture_and_upload_screenshot(page, "no_matching_booking")
            raise Exception(
                f"No matching booking found{f' | screenshot: {screenshot_url}' if screenshot_url else ''}"
            )
        return same_client_period

    try:
        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        page.goto(INITIAL_URL)
        page.fill("input[name='uid']", username)
        page.fill("input[name='pw']", password)
        page.click("input[type='submit']")
        page.wait_for_load_state("networkidle", timeout=0)
        base_url = page.url
        if "Dashboard" in base_url:
            page.goto("https://app.clubready.com/admin/schedulingdayview.asp")
            page.wait_for_load_state("networkidle", timeout=0)

            all_bookings_cards = get_bookings(page)

            if len(all_bookings_cards) > 0:
                same_client_period = handle_submission(page, all_bookings_cards)

            else:
                screenshot_url = capture_and_upload_screenshot(page, "no_container")
                raise Exception(
                    f"No container found{f' | screenshot: {screenshot_url}' if screenshot_url else ''}"
                )

        else:
            print(location, "location")
            page.wait_for_selector("select[name='stores']")
            select_element = page.query_selector("select[name='stores']")
            options = select_element.query_selector_all("option")
            option = None
            for opt in options:
                if opt.inner_text().lower() == location.lower():
                    option = opt
                    break
            if option:
                option.click()
                page.click("input[name='Submit2']")
                page.wait_for_load_state("networkidle", timeout=0)
                page.goto("https://app.clubready.com/admin/schedulingdayview.asp")
                page.wait_for_load_state("networkidle", timeout=0)
                all_bookings_cards = get_bookings(page)

                if len(all_bookings_cards) > 0:
                    same_client_period = handle_submission(page, all_bookings_cards)

                else:
                    screenshot_url = capture_and_upload_screenshot(page, "no_container")
                    raise Exception(
                        f"No container found{f' | screenshot: {screenshot_url}' if screenshot_url else ''}"
                    )
        return {
            "status": True,
            "same_client_period": same_client_period,
            "message": "Notes submitted successfully",
        }

    except Exception as e:
        print(f"An error occurred during submitting notes: {str(e)}")
        screenshot_url = capture_and_upload_screenshot(page, "no_container")
        raise Exception(
            f"{str(e)}{f' | screenshot: {screenshot_url}' if screenshot_url else ''}"
        )
    finally:
        if page:
            page.close()
        if context:
            context.close()
        if browser:
            browser.close()
        if playwright:
            playwright.stop()


def log_off_booking(username, password, period, location=None, client_name=None):
    password = reverse_hash_credentials(username, password)
    playwright = None
    browser = None
    context = None
    page = None
    modal_details = None

    def capture_and_upload_screenshot(local_page, label):
        try:
            png_bytes = local_page.screenshot(full_page=True)
            image_name = f"errors/{int(time.time())}_{uuid.uuid4().hex}_{label}.png"

            result = save_error_image_to_s3(
                BytesIO(png_bytes), image_name, content_type="image/png"
            )
            if isinstance(result, dict) and result.get("status") == "success":
                return result.get("url")
            else:
                logging.error(
                    f"S3 upload failed: {result.get('message', 'Unknown error')}"
                )
                return None
        except Exception as _s3e:
            logging.error(f"Failed to capture/upload screenshot: {_s3e}")
            return None

    def get_bookings(page):
        my_booking_tab = page.wait_for_selector(
            "#dvtab1", state="visible", timeout=40000
        )
        my_booking_tab.click()
        all_bookings_cards = []

        all_bookings_cards = (
            page.query_selector_all("table[class*='bookby']")
            if page.query_selector_all("table[class*='bookby']")
            else []
        )
        return all_bookings_cards

    def handle_log_off(page, all_bookings_cards):
        same_client_booking = None
        same_client_period = None
        unpaid_modal = False

        print(f"Bookings found for location: {location} {len(all_bookings_cards)}")

        matching_booking = None
        matching_index = -1

        for i, div in enumerate(all_bookings_cards):
            event_date = div.query_selector(
                "table tbody tr td:nth-child(2) .headertxt"
            ).inner_text()
            print(event_date, period)
            print(event_date == period)
            if event_date == period:
                matching_booking = div
                matching_index = i
                break

        if (
            matching_booking
            and matching_index >= 0
            and matching_index + 1 < len(all_bookings_cards)
        ):
            check_client = (
                all_bookings_cards[matching_index + 1]
                .query_selector("table tbody tr td:nth-child(3) a strong")
                .inner_text()
                .lower()
            )
            if check_client == client_name:
                same_client_booking = all_bookings_cards[matching_index + 1]
                same_client_period = same_client_booking.query_selector(
                    "table tbody tr td:nth-child(2) .headertxt"
                ).inner_text()
                print(
                    f"Found next booking for same client at index {matching_index + 1}"
                )
            else:
                print(
                    f"Found next booking for different client at index {matching_index + 1}"
                )

        if matching_booking:
            booking_number_elem = matching_booking.query_selector(
                "table tbody tr td:nth-child(2) div:nth-child(4) span strong a"
            )
            booking_number_elem.wait_for_element_state("visible", timeout=10000)
            booking_number_elem.wait_for_element_state("stable", timeout=10000)
            booking_number_elem.click()

            more_modal = page.wait_for_selector(
                ".fancybox-skin",
                state="visible",
                timeout=10000,
            )
            log_off_tab = more_modal.query_selector("#subnav2 li:last-child")
            log_off_tab.wait_for_element_state("visible", timeout=10000)
            log_off_tab.wait_for_element_state("stable", timeout=10000)
            log_off_tab.click()
            page.wait_for_function("element => !element.isConnected", arg=log_off_tab)
            page.wait_for_selector("#subnav2 li.activesublink2", timeout=10000)
            form_details = page.wait_for_selector(
                "#bkdetailform", state="visible", timeout=40000
            )
            page.wait_for_function(
                "element => element.isConnected && element.offsetParent !== null",
                arg=form_details,
            )

            booking_successful = page.query_selector(".baseline #lg_stat5")
            if booking_successful:
                booking_successful.wait_for_element_state("visible", timeout=10000)
                booking_successful.wait_for_element_state("stable", timeout=10000)
                booking_successful.click()
                page.wait_for_function(
                    "element => element.getAttribute('src') === '/images/bookingstatus5.png'",
                    arg=booking_successful,
                    timeout=10000,
                )

                text_area = page.query_selector("#bkdetailform textarea#note")
                notes = "Client showed up"
                if text_area:
                    text_area.fill(notes)
                else:
                    screenshot_url = capture_and_upload_screenshot(page, "no_text_area")
                    raise Exception(
                        f"No text area found in the booking{f' | screenshot: {screenshot_url}' if screenshot_url else ''}"
                    )

                log_off_btn = page.query_selector("#logbutton input:first-child")
                log_off_btn.wait_for_element_state("visible", timeout=10000)
                log_off_btn.wait_for_element_state("stable", timeout=10000)

                log_off_btn.click()
                page.wait_for_timeout(1000)
                unpaid_modal = (
                    True
                    if matching_booking.query_selector(
                        "table tbody tr td:nth-child(2) div:nth-child(5)"
                    )
                    else False
                )
            else:
                mid_div = page.query_selector("#bkdetailform .infobox")
                if mid_div:
                    if (
                        "session logged as completed"
                        not in mid_div.inner_text().lower()
                    ):
                        screenshot_url = capture_and_upload_screenshot(
                            page, "log_off_error"
                        )
                        raise Exception(
                            f"No log off button {f' | screenshot: {screenshot_url}' if screenshot_url else ''}"
                        )
                else:
                    screenshot_url = capture_and_upload_screenshot(
                        page, "log_off_error"
                    )
                    raise Exception(
                        f"No log off button {f' | screenshot: {screenshot_url}' if screenshot_url else ''}"
                    )

        else:
            screenshot_url = capture_and_upload_screenshot(page, "no_matching_booking")
            raise Exception(
                f"No matching booking found{f' | screenshot: {screenshot_url}' if screenshot_url else ''}"
            )

        if same_client_booking:
            all_bookings = page.query_selector_all("table[class*='bookby']")
            same_client_booking = all_bookings[matching_index + 1]
            booking_number_elem = same_client_booking.query_selector(
                "table tbody tr td:nth-child(2) div:nth-child(4) span strong a"
            )
            booking_number_elem.wait_for_element_state("visible", timeout=10000)
            booking_number_elem.wait_for_element_state("stable", timeout=10000)
            booking_number_elem.click()

            more_modal = page.wait_for_selector(
                ".fancybox-skin",
                state="visible",
                timeout=10000,
            )
            log_off_tab = more_modal.query_selector("#subnav2 li:last-child")
            log_off_tab.wait_for_element_state("visible", timeout=10000)
            log_off_tab.wait_for_element_state("stable", timeout=10000)
            log_off_tab.click()
            page.wait_for_function("element => !element.isConnected", arg=log_off_tab)
            page.wait_for_selector("#subnav2 li.activesublink2", timeout=10000)
            form_details = page.wait_for_selector(
                "#bkdetailform", state="visible", timeout=40000
            )
            page.wait_for_function(
                "element => element.isConnected && element.offsetParent !== null",
                arg=form_details,
            )

            booking_successful = page.query_selector(".baseline #lg_stat5")
            if booking_successful:
                booking_successful.wait_for_element_state("visible", timeout=10000)
                booking_successful.wait_for_element_state("stable", timeout=10000)
                booking_successful.click()
                page.wait_for_function(
                    "element => element.getAttribute('src') === '/images/bookingstatus5.png'",
                    arg=booking_successful,
                    timeout=10000,
                )
                text_area = page.query_selector("#bkdetailform textarea#note")
                notes = "Client showed up"
                if text_area:
                    text_area.fill(notes)
                else:
                    screenshot_url = capture_and_upload_screenshot(page, "no_text_area")
                    raise Exception(
                        f"No text area found{f' | screenshot: {screenshot_url}' if screenshot_url else ''}"
                    )

                log_off_btn = page.query_selector("#logbutton input:first-child")
                log_off_btn.wait_for_element_state("visible", timeout=10000)
                log_off_btn.wait_for_element_state("stable", timeout=10000)

                log_off_btn.click()
                page.wait_for_timeout(600)
                unpaid_modal = (
                    True
                    if matching_booking.query_selector(
                        "table tbody tr td:nth-child(2) div:nth-child(5)"
                    )
                    else False
                )
            else:
                mid_div = page.query_selector("#bkdetailform .infobox")
                if mid_div:
                    if (
                        "session logged as completed"
                        not in mid_div.inner_text().lower()
                    ):
                        screenshot_url = capture_and_upload_screenshot(
                            page, "log_off_error"
                        )
                        raise Exception(
                            f"No log off button {f' | screenshot: {screenshot_url}' if screenshot_url else ''}"
                        )
                else:
                    screenshot_url = capture_and_upload_screenshot(
                        page, "log_off_error"
                    )
                    raise Exception(
                        f"No log off button {f' | screenshot: {screenshot_url}' if screenshot_url else ''}"
                    )

        return same_client_period, unpaid_modal

    try:
        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        page.goto(INITIAL_URL)
        page.fill("input[name='uid']", username)
        page.fill("input[name='pw']", password)
        page.click("input[type='submit']")
        page.wait_for_load_state("networkidle", timeout=0)
        base_url = page.url
        if "Dashboard" in base_url:
            page.goto("https://app.clubready.com/admin/schedulingdayview.asp")
            page.wait_for_load_state("networkidle", timeout=0)

            all_bookings_cards = get_bookings(page)

            unpaid_modal = False
            if len(all_bookings_cards) > 0:
                same_client_period, unpaid_modal = handle_log_off(
                    page, all_bookings_cards
                )
            else:
                screenshot_url = capture_and_upload_screenshot(page, "no_container")
                raise Exception(
                    f"No container found{f' | screenshot: {screenshot_url}' if screenshot_url else ''}"
                )
            # remove_notes(user_id, all_bookings)
        else:
            print(location, "location")
            page.wait_for_selector("select[name='stores']")
            select_element = page.query_selector("select[name='stores']")
            options = select_element.query_selector_all("option")
            option = None
            for opt in options:
                if opt.inner_text().lower() == location.lower():
                    option = opt
                    break
            if option:
                option.click()
                page.click("input[name='Submit2']")
                page.wait_for_load_state("networkidle", timeout=0)
                page.goto("https://app.clubready.com/admin/schedulingdayview.asp")
                page.wait_for_load_state("networkidle", timeout=0)
                all_bookings_cards = get_bookings(page)

                if len(all_bookings_cards) > 0:
                    same_client_period, unpaid_modal = handle_log_off(
                        page, all_bookings_cards
                    )

                else:
                    screenshot_url = capture_and_upload_screenshot(page, "no_container")
                    raise Exception(
                        f"No container found{f' | screenshot: {screenshot_url}' if screenshot_url else ''}"
                    )
                # remove_notes(user_id, all_bookings)
        return {
            "status": True,
            "same_client_period": same_client_period,
            "message": (
                "Session was logged off, but unpaid"
                if unpaid_modal
                else "Session logged off"
            ),
        }
    except Exception as e:
        print(f"An error occurred during logging off notes: {str(e)}")
        screenshot_url = capture_and_upload_screenshot(page, "no_container")
        raise Exception(
            f"{str(e)}{f' | screenshot: {screenshot_url}' if screenshot_url else ''}"
        )
        raise
    finally:
        if page:
            page.close()
        if context:
            context.close()
        if browser:
            browser.close()
        if playwright:
            playwright.stop()


def generate_random_password(length=12):
    letters = string.ascii_letters
    digits = string.digits
    # special_chars = string.punctuation.replace("/", "")

    all_chars = letters + digits

    # Ensure the password is exactly 12 characters long
    password = "".join(secrets.choice(all_chars) for _ in range(12))
    hashed_password = hash_password(password)

    return password, hashed_password


def hash_password(password):
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(password, hashed_password):
    return bcrypt.checkpw(password.encode("utf-8"), hashed_password.encode("utf-8"))


def generate_verification_code(length=6):
    return "".join(random.choices(string.digits, k=length))


def decode_jwt_token(token):
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
