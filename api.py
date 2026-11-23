from flask import Blueprint, abort, current_app, jsonify, request
from flask_login import current_user
from sqlalchemy import func
from werkzeug.exceptions import HTTPException

from extensions import db
from integrations.weather import (
    WeatherIntegrationError,
    get_irrigation_advisory,
    get_weather_report,
)
from models import (
    Crop,
    DiseaseDetection,
    Farm,
    Field,
    Notification,
    User,
)


api_v1 = Blueprint("api_v1", __name__, url_prefix="/api/v1")


@api_v1.before_request
def require_api_authentication():
    if not current_user.is_authenticated:
        return jsonify(error="authentication_required"), 401


@api_v1.errorhandler(HTTPException)
def api_http_error(error):
    return jsonify(error=error.name.lower().replace(" ", "_")), error.code


def _request_weather_report():
    location = current_user.location or ""
    if not location:
        return None, (jsonify(error="location_required"), 400)
    try:
        return get_weather_report(
            location,
            latitude=current_user.latitude,
            longitude=current_user.longitude,
            resolved_location=current_user.location,
        ), None
    except WeatherIntegrationError as error:
        if error.code in {"location_required", "invalid_location"}:
            status = 400
        elif error.code == "location_not_found":
            status = 404
        else:
            status = 503
        current_app.logger.warning("Weather API integration failed (%s).", error.code)
        return None, (jsonify(error=error.code), status)


@api_v1.get("/weather")
def weather():
    report, error_response = _request_weather_report()
    if error_response:
        return error_response
    return jsonify(report)


@api_v1.get("/irrigation/advisory")
def irrigation_advisory():
    report, error_response = _request_weather_report()
    if error_response:
        return error_response
    return jsonify(
        location=report["location"],
        advisory=get_irrigation_advisory(report),
        forecast=report["forecast"],
    )


@api_v1.get("/summary")
def summary():
    crops = Crop.query.filter_by(user_id=current_user.id)
    return jsonify(
        farms=Farm.query.filter_by(user_id=current_user.id).count(),
        fields=(
            Field.query.join(Farm).filter(Farm.user_id == current_user.id).count()
        ),
        crops=crops.count(),
        healthy=crops.filter(func.lower(Crop.health_status) == "healthy").count(),
        detections=DiseaseDetection.query.filter_by(user_id=current_user.id).count(),
        unread_notifications=Notification.query.filter_by(
            user_id=current_user.id, is_read=False
        ).count(),
    )


@api_v1.route("/farms", methods=["GET", "POST"])
def farms():
    if request.method == "POST":
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify(error="invalid_json"), 400
        name = str(payload.get("farm_name", "")).strip()
        location = str(payload.get("location", "")).strip()
        description = str(payload.get("description", "")).strip()
        try:
            size = float(payload["farm_size"]) if payload.get("farm_size") not in (None, "") else None
            if not name or len(name) > 120 or (size is not None and size <= 0):
                raise ValueError
        except (TypeError, ValueError):
            return jsonify(error="invalid_farm_details"), 400
        farm = Farm(
            user_id=current_user.id,
            farm_name=name,
            location=location or None,
            farm_size=size,
            description=description or None,
        )
        db.session.add(farm)
        db.session.commit()
        return jsonify(_farm_payload(farm)), 201

    records = (
        Farm.query.filter_by(user_id=current_user.id)
        .order_by(Farm.created_at.desc())
        .all()
    )
    return jsonify(items=[_farm_payload(record) for record in records])


@api_v1.get("/fields")
def fields():
    records = (
        Field.query.join(Farm)
        .filter(Farm.user_id == current_user.id)
        .order_by(Farm.farm_name, Field.field_name)
        .all()
    )
    return jsonify(
        items=[
            {
                "id": record.id,
                "farm_id": record.farm_id,
                "farm_name": record.farm.farm_name,
                "field_name": record.field_name,
                "area": record.area,
                "location": record.location,
                "assigned_crop": record.assigned_crop,
            }
            for record in records
        ]
    )


@api_v1.get("/crops")
def crops():
    records = (
        Crop.query.filter_by(user_id=current_user.id)
        .order_by(Crop.created_at.desc())
        .all()
    )
    return jsonify(
        items=[
            {
                "id": record.id,
                "farm_id": record.farm_id,
                "field_id": record.field_id,
                "crop_name": record.crop_name,
                "planting_date": record.planting_date.isoformat()
                if record.planting_date
                else None,
                "harvesting_date": record.harvesting_date.isoformat()
                if record.harvesting_date
                else None,
                "growth_stage": record.growth_stage,
                "health_status": record.health_status,
            }
            for record in records
        ]
    )


@api_v1.get("/detections")
def detections():
    page = max(request.args.get("page", 1, type=int) or 1, 1)
    per_page = min(max(request.args.get("per_page", 20, type=int) or 20, 1), 100)
    query = DiseaseDetection.query.filter_by(user_id=current_user.id)
    crop_name = request.args.get("crop", "").strip()
    disease = request.args.get("disease", "").strip()
    if crop_name:
        query = query.filter(DiseaseDetection.crop_name == crop_name)
    if disease:
        query = query.filter(DiseaseDetection.predicted_disease.ilike(f"%{disease}%"))
    pagination = query.order_by(DiseaseDetection.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    return jsonify(
        items=[
            {
                "id": record.unique_detection_id,
                "crop_name": record.crop_name,
                "predicted_disease": record.predicted_disease,
                "confidence_score": record.confidence_score,
                "created_at": record.created_at.isoformat(),
                "farm_id": record.farm_id,
                "field_id": record.field_id,
            }
            for record in pagination.items
        ],
        page=pagination.page,
        per_page=pagination.per_page,
        pages=pagination.pages,
        total=pagination.total,
    )


@api_v1.route("/notifications", methods=["GET"])
def notifications():
    records = (
        Notification.query.filter_by(user_id=current_user.id)
        .order_by(Notification.created_at.desc())
        .limit(100)
        .all()
    )
    return jsonify(
        items=[
            {
                "id": record.id,
                "title": record.title,
                "message": record.message,
                "type": record.notification_type,
                "is_read": record.is_read,
                "created_at": record.created_at.isoformat(),
            }
            for record in records
        ]
    )


@api_v1.patch("/notifications/<int:notification_id>")
def update_notification(notification_id):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or not isinstance(payload.get("is_read"), bool):
        return jsonify(error="is_read_boolean_required"), 400
    record = Notification.query.filter_by(
        id=notification_id, user_id=current_user.id
    ).first()
    if record is None:
        abort(404)
    record.is_read = payload["is_read"]
    db.session.commit()
    return jsonify(id=record.id, is_read=record.is_read)


@api_v1.get("/admin/summary")
def admin_summary():
    if current_user.role != "admin":
        abort(403)
    return jsonify(
        users=User.query.count(),
        farms=Farm.query.count(),
        crops=Crop.query.count(),
        detections=DiseaseDetection.query.count(),
    )


def _farm_payload(farm):
    return {
        "id": farm.id,
        "farm_name": farm.farm_name,
        "location": farm.location,
        "farm_size": farm.farm_size,
        "description": farm.description,
        "created_at": farm.created_at.isoformat(),
        "field_count": len(farm.fields),
    }
