import json
from services.supabase_client import get_supabase

UPLOADS_BUCKET = "uploads"
OUTPUTS_TABLE = "project_files"


def save_upload(project_id: str, filename: str, data: bytes) -> str:
    """Upload a file to the 'uploads' Storage bucket. Returns the storage path."""
    sb = get_supabase()
    path = f"{project_id}/{filename}"
    
    # Note: "upsert" MUST be the string "true", not boolean True, 
    # because it is sent as an HTTP header.
    sb.storage.from_(UPLOADS_BUCKET).upload(
        path,
        data,
        {"content-type": "application/octet-stream", "upsert": "true"},
    )
    return path


def save_json(project_id: str, name: str, obj) -> str:
    """Store a JSON document as a row in project_files. Returns a path-like key."""
    sb = get_supabase()
    sb.table(OUTPUTS_TABLE).upsert(
        {
            "project_id": project_id,
            "name": name,
            "data": obj,
        },
        on_conflict="project_id,name",
    ).execute()
    return f"{project_id}/{name}"


def load_json(project_id: str, name: str):
    """Fetch a JSON document by (project_id, name). Returns None if not found."""
    sb = get_supabase()
    res = (
        sb.table(OUTPUTS_TABLE)
        .select("data")
        .eq("project_id", project_id)
        .eq("name", name)
        .limit(1)
        .execute()
    )
    if not res.data:
        return None
    return res.data[0]["data"]