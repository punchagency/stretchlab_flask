from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    ForeignKey,
    DateTime,
    Boolean,
    Time,
)
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


# Status: 1 - Active, 2 - Disabled, 3 - Invited, 4 - Pending, 5-Awating Clubready Credentials(admin and user)
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    full_name = Column(String(64), nullable=True)
    username = Column(String(64), nullable=False)
    email = Column(String(120), unique=True, nullable=False)
    password = Column(String(120), nullable=False)
    is_verified = Column(Boolean, default=False)
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False)
    clubready_username = Column(String(64), nullable=True)
    clubready_password = Column(String(120), nullable=True)
    clubready_location_id = Column(String(64), nullable=True)
    clubready_user_id = Column(String(64), nullable=True)
    verification_code = Column(String(120), nullable=True)
    notification = Column(Boolean, default=True)
    two_factor_auth = Column(Boolean, default=False)
    totp_secret = Column(String(64), nullable=True)
    backup_codes = Column(Text, nullable=True)
    admin_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    status = Column(Integer, nullable=True)
    last_login = Column(DateTime, nullable=True)
    invited_at = Column(DateTime, nullable=True)
    verification_code_expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    profile_picture = Column(String(255), nullable=True)
    profile_picture_url = Column(String(255), nullable=True)

    def __repr__(self):
        return f"<User {self.email}>"


class Role(Base):
    __tablename__ = "roles"
    id = Column(Integer, primary_key=True)
    name = Column(String(64), nullable=False)
    users = relationship("User", backref="role", lazy=True)


class Business(Base):
    __tablename__ = "businesses"
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), unique=True, nullable=False)
    customer_id = Column(String(64), nullable=True)
    payment_id = Column(String(64), nullable=True)
    note_taking_subscription_id = Column(String(64), nullable=True)
    note_taking_subscription_status = Column(String(64), nullable=True)
    robot_process_automation_subscription_id = Column(String(64), nullable=True)
    robot_process_automation_subscription_status = Column(String(64), nullable=True)
    locations = Column(Text, nullable=True)
    note_taking_active = Column(Boolean, default=False)
    robot_process_automation_active = Column(Boolean, default=False)
    note_taking_subscription_expires_at = Column(DateTime, nullable=True)
    robot_process_automation_subscription_expires_at = Column(DateTime, nullable=True)
    admin_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    users = relationship("User", backref="business", lazy=True)


class Price(Base):
    __tablename__ = "prices"
    id = Column(Integer, primary_key=True, autoincrement=True)
    price_id = Column(String(64), nullable=False)
    price = Column(Integer, nullable=False)
    type = Column(String(64), nullable=False)
    created_at = Column(DateTime, default=datetime.now)


class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    message = Column(Text, nullable=False)
    is_read = Column(Boolean, default=False)
    type = Column(String(64), nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    users = relationship("User", backref="notification", lazy=True)


class ClubreadyBooking(Base):
    __tablename__ = "clubready_bookings"
    id = Column(Integer, primary_key=True, autoincrement=True)
    client_name = Column(String(64), nullable=True)
    booking_id = Column(String(64), nullable=True)
    workout_type = Column(String(64), nullable=True)
    first_timer = Column(String(64), nullable=True)
    active_member = Column(String(64), nullable=True)
    location = Column(String(64), nullable=True)
    phone_number = Column(String(64), nullable=True)
    booking_time = Column(String(64), nullable=True)
    period = Column(String(64), nullable=True)
    past_booking = Column(Boolean, default=False)
    flexologist_name = Column(String(64), nullable=True)
    submitted = Column(Boolean, default=False)
    submitted_notes = Column(Text, nullable=True)
    coaching_notes = Column(Text, nullable=True)
    task_id = Column(String(64), nullable=True)
    task_status = Column(String(64), nullable=True)
    task_message = Column(Text, nullable=True)
    task_error = Column(Text, nullable=True)
    submitted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    # admin_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    users = relationship("User", backref="clubready_booking", lazy=True)


class BookingTask(Base):
    __tablename__ = "booking_tasks"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    task_id = Column(String(64), nullable=True)
    task_status = Column(String(64), nullable=True)
    task_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    users = relationship("User", backref="booking_task", lazy=True)


class BookingNotes(Base):
    __tablename__ = "booking_notes"
    id = Column(Integer, primary_key=True, autoincrement=True)
    booking_id = Column(Integer, nullable=False)
    note = Column(Text, nullable=True)
    flexologist_uid = Column(Integer, ForeignKey("users.id"), nullable=False)
    time = Column(DateTime, nullable=False)
    voice = Column(String(64), nullable=True)
    type = Column(String(64), nullable=True)
    formatted_notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    users = relationship("User", backref="booking_note", lazy=True)


class RobotProcessAutomationConfig(Base):
    __tablename__ = "robot_process_automation_config"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), nullable=False)
    number_of_locations = Column(Integer, nullable=False)
    locations = Column(Text, nullable=True)
    selected_locations = Column(Text, nullable=True)
    unlogged_booking = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)
    run_time = Column(Time, nullable=False)
    rule_arn = Column(String(64), nullable=True)
    bucket_name = Column(String(64), nullable=True)
    active = Column(Boolean, default=True)
    updated_at = Column(DateTime, default=datetime.now)
    status = Column(String(64), nullable=True, default="STOPPED")
    admin_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    users = relationship("User", backref="robot_process_automation", lazy=True)


class RobotProcessAutomationNotesRecords(Base):
    __tablename__ = "robot_process_automation_notes_records"
    id = Column(Integer, primary_key=True, autoincrement=True)
    config_id = Column(
        Integer, ForeignKey("robot_process_automation_config.id"), nullable=False
    )
    client_name = Column(String(64), nullable=True)
    first_timer = Column(String(64), nullable=True)
    unpaid_booking = Column(String(64), nullable=True)
    member_rep_name = Column(String(64), nullable=True)
    flexologist_name = Column(String(64), nullable=True)
    booking_id = Column(String(64), nullable=True)
    workout_type = Column(String(64), nullable=True)
    location = Column(String(64), nullable=True)
    key_note = Column(Text, nullable=True)
    status = Column(String(64), nullable=True)
    booked_on_date = Column(String(64), nullable=True)
    run_date = Column(DateTime, nullable=True)
    appointment_date = Column(String(64), nullable=True)
    note_analysis_progressive_moments = Column(Text, nullable=True)
    note_analysis_improvements = Column(Text, nullable=True)
    note_oppurtunities = Column(Text, nullable=True)
    note_summary = Column(Text, nullable=True)
    note_score = Column(String(64), nullable=True)
    pre_visit_preparation_rubric = Column(String(64), nullable=True)
    session_notes_rubric = Column(String(64), nullable=True)
    missed_sale_follow_up_rubric = Column(String(64), nullable=True)
    config = relationship(
        "RobotProcessAutomationConfig",
        backref="robot_process_automation_records",
        lazy=True,
    )
    created_at = Column(DateTime, default=datetime.now)


class RobotProcessAutomationUnloggedBookingRecords(Base):
    __tablename__ = "robot_process_automation_unlogged_booking_records"
    id = Column(Integer, primary_key=True, autoincrement=True)
    config_id = Column(
        Integer, ForeignKey("robot_process_automation_config.id"), nullable=False
    )
    full_name = Column(String(64), nullable=True)
    booking_location = Column(String(64), nullable=True)
    booking_id = Column(String(64), nullable=True)
    booking_detail = Column(Text, nullable=True)
    appointment_date = Column(String(64), nullable=True)
    session_mins = Column(String(64), nullable=True)
    booking_with = Column(String(64), nullable=True)
    booking_date = Column(String(64), nullable=True)
    config = relationship(
        "RobotProcessAutomationConfig",
        backref="robot_process_automation_unlogged_booking_records",
        lazy=True,
    )
    created_at = Column(DateTime, default=datetime.now)


class BillingHistory(Base):
    __tablename__ = "billing_history"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    amount = Column(Integer, nullable=False)
    invoice_id = Column(String(64), nullable=False)
    subscription_id = Column(String(64), nullable=False)
    status = Column(String(64), nullable=False)
    invoice_url = Column(Text, nullable=False)
    invoice_pdf_url = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    users = relationship("User", backref="billing_history", lazy=True)
