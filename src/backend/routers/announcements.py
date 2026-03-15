"""
Announcements endpoints for the High School Management System API
"""

from datetime import datetime
from fastapi import APIRouter, HTTPException, Query
from typing import Any, Dict, List, Optional

from bson import ObjectId

from ..database import announcements_collection, teachers_collection

router = APIRouter(
    prefix="/announcements",
    tags=["announcements"]
)


def _serialize(ann: dict) -> dict:
    """Convert a MongoDB document to a JSON-serializable dict."""
    ann["id"] = str(ann.pop("_id"))
    return ann


def _validate_dates(expires_at: str, starts_at: Optional[str]) -> None:
    """Validate date strings and their relative order."""
    try:
        expires_dt = datetime.strptime(expires_at, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid expiration date format. Use YYYY-MM-DD."
        )

    if starts_at:
        try:
            starts_dt = datetime.strptime(starts_at, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid start date format. Use YYYY-MM-DD."
            )
        if starts_dt > expires_dt:
            raise HTTPException(
                status_code=400,
                detail="Start date must be on or before expiration date."
            )


def _require_teacher(teacher_username: Optional[str]) -> None:
    """Raise 401 if the given teacher username is not authenticated."""
    if not teacher_username:
        raise HTTPException(
            status_code=401,
            detail="Authentication required for this action."
        )
    teacher = teachers_collection.find_one({"_id": teacher_username})
    if not teacher:
        raise HTTPException(
            status_code=401,
            detail="Invalid teacher credentials."
        )


@router.get("", response_model=List[Dict[str, Any]])
@router.get("/", response_model=List[Dict[str, Any]])
def get_active_announcements() -> List[Dict[str, Any]]:
    """
    Return all currently active announcements (public).

    An announcement is active when:
    - expires_at >= today, AND
    - starts_at is null/missing or starts_at <= today
    """
    today = datetime.now().strftime("%Y-%m-%d")
    query = {
        "expires_at": {"$gte": today},
        "$or": [
            {"starts_at": None},
            {"starts_at": {"$exists": False}},
            {"starts_at": ""},
            {"starts_at": {"$lte": today}},
        ],
    }
    return [_serialize(ann) for ann in announcements_collection.find(query).sort("expires_at", 1)]


@router.get("/all", response_model=List[Dict[str, Any]])
def get_all_announcements(
    teacher_username: Optional[str] = Query(None)
) -> List[Dict[str, Any]]:
    """
    Return all announcements regardless of status.
    Requires teacher authentication.
    """
    _require_teacher(teacher_username)
    return [_serialize(ann) for ann in announcements_collection.find().sort("expires_at", -1)]


@router.post("", response_model=Dict[str, Any])
def create_announcement(
    message: str,
    expires_at: str,
    starts_at: Optional[str] = None,
    teacher_username: Optional[str] = Query(None),
) -> Dict[str, Any]:
    """
    Create a new announcement.
    Requires teacher authentication.
    expires_at is required; starts_at is optional.
    """
    _require_teacher(teacher_username)
    _validate_dates(expires_at, starts_at or None)

    if not message or not message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")
    if len(message) > 500:
        raise HTTPException(status_code=400, detail="Message cannot exceed 500 characters.")

    doc = {
        "message": message.strip(),
        "expires_at": expires_at,
        "starts_at": starts_at or None,
        "created_by": teacher_username,
        "created_at": datetime.now().isoformat(),
    }
    result = announcements_collection.insert_one(doc)
    doc["id"] = str(result.inserted_id)
    doc.pop("_id", None)
    return doc


@router.put("/{announcement_id}", response_model=Dict[str, Any])
def update_announcement(
    announcement_id: str,
    message: str,
    expires_at: str,
    starts_at: Optional[str] = None,
    teacher_username: Optional[str] = Query(None),
) -> Dict[str, Any]:
    """
    Update an existing announcement.
    Requires teacher authentication.
    """
    _require_teacher(teacher_username)
    _validate_dates(expires_at, starts_at or None)

    if not message or not message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")
    if len(message) > 500:
        raise HTTPException(status_code=400, detail="Message cannot exceed 500 characters.")

    try:
        object_id = ObjectId(announcement_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid announcement ID.")

    update_fields = {
        "message": message.strip(),
        "expires_at": expires_at,
        "starts_at": starts_at or None,
    }
    result = announcements_collection.update_one(
        {"_id": object_id},
        {"$set": update_fields},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found.")

    updated = announcements_collection.find_one({"_id": object_id})
    return _serialize(updated)


@router.delete("/{announcement_id}", response_model=Dict[str, Any])
def delete_announcement(
    announcement_id: str,
    teacher_username: Optional[str] = Query(None),
) -> Dict[str, Any]:
    """
    Delete an announcement.
    Requires teacher authentication.
    """
    _require_teacher(teacher_username)

    try:
        object_id = ObjectId(announcement_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid announcement ID.")

    result = announcements_collection.delete_one({"_id": object_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found.")

    return {"message": "Announcement deleted successfully."}
