import os
import tempfile
import unittest
from datetime import datetime, timezone
from io import BytesIO
from unittest.mock import Mock, patch
from uuid import uuid4

from PIL import Image

import app as cropfarm_app
from extensions import db
from models import (
    Crop,
    DiseaseDetection,
    Farm,
    Field,
    IrrigationRecord,
    Notification,
    SoilReading,
    User,
)
from translations import format_localized_date


class CropFarmAppTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = self.temp_dir.name
        self.application = cropfarm_app.create_app(
            {
                "TESTING": True,
                "WTF_CSRF_ENABLED": False,
                "RATELIMIT_ENABLED": False,
                "SECRET_KEY": "test-key-not-for-production",
                "SQLALCHEMY_DATABASE_URI": f"sqlite:///{os.path.join(root, 'test.db')}",
                "AUTO_CREATE_DB": True,
                "UPLOAD_FOLDER": os.path.join(root, "uploads"),
                "REPORT_FOLDER": os.path.join(root, "reports"),
            }
        )
        self.client = self.application.test_client()
        with self.application.app_context():
            db.drop_all()
            db.create_all()

    def tearDown(self):
        with self.application.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()
        self.temp_dir.cleanup()

    def create_user(self, email="farmer@example.test", role="farmer"):
        user = User(full_name="Test Farmer", email=email, role=role)
        user.set_password("safe-password-123")
        db.session.add(user)
        db.session.commit()
        return user

    def sign_in(self, email="farmer@example.test"):
        return self.client.post(
            "/login",
            data={"email": email, "password": "safe-password-123"},
            follow_redirects=True,
        )

    def test_registration_hashes_password_and_opens_workspace(self):
        weather_report = {
            "provider": "Open-Meteo",
            "location": "Ambedkar Nagar, Uttar Pradesh, India",
            "timezone": "Asia/Kolkata",
            "latitude": 26.4045941,
            "longitude": 82.6065154,
            "current": {
                "time": "2026-11-24T00:00",
                "temperature_c": 16.7,
                "apparent_temperature_c": 16.0,
                "humidity_pct": 70,
                "precipitation_mm": 0,
                "wind_speed_kmh": 8,
                "condition": "Clear sky",
                "is_day": True,
            },
            "forecast": [],
            "details": {
                "icon": "☀",
                "rainfall_mm": 0,
                "pressure_hpa": 1008,
                "cloud_cover_pct": 0,
                "wind_direction_degrees": 180,
                "sunrise": "2026-11-24T06:20",
                "sunset": "2026-11-24T17:20",
                "last_updated": "2026-11-24T00:00",
            },
        }
        with patch("app.resolve_location", return_value={
            "latitude": 26.4045941,
            "longitude": 82.6065154,
            "location": "Ambedkar Nagar, Uttar Pradesh, India",
        }), patch("app.get_weather_report", return_value=weather_report):
            response = self.client.post(
                "/register",
                data={
                    "full_name": "A Farmer",
                    "email": "new-farmer@example.test",
                    "password": "secure-password-123",
                    "confirm_password": "secure-password-123",
                    "farm_name": "Green Acres",
                    "location": "Ambedkar Nagar, UP",
                },
                follow_redirects=True,
            )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"LOCAL CONDITIONS", response.data)
        with self.application.app_context():
            user = User.query.filter_by(email="new-farmer@example.test").one()
            self.assertNotEqual(user.password_hash, "secure-password-123")
            self.assertTrue(user.check_password("secure-password-123"))
            self.assertEqual(len(user.farms), 1)
            self.assertEqual(user.location, "Ambedkar Nagar, UP")
            self.assertEqual(user.latitude, 26.4045941)
            self.assertEqual(user.longitude, 82.6065154)

    def test_registration_requires_address(self):
        response = self.client.post(
            "/register",
            data={
                "full_name": "A Farmer",
                "email": "no-address@example.test",
                "password": "secure-password-123",
                "confirm_password": "secure-password-123",
            },
            follow_redirects=True,
        )
        self.assertIn(b"Enter a valid registered address.", response.data)
        with self.application.app_context():
            self.assertIsNone(
                User.query.filter_by(email="no-address@example.test").first()
            )

    def test_welcome_page_keeps_existing_product_overview_available(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Grow with confidence.", response.data)
        self.assertIn(b"languageDialog", response.data)
        self.assertIn(b"welcome-animation-config.js", response.data)
        self.assertIn(b"Background animation is not configured", response.data)
        self.assertIn(b'id="services"', response.data)
        self.assertIn(b'id="about"', response.data)
        self.assertIn(b'id="contact"', response.data)

        overview = self.client.get("/explore")
        self.assertEqual(overview.status_code, 302)
        self.assertTrue(overview.headers["Location"].endswith("/#services"))

        self.assertEqual(self.client.get("/privacy").status_code, 200)
        self.assertEqual(self.client.get("/terms").status_code, 200)

    def test_contact_form_requires_delivery_configuration_and_only_reports_delivery(self):
        response = self.client.get("/")
        self.assertIn(b"Contact delivery is not configured.", response.data)
        self.assertIn(b'disabled>Send message', response.data)

        unavailable = self.client.post(
            "/contact",
            data={
                "full_name": "A Farmer",
                "email": "farmer@example.test",
                "subject": "Question",
                "message": "I have a question about my farm records.",
            },
            follow_redirects=True,
        )
        self.assertIn(b"Contact delivery is unavailable", unavailable.data)
        self.assertNotIn(b"Your message was delivered", unavailable.data)

        self.application.config.update(
            SMTP_HOST="smtp.example.test",
            SMTP_PORT=587,
            SMTP_USER="mailer",
            SMTP_PASSWORD="test-password",
            MAIL_FROM="noreply@example.test",
            SUPPORT_EMAIL="support@example.test",
        )
        with patch("app.send_email_message") as send_message:
            invalid_subject = self.client.post(
                "/contact",
                data={
                    "full_name": "A Farmer",
                    "email": "farmer@example.test",
                    "subject": "Question\nBcc: attacker@example.test",
                    "message": "I have a question about my farm records.",
                },
                follow_redirects=True,
            )
            self.assertIn(b"Check the contact form fields", invalid_subject.data)
            send_message.assert_not_called()

            delivered = self.client.post(
                "/contact",
                data={
                    "full_name": "A Farmer",
                    "email": "farmer@example.test",
                    "subject": "Question",
                    "message": "I have a question about my farm records.",
                },
                follow_redirects=True,
            )
        self.assertIn(b"Your message was accepted by the configured email service.", delivered.data)
        sent_email, _settings = send_message.call_args.args
        self.assertEqual(sent_email["To"], "support@example.test")
        self.assertEqual(sent_email["Reply-To"], "farmer@example.test")

        with patch("app.send_email_message", side_effect=OSError("SMTP unavailable")):
            failed = self.client.post(
                "/contact",
                data={
                    "full_name": "A Farmer",
                    "email": "farmer@example.test",
                    "subject": "Question",
                    "message": "I have a question about my farm records.",
                },
                follow_redirects=True,
            )
        self.assertIn(b"Your message could not be delivered.", failed.data)
        self.assertNotIn(b"Your message was accepted", failed.data)

    def test_auth_password_controls_and_hindi_dashboard_labels_render(self):
        self.assertEqual(
            format_localized_date(datetime(2026, 11, 22), "hi"),
            "२२ नवंबर २०२६",
        )
        registration = self.client.get("/register")
        self.assertEqual(registration.status_code, 200)
        self.assertIn(b"data-password-toggle", registration.data)
        self.assertIn(b"Show password", registration.data)

        with self.application.app_context():
            user = self.create_user()
            user.language = "hi"
            user.language_onboarding_done = True
            db.session.add(
                DiseaseDetection(
                    unique_detection_id=str(uuid4()),
                    user_id=user.id,
                    crop_name="Tomato",
                    predicted_disease="Tomato_Early_blight",
                    confidence_score=88,
                    model_name="test model",
                    created_at=datetime(2026, 11, 22, tzinfo=timezone.utc),
                )
            )
            db.session.commit()
        self.sign_in()
        dashboard = self.client.get("/dashboard")
        self.assertEqual(dashboard.status_code, 200)
        self.assertIn("खेत का अवलोकन".encode(), dashboard.data)
        self.assertIn("एआई फसल स्कैनर".encode(), dashboard.data)
        self.assertIn("अंग्रेज़ी".encode(), dashboard.data)
        self.assertIn("टमाटर का अगेती झुलसा रोग".encode(), dashboard.data)
        self.assertIn("२२ नवंबर २०२६".encode(), dashboard.data)
        self.assertNotIn(b"Tomato_Early_blight", dashboard.data)

        scanner = self.client.get("/scanner")
        self.assertEqual(scanner.status_code, 200)
        self.assertIn("गैलरी".encode(), scanner.data)
        self.assertIn("कैमरा".encode(), scanner.data)
        self.assertIn("फसल स्वास्थ्य स्कैनर".encode(), scanner.data)

        settings = self.client.get("/settings")
        self.assertIn("सूरज/चाँद नियंत्रण".encode(), settings.data)
        profile = self.client.get("/profile")
        self.assertIn("आपका खाता".encode(), profile.data)
        notifications = self.client.get("/notifications")
        self.assertIn("सूचनाएँ".encode(), notifications.data)

    def test_guest_language_selection_persists_language_and_onboarding_cookie(self):
        response = self.client.post(
            "/set_language",
            data={"language": "hi", "onboarding_complete": "true"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"language": "hi", "saved": True})
        cookies = response.headers.getlist("Set-Cookie")
        self.assertTrue(any("cropfarm_language=hi" in cookie for cookie in cookies))
        self.assertTrue(
            any("cropfarm_language_prompt=done" in cookie for cookie in cookies)
        )
        self.assertTrue(any("HttpOnly" in cookie for cookie in cookies))

        welcome = self.client.get("/")
        self.assertIn(b'data-language="hi"', welcome.data)
        self.assertIn(b'data-language-prompt-done="true"', welcome.data)

    def test_english_is_the_initial_language_until_the_visitor_chooses(self):
        self.client.post("/set_language", data={"language": "hi"})
        welcome = self.client.get("/")
        self.assertIn(b'data-language="en"', welcome.data)
        self.assertIn(b'data-language-prompt-done="false"', welcome.data)

        registration = self.client.post(
            "/register",
            data={
                "full_name": "New Farmer",
                "email": "english-default@example.test",
                "password": "secure-password-123",
                "confirm_password": "secure-password-123",
            },
            follow_redirects=True,
        )
        self.assertEqual(registration.status_code, 200)
        with self.application.app_context():
            user = User.query.filter_by(email="english-default@example.test").one()
            self.assertEqual(user.language, "en")
            self.assertFalse(user.language_onboarding_done)

    def test_authenticated_language_selection_updates_account_preference(self):
        with self.application.app_context():
            user = self.create_user()
            user_id = user.id
        self.sign_in()

        response = self.client.post(
            "/set_language",
            data={"language": "bn", "onboarding_complete": "true"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        self.assertEqual(response.status_code, 200)
        with self.application.app_context():
            user = db.session.get(User, user_id)
            self.assertEqual(user.language, "bn")
            self.assertTrue(user.language_onboarding_done)

        settings = self.client.get("/settings")
        self.assertIn("বাংলা".encode(), settings.data)
        self.assertIn(b"English fallback", settings.data)

    def test_workspace_pages_render_and_guest_scanner_requires_login(self):
        guest_response = self.client.get("/scanner")
        self.assertEqual(guest_response.status_code, 302)
        self.assertIn("/login", guest_response.headers["Location"])
        with self.application.app_context():
            self.create_user()
        self.sign_in()
        for path in (
            "/dashboard",
            "/farms",
            "/fields",
            "/crops",
            "/crop-health",
            "/scanner",
            "/history",
            "/irrigation",
            "/soil",
            "/weather",
            "/analytics",
            "/reports",
            "/notifications",
            "/profile",
            "/settings",
            "/help",
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
        scanner_page = self.client.get("/scanner")
        drop_zone = scanner_page.data.split(b'id="dropZone"', 1)[1].split(
            b"</label>", 1
        )[0]
        self.assertIn(b'id="imagePreview"', drop_zone)
        self.assertIn(b'id="scannerLoading"', scanner_page.data)
        self.assertIn(
            "img-src 'self' data: blob:",
            scanner_page.headers["Content-Security-Policy"],
        )
        self.assertEqual(self.client.get("/admin").status_code, 403)

    def test_scanner_submission_without_image_shows_validation_message(self):
        with self.application.app_context():
            self.create_user()
        self.sign_in()

        response = self.client.post(
            "/scanner", data={}, content_type="multipart/form-data"
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Choose a crop image to analyze.", response.data)

    def test_dashboard_greeting_uses_time_labels_and_user_name(self):
        with self.application.app_context():
            self.create_user()
        self.sign_in()

        response = self.client.get("/dashboard")
        greeting_markup = response.data.split(
            b'id="dashboardGreeting"', 1
        )[1].split(b"</h1>", 1)[0]

        self.assertIn(b'data-name="Test Farmer"', greeting_markup)
        for period, greeting in (
            ("morning", "Good Morning!"),
            ("afternoon", "Good Afternoon!"),
            ("evening", "Good Evening!"),
            ("night", "Good Night!"),
        ):
            self.assertIn(
                f'data-{period}="{greeting}"'.encode(), response.data
            )
        self.assertIn(
            "Here’s the activity in your CropFarmAI workspace.".encode(),
            response.data,
        )

    def test_theme_preference_persists_and_workspace_shows_one_notification_link(self):
        with self.application.app_context():
            user = self.create_user()
            user_id = user.id
            db.session.add(
                Notification(
                    user_id=user_id,
                    title="Farm update",
                    message="A new crop record is available.",
                )
            )
            db.session.commit()
        self.sign_in()

        dashboard = self.client.get("/dashboard")
        self.assertEqual(dashboard.status_code, 200)
        self.assertIn(b'data-theme="day"', dashboard.data)
        self.assertIn(
            b'class="notification-count" aria-hidden="true">1</span>',
            dashboard.data,
        )
        self.assertEqual(dashboard.data.count(b'href="/notifications"'), 1)

        saved = self.client.post("/set-theme", data={"theme": "night"})
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json, {"saved": True, "theme": "night"})
        with self.application.app_context():
            user = db.session.get(User, user_id)
            self.assertEqual(user.theme, "night")

        night_dashboard = self.client.get("/dashboard")
        self.assertIn(b'data-theme="night"', night_dashboard.data)
        rejected = self.client.post("/set-theme", data={"theme": "dark"})
        self.assertEqual(rejected.status_code, 400)
        self.assertEqual(rejected.json["saved"], False)

    def test_workspace_preserves_right_to_left_language_direction(self):
        with self.application.app_context():
            user = self.create_user()
            user.language = "ur"
            db.session.commit()
        self.sign_in()

        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'<html lang="ur" dir="rtl"', response.data)

    def test_detection_is_saved_from_real_model_and_image_is_private(self):
        if cropfarm_app.model is None:
            self.skipTest("Bundled model is unavailable in this environment.")
        with self.application.app_context():
            owner = self.create_user()
            other = self.create_user("other@example.test")
            owner_id = owner.id
            other_id = other.id
        self.sign_in()
        image_bytes = BytesIO()
        Image.new("RGB", (128, 128), color=(42, 116, 52)).save(image_bytes, format="PNG")
        image_bytes.seek(0)
        response = self.client.post(
            "/scanner",
            data={"crop_image": (image_bytes, "leaf.png")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"ANALYSIS COMPLETE", response.data)
        self.assertIn(b"Disease detection overview", response.data)
        self.assertIn(b"Prediction confidence", response.data)
        self.assertIn(b"Possible causes", response.data)
        self.assertIn(b"Information not available", response.data)
        with self.application.app_context():
            detection = DiseaseDetection.query.filter_by(user_id=owner_id).one()
            self.assertIn(detection.predicted_disease, cropfarm_app.class_names.values())
            expected_health_status = (
                b"Healthy class predicted"
                if detection.predicted_disease.lower().endswith("healthy")
                else b"Non-healthy class predicted"
            )
            expected_health_dot = (
                b'class="health-dot health-good"'
                if detection.predicted_disease.lower().endswith("healthy")
                else b'class="health-dot health-risk"'
            )
            self.assertIn(expected_health_status, response.data)
            self.assertIn(expected_health_dot, response.data)
            self.assertGreaterEqual(detection.confidence_score, 0)
            self.assertLessEqual(detection.confidence_score, 100)
            self.assertEqual(len(detection.images), 1)
            image_path = detection.images[0].original_image_path
            detection_id = detection.unique_detection_id
            other_user = db.session.get(User, other_id)
            self.assertIsNotNone(other_user)
        other_client = self.application.test_client()
        other_client.post(
            "/login",
            data={"email": "other@example.test", "password": "safe-password-123"},
        )
        self.assertEqual(
            other_client.get(f"/uploads/{image_path}").status_code, 404
        )
        self.assertEqual(
            other_client.get(f"/history/{detection_id}").status_code, 404
        )
        report_response = self.client.get(
            f"/history/{detection_id}/report"
        )
        self.assertEqual(report_response.status_code, 200)
        report_response.close()
        analytics_response = self.client.get("/analytics?period=all")
        self.assertEqual(analytics_response.status_code, 200)

    def test_history_export_contains_only_signed_in_users_records(self):
        with self.application.app_context():
            owner = self.create_user()
            private_user = self.create_user("private@example.test")
            own_record = DiseaseDetection(
                unique_detection_id="fbb51c11-6427-4ab0-898f-a8f8de8d60d2",
                user_id=owner.id,
                crop_name="Tomato",
                predicted_disease="Tomato_healthy",
                confidence_score=91.0,
                model_name="test model",
                created_at=datetime.now(timezone.utc),
            )
            private_record = DiseaseDetection(
                unique_detection_id="ddc34c43-9772-4c11-af2a-80c50ccafc7f",
                user_id=private_user.id,
                crop_name="Potato",
                predicted_disease="Potato___Late_blight",
                confidence_score=88.0,
                model_name="test model",
            )
            db.session.add_all((own_record, private_record))
            db.session.commit()
        self.sign_in()
        response = self.client.get("/reports/detections.csv")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Tomato_healthy", response.data)
        self.assertNotIn(b"Potato___Late_blight", response.data)

    def test_farm_field_and_crop_records_are_user_scoped(self):
        with self.application.app_context():
            self.create_user()
        self.sign_in()
        response = self.client.post(
            "/farms",
            data={"farm_name": "North Farm", "location": "Valley", "farm_size": "4.5"},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        with self.application.app_context():
            farm = Farm.query.filter_by(farm_name="North Farm").one()
            farm_id = farm.id
        response = self.client.post(
            "/fields",
            data={"farm_id": str(farm_id), "field_name": "East Plot", "area": "1.25"},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        with self.application.app_context():
            field_id = Field.query.filter_by(field_name="East Plot").one().id
        response = self.client.post(
            "/crops",
            data={
                "farm_id": str(farm_id),
                "field_id": str(field_id),
                "crop_name": "Tomato",
                "health_status": "Healthy",
                "planting_date": "2026-01-02",
                "harvesting_date": "2026-04-02",
            },
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Tomato", response.data)

        other_client = self.application.test_client()
        with self.application.app_context():
            self.create_user("other@example.test")
        other_client.post(
            "/login",
            data={"email": "other@example.test", "password": "safe-password-123"},
        )
        self.assertEqual(
            other_client.post(f"/farms/{farm_id}/delete").status_code, 404
        )
        self.assertNotIn(b"North Farm", other_client.get("/farms").data)
        self.client.post(
            "/irrigation",
            data={
                "field_id": str(field_id),
                "irrigation_date": "2026-03-01",
                "water_quantity": "1.5",
                "schedule": "Morning",
            },
        )
        self.client.post(
            "/soil",
            data={
                "field_id": str(field_id),
                "moisture": "42",
                "ph_value": "6.7",
            },
        )
        self.client.post(f"/farms/{farm_id}/delete")
        with self.application.app_context():
            self.assertIsNone(Crop.query.filter_by(crop_name="Tomato").one().farm_id)
            self.assertIsNone(IrrigationRecord.query.one().field_id)
            self.assertIsNone(SoilReading.query.one().field_id)

    def test_post_requests_require_csrf_tokens(self):
        self.application.config["WTF_CSRF_ENABLED"] = True
        response = self.client.post("/set_language", data={"language": "en"})
        self.assertEqual(response.status_code, 400)

    def test_versioned_json_api_is_authenticated_and_user_scoped(self):
        guest_response = self.client.get("/api/v1/summary")
        self.assertEqual(guest_response.status_code, 401)
        self.assertEqual(guest_response.json["error"], "authentication_required")
        with self.application.app_context():
            owner = self.create_user()
            own_record = DiseaseDetection(
                unique_detection_id="fbb51c11-6427-4ab0-898f-a8f8de8d60d2",
                user_id=owner.id,
                crop_name="Tomato",
                predicted_disease="Tomato_healthy",
                confidence_score=91.0,
                model_name="test model",
            )
            db.session.add(own_record)
            self.create_user("other@example.test")
            db.session.commit()
        self.sign_in()
        summary = self.client.get("/api/v1/summary")
        self.assertEqual(summary.status_code, 200)
        self.assertEqual(summary.json["detections"], 1)
        created_farm = self.client.post(
            "/api/v1/farms",
            json={"farm_name": "API Farm", "farm_size": 2},
        )
        self.assertEqual(created_farm.status_code, 201)
        self.assertEqual(created_farm.json["farm_name"], "API Farm")

        other_client = self.application.test_client()
        other_client.post(
            "/login",
            data={"email": "other@example.test", "password": "safe-password-123"},
        )
        other_detections = other_client.get("/api/v1/detections")
        self.assertEqual(other_detections.status_code, 200)
        self.assertEqual(other_detections.json["total"], 0)
        self.assertEqual(other_client.get("/api/v1/admin/summary").status_code, 403)

    def test_weather_forecast_is_shared_by_page_irrigation_and_json_api(self):
        location = f"Weather Test {uuid4().hex}"
        with self.application.app_context():
            user = self.create_user()
            user.location = location
            db.session.commit()
        self.sign_in()

        geocoding_response = Mock()
        geocoding_response.json.return_value = {
            "results": [
                {
                    "name": location,
                    "country": "Test Country",
                    "latitude": 36.7,
                    "longitude": -119.8,
                }
            ]
        }
        geocoding_response.raise_for_status.return_value = None
        forecast_response = Mock()
        forecast_response.json.return_value = {
            "timezone": "America/Los_Angeles",
            "current": {
                "time": "2026-11-21T10:00",
                "temperature_2m": 19.4,
                "apparent_temperature": 18.8,
                "relative_humidity_2m": 58,
                "precipitation": 0.1,
                "weather_code": 2,
                "wind_speed_10m": 8.5,
                "is_day": 1,
            },
            "daily": {
                "time": [f"2026-11-{day:02d}" for day in range(21, 28)],
                "weather_code": [61, 2, 1, 0, 3, 2, 1],
                "precipitation_probability_max": [80, 10, 0, 0, 10, 20, 10],
                "precipitation_sum": [4.5, 0, 0, 0, 0.2, 0, 0],
                "et0_fao_evapotranspiration": [1.4, 2, 2.2, 3, 2.1, 1.8, 2],
            },
        }
        forecast_response.raise_for_status.return_value = None
        with patch(
            "integrations.weather.requests.get",
            side_effect=(geocoding_response, forecast_response),
        ) as provider_request:
            weather_page = self.client.get("/weather")
            self.assertEqual(weather_page.status_code, 200)
            self.assertIn(b"Weather Test", weather_page.data)
            self.assertIn(b"NEXT SEVEN DAYS", weather_page.data)
            self.assertEqual(provider_request.call_count, 2)

            weather_api = self.client.get("/api/v1/weather")
            self.assertEqual(weather_api.status_code, 200)
            self.assertEqual(weather_api.json["current"]["temperature_c"], 19.4)
            advisory_api = self.client.get("/api/v1/irrigation/advisory")
            self.assertEqual(advisory_api.status_code, 200)
            self.assertIn(b"Rain is forecast", advisory_api.data)
            irrigation_page = self.client.get("/irrigation")
            self.assertEqual(irrigation_page.status_code, 200)
            self.assertIn(b"Weather context", irrigation_page.data)
            self.assertEqual(provider_request.call_count, 2)

    def test_weather_api_requires_location_and_reports_unknown_places(self):
        with self.application.app_context():
            self.create_user()
        self.sign_in()
        missing_location = self.client.get("/api/v1/weather")
        self.assertEqual(missing_location.status_code, 400)
        self.assertEqual(missing_location.json["error"], "location_required")

        no_results = Mock()
        no_results.json.return_value = {"results": []}
        no_results.raise_for_status.return_value = None
        with patch("integrations.weather.requests.get", return_value=no_results):
            unknown_location = self.client.get(
                f"/api/v1/weather?location=Unknown-{uuid4().hex}"
            )
        self.assertEqual(unknown_location.status_code, 404)
        self.assertEqual(unknown_location.json["error"], "location_not_found")


if __name__ == "__main__":
    unittest.main()
