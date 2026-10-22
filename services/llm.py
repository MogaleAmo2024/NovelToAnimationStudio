import json
import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    api_key=os.environ.get("OPENROUTER_API_KEY", ""),
    base_url="https://openrouter.ai/api/v1",
)
MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/free")

def _parse_json(text: str) -> dict:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("```", 2)[1]
        if t.lower().startswith("json"):
            t = t[4:]
        t = t.strip()
    return json.loads(t)

def _chat_json(system: str, user: str, retries: int = 2) -> dict:
    last_err = None
    for attempt in range(retries + 1):
        print(f"--> [LLM] Calling {MODEL} (Attempt {attempt+1})...")
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
            raw = resp.choices[0].message.content
            return _parse_json(raw)
        except Exception as e:
            last_err = e
            print(f"--> [LLM] ERROR: {e}")
            system = system + " Return ONLY the JSON object, no markdown fences."
            
    raise RuntimeError(f"LLM failed after {retries} retries. Last error: {last_err}")


# ---------- Story Bible ----------
CHUNK_SYSTEM = "You are a literary analyst extracting structured data from a novel chunk."
CHUNK_USER = """Extract entities and events from this chunk of a novel.
Return JSON:
{{
  "characters": [{{"name": string, "aliases": [string], "role": string, "description": string, "appearance": string}}],
  "locations": [{{"name": string, "description": string}}],
  "events": [string],
  "key_dialogue": [{{"speaker": string, "line": string}}],
  "tone": string
}}
CHUNK:
---
{chunk}
---
"""
def extract_chunk(chunk: str) -> dict:
    return _chat_json(CHUNK_SYSTEM, CHUNK_USER.format(chunk=chunk))

REDUCE_SYSTEM = "You merge structured story extractions into a single coherent story bible."
REDUCE_USER = """Merge these extractions into one story bible.
Return JSON:
{{
  "title_guess": string,
  "logline": string,
  "genre": string,
  "themes": [string],
  "characters": [{{"name": string, "aliases": [string], "role": string, "description": string, "appearance": string}}],
  "locations": [{{"name": string, "description": string}}],
  "plot_beats": [string],
  "key_dialogue": [{{"speaker": string, "line": string}}]
}}
EXTRACTIONS:
{extractions}
"""
def merge_extractions(extractions: list[dict]) -> dict:
    return _chat_json(REDUCE_SYSTEM, REDUCE_USER.format(extractions=json.dumps(extractions, ensure_ascii=False)))

def build_story_bible(chunks: list[str], progress_cb=None) -> dict:
    total = len(chunks)
    extractions = []
    for i, chunk in enumerate(chunks):
        if progress_cb:
            progress_cb("map", i, total)
        try:
            extractions.append(extract_chunk(chunk))
        except Exception as e:
            print(f"--> [LLM] Chunk {i} failed: {e}")
            extractions.append({"characters": [], "locations": [], "events": [], "key_dialogue": [], "tone": ""})

    if progress_cb:
        progress_cb("reduce", total, total + 1)

    if len(extractions) <= 5:
        bible = merge_extractions(extractions)
    else:
        batched = [merge_extractions(extractions[i:i + 5]) for i in range(0, len(extractions), 5)]
        bible = merge_extractions(batched)

    if progress_cb:
        progress_cb("done", total + 1, total + 1)
    return bible

# ---------- Episode Planning ----------
PLAN_SYSTEM = "You are a showrunner adapting a novel into an animated series."
PLAN_USER = """Using this story bible, produce an episode plan as JSON:
{{
  "series_title": string,
  "episode_count": int,
  "episodes": [
    {{
      "number": int,
      "title": string,
      "summary": string,
      "scenes": [
        {{
          "number": int,
          "setting": string,
          "characters": [string],
          "script": string,
          "visual_prompt": "Description of the scene",
          "book_image_number": int,
          "narration": string
        }}
      ]
    }}
  ]
}}
Produce exactly {episode_count} episodes. Each episode should have 3–6 scenes.
Assign a "book_image_number" (1, 2, 3...) to each scene based on the order of events in the story. If this is a standard novel without pictures, just output 0.
STORY BIBLE:
{bible}
"""
def build_episode_plan(story_bible: dict, episode_count: int = 3) -> dict:
    return _chat_json(
        PLAN_SYSTEM,
        PLAN_USER.format(bible=json.dumps(story_bible, ensure_ascii=False), episode_count=episode_count)
    )