import csv
import json
import logging
import os
import re
import secrets
import smtplib
import uuid
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage
from io import StringIO
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import numpy as np
import tensorflow as tf
from dotenv import load_dotenv
from flask import (
    Flask,
    abort,
    current_app,
    flash,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    send_file,
    send_from_directory,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user
from PIL import Image, UnidentifiedImageError
from sqlalchemy import func
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.utils import secure_filename

from extensions import csrf, db, limiter, login_manager, migrate
from api import api_v1
from integrations.email_delivery import send_email_message, smtp_is_configured
from integrations.weather import WeatherIntegrationError, get_irrigation_advisory, get_weather_report
from models import (
    Crop,
    DetectionImage,
    DiseaseDetection,
    Farm,
    Field,
    IrrigationRecord,
    Notification,
    SoilReading,
    TreatmentRecord,
    User,
)
from multilingual_disease_info import DISEASE_NAMES, MULTILINGUAL_DISEASE_INFO
from pdf_report import generate_pdf_report
from translations import (
    SUPPORTED_LANGUAGES,
    TRANSLATIONS,
    TRANSLATION_STATUS,
    format_localized_date,
)


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

MODEL_PATH = BASE_DIR / "models" / "crop_disease_model.keras"
CLASS_PATH = BASE_DIR / "models" / "class_indices.json"
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
PASSWORD_MIN_LENGTH = 10


def _load_model():
    if not MODEL_PATH.is_file() or not CLASS_PATH.is_file():
        logging.getLogger(__name__).error(
            "The crop disease model or class-index file is missing."
        )
        return None, {}
    try:
        with CLASS_PATH.open(encoding="utf-8") as file:
            indices = json.load(file)
        loaded_model = tf.keras.models.load_model(MODEL_PATH)
        return loaded_model, {index: name for name, index in indices.items()}
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        logging.getLogger(__name__).exception("Could not load crop disease model.")
        return None, {}
    except Exception:
        logging.getLogger(__name__).exception("Unexpected error loading crop disease model.")
        return None, {}


model, class_names = _load_model()
SUPPORTED_CROPS = sorted(
    {
        "Bell pepper" if name.startswith("Pepper__bell") else name.split("_", 1)[0]
        for name in class_names.values()
    }
)


def _database_url():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        return f"sqlite:///{(BASE_DIR / 'instance' / 'cropfarm.db').as_posix()}"
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+psycopg://", 1)
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


def _secret_key(instance_path):
    configured_key = os.getenv("SECRET_KEY")
    environment = os.getenv("APP_ENV", os.getenv("FLASK_ENV", "development")).lower()
    if configured_key:
        return configured_key
    if environment == "production":
        raise RuntimeError("SECRET_KEY must be configured for production.")

    secret_file = Path(instance_path) / ".secret_key"
    try:
        key = secrets.token_urlsafe(48)
        with secret_file.open("x", encoding="utf-8") as file:
            file.write(key)
        os.chmod(secret_file, 0o600)
        return key
    except FileExistsError:
        return secret_file.read_text(encoding="utf-8").strip()


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    os.makedirs(app.instance_path, exist_ok=True)

    database_url = _database_url()
    app.config.from_mapping(
        SECRET_KEY=_secret_key(app.instance_path),
        SQLALCHEMY_DATABASE_URI=database_url,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        AUTO_CREATE_DB=os.getenv(
            "AUTO_CREATE_DB", "true" if database_url.startswith("sqlite:") else "false"
        ).lower() == "true",
        UPLOAD_FOLDER=os.path.join(app.instance_path, "uploads"),
        REPORT_FOLDER=os.path.join(app.instance_path, "reports"),
        MAX_CONTENT_LENGTH=10 * 1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "false").lower() == "true",
        RATELIMIT_STORAGE_URI=os.getenv("RATELIMIT_STORAGE_URI", "memory://"),
        PERMANENT_SESSION_LIFETIME=timedelta(days=14),
        WEATHER_LOCATION=os.getenv("WEATHER_LOCATION"),
        SMTP_HOST=os.getenv("SMTP_HOST"),
        SMTP_PORT=int(os.getenv("SMTP_PORT", "587")),
        SMTP_USER=os.getenv("SMTP_USER"),
        SMTP_PASSWORD=os.getenv("SMTP_PASSWORD"),
        MAIL_FROM=os.getenv("MAIL_FROM"),
        SUPPORT_EMAIL=os.getenv("SUPPORT_EMAIL"),
        REPORT_FONT_PATH=os.getenv("REPORT_FONT_PATH"),
    )
    if test_config:
        app.config.update(test_config)

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    os.makedirs(app.config["REPORT_FOLDER"], exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    app.register_blueprint(api_v1)

    @login_manager.user_loader
    def load_user(user_id):
        try:
            return db.session.get(User, int(user_id))
        except (TypeError, ValueError):
            return None

    @app.before_request
    def reject_inactive_accounts():
        if current_user.is_authenticated and not current_user.is_active:
            logout_user()
            flash("This account is currently disabled.", "error")
            return redirect(url_for("login"))

    @app.context_processor
    def inject_template_state():
        if current_user.is_authenticated:
            language = current_user.language
        elif request.cookies.get("cropfarm_language_prompt") == "done":
            language = request.cookies.get("cropfarm_language", "en")
        else:
            language = "en"
        if language not in TRANSLATIONS:
            language = "en"
        unread_count = 0
        if current_user.is_authenticated:
            unread_count = Notification.query.filter_by(
                user_id=current_user.id, is_read=False
            ).count()
        return {
            "t": TRANSLATIONS.get(language, TRANSLATIONS["en"]),
            "current_language": language,
            "current_language_direction": next(
                item["direction"]
                for item in SUPPORTED_LANGUAGES
                if item["code"] == language
            ),
            "supported_languages": SUPPORTED_LANGUAGES,
            "translation_status": TRANSLATION_STATUS.get(language, "fallback"),
            "translation_statuses": TRANSLATION_STATUS,
            "language_prompt_done": (
                current_user.language_onboarding_done
                if current_user.is_authenticated
                else request.cookies.get("cropfarm_language_prompt") == "done"
            ),
            "language_onboarding_key": (
                f"cropfarmai-language-onboarding-v1:{current_user.id}"
                if current_user.is_authenticated
                else "cropfarmai-language-onboarding-v1:guest"
            ),
            "unread_notification_count": unread_count,
            "supported_crops": SUPPORTED_CROPS,
            "contact_form_enabled": _contact_form_enabled(),
            "current_theme": (
                current_user.theme if current_user.is_authenticated else "day"
            ),
        }

    def _contact_form_enabled():
        support_email = app.config.get("SUPPORT_EMAIL")
        sender_email = app.config.get("MAIL_FROM")
        return (
            smtp_is_configured(app.config)
            and isinstance(support_email, str)
            and bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", support_email.strip()))
            and isinstance(sender_email, str)
            and bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", sender_email.strip()))
        )

    @app.after_request
    def set_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data: https://images.unsplash.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; script-src 'self' 'unsafe-inline'; "
            "connect-src 'self'; media-src 'self' https:; "
            "frame-src 'self' https://www.youtube.com https://www.youtube-nocookie.com "
            "https://player.vimeo.com",
        )
        return response

    @app.errorhandler(413)
    def file_too_large(_error):
        flash("The image must be 10 MB or smaller.", "error")
        return redirect(request.referrer or url_for("scanner")), 413

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        app.logger.error("Unhandled application error: %s", error)
        return render_template("error.html", code=500), 500

    if app.config["AUTO_CREATE_DB"]:
        with app.app_context():
            db.create_all()

    @app.cli.command("init-db")
    def init_db_command():
        """Create any missing tables without dropping existing data."""
        db.create_all()
        print("Database tables are ready.")

    @app.cli.command("promote-admin")
    def promote_admin_command():
        """Promote an existing account to administrator by email."""
        import click

        email = click.prompt("Account email").strip().lower()
        user = User.query.filter_by(email=email).first()
        if user is None:
            raise click.ClickException("No account exists for that email.")
        user.role = "admin"
        db.session.commit()
        click.echo(f"Administrator role granted to {email}.")

    @app.route("/")
    def home():
        return render_template("welcome.html")

    @app.route("/explore")
    def explore():
        return redirect(url_for("home", _anchor="services"))

    @app.route("/about")
    def about():
        return render_template("about.html")

    @app.get("/privacy")
    def privacy():
        return render_template("privacy.html")

    @app.get("/terms")
    def terms():
        return render_template("terms.html")

    @app.post("/contact")
    @limiter.limit("3 per hour")
    def contact_submit():
        if not _contact_form_enabled():
            flash(
                "Contact delivery is unavailable because the deployment has not configured support email and SMTP.",
                "error",
            )
            return redirect(url_for("home", _anchor="contact"))

        if request.form.get("company", "").strip():
            current_app.logger.info("Contact form honeypot was submitted.")
            flash("The message could not be submitted. Please try again.", "error")
            return redirect(url_for("home", _anchor="contact"))

        full_name = " ".join(request.form.get("full_name", "").split())
        email = request.form.get("email", "").strip().lower()
        subject = request.form.get("subject", "").strip()
        message_body = request.form.get("message", "").strip()
        if (
            not full_name
            or len(full_name) > 120
            or len(email) > 254
            or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email)
            or not 3 <= len(subject) <= 180
            or "\r" in subject
            or "\n" in subject
            or not 10 <= len(message_body) <= 5000
        ):
            flash("Check the contact form fields and try again.", "error")
            return redirect(url_for("home", _anchor="contact"))

        email_message = EmailMessage()
        email_message["Subject"] = f"[CropFarmAI contact] {subject}"
        email_message["From"] = app.config["MAIL_FROM"]
        email_message["To"] = app.config["SUPPORT_EMAIL"].strip()
        email_message["Reply-To"] = email
        email_message.set_content(
            f"Name: {full_name}\nEmail: {email}\n\n{message_body}"
        )
        try:
            send_email_message(email_message, app.config)
        except (OSError, smtplib.SMTPException):
            current_app.logger.exception("Could not deliver contact form message.")
            flash("Your message could not be delivered. Please try again later.", "error")
        else:
            flash("Your message was accepted by the configured email service.", "success")
        return redirect(url_for("home", _anchor="contact"))

    @app.route("/set_language", methods=["POST"])
    def set_language():
        language = request.form.get("language", "en")
        if language not in TRANSLATIONS:
            abort(400)
        onboarding_complete = request.form.get("onboarding_complete") == "true"
        if current_user.is_authenticated:
            current_user.language = language
            if onboarding_complete:
                current_user.language_onboarding_done = True
            db.session.commit()
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            response = jsonify({"language": language, "saved": True})
        else:
            response = redirect(request.referrer or url_for("home"))
        response.set_cookie(
            "cropfarm_language",
            language,
            max_age=60 * 60 * 24 * 365,
            httponly=True,
            samesite="Lax",
            secure=request.is_secure,
        )
        if onboarding_complete:
            response.set_cookie(
                "cropfarm_language_prompt",
                "done",
                max_age=60 * 60 * 24 * 365,
                httponly=True,
                samesite="Lax",
                secure=request.is_secure,
            )
        return response

    @app.post("/set-theme")
    @login_required
    def set_theme():
        theme = request.form.get("theme", "")
        if theme not in {"day", "night"}:
            return jsonify(
                {
                    "saved": False,
                    "error": TRANSLATIONS.get(
                        current_user.language, TRANSLATIONS["en"]
                    )["theme_save_error"],
                }
            ), 400
        current_user.theme = theme
        db.session.commit()
        return jsonify({"saved": True, "theme": theme})

    @app.route("/register", methods=["GET", "POST"])
    @limiter.limit("5 per minute", methods=["POST"])
    def register():
        if current_user.is_authenticated:
            return redirect(url_for("dashboard"))
        if request.method == "POST":
            full_name = request.form.get("full_name", "").strip()
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            confirm_password = request.form.get("confirm_password", "")
            phone = request.form.get("phone", "").strip()
            farm_name = request.form.get("farm_name", "").strip()
            location = request.form.get("location", "").strip()
            errors = []
            if not full_name or len(full_name) > 120:
                errors.append("Enter your name (up to 120 characters).")
            if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
                errors.append("Enter a valid email address.")
            if User.query.filter(func.lower(User.email) == email).first():
                errors.append("An account already exists for that email.")
            if (
                len(password) < PASSWORD_MIN_LENGTH
                or not any(character.isalpha() for character in password)
                or not any(character.isdigit() for character in password)
            ):
                errors.append(
                    f"Use at least {PASSWORD_MIN_LENGTH} characters with a letter and a number."
                )
            if password != confirm_password:
                errors.append("The passwords do not match.")

            if errors:
                for error in errors:
                    flash(error, "error")
                return render_template("auth.html", mode="register")

            user = User(
                full_name=full_name,
                email=email,
                phone=phone or None,
                location=location or None,
                role="farmer",
                language=(
                    request.cookies.get("cropfarm_language", "en")
                    if request.cookies.get("cropfarm_language_prompt") == "done"
                    and request.cookies.get("cropfarm_language", "en") in TRANSLATIONS
                    else "en"
                ),
                language_onboarding_done=(
                    request.cookies.get("cropfarm_language_prompt") == "done"
                ),
            )
            user.set_password(password)
            if farm_name:
                user.farms.append(
                    Farm(farm_name=farm_name, location=location or None)
                )
            db.session.add(user)
            db.session.commit()
            login_user(user)
            flash("Your CropFarmAI account is ready.", "success")
            return redirect(url_for("dashboard"))
        return render_template("auth.html", mode="register")

    @app.route("/login", methods=["GET", "POST"])
    @limiter.limit("5 per minute", methods=["POST"])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for("dashboard"))
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            user = User.query.filter(func.lower(User.email) == email).first()
            if user is None or not user.is_active or not user.check_password(password):
                flash("Email or password is incorrect.", "error")
                return render_template("auth.html", mode="login")
            login_user(user, remember=request.form.get("remember") == "on")
            if (
                not user.language_onboarding_done
                and request.cookies.get("cropfarm_language_prompt") == "done"
            ):
                guest_language = request.cookies.get("cropfarm_language", "en")
                if guest_language in TRANSLATIONS:
                    user.language = guest_language
                    user.language_onboarding_done = True
                    db.session.commit()
            next_url = request.args.get("next")
            if next_url:
                target = urlsplit(urljoin(request.host_url, next_url))
                if target.scheme in {"http", "https"} and target.netloc == request.host:
                    return redirect(next_url)
            return redirect(url_for("dashboard"))
        return render_template("auth.html", mode="login")

    @app.post("/logout")
    @login_required
    def logout():
        logout_user()
        flash("You have been signed out.", "info")
        return redirect(url_for("home"))

    def _reset_serializer():
        return URLSafeTimedSerializer(current_app.config["SECRET_KEY"])

    def _send_reset_email(user, reset_url):
        if not smtp_is_configured(current_app.config):
            current_app.logger.info(
                "Password reset requested for %s, but SMTP is not configured.", user.email
            )
            return
        message = EmailMessage()
        message["Subject"] = "Reset your CropFarmAI password"
        message["From"] = current_app.config["MAIL_FROM"]
        message["To"] = user.email
        message.set_content(
            "Use the following link to reset your CropFarmAI password. "
            "It expires in one hour:\n\n" + reset_url
        )
        send_email_message(message, current_app.config)

    @app.route("/forgot-password", methods=["GET", "POST"])
    @limiter.limit("3 per minute", methods=["POST"])
    def forgot_password():
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            user = User.query.filter(func.lower(User.email) == email).first()
            if user:
                token = _reset_serializer().dumps(user.email, salt="password-reset")
                reset_url = url_for("reset_password", token=token, _external=True)
                try:
                    _send_reset_email(user, reset_url)
                except (OSError, smtplib.SMTPException):
                    current_app.logger.exception("Could not send password reset email.")
            flash(
                "If an account matches that email and email delivery is configured, "
                "a password reset link will be sent.",
                "info",
            )
            return redirect(url_for("login"))
        return render_template("auth.html", mode="forgot")

    @app.route("/reset-password/<token>", methods=["GET", "POST"])
    def reset_password(token):
        try:
            email = _reset_serializer().loads(
                token, salt="password-reset", max_age=3600
            )
        except (BadSignature, SignatureExpired):
            flash("That password reset link is invalid or has expired.", "error")
            return redirect(url_for("forgot_password"))
        user = User.query.filter_by(email=email).first()
        if user is None:
            flash("That password reset link is invalid or has expired.", "error")
            return redirect(url_for("forgot_password"))
        if request.method == "POST":
            password = request.form.get("password", "")
            if (
                len(password) < PASSWORD_MIN_LENGTH
                or not any(character.isalpha() for character in password)
                or not any(character.isdigit() for character in password)
            ):
                flash(
                    f"Use at least {PASSWORD_MIN_LENGTH} characters with a letter and a number.",
                    "error",
                )
            elif password != request.form.get("confirm_password", ""):
                flash("The passwords do not match.", "error")
            else:
                user.set_password(password)
                db.session.commit()
                flash("Your password has been updated. Please sign in.", "success")
                return redirect(url_for("login"))
        return render_template("auth.html", mode="reset")

    @app.route("/dashboard")
    @login_required
    def dashboard():
        farms = Farm.query.filter_by(user_id=current_user.id).count()
        fields = (
            Field.query.join(Farm).filter(Farm.user_id == current_user.id).count()
        )
        crops_query = Crop.query.filter_by(user_id=current_user.id)
        crops = crops_query.count()
        healthy = crops_query.filter(func.lower(Crop.health_status) == "healthy").count()
        at_risk = crops_query.filter(
            func.lower(Crop.health_status).in_(("at risk", "needs attention"))
        ).count()
        detection_count = DiseaseDetection.query.filter_by(
            user_id=current_user.id
        ).count()
        recent_detections = (
            DiseaseDetection.query.filter_by(user_id=current_user.id)
            .order_by(DiseaseDetection.created_at.desc())
            .limit(5)
            .all()
        )
        localized_disease_names = DISEASE_NAMES.get(
            current_user.language, DISEASE_NAMES["en"]
        )
        recent_disease_names = {
            detection.unique_detection_id: localized_disease_names.get(
                detection.predicted_disease,
                detection.predicted_disease.replace("_", " "),
            )
            for detection in recent_detections
        }
        recent_detection_dates = {
            detection.unique_detection_id: format_localized_date(
                detection.created_at, current_user.language
            )
            for detection in recent_detections
        }
        return render_template(
            "dashboard.html",
            active_page="overview",
            stats={
                "farms": farms,
                "fields": fields,
                "crops": crops,
                "healthy": healthy,
                "at_risk": at_risk,
                "detections": detection_count,
            },
            recent_detections=recent_detections,
            recent_disease_names=recent_disease_names,
            recent_detection_dates=recent_detection_dates,
            model_available=model is not None,
        )

    @app.route("/farms", methods=["GET", "POST"])
    @login_required
    def farms_page():
        if request.method == "POST":
            name = request.form.get("farm_name", "").strip()
            location = request.form.get("location", "").strip()
            size_text = request.form.get("farm_size", "").strip()
            description = request.form.get("description", "").strip()
            try:
                size = float(size_text) if size_text else None
                if size is not None and size <= 0:
                    raise ValueError
                if not name or len(name) > 120:
                    raise ValueError
            except ValueError:
                flash("Enter a farm name and a positive farm size.", "error")
            else:
                db.session.add(
                    Farm(
                        user_id=current_user.id,
                        farm_name=name,
                        location=location or None,
                        farm_size=size,
                        description=description or None,
                    )
                )
                db.session.commit()
                flash("Farm added.", "success")
                return redirect(url_for("farms_page"))
        farms = Farm.query.filter_by(user_id=current_user.id).order_by(Farm.created_at.desc()).all()
        return render_template("farms.html", active_page="farms", farms=farms)

    @app.post("/farms/<int:farm_id>/update")
    @login_required
    def update_farm(farm_id):
        farm = Farm.query.filter_by(id=farm_id, user_id=current_user.id).first_or_404()
        name = request.form.get("farm_name", "").strip()
        location = request.form.get("location", "").strip()
        size_text = request.form.get("farm_size", "").strip()
        try:
            size = float(size_text) if size_text else None
            if not name or len(name) > 120 or (size is not None and size <= 0):
                raise ValueError
        except ValueError:
            flash("Enter a farm name and a positive farm size.", "error")
        else:
            farm.farm_name = name
            farm.location = location or None
            farm.farm_size = size
            farm.description = request.form.get("description", "").strip() or None
            db.session.commit()
            flash("Farm updated.", "success")
        return redirect(url_for("farms_page"))

    @app.post("/farms/<int:farm_id>/delete")
    @login_required
    def delete_farm(farm_id):
        farm = Farm.query.filter_by(id=farm_id, user_id=current_user.id).first_or_404()
        db.session.delete(farm)
        db.session.commit()
        flash("Farm deleted.", "success")
        return redirect(url_for("farms_page"))

    @app.route("/fields", methods=["GET", "POST"])
    @login_required
    def fields_page():
        farms = Farm.query.filter_by(user_id=current_user.id).order_by(Farm.farm_name).all()
        if request.method == "POST":
            name = request.form.get("field_name", "").strip()
            farm = Farm.query.filter_by(
                id=request.form.get("farm_id", type=int), user_id=current_user.id
            ).first()
            area_text = request.form.get("area", "").strip()
            try:
                area = float(area_text) if area_text else None
                if not farm or not name or len(name) > 120 or (
                    area is not None and area <= 0
                ):
                    raise ValueError
            except ValueError:
                flash("Choose one of your farms and enter valid field details.", "error")
            else:
                db.session.add(
                    Field(
                        farm_id=farm.id,
                        field_name=name,
                        area=area,
                        location=request.form.get("location", "").strip() or None,
                        assigned_crop=request.form.get("assigned_crop", "").strip() or None,
                    )
                )
                db.session.commit()
                flash("Field added.", "success")
                return redirect(url_for("fields_page"))
        fields = (
            Field.query.join(Farm)
            .filter(Farm.user_id == current_user.id)
            .order_by(Farm.farm_name, Field.field_name)
            .all()
        )
        return render_template(
            "fields.html", active_page="fields", farms=farms, fields=fields
        )

    @app.post("/fields/<int:field_id>/delete")
    @login_required
    def delete_field(field_id):
        field = (
            Field.query.join(Farm)
            .filter(Field.id == field_id, Farm.user_id == current_user.id)
            .first_or_404()
        )
        db.session.delete(field)
        db.session.commit()
        flash("Field deleted.", "success")
        return redirect(url_for("fields_page"))

    @app.route("/crops", methods=["GET", "POST"])
    @login_required
    def crops_page():
        farms = Farm.query.filter_by(user_id=current_user.id).order_by(Farm.farm_name).all()
        fields = (
            Field.query.join(Farm).filter(Farm.user_id == current_user.id).order_by(Field.field_name).all()
        )
        if request.method == "POST":
            crop_name = request.form.get("crop_name", "").strip()
            farm = Farm.query.filter_by(
                id=request.form.get("farm_id", type=int), user_id=current_user.id
            ).first() if request.form.get("farm_id") else None
            field = Field.query.join(Farm).filter(
                Field.id == request.form.get("field_id", type=int),
                Farm.user_id == current_user.id,
            ).first() if request.form.get("field_id") else None
            try:
                planting_date = _parse_date(request.form.get("planting_date"))
                harvesting_date = _parse_date(request.form.get("harvesting_date"))
                if crop_name not in SUPPORTED_CROPS:
                    raise ValueError
                if request.form.get("farm_id") and farm is None:
                    raise ValueError
                if request.form.get("field_id") and field is None:
                    raise ValueError
                if field and farm and field.farm_id != farm.id:
                    raise ValueError
                if planting_date and harvesting_date and harvesting_date < planting_date:
                    raise ValueError
            except ValueError:
                flash("Choose a supported crop and valid farm, field, and dates.", "error")
            else:
                crop = Crop(
                    user_id=current_user.id,
                    farm_id=farm.id if farm else (field.farm_id if field else None),
                    field_id=field.id if field else None,
                    crop_name=crop_name,
                    planting_date=planting_date,
                    harvesting_date=harvesting_date,
                    growth_stage=request.form.get("growth_stage", "").strip() or None,
                    health_status=request.form.get("health_status", "Unknown"),
                )
                db.session.add(crop)
                db.session.commit()
                flash("Crop added.", "success")
                return redirect(url_for("crops_page"))
        crops = (
            Crop.query.filter_by(user_id=current_user.id)
            .order_by(Crop.created_at.desc())
            .all()
        )
        return render_template(
            "crops.html",
            active_page="crops",
            crops=crops,
            farms=farms,
            fields=fields,
            supported_crops=SUPPORTED_CROPS,
        )

    @app.post("/crops/<int:crop_id>/update")
    @login_required
    def update_crop(crop_id):
        crop = Crop.query.filter_by(id=crop_id, user_id=current_user.id).first_or_404()
        status = request.form.get("health_status", "")
        if status not in {"Unknown", "Healthy", "At risk", "Needs attention"}:
            abort(400)
        crop.health_status = status
        crop.growth_stage = request.form.get("growth_stage", "").strip() or None
        db.session.commit()
        flash("Crop monitoring details updated.", "success")
        return redirect(url_for("crops_page"))

    @app.post("/crops/<int:crop_id>/delete")
    @login_required
    def delete_crop(crop_id):
        crop = Crop.query.filter_by(id=crop_id, user_id=current_user.id).first_or_404()
        db.session.delete(crop)
        db.session.commit()
        flash("Crop deleted.", "success")
        return redirect(url_for("crops_page"))

    @app.route("/crop-health")
    @login_required
    def crop_health():
        crops = Crop.query.filter_by(user_id=current_user.id).order_by(Crop.crop_name).all()
        recent = (
            DiseaseDetection.query.filter_by(user_id=current_user.id)
            .order_by(DiseaseDetection.created_at.desc())
            .limit(10)
            .all()
        )
        return render_template(
            "health.html", active_page="health", crops=crops, detections=recent
        )

    @app.route("/scanner", methods=["GET", "POST"])
    @login_required
    def scanner():
        farms = Farm.query.filter_by(user_id=current_user.id).order_by(Farm.farm_name).all()
        crops = Crop.query.filter_by(user_id=current_user.id).order_by(Crop.crop_name).all()
        fields = (
            Field.query.join(Farm)
            .filter(Farm.user_id == current_user.id)
            .order_by(Field.field_name)
            .all()
        )
        result = None
        if request.method == "POST":
            uploaded = request.files.get("crop_image")
            if not uploaded or not uploaded.filename:
                flash("Choose a crop image to analyze.", "error")
                return render_template(
                    "scanner.html", active_page="scanner", farms=farms, crops=crops,
                    fields=fields, model_available=model is not None
                )
            filename = secure_filename(uploaded.filename)
            extension = Path(filename).suffix.lower().lstrip(".")
            if extension not in ALLOWED_EXTENSIONS:
                flash("Upload a JPG, JPEG, PNG, or WebP image.", "error")
                return render_template(
                    "scanner.html", active_page="scanner", farms=farms, crops=crops,
                    fields=fields, model_available=model is not None
                )
            if model is None:
                current_app.logger.error("Disease model is unavailable for inference.")
                flash("AI analysis is temporarily unavailable. Please check model configuration.", "error")
                return render_template(
                    "scanner.html", active_page="scanner", farms=farms, crops=crops,
                    fields=fields, model_available=False
                )
            try:
                image = Image.open(uploaded.stream)
                if image.width * image.height > 25_000_000:
                    raise ValueError("Image dimensions exceed the supported limit.")
                image.verify()
                actual_format = image.format
                if actual_format not in {"JPEG", "PNG", "WEBP"}:
                    raise ValueError("Unsupported image format.")
                accepted_extensions = {
                    "JPEG": {"jpg", "jpeg"},
                    "PNG": {"png"},
                    "WEBP": {"webp"},
                }
                if extension not in accepted_extensions[actual_format]:
                    raise ValueError("The file extension does not match its image format.")
                uploaded.stream.seek(0)
            except (UnidentifiedImageError, OSError, ValueError):
                flash("The selected file is not a valid supported image.", "error")
                return render_template(
                    "scanner.html", active_page="scanner", farms=farms, crops=crops,
                    fields=fields, model_available=model is not None
                )

            farm = None
            field = None
            crop = None
            if request.form.get("farm_id"):
                farm = Farm.query.filter_by(
                    id=request.form.get("farm_id", type=int), user_id=current_user.id
                ).first()
                if farm is None:
                    abort(400)
            if request.form.get("field_id"):
                field = Field.query.join(Farm).filter(
                    Field.id == request.form.get("field_id", type=int),
                    Farm.user_id == current_user.id,
                ).first()
                if field is None or (farm and field.farm_id != farm.id):
                    abort(400)
                farm = farm or field.farm
            if request.form.get("crop_id"):
                crop = Crop.query.filter_by(
                    id=request.form.get("crop_id", type=int),
                    user_id=current_user.id,
                ).first()
                if crop is None:
                    abort(400)
                if farm and crop.farm_id != farm.id:
                    abort(400)
                if field and crop.field_id != field.id:
                    abort(400)
                farm = farm or (db.session.get(Farm, crop.farm_id) if crop.farm_id else None)
                field = field or (db.session.get(Field, crop.field_id) if crop.field_id else None)

            detection_id = str(uuid.uuid4())
            safe_extension = "jpg" if actual_format == "JPEG" else actual_format.lower()
            relative_image_path = os.path.join(
                "users", str(current_user.id), "detections", detection_id,
                f"original.{safe_extension}",
            )
            image_path = os.path.join(
                current_app.config["UPLOAD_FOLDER"], relative_image_path
            )
            os.makedirs(os.path.dirname(image_path), exist_ok=True)
            uploaded.save(image_path)

            try:
                predicted_disease, confidence = predict_disease(image_path)
            except (OSError, ValueError, KeyError, tf.errors.OpError):
                current_app.logger.exception("Image inference failed.")
                _remove_file(image_path)
                flash("Unable to analyze this image. Please try another crop photo.", "error")
                return render_template(
                    "scanner.html", active_page="scanner", farms=farms, crops=crops,
                    fields=fields, model_available=model is not None
                )

            language = current_user.language if current_user.language in DISEASE_NAMES else "en"
            disease_name = DISEASE_NAMES.get(language, DISEASE_NAMES["en"]).get(
                predicted_disease, predicted_disease.replace("_", " ")
            )
            details = MULTILINGUAL_DISEASE_INFO.get(
                language, MULTILINGUAL_DISEASE_INFO["en"]
            ).get(
                predicted_disease,
                MULTILINGUAL_DISEASE_INFO["en"].get(predicted_disease, {}),
            )
            inferred_crop = (
                "Bell pepper"
                if predicted_disease.startswith("Pepper__bell")
                else predicted_disease.split("_", 1)[0]
            )
            detection = DiseaseDetection(
                unique_detection_id=detection_id,
                user_id=current_user.id,
                farm_id=farm.id if farm else None,
                field_id=field.id if field else None,
                crop_id=crop.id if crop else None,
                crop_name=crop.crop_name if crop else inferred_crop,
                predicted_disease=predicted_disease,
                confidence_score=confidence,
                disease_description=details.get("description"),
                treatment_recommendation=details.get("treatment"),
                prevention_recommendation=details.get("prevention"),
                model_name="CropFarmAI crop disease classifier",
                model_version=tf.__version__,
            )
            detection.images.append(
                DetectionImage(
                    original_image_path=relative_image_path,
                    image_format=actual_format.lower(),
                    file_size=os.path.getsize(image_path),
                )
            )
            try:
                report = generate_pdf_report(
                    image_path,
                    DISEASE_NAMES["en"].get(
                        predicted_disease, predicted_disease.replace("_", " ")
                    ),
                    confidence,
                    MULTILINGUAL_DISEASE_INFO["en"].get(predicted_disease, {}),
                    language="en",
                    font_path=current_app.config.get("REPORT_FONT_PATH"),
                )
                report_path = os.path.join(
                    current_app.config["REPORT_FOLDER"], f"{detection_id}.pdf"
                )
                with open(report_path, "wb") as report_file:
                    report_file.write(report.getvalue())
                detection.report_path = report_path
            except (OSError, ValueError, KeyError):
                current_app.logger.exception("Could not generate diagnosis report.")
            db.session.add(detection)
            db.session.add(
                Notification(
                    user_id=current_user.id,
                    title="Crop analysis complete",
                    message=f"{detection.crop_name}: {disease_name} ({confidence:.2f}% confidence).",
                    notification_type="detection",
                )
            )
            db.session.commit()
            result = {
                "detection": detection,
                "disease_name": disease_name,
                "details": details,
                "image_url": url_for(
                    "uploaded_image", filename=relative_image_path
                ),
            }
        return render_template(
            "scanner.html",
            active_page="scanner",
            farms=farms,
            crops=crops,
            fields=fields,
            model_available=model is not None,
            result=result,
        )

    @app.route("/uploads/<path:filename>")
    @login_required
    def uploaded_image(filename):
        image_record = (
            DetectionImage.query.join(DiseaseDetection)
            .filter(DetectionImage.original_image_path == filename)
            .first_or_404()
        )
        if (
            image_record.detection.user_id != current_user.id
            and current_user.role != "admin"
        ):
            abort(404)
        return send_from_directory(current_app.config["UPLOAD_FOLDER"], filename)

    @app.route("/history")
    @login_required
    def history():
        query = DiseaseDetection.query.filter_by(user_id=current_user.id)
        crop_filter = request.args.get("crop", "").strip()
        disease_filter = request.args.get("disease", "").strip()
        start_date = request.args.get("start", "").strip()
        end_date = request.args.get("end", "").strip()
        if crop_filter:
            query = query.filter(DiseaseDetection.crop_name == crop_filter)
        if disease_filter:
            query = query.filter(
                DiseaseDetection.predicted_disease.ilike(f"%{disease_filter}%")
            )
        try:
            if start_date:
                query = query.filter(
                    DiseaseDetection.created_at >= datetime.combine(
                        date.fromisoformat(start_date), datetime.min.time()
                    )
                )
            if end_date:
                query = query.filter(
                    DiseaseDetection.created_at < datetime.combine(
                        date.fromisoformat(end_date) + timedelta(days=1),
                        datetime.min.time(),
                    )
                )
        except ValueError:
            abort(400, description="Use valid ISO dates for history filters.")
        page = request.args.get("page", 1, type=int)
        pagination = query.order_by(DiseaseDetection.created_at.desc()).paginate(
            page=max(page or 1, 1), per_page=12, error_out=False
        )
        crops = [
            row[0]
            for row in db.session.query(DiseaseDetection.crop_name)
            .filter_by(user_id=current_user.id)
            .distinct()
            .order_by(DiseaseDetection.crop_name)
            .all()
        ]
        return render_template(
            "history.html",
            active_page="history",
            pagination=pagination,
            crops=crops,
            filters={
                "crop": crop_filter,
                "disease": disease_filter,
                "start": start_date,
                "end": end_date,
            },
        )

    @app.route("/history/<detection_id>")
    @login_required
    def detection_detail(detection_id):
        detection = DiseaseDetection.query.filter_by(
            unique_detection_id=detection_id, user_id=current_user.id
        ).first_or_404()
        language = current_user.language if current_user.language in DISEASE_NAMES else "en"
        disease_name = DISEASE_NAMES.get(language, DISEASE_NAMES["en"]).get(
            detection.predicted_disease,
            detection.predicted_disease.replace("_", " "),
        )
        details = MULTILINGUAL_DISEASE_INFO.get(
            language, MULTILINGUAL_DISEASE_INFO["en"]
        ).get(
            detection.predicted_disease,
            MULTILINGUAL_DISEASE_INFO["en"].get(detection.predicted_disease, {}),
        )
        return render_template(
            "detection_detail.html",
            active_page="history",
            detection=detection,
            disease_name=disease_name,
            details=details,
        )

    @app.post("/history/<detection_id>/treatments")
    @login_required
    def add_treatment_record(detection_id):
        detection = DiseaseDetection.query.filter_by(
            unique_detection_id=detection_id, user_id=current_user.id
        ).first_or_404()
        treatment_name = request.form.get("treatment_name", "").strip()
        status = request.form.get("status", "planned")
        if not treatment_name or len(treatment_name) > 160:
            flash("Enter a treatment name up to 160 characters.", "error")
        elif status not in {"planned", "applied", "skipped"}:
            abort(400)
        else:
            try:
                application_date = _parse_date(
                    request.form.get("application_date")
                )
            except ValueError:
                flash("Enter a valid treatment date.", "error")
            else:
                db.session.add(
                    TreatmentRecord(
                        user_id=current_user.id,
                        detection_id=detection.id,
                        treatment_name=treatment_name,
                        treatment_description=request.form.get(
                            "treatment_description", ""
                        ).strip() or None,
                        application_date=application_date,
                        status=status,
                        notes=request.form.get("notes", "").strip() or None,
                    )
                )
                db.session.commit()
                flash("Treatment record saved.", "success")
                return redirect(
                    url_for("detection_detail", detection_id=detection_id)
                )
        return redirect(url_for("detection_detail", detection_id=detection_id))

    @app.post("/history/<detection_id>/delete")
    @login_required
    def delete_detection(detection_id):
        detection = DiseaseDetection.query.filter_by(
            unique_detection_id=detection_id, user_id=current_user.id
        ).first_or_404()
        for image in detection.images:
            _remove_file(
                os.path.join(
                    current_app.config["UPLOAD_FOLDER"], image.original_image_path
                )
            )
        if detection.report_path:
            _remove_file(detection.report_path)
        db.session.delete(detection)
        db.session.commit()
        flash("Detection and its stored files were deleted.", "success")
        return redirect(url_for("history"))

    @app.route("/history/<detection_id>/report")
    @login_required
    def download_report(detection_id):
        detection = DiseaseDetection.query.filter_by(
            unique_detection_id=detection_id, user_id=current_user.id
        ).first_or_404()
        if not detection.report_path or not os.path.isfile(detection.report_path):
            flash("A report is not available for this detection.", "error")
            return redirect(url_for("detection_detail", detection_id=detection_id))
        return send_file(
            detection.report_path,
            as_attachment=True,
            download_name=f"CropFarmAI-{detection_id}.pdf",
        )

    def load_weather(location):
        if not location:
            return None, "Add a location to your profile or .env to see weather context."
        try:
            return get_weather_report(location), None
        except WeatherIntegrationError as error:
            current_app.logger.warning("Weather integration failed (%s).", error.code)
            if error.code == "location_not_found":
                return None, "No matching location was found. Check the spelling and try again."
            if error.code == "invalid_location":
                return None, "Enter a location with no more than 120 characters."
            return None, "Live weather is currently unavailable. Try again later."

    @app.route("/irrigation", methods=["GET", "POST"])
    @login_required
    def irrigation():
        fields = (
            Field.query.join(Farm)
            .filter(Farm.user_id == current_user.id)
            .order_by(Field.field_name)
            .all()
        )
        if request.method == "POST":
            field = Field.query.join(Farm).filter(
                Field.id == request.form.get("field_id", type=int),
                Farm.user_id == current_user.id,
            ).first() if request.form.get("field_id") else None
            try:
                irrigation_date = _parse_date(request.form.get("irrigation_date"))
                amount_text = request.form.get("water_quantity", "").strip()
                amount = float(amount_text) if amount_text else None
                if irrigation_date is None or (
                    request.form.get("field_id") and field is None
                ) or (amount is not None and amount <= 0):
                    raise ValueError
            except ValueError:
                flash("Enter a valid date, field, and positive water quantity.", "error")
            else:
                db.session.add(
                    IrrigationRecord(
                        user_id=current_user.id,
                        field_id=field.id if field else None,
                        irrigation_date=irrigation_date,
                        water_quantity=amount,
                        schedule=request.form.get("schedule", "").strip() or None,
                        status="scheduled",
                    )
                )
                db.session.commit()
                flash("Irrigation schedule saved.", "success")
                return redirect(url_for("irrigation"))
        records = (
            IrrigationRecord.query.filter_by(user_id=current_user.id)
            .order_by(IrrigationRecord.irrigation_date.desc())
            .all()
        )
        location = (
            request.args.get("location", "").strip()
            or current_user.location
            or current_app.config.get("WEATHER_LOCATION")
            or ""
        )
        weather_report, weather_error = load_weather(location)
        return render_template(
            "irrigation.html",
            active_page="irrigation",
            fields=fields,
            records=records,
            weather_report=weather_report,
            weather_error=weather_error,
            location=location,
            irrigation_advisory=(
                get_irrigation_advisory(weather_report) if weather_report else None
            ),
        )

    @app.post("/irrigation/<int:record_id>/delete")
    @login_required
    def delete_irrigation(record_id):
        record = IrrigationRecord.query.filter_by(
            id=record_id, user_id=current_user.id
        ).first_or_404()
        db.session.delete(record)
        db.session.commit()
        flash("Irrigation record deleted.", "success")
        return redirect(url_for("irrigation"))

    @app.post("/irrigation/<int:record_id>/complete")
    @login_required
    def complete_irrigation(record_id):
        record = IrrigationRecord.query.filter_by(
            id=record_id, user_id=current_user.id
        ).first_or_404()
        record.status = "completed"
        db.session.commit()
        flash("Irrigation marked as completed.", "success")
        return redirect(url_for("irrigation"))

    @app.route("/soil", methods=["GET", "POST"])
    @login_required
    def soil():
        fields = (
            Field.query.join(Farm)
            .filter(Farm.user_id == current_user.id)
            .order_by(Field.field_name)
            .all()
        )
        if request.method == "POST":
            field = Field.query.join(Farm).filter(
                Field.id == request.form.get("field_id", type=int),
                Farm.user_id == current_user.id,
            ).first() if request.form.get("field_id") else None
            try:
                values = {
                    key: float(request.form[key])
                    for key in ("moisture", "temperature", "ph_value")
                    if request.form.get(key, "").strip()
                }
                if request.form.get("field_id") and field is None:
                    raise ValueError
                if "moisture" in values and not 0 <= values["moisture"] <= 100:
                    raise ValueError
                if "ph_value" in values and not 0 <= values["ph_value"] <= 14:
                    raise ValueError
                if not values and not request.form.get("nutrient_information", "").strip():
                    raise ValueError
            except ValueError:
                flash("Enter valid soil measurements (moisture 0-100%, pH 0-14).", "error")
            else:
                db.session.add(
                    SoilReading(
                        user_id=current_user.id,
                        field_id=field.id if field else None,
                        moisture=values.get("moisture"),
                        temperature=values.get("temperature"),
                        ph_value=values.get("ph_value"),
                        nutrient_information=request.form.get(
                            "nutrient_information", ""
                        ).strip() or None,
                        reading_source="manual",
                    )
                )
                db.session.commit()
                flash("Manual soil reading saved.", "success")
                return redirect(url_for("soil"))
        readings = (
            SoilReading.query.filter_by(user_id=current_user.id)
            .order_by(SoilReading.recorded_at.desc())
            .limit(50)
            .all()
        )
        return render_template(
            "soil.html", active_page="soil", fields=fields, readings=readings
        )

    @app.post("/soil/<int:reading_id>/delete")
    @login_required
    def delete_soil_reading(reading_id):
        reading = SoilReading.query.filter_by(
            id=reading_id, user_id=current_user.id
        ).first_or_404()
        db.session.delete(reading)
        db.session.commit()
        flash("Soil reading deleted.", "success")
        return redirect(url_for("soil"))

    @app.route("/weather")
    @login_required
    def weather():
        location = (
            request.args.get("location", "").strip()
            or current_user.location
            or current_app.config.get("WEATHER_LOCATION")
            or ""
        )
        weather_report, weather_error = load_weather(location)
        return render_template(
            "weather.html",
            active_page="weather",
            weather_report=weather_report,
            weather_error=weather_error,
            location=location,
        )

    @app.route("/analytics")
    @login_required
    def analytics():
        period = request.args.get("period", "30d")
        if period not in {"7d", "30d", "3m", "6m", "all", "custom"}:
            abort(400, description="Choose a supported analytics period.")
        days = {"7d": 7, "30d": 30, "3m": 90, "6m": 180}.get(period)
        query = DiseaseDetection.query.filter_by(user_id=current_user.id)
        if days:
            query = query.filter(
                DiseaseDetection.created_at >= datetime.now(timezone.utc) - timedelta(days=days)
            )
        start_date = request.args.get("start", "").strip()
        end_date = request.args.get("end", "").strip()
        custom_start = None
        custom_end = None
        try:
            if period == "custom":
                if start_date:
                    custom_start = date.fromisoformat(start_date)
                if end_date:
                    custom_end = date.fromisoformat(end_date)
                if custom_start and custom_end and custom_end < custom_start:
                    raise ValueError
        except ValueError:
            abort(400, description="Use valid ISO dates for analytics filters.")
        if custom_start:
            query = query.filter(
                DiseaseDetection.created_at
                >= datetime.combine(custom_start, datetime.min.time(), timezone.utc)
            )
        if custom_end:
            query = query.filter(
                DiseaseDetection.created_at
                < datetime.combine(
                    custom_end + timedelta(days=1),
                    datetime.min.time(),
                    timezone.utc,
                )
            )
        detections = query.order_by(DiseaseDetection.created_at.desc()).all()
        disease_counts = {}
        crop_counts = {}
        monthly_counts = {}
        for detection in detections:
            disease_counts[detection.predicted_disease] = (
                disease_counts.get(detection.predicted_disease, 0) + 1
            )
            crop_counts[detection.crop_name] = crop_counts.get(detection.crop_name, 0) + 1
            month_key = detection.created_at.strftime("%Y-%m")
            monthly_counts[month_key] = monthly_counts.get(month_key, 0) + 1
        health_counts = {
            status: Crop.query.filter_by(user_id=current_user.id, health_status=status).count()
            for status in ("Healthy", "At risk", "Needs attention", "Unknown")
        }
        treatment_query = (
            TreatmentRecord.query.join(DiseaseDetection)
            .filter(DiseaseDetection.user_id == current_user.id)
        )
        if days:
            treatment_query = treatment_query.filter(
                DiseaseDetection.created_at
                >= datetime.now(timezone.utc) - timedelta(days=days)
            )
        if custom_start:
            treatment_query = treatment_query.filter(
                DiseaseDetection.created_at
                >= datetime.combine(custom_start, datetime.min.time(), timezone.utc)
            )
        if custom_end:
            treatment_query = treatment_query.filter(
                DiseaseDetection.created_at
                < datetime.combine(
                    custom_end + timedelta(days=1),
                    datetime.min.time(),
                    timezone.utc,
                )
            )
        treatment_count = treatment_query.count()
        return render_template(
            "analytics.html",
            active_page="analytics",
            period=period,
            detections=detections,
            disease_counts=sorted(disease_counts.items(), key=lambda item: (-item[1], item[0])),
            crop_counts=sorted(crop_counts.items(), key=lambda item: (-item[1], item[0])),
            monthly_counts=sorted(monthly_counts.items()),
            health_counts=health_counts,
            treatment_count=treatment_count,
            start_date=start_date,
            end_date=end_date,
        )

    @app.route("/reports")
    @login_required
    def reports():
        count = DiseaseDetection.query.filter_by(user_id=current_user.id).count()
        return render_template("reports.html", active_page="reports", detection_count=count)

    @app.route("/reports/detections.csv")
    @login_required
    def export_detections():
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(
            ["Detection ID", "Crop", "Prediction", "Confidence (%)", "Farm", "Field", "Created (UTC)"]
        )
        records = (
            DiseaseDetection.query.filter_by(user_id=current_user.id)
            .order_by(DiseaseDetection.created_at.desc())
            .all()
        )
        for record in records:
            writer.writerow(
                [
                    _csv_safe(record.unique_detection_id),
                    _csv_safe(record.crop_name),
                    _csv_safe(record.predicted_disease),
                    _csv_safe(f"{record.confidence_score:.2f}"),
                    _csv_safe(record.crop.farm.farm_name)
                    if record.crop and record.crop.farm
                    else (_csv_safe(record.farm.farm_name) if record.farm else ""),
                    _csv_safe(record.crop.field.field_name)
                    if record.crop and record.crop.field
                    else (_csv_safe(record.field.field_name) if record.field else ""),
                    _csv_safe(record.created_at.isoformat()),
                ]
            )
        response = make_response("\ufeff" + output.getvalue())
        response.headers["Content-Type"] = "text/csv; charset=utf-8"
        response.headers["Content-Disposition"] = "attachment; filename=cropfarm-detections.csv"
        return response

    @app.route("/notifications")
    @login_required
    def notifications():
        records = (
            Notification.query.filter_by(user_id=current_user.id)
            .order_by(Notification.created_at.desc())
            .limit(100)
            .all()
        )
        return render_template(
            "notifications.html", active_page="notifications", notifications=records
        )

    @app.post("/notifications/<int:notification_id>/read")
    @login_required
    def mark_notification_read(notification_id):
        notification = Notification.query.filter_by(
            id=notification_id, user_id=current_user.id
        ).first_or_404()
        notification.is_read = True
        db.session.commit()
        return redirect(request.referrer or url_for("notifications"))

    @app.post("/notifications/read-all")
    @login_required
    def mark_all_notifications_read():
        Notification.query.filter_by(
            user_id=current_user.id, is_read=False
        ).update({"is_read": True})
        db.session.commit()
        flash("Notifications marked as read.", "success")
        return redirect(url_for("notifications"))

    @app.post("/notifications/<int:notification_id>/delete")
    @login_required
    def delete_notification(notification_id):
        notification = Notification.query.filter_by(
            id=notification_id, user_id=current_user.id
        ).first_or_404()
        db.session.delete(notification)
        db.session.commit()
        return redirect(url_for("notifications"))

    @app.route("/profile", methods=["GET", "POST"])
    @login_required
    def profile():
        if request.method == "POST":
            name = request.form.get("full_name", "").strip()
            email = request.form.get("email", "").strip().lower()
            phone = request.form.get("phone", "").strip()
            location = request.form.get("location", "").strip()
            password = request.form.get("current_password", "")
            new_password = request.form.get("new_password", "")
            if not name or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
                flash("Enter a valid name and email address.", "error")
            elif User.query.filter(
                func.lower(User.email) == email, User.id != current_user.id
            ).first():
                flash("That email address is already in use.", "error")
            elif new_password and (
                not current_user.check_password(password)
                or len(new_password) < PASSWORD_MIN_LENGTH
                or not any(character.isalpha() for character in new_password)
                or not any(character.isdigit() for character in new_password)
            ):
                flash(
                    "To change your password, enter your current password and use a new "
                    f"password with at least {PASSWORD_MIN_LENGTH} characters, a letter, and a number.",
                    "error",
                )
            else:
                current_user.full_name = name
                current_user.email = email
                current_user.phone = phone or None
                current_user.location = location or None
                if new_password:
                    current_user.set_password(new_password)
                db.session.commit()
                flash("Profile updated.", "success")
                return redirect(url_for("profile"))
        return render_template("profile.html", active_page="profile")

    @app.route("/settings", methods=["GET", "POST"])
    @login_required
    def settings():
        if request.method == "POST":
            language = request.form.get("language", "en")
            if language not in TRANSLATIONS:
                abort(400)
            current_user.language = language
            current_user.language_onboarding_done = True
            db.session.commit()
            flash(TRANSLATIONS[language]["language_saved"], "success")
            response = redirect(url_for("settings"))
            response.set_cookie(
                "cropfarm_language",
                language,
                max_age=60 * 60 * 24 * 365,
                httponly=True,
                samesite="Lax",
                secure=request.is_secure,
            )
            response.set_cookie(
                "cropfarm_language_prompt",
                "done",
                max_age=60 * 60 * 24 * 365,
                httponly=True,
                samesite="Lax",
                secure=request.is_secure,
            )
            return response
        return render_template("settings.html", active_page="settings")

    @app.route("/help")
    @login_required
    def help_page():
        return render_template("help.html", active_page="help")

    @app.route("/admin")
    @login_required
    def admin_dashboard():
        if current_user.role != "admin":
            abort(403)
        return render_template(
            "admin.html",
            active_page="admin",
            user_count=User.query.count(),
            farm_count=Farm.query.count(),
            crop_count=Crop.query.count(),
            detection_count=DiseaseDetection.query.count(),
            users=User.query.order_by(User.created_at.desc()).limit(100).all(),
            model_available=model is not None,
        )

    @app.post("/admin/users/<int:user_id>/toggle")
    @login_required
    def admin_toggle_user(user_id):
        if current_user.role != "admin":
            abort(403)
        user = User.query.get_or_404(user_id)
        if user.id == current_user.id:
            flash("You cannot deactivate your own administrator account.", "error")
        else:
            user.is_active = not user.is_active
            db.session.commit()
            flash("Account status updated.", "success")
        return redirect(url_for("admin_dashboard"))

    @app.errorhandler(403)
    def forbidden(_error):
        return render_template("error.html", code=403), 403

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("error.html", code=404), 404

    return app


def _parse_date(value):
    if not value:
        return None
    return date.fromisoformat(value)


def _csv_safe(value):
    text = "" if value is None else str(value)
    if text.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + text
    return text


def _remove_file(path):
    resolved = os.path.realpath(path)
    allowed_roots = (
        os.path.realpath(os.path.join(BASE_DIR, "instance", "uploads")),
        os.path.realpath(os.path.join(BASE_DIR, "instance", "reports")),
    )
    if any(os.path.commonpath((root, resolved)) == root for root in allowed_roots):
        try:
            os.remove(resolved)
        except FileNotFoundError:
            pass


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def predict_disease(image_path):
    if model is None:
        raise RuntimeError("The crop disease model is unavailable.")
    image = tf.keras.utils.load_img(image_path, target_size=(128, 128))
    image_array = tf.keras.utils.img_to_array(image) / 255.0
    image_array = np.expand_dims(image_array, axis=0)
    predictions = model.predict(image_array, verbose=0)
    predicted_index = int(np.argmax(predictions[0]))
    disease_name = class_names[predicted_index]
    confidence = float(predictions[0][predicted_index]) * 100
    return disease_name, round(confidence, 2)


app = create_app()


if __name__ == "__main__":
    app.run(
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "5000")),
        debug=os.getenv("FLASK_DEBUG", "false").lower() == "true",
    )
