from datetime import datetime, timezone

from flask_login import UserMixin
import sqlalchemy as sa
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db


def utc_now():
    return datetime.now(timezone.utc)


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(254), unique=True, nullable=False, index=True)
    phone = db.Column(db.String(40))
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="farmer")
    profile_image = db.Column(db.String(500))
    location = db.Column(db.String(180))
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    language = db.Column(db.String(8), nullable=False, default="en")
    language_onboarding_done = db.Column(
        db.Boolean, nullable=False, default=False, server_default=sa.true()
    )
    theme = db.Column(
        db.String(10), nullable=False, default="day", server_default="day"
    )
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    farms = db.relationship(
        "Farm", back_populates="owner", cascade="all, delete-orphan"
    )
    crops = db.relationship(
        "Crop", back_populates="owner", cascade="all, delete-orphan"
    )
    detections = db.relationship(
        "DiseaseDetection", back_populates="owner", cascade="all, delete-orphan"
    )
    notifications = db.relationship(
        "Notification", back_populates="owner", cascade="all, delete-orphan"
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Farm(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False,
        index=True,
    )
    farm_name = db.Column(db.String(120), nullable=False)
    location = db.Column(db.String(180))
    farm_size = db.Column(db.Float)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)

    owner = db.relationship("User", back_populates="farms")
    fields = db.relationship(
        "Field", back_populates="farm", cascade="all, delete-orphan"
    )
    crops = db.relationship("Crop", back_populates="farm")


class Field(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    farm_id = db.Column(
        db.Integer, db.ForeignKey("farm.id", ondelete="CASCADE"), nullable=False,
        index=True,
    )
    field_name = db.Column(db.String(120), nullable=False)
    area = db.Column(db.Float)
    location = db.Column(db.String(180))
    assigned_crop = db.Column(db.String(80))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)

    farm = db.relationship("Farm", back_populates="fields")
    crops = db.relationship("Crop", back_populates="field")
    irrigation_records = db.relationship(
        "IrrigationRecord", back_populates="field"
    )
    soil_readings = db.relationship("SoilReading", back_populates="field")


class Crop(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False,
        index=True,
    )
    farm_id = db.Column(
        db.Integer, db.ForeignKey("farm.id", ondelete="SET NULL"), index=True
    )
    field_id = db.Column(
        db.Integer, db.ForeignKey("field.id", ondelete="SET NULL"), index=True
    )
    crop_name = db.Column(db.String(80), nullable=False)
    planting_date = db.Column(db.Date)
    harvesting_date = db.Column(db.Date)
    growth_stage = db.Column(db.String(80))
    health_status = db.Column(db.String(40), nullable=False, default="Unknown")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)

    owner = db.relationship("User", back_populates="crops")
    farm = db.relationship("Farm", back_populates="crops")
    field = db.relationship("Field", back_populates="crops")
    detections = db.relationship("DiseaseDetection", back_populates="crop")


class DiseaseDetection(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    unique_detection_id = db.Column(
        db.String(36), unique=True, nullable=False, index=True
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False,
        index=True,
    )
    farm_id = db.Column(
        db.Integer, db.ForeignKey("farm.id", ondelete="SET NULL"), index=True
    )
    field_id = db.Column(
        db.Integer, db.ForeignKey("field.id", ondelete="SET NULL"), index=True
    )
    crop_id = db.Column(
        db.Integer, db.ForeignKey("crop.id", ondelete="SET NULL"), index=True
    )
    crop_name = db.Column(db.String(80), nullable=False)
    predicted_disease = db.Column(db.String(180), nullable=False)
    confidence_score = db.Column(db.Float, nullable=False)
    severity = db.Column(db.String(40))
    disease_description = db.Column(db.Text)
    treatment_recommendation = db.Column(db.Text)
    prevention_recommendation = db.Column(db.Text)
    model_name = db.Column(db.String(120), nullable=False)
    model_version = db.Column(db.String(80))
    processing_status = db.Column(db.String(32), nullable=False, default="completed")
    report_path = db.Column(db.String(500))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)

    owner = db.relationship("User", back_populates="detections")
    crop = db.relationship("Crop", back_populates="detections")
    farm = db.relationship("Farm")
    field = db.relationship("Field")
    images = db.relationship(
        "DetectionImage", back_populates="detection", cascade="all, delete-orphan"
    )
    treatments = db.relationship(
        "TreatmentRecord", back_populates="detection", cascade="all, delete-orphan"
    )


class DetectionImage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    detection_id = db.Column(
        db.Integer,
        db.ForeignKey("disease_detection.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    original_image_path = db.Column(db.String(500), nullable=False)
    processed_image_path = db.Column(db.String(500))
    image_format = db.Column(db.String(16), nullable=False)
    file_size = db.Column(db.Integer, nullable=False)
    uploaded_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)

    detection = db.relationship("DiseaseDetection", back_populates="images")


class TreatmentRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False,
        index=True,
    )
    detection_id = db.Column(
        db.Integer,
        db.ForeignKey("disease_detection.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    treatment_name = db.Column(db.String(160), nullable=False)
    treatment_description = db.Column(db.Text)
    application_date = db.Column(db.Date)
    status = db.Column(db.String(40), nullable=False, default="planned")
    notes = db.Column(db.Text)

    detection = db.relationship("DiseaseDetection", back_populates="treatments")


class IrrigationRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False,
        index=True,
    )
    field_id = db.Column(
        db.Integer, db.ForeignKey("field.id", ondelete="SET NULL"), index=True
    )
    irrigation_date = db.Column(db.Date, nullable=False)
    water_quantity = db.Column(db.Float)
    schedule = db.Column(db.String(180))
    status = db.Column(db.String(40), nullable=False, default="scheduled")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)

    field = db.relationship("Field", back_populates="irrigation_records")


class SoilReading(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False,
        index=True,
    )
    field_id = db.Column(
        db.Integer, db.ForeignKey("field.id", ondelete="SET NULL"), index=True
    )
    moisture = db.Column(db.Float)
    temperature = db.Column(db.Float)
    ph_value = db.Column(db.Float)
    nutrient_information = db.Column(db.Text)
    reading_source = db.Column(db.String(40), nullable=False, default="manual")
    recorded_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)

    field = db.relationship("Field", back_populates="soil_readings")


class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False,
        index=True,
    )
    title = db.Column(db.String(180), nullable=False)
    message = db.Column(db.Text, nullable=False)
    notification_type = db.Column(db.String(40), nullable=False, default="info")
    is_read = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)

    owner = db.relationship("User", back_populates="notifications")
