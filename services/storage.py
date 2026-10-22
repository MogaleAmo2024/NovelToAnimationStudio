import json
from pathlib import Path

OUT = Path("outputs")
UPLOADS = Path("uploads")


def _project_dir(project_id: str) -> Path:
    p = OUT / project_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def save_upload(project_id: str, filename: str, data: bytes) -> Path:
    d = UPLOADS / project_id
    d.mkdir(parents=True, exist_ok=True)
    path = d / filename
    path.write_bytes(data)
    return path


def save_json(project_id: str, name: str, obj) -> Path:
    path = _project_dir(project_id) / name
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_json(project_id: str, name: str):
    path = OUT / project_id / name
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))