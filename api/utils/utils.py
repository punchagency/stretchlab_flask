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

load_dotenv()

# Initilaizing variables with the env values
INITIAL_URL = os.getenv("INITIAL_URL")
SECRET_KEY = os.getenv("JWT_SECRET_KEY")


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
            return {
                "status": False,
                "message": "This is not an admin account",
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
            await page.goto("https://scheduling.clubready.com/day")
            await page.wait_for_load_state("networkidle", timeout=0)

            await page.wait_for_selector(
                ".spinner-background", state="hidden", timeout=40000
            )

            await page.click("#dropdown-button")
            await page.wait_for_selector(
                ".sidebar-events-filter-menu", state="visible", timeout=2000
            )
            my_filter = await page.query_selector(".dropdown--item:has(input#only-me)")
            if not my_filter:
                print(f"No 'only-me' filter found for location: {location_text}")
                return []

            await page.click(".dropdown--item:has(input#only-me)")
            container = await page.query_selector_all(".sidebar-section-content")
            print(container, "container")
            print(len(container), "length of container")

            all_div_selectors = []
            for cont in container:
                div_selector = await cont.query_selector_all(
                    "div[class*='sidebar-event-card']"
                )
                all_div_selectors.extend(div_selector)

            print(f"Total event cards found: {len(all_div_selectors)}")
            await page.click("#dropdown-button")
            await page.wait_for_selector(
                ".sidebar-events-filter-menu", state="hidden", timeout=2000
            )

            if all_div_selectors:
                print(
                    f"Found {len(all_div_selectors)} event cards for location: {location_text}"
                )

                for div in all_div_selectors:
                    event_date = await (
                        await div.query_selector(".event-date")
                    ).inner_text()
                    past = "previous-event" in await div.get_attribute("id")
                    await div.click()
                    modal_details = await page.wait_for_selector(
                        ".booking-panel", state="visible"
                    )
                    await page.wait_for_function(
                        expression="""
                        (element) => {
                            const loaders = element.querySelectorAll('[class*="spinner"]');
                            return element && element.offsetParent !== null && loaders.length === 0;
                        }
                        """,
                        arg=modal_details,
                        timeout=20000,
                    )
                    first_timer = (
                        "YES"
                        if await modal_details.query_selector(
                            ".booking-header-tags .text-first-visit"
                        )
                        else "NO"
                    )
                    active = (
                        "YES"
                        if await modal_details.query_selector(
                            ".client-membership-tags .container-active"
                        )
                        else "NO"
                    )

                    html = await modal_details.inner_html()
                    result = extract_booking_data_from_html(html)
                    print(f"Extracted booking data: {result}")
                    result["event_date"] = event_date
                    result["past"] = past
                    result["first_timer"] = first_timer
                    result["active"] = active
                    result["location"] = location_text
                    all_bookings.append(result)

                    close_btn = await modal_details.query_selector("#header-close")
                    if close_btn:
                        await close_btn.click()
                        await page.wait_for_selector(".booking-panel", state="hidden")
                        print("Close button clicked")
                    else:
                        print("Close button not found")

            return all_bookings

        except PlaywrightTimeoutError as e:
            print(f"Timeout error for location {location_text}: {e}")
            return []
        except Exception as e:
            print(f"Error processing location {location_text}: {e}")
            return []


async def get_user_bookings_from_clubready(user_details, max_concurrency=3):
    username = user_details["Username"]
    password = user_details["Password"]
    password = reverse_hash_credentials(username, password)
    print(username, password)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context()
            page = await context.new_page()

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
            if "Dashboard" in current_url:
                await page.goto("https://scheduling.clubready.com/day")
                await page.wait_for_load_state("networkidle", timeout=0)

                await page.wait_for_selector(
                    ".spinner-background", state="hidden", timeout=40000
                )

                await page.click("#dropdown-button")
                await page.wait_for_selector(
                    ".sidebar-events-filter-menu", state="visible", timeout=2000
                )

                await page.click(".dropdown--item:has(input#only-me)")
                container = await page.query_selector_all(".sidebar-section-content")

                all_div_selectors = []
                for cont in container:
                    div_selector = await cont.query_selector_all(
                        "div[class*='sidebar-event-card']"
                    )
                    all_div_selectors.extend(div_selector)

                await page.click("#dropdown-button")
                await page.wait_for_selector(
                    ".sidebar-events-filter-menu", state="hidden", timeout=2000
                )

                if all_div_selectors:
                    print(f"Found {len(all_div_selectors)} event cards")
                    for div in all_div_selectors:
                        event_date = await (
                            await div.query_selector(".event-date")
                        ).inner_text()
                        past = "previous-event" in await div.get_attribute("id")
                        await div.click()
                        modal_details = await page.wait_for_selector(
                            ".booking-panel", state="visible"
                        )
                        await page.wait_for_function(
                            expression="""
                        (element) => {
                            const loaders = element.querySelectorAll('[class*="spinner"]');
                            return element && element.offsetParent !== null && loaders.length === 0;
                        }
                        """,
                            arg=modal_details,
                            timeout=20000,
                        )
                        first_timer = (
                            "YES"
                            if await modal_details.query_selector(
                                ".booking-header-tags .text-first-visit"
                            )
                            else "NO"
                        )
                        active = (
                            "YES"
                            if await modal_details.query_selector(
                                ".client-membership-tags .container-active"
                            )
                            else "NO"
                        )

                        html = await modal_details.inner_html()
                        result = extract_booking_data_from_html(html)
                        print(f"Extracted booking data: {result}")
                        result["event_date"] = event_date
                        result["past"] = past
                        result["first_timer"] = first_timer
                        result["active"] = active
                        all_bookings.append(result)

                        close_btn = await modal_details.query_selector("#header-close")
                        if close_btn:
                            await close_btn.click()
                            await page.wait_for_selector(
                                ".booking-panel", state="hidden"
                            )
                            print("Close button clicked")
                        else:
                            print("Close button not found")
            else:
                await page.wait_for_selector("select[name='stores']")
                select_element = await page.query_selector("select[name='stores']")
                option_elements = await select_element.query_selector_all("option")
                location_texts = [await opt.inner_text() for opt in option_elements]
                await context.close()

                if not location_texts:
                    print("No locations found in dropdown")
                    return {
                        "status": False,
                        "message": "No locations found",
                        "bookings": [],
                    }

                print(f"Found {len(location_texts)} locations: {location_texts}")

                semaphore = asyncio.Semaphore(max_concurrency)
                tasks = []
                for location_text in location_texts:
                    new_context = await browser.new_context()
                    new_page = await new_context.new_page()
                    await new_page.goto(INITIAL_URL)
                    await new_page.fill("input[name='uid']", username)
                    await new_page.fill("input[name='pw']", password)
                    await new_page.click("input[type='submit']")
                    await new_page.wait_for_load_state("networkidle", timeout=0)
                    task = asyncio.create_task(
                        fetch_bookings_for_location(
                            new_page, current_url, location_text, semaphore
                        )
                    )
                    tasks.append((task, new_context))

                for task, context in tasks:
                    bookings = await task
                    all_bookings.extend(bookings)
                    await context.close()

            return {
                "status": True,
                "message": "Bookings fetched successfully",
                "bookings": all_bookings,
            }

        except PlaywrightTimeoutError as e:
            print(f"Timeout error: {e}")
            raise e
        except Exception as e:
            print(f"Error fetching bookings: {e}")
            raise e
        finally:
            await browser.close()


def submit_notes(username, password, period, notes, location=None):
    password = reverse_hash_credentials(username, password)
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
        page.fill("input[name='uid']", username)
        page.fill("input[name='pw']", password)
        page.click("input[type='submit']")
        page.wait_for_load_state("networkidle", timeout=0)
        base_url = page.url
        if "Dashboard" in base_url:
            page.goto("https://scheduling.clubready.com/day")
            page.wait_for_load_state("networkidle", timeout=0)
            page.wait_for_selector(".spinner-background", state="hidden", timeout=40000)

            page.click("#dropdown-button")
            page.wait_for_selector(
                ".sidebar-events-filter-menu",
                state="visible",
                timeout=2000,
            )

            page.click(".dropdown--item:has(input#only-me)")
            container = page.query_selector_all(".sidebar-section-content")
            all_div_selectors = []
            for cont in container:
                div_selector = cont.query_selector_all(
                    "div[class*='sidebar-event-card']"
                )
                all_div_selectors.extend(div_selector)
            page.click("#dropdown-button")
            page.wait_for_selector(
                ".sidebar-events-filter-menu",
                state="hidden",
                timeout=2000,
            )
            unpaid_modal = None

            if len(all_div_selectors) > 0:
                matching_booking = None
                for div in all_div_selectors:
                    event_date = div.query_selector(".event-date").inner_text()
                    if event_date == period:
                        matching_booking = div
                        break

                if matching_booking:
                    matching_booking.click()
                    modal_details = page.wait_for_selector(
                        ".booking-panel", state="visible"
                    )
                    page.wait_for_function(
                        """
                                                (element) => {                                 
                                                    const loaders = element.querySelectorAll('[class*="spinner"]');
                                                    return element && element.offsetParent !== null && loaders.length === 0;
                                                }
                                                """,
                        arg=modal_details,
                        timeout=20000,
                    )

                    open_notes_btn = modal_details.query_selector(
                        "button[id='make-note-footer']"
                    )

                    if open_notes_btn:
                        open_notes_btn.click()

                        note_modal = page.wait_for_selector(
                            "div[class='desktop-modal add-note']",
                            state="visible",
                            timeout=10000,
                        )
                        if note_modal:
                            subject_input = note_modal.query_selector(
                                "input[id='subject']"
                            )
                            notes_textarea = note_modal.query_selector(
                                "textarea[id='text']"
                            )
                            if subject_input and notes_textarea:
                                note_modal.query_selector("#tag-0").click()
                                subject_input.fill("Session Notes")
                                notes_textarea.fill(notes)

                                submit_btn = note_modal.query_selector(
                                    "button[id='add-note-btn']"
                                )
                                if submit_btn:

                                    submit_btn.click()
                                    page.wait_for_selector(
                                        ".spinner-background",
                                        state="hidden",
                                        timeout=40000,
                                    )

                            else:
                                logging.error(
                                    "Subject input or notes textarea not found"
                                )
                            close_btn = note_modal.query_selector(
                                "div[class='desktop-modal-header-close']"
                            )
                            if close_btn:
                                close_btn.click()

                            modal_details.query_selector(
                                "button[id='log-status-show']"
                            ).click()

                            try:
                                unpaid_modal = page.wait_for_selector(
                                    ".log-as-completed",
                                    state="visible",
                                    timeout=10000,
                                )
                                if unpaid_modal:
                                    unpaid_modal.query_selector(
                                        "button[id='log-and-go-to-pos-button']"
                                    ).click()
                                    page.wait_for_timeout(500)
                                    unpaid_modal.query_selector(
                                        ".desktop-modal-header-close"
                                    ).click()
                            except:
                                page.wait_for_selector(
                                    ".spinner-background",
                                    state="hidden",
                                    timeout=40000,
                                )

                else:
                    logging.info("No matching booking found")

                close_btn = modal_details.query_selector("#header-close")
                if close_btn:
                    close_btn.click()
                    page.wait_for_selector(
                        ".booking-panel",
                        state="hidden",
                    )
                else:
                    logging.error("Close button not found")
            else:
                logging.info("No bookings found")

            return {
                "status": True,
                "message": (
                    "Heads Up - Session was logged off, but unpaid.  Ask front desk team to process payment"
                    if unpaid_modal
                    else "Notes submitted successfully"
                ),
            }
        else:
            page.wait_for_selector("select[name='stores']")
            select_element = page.query_selector("select[name='stores']")
            options = select_element.query_selector_all("option")
            option = None
            for opt in options:
                if opt.inner_text() == location:
                    option = opt
                    break
            if option:
                option.click()
                page.click("input[name='Submit2']")
                page.wait_for_load_state("networkidle", timeout=0)
                page.goto("https://scheduling.clubready.com/day")
                page.wait_for_load_state("networkidle", timeout=0)
                page.wait_for_selector(
                    ".spinner-background", state="hidden", timeout=40000
                )

                page.click("#dropdown-button")
                page.wait_for_selector(
                    ".sidebar-events-filter-menu",
                    state="visible",
                    timeout=2000,
                )

                page.click(".dropdown--item:has(input#only-me)")
                container = page.query_selector_all(".sidebar-section-content")
                all_div_selectors = []
                for cont in container:
                    div_selector = cont.query_selector_all(
                        "div[class*='sidebar-event-card']"
                    )
                all_div_selectors.extend(div_selector)
                page.click("#dropdown-button")
                page.wait_for_selector(
                    ".sidebar-events-filter-menu",
                    state="hidden",
                    timeout=2000,
                )
                unpaid_modal = None

                if len(all_div_selectors) > 0:
                    matching_booking = None
                    for div in all_div_selectors:
                        event_date = div.query_selector(".event-date").inner_text()
                        if event_date == period:
                            matching_booking = div
                            break

                    if matching_booking:
                        matching_booking.click()
                        modal_details = page.wait_for_selector(
                            ".booking-panel", state="visible"
                        )
                        page.wait_for_function(
                            """
                                                    (element) => {                                 
                                                        const loaders = element.querySelectorAll('[class*="spinner"]');
                                                        return element && element.offsetParent !== null && loaders.length === 0;
                                                    }
                                                    """,
                            arg=modal_details,
                            timeout=20000,
                        )

                        open_notes_btn = modal_details.query_selector(
                            "button[id='make-note-footer']"
                        )

                        if open_notes_btn:
                            open_notes_btn.click()

                            note_modal = page.wait_for_selector(
                                "div[class='desktop-modal add-note']",
                                state="visible",
                                timeout=10000,
                            )
                            if note_modal:
                                subject_input = note_modal.query_selector(
                                    "input[id='subject']"
                                )
                                notes_textarea = note_modal.query_selector(
                                    "textarea[id='text']"
                                )
                                if subject_input and notes_textarea:
                                    note_modal.query_selector("#tag-0").click()
                                    subject_input.fill("Session Notes")
                                    notes_textarea.fill(notes)

                                    submit_btn = note_modal.query_selector(
                                        "button[id='add-note-btn']"
                                    )
                                    if submit_btn:

                                        submit_btn.click()
                                        page.wait_for_selector(
                                            ".spinner-background",
                                            state="hidden",
                                            timeout=40000,
                                        )

                                else:
                                    logging.error(
                                        "Subject input or notes textarea not found"
                                    )
                                close_btn = note_modal.query_selector(
                                    "div[class='desktop-modal-header-close']"
                                )
                                if close_btn:
                                    close_btn.click()

                                modal_details.query_selector(
                                    "button[id='log-status-show']"
                                ).click()

                                try:
                                    unpaid_modal = page.wait_for_selector(
                                        ".log-as-completed",
                                        state="visible",
                                        timeout=10000,
                                    )
                                    if unpaid_modal:
                                        unpaid_modal.query_selector(
                                            "button[id='log-and-go-to-pos-button']"
                                        ).click()
                                        page.wait_for_timeout(500)
                                        unpaid_modal.query_selector(
                                            ".desktop-modal-header-close"
                                        ).click()
                                except:
                                    page.wait_for_selector(
                                        ".spinner-background",
                                        state="hidden",
                                        timeout=40000,
                                    )

                    else:
                        logging.info("No matching booking found")

                    close_btn = modal_details.query_selector("#header-close")
                    if close_btn:
                        close_btn.click()
                        page.wait_for_selector(
                            ".booking-panel",
                            state="hidden",
                        )
                    else:
                        logging.error("Close button not found")
                else:
                    logging.info("No bookings found")

                return {
                    "status": True,
                    "message": (
                        "Heads Up - Session was logged off, but unpaid.  Ask front desk team to process payment"
                        if unpaid_modal
                        else "Notes submitted successfully"
                    ),
                }

    except Exception as e:
        logging.error(f"An error occurred during submitting notes: {str(e)}")
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
