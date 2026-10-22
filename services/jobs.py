import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor

from services.chunking import split_text
from services.llm import build_episode_plan, build_story_bible
from services.storage_supabase import load_json, save_json

_executor = ThreadPoolExecutor(max_workers=2)
_jobs: dict[str, dict] = {}


def _new_job(project_id: str, kind: str) -> str:
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {
        "job_id": job_id,
        "project_id": project_id,
        "kind": kind,
        "status": "queued",
        "stage": None,
        "progress": {"done": 0, "total": 0},
        "result": None,
        "error": None,
    }
    return job_id


def get_job(job_id: str) -> dict | None:
    return _jobs.get(job_id)


def enqueue_story_bible_job(project_id: str, text: str) -> str:
    job_id = _new_job(project_id, "story_bible")

    def run():
        try:
            _jobs[job_id]["status"] = "running"
            chunks = split_text(text)
            _jobs[job_id]["progress"]["total"] = len(chunks)
            
            print(f"--> [JOB {job_id}] Starting. Extracted {len(chunks)} chunks.")

            def cb(stage, done, total):
                _jobs[job_id]["stage"] = stage
                _jobs[job_id]["progress"] = {"done": done, "total": total}
                print(f"--> [JOB {job_id}] Progress: {stage} {done}/{total}")

            bible = build_story_bible(chunks, progress_cb=cb)
            
            print(f"--> [JOB {job_id}] Saving JSON to database...")
            save_json(project_id, "story_bible.json", bible)
            
            _jobs[job_id]["result"] = bible
            _jobs[job_id]["status"] = "done"
            print(f"--> [JOB {job_id}] DONE!")
            
        except Exception as e:
            _jobs[job_id]["status"] = "error"
            _jobs[job_id]["error"] = str(e)
            print(f"--> [JOB {job_id}] FAILED WITH ERROR: {e}")
            traceback.print_exc()

    _executor.submit(run)
    return job_id


def enqueue_episode_plan_job(project_id: str, episode_count: int = 3) -> str:
    job_id = _new_job(project_id, "episode_plan")

    def run():
        _jobs[job_id]["status"] = "running"
        try:
            print(f"--> [JOB {job_id}] Loading story bible for plan...")
            bible = load_json(project_id, "story_bible.json")
            if not bible:
                raise RuntimeError("story_bible.json missing — run story bible first")
                
            print(f"--> [JOB {job_id}] Generating episode plan...")
            plan = build_episode_plan(bible, episode_count)
            
            print(f"--> [JOB {job_id}] Saving plan to database...")
            save_json(project_id, "episode_plan.json", plan)
            
            _jobs[job_id]["result"] = plan
            _jobs[job_id]["status"] = "done"
            print(f"--> [JOB {job_id}] DONE!")
        except Exception as e:
            _jobs[job_id]["status"] = "error"
            _jobs[job_id]["error"] = str(e)
            print(f"--> [JOB {job_id}] FAILED WITH ERROR: {e}")
            traceback.print_exc()

    _executor.submit(run)
    return job_id