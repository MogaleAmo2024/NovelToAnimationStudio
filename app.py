import uuid
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import asyncio

from services.jobs import (
    enqueue_episode_plan_job,
    enqueue_story_bible_job,
    get_job,
)
from services.image_gen import generate_scene_image
from services.video_maker import build_episode_video

# --- LOCAL STORAGE ---
UPLOADS = Path("uploads")
def save_upload(project_id: str, filename: str, data: bytes) -> Path:
    d = UPLOADS / project_id
    d.mkdir(parents=True, exist_ok=True)
    path = d / filename
    path.write_bytes(data)
    return path

app = FastAPI(title="Novel to Animation Studio")

app.mount("/outputs", StaticFiles(directory="outputs"), name="outputs")
app.mount("/static", StaticFiles(directory="static"), name="static")


class PlanRequest(BaseModel):
    project_id: str
    episode_count: int = 3


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        return "\n".join((p.extract_text() or "") for p in reader.pages)
    if suffix == ".docx":
        from docx import Document
        doc = Document(str(path))
        return "\n".join(p.text for p in doc.paragraphs)
    if suffix == ".txt":
        return path.read_text(encoding="utf-8", errors="ignore")
    raise HTTPException(400, f"Unsupported file type: {suffix}")


def extract_images_from_pdf(pdf_path: Path, project_id: str):
    """Extracts all images from the PDF using pypdf (No DLLs required)."""
    from pypdf import PdfReader
    
    dir_path = Path("outputs") / project_id / "assets" / "images"
    dir_path.mkdir(parents=True, exist_ok=True)
    
    reader = PdfReader(str(pdf_path))
    image_count = 0
    
    for page in reader.pages:
        for image_file_object in page.images:
            image_count += 1
            # pypdf extracts images as data chunks
            file_path = dir_path / f"book_img_{image_count}.png"
            with open(file_path, "wb") as fp:
                fp.write(image_file_object.data)
            
    print(f"Extracted {image_count} images from the PDF.")


@app.get("/")
def index():
    return FileResponse("static/index.html")


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    project_id = str(uuid.uuid4())
    data = await file.read()
    
    path = save_upload(project_id, file.filename, data)
    text = extract_text(path)
    
    # IF it's a PDF, try to extract images using pypdf
    if file.filename.lower().endswith(".pdf"):
        try:
            extract_images_from_pdf(path, project_id)
        except Exception as e:
            print(f"Could not extract images from PDF: {e}")
        
    job_id = enqueue_story_bible_job(project_id, text)
    
    return {
        "project_id": project_id,
        "filename": file.filename,
        "chars": len(text),
        "story_bible_job": job_id,
    }


@app.post("/api/create-episode-plan")
async def create_episode_plan(payload: PlanRequest):
    job_id = enqueue_episode_plan_job(payload.project_id, payload.episode_count)
    return {"job_id": job_id, "status": "queued"}


@app.get("/api/jobs/{job_id}")
async def job_status(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    return job


@app.post("/api/generate-scene-image")
async def generate_image(payload: dict):
    try:
        project_id = payload.get("project_id")
        ep_num = payload.get("episode_num")
        sc_num = payload.get("scene_num")
        prompt = payload.get("prompt")
        
        if not all([project_id, prompt]):
            raise HTTPException(400, "Missing project_id or prompt")
            
        file_path = generate_scene_image(project_id, ep_num, sc_num, prompt)
        
        return {"status": "success", "image_url": f"/outputs/{project_id}/assets/images/ep{ep_num}_sc{sc_num}.jpg"}
    except Exception as e:
        print(f"Image generation error: {e}")
        raise HTTPException(500, str(e))


@app.post("/api/build-video")
async def build_video(payload: dict):
    project_id = payload.get("project_id")
    episode_data = payload.get("episode")
    
    if not project_id or not episode_data:
        raise HTTPException(400, "Missing project_id or episode data")
        
    try:
        final_video_path = await build_episode_video(project_id, episode_data)
        
        if final_video_path:
            return {"status": "success", "video_url": f"/outputs/{project_id}/Episode_{episode_data['number']}.mp4"}
        else:
            raise Exception("Failed to build video. Missing images?")
            
    except Exception as e:
        print(f"Video build error: {e}")
        raise HTTPException(500, str(e))