import os
from pyairtable import Api
from dotenv import load_dotenv
from datetime import datetime
import json
import logging

# Loading env instance
load_dotenv()

ACCESS_TOKEN = os.getenv("AIRTABLE_TOKEN")
BASEID = os.getenv("AIRTABLE_BASE")
TABLEID = os.getenv("NOTE_TAKING_TABLE")
TABLEID_NOTES = os.getenv("NOTE_TAKING_TABLE_NOTES")
TABLEID_EMPLOYEE = os.getenv("EMPLOYEE_TABLE")
VIEW_FLEX_EMPLOYEE = os.getenv("FLEXVIEW")
TABLEID_ROBOT_NOTES = os.getenv("AIRTABLE_TABLE")
TABLEID_ROBOT_UNLOGGED = os.getenv("BOOKING_TABLE_ID")

# Initializing api from airtable
api = Api(ACCESS_TOKEN)


# Initialize table, to check if connection works
table = api.table(BASEID, TABLEID)
table_notes = api.table(BASEID, TABLEID_NOTES)
table_employee = api.table(BASEID, TABLEID_EMPLOYEE)
table_robot_notes = api.table(BASEID, TABLEID_ROBOT_NOTES)
table_robot_unlogged = api.table(BASEID, TABLEID_ROBOT_UNLOGGED)


def save_flexology_data(data):
    expires_at = datetime.now().replace(
        hour=23, minute=59, second=59, microsecond=999999
    )
    username = data.get("username")
    existing_records = table.all(formula=f"{{Username}} = '{username}'")

    if existing_records:
        record_id = existing_records[0]["id"]
        table.update(record_id, {"expiresAt": expires_at.isoformat()})
        return record_id
    else:
        fields = {
            "Username": username,
            "Password": data.get("password"),
            "expiresAt": expires_at.isoformat(),
        }
        new_record = table.create(fields)
        return new_record["id"]


def update_user_bookings(user_id, bookings):
    try:
        record = table.get(user_id)
        if not record:
            raise ValueError("User not found")

        bookings_json = json.dumps(bookings)

        table.update(
            user_id,
            {
                "Bookings": bookings_json,
                "BookingsCreatedAt": datetime.now().isoformat(),
            },
        )
        return {"status": "success", "message": "Bookings updated successfully"}
    except Exception as e:
        logging.error(f"An error occurred during updating bookings: {str(e)}")
        raise


def get_bookings_if_not_expired(user_id):
    try:
        record = table.get(user_id)
        if not record:
            raise ValueError("User not found")

        bookings_json = record["fields"].get("Bookings", "[]")
        booking_created_at_str = record["fields"].get("BookingsCreatedAt")
        if not booking_created_at_str:
            return False

        booking_created_at = datetime.fromisoformat(booking_created_at_str)
        current_date = datetime.now().date()
        if booking_created_at.date() == current_date:
            try:
                return json.loads(bookings_json)
            except json.JSONDecodeError:
                logging.error("Error decoding bookings JSON")
                return []
        else:
            return False
    except Exception as e:
        logging.error(f"An error occurred during fetching bookings: {str(e)}")
        raise


def get_user_details(user_id):
    try:
        record = table.get(user_id)
        if not record:
            raise ValueError("User not found")
        return {
            "Username": record["fields"].get("Username"),
            "Password": record["fields"].get("Password"),
        }
    except Exception as e:
        logging.error(f"An error occurred during fetching user details: {str(e)}")
        raise


def save_notes(data):
    try:
        table_notes.create(data)
    except Exception as e:
        logging.error(f"An error occurred during adding notes: {str(e)}")
        raise


def get_user_notes(user_id, booking_id):
    try:
        get_user = table.get(user_id)
        if not get_user:
            raise ValueError("User not found")
        records = table_notes.all(
            formula=f"AND({{Flexologist UID}} = '{user_id}', {{Booking ID}} = '{booking_id}')"
        )
        return records if records else []
    except Exception as e:
        logging.error(f"An error occurred during fetching notes: {str(e)}")
        raise


def get_employee_ownwer():
    try:
        all_employees = table_employee.all(
            view=VIEW_FLEX_EMPLOYEE,
        )
        return [
            {
                "full_name": emp["fields"].get("Name"),
                "email": emp["fields"].get("Personal Email"),
                "id": emp["id"],
            }
            for emp in all_employees
        ]
    except Exception as e:
        logging.error(f"An error occurred during fetching all employess: {str(e)}")
        raise


field_mapping = {
    "client_name": "Client Name",
    "first_timer": "First Timer",
    "unpaid_booking": "Unpaid Booking",
    "member_rep_name": "Member Rep Name",
    "flexologist_name": "Flexologist Name",
    "booking_id": "Booking ID",
    "workout_type": "Workout Type",
    "location": "Location",
    "key_note": "Key Note",
    "status": "Status",
    "booked_on_date": "Booked On Date (formatted)",
    "run_date": "Run Date",
    "appointment_date": "Appointment Date (Formatted)",
    "note_analysis_progressive_moments": "Note Analysis(progressive moments)",
    "note_analysis_improvements": "Note Analysis(improvements)",
    "note_summary": "Note Summary",
    "note_score": "Note Score",
    "pre_visit_preparation_rubric": "Pre-Visit Preparation(rubric)",
    "session_notes_rubric": "Session Notes(rubric)",
    "missed_sale_follow_up_rubric": "Missed Sale Follow-Up(rubric)",
}

unlogged_field_mapping = {
    "full_name": "Full Name",
    "booking_location": "Booking Location",
    "booking_id": "Booking ID",
    "booking_detail": "Booking Detail",
    "appointment_date": "Appointment Date",
    "session_mins": "Session Mins",
    "booking_with": "Booking With",
    "booking_date": "Booking Date",
}


def map_robot_note(note):
    mapped_note = {}
    fields = note.get("fields", {})
    for schema_field, note_key in field_mapping.items():
        mapped_note[schema_field] = fields.get(note_key)
    return {**mapped_note, "id": note.get("id")}


def map_robot_unlogged_note(note):
    mapped_note = {}
    fields = note.get("fields", {})
    for schema_field, note_key in unlogged_field_mapping.items():
        mapped_note[schema_field] = fields.get(note_key)
    return {**mapped_note, "id": note.get("id")}


def get_owner_robot_automation_notes(start_date, end_date):
    try:
        today_date = datetime.now().strftime("%Y-%m-%d")

        if start_date and end_date:
            start_date = datetime.strptime(start_date, "%Y-%m-%dT%H:%M:%S.%fZ")
            start_date = start_date.strftime("%Y-%m-%d %H:%M:%S.%f")
            end_date = datetime.strptime(end_date, "%Y-%m-%dT%H:%M:%S.%fZ")
            end_date = end_date.strftime("%Y-%m-%d %H:%M:%S.%f")
            robot_notes = table_robot_notes.all(
                formula=f"AND(DATESTR(CREATED_TIME()) >= '{start_date}', DATESTR(CREATED_TIME()) <= '{end_date}')"
            )
        else:
            robot_notes = table_robot_notes.all(
                formula=f"DATESTR(CREATED_TIME()) = '{today_date}'"
            )
        formatted_robot_notes = [map_robot_note(note) for note in robot_notes]
        return formatted_robot_notes
    except Exception as e:
        logging.error(f"An error occurred during fetching all employess: {str(e)}")
        raise


def get_owner_robot_automation_unlogged(start_date, end_date):
    try:
        today_date = datetime.now().strftime("%Y-%m-%d")
        if start_date and end_date:
            start_date = datetime.strptime(start_date, "%Y-%m-%dT%H:%M:%S.%fZ")
            start_date = start_date.strftime("%Y-%m-%d %H:%M:%S.%f")
            end_date = datetime.strptime(end_date, "%Y-%m-%dT%H:%M:%S.%fZ")
            end_date = end_date.strftime("%Y-%m-%d %H:%M:%S.%f")
            unlogged_bookings = table_robot_unlogged.all(
                formula=f"AND(DATESTR(CREATED_TIME()) >= '{start_date}', DATESTR(CREATED_TIME()) <= '{end_date}')"
            )
        else:
            unlogged_bookings = table_robot_unlogged.all(
                formula=f"DATESTR(CREATED_TIME()) = '{today_date}'"
            )
        formatted_unlogged_bookings = [
            map_robot_unlogged_note(note) for note in unlogged_bookings
        ]
        return formatted_unlogged_bookings
    except Exception as e:
        logging.error(f"An error occurred during fetching all employess: {str(e)}")
        raise


def get_notes_by_id(booking_id):
    try:
        records = table_notes.all(
            formula=f"AND({{Booking ID}} = '{booking_id}', {{type}} = 'user')"
        )
        sorted_records = sorted(records, key=lambda record: record["createdTime"])
        notes = [record["fields"].get("Note", "") for record in sorted_records]
        return "\n".join(notes) if notes else ""
    except Exception as e:
        logging.error(f"An error occurred during fetching notes: {str(e)}")
        raise


def get_active_by_id(user_id, booking_id):
    try:
        record = table.get(user_id)
        if not record:
            raise ValueError("User not found")
        bookings_json = record["fields"].get("Bookings", "[]")
        bookings = json.loads(bookings_json)
        for booking in bookings:
            if booking["booking_id"] == booking_id:
                return booking["active"]
        return "Booking not found"
    except Exception as e:
        logging.error(f"An error occurred during fetching active status: {str(e)}")
        raise


def remove_booking_created_at(user_id):
    try:
        record = table.get(user_id)
        if not record:
            raise ValueError("User not found")

        table.update(user_id, {"BookingsCreatedAt": ""})

        return {"status": True, "message": "Logged out successfully"}
    except Exception as e:
        logging.error(f"An error occurred during logging out: {str(e)}")
        raise
