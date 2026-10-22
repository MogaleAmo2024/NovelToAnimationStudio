import urllib.parse
import httpx
import time
from pathlib import Path

OUT = Path("outputs")

def generate_scene_image(project_id: str, episode_num: int, scene_num: int, prompt: str) -> str:
    # Stronger anime styling for consistent YouTube Shorts look
    style_prompt = (
        "anime keyframe, cinematic lighting, studio ghibli, makoto shinkai, "
        "highly detailed 2d illustration, vibrant colors, wide angle shot"
    )
    full_prompt = f"{prompt}, {style_prompt}"
    encoded_prompt = urllib.parse.quote(full_prompt)
    
    # PASTE YOUR POLLINATIONS TOKEN HERE IF YOU HAVE ONE (pk_...)
    TOKEN = "" 
    token_param = f"&token={TOKEN}" if TOKEN else ""
    
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1280&height=720&nologo=true{token_param}"
    
    dir_path = OUT / project_id / "assets" / "images"
    dir_path.mkdir(parents=True, exist_ok=True)
    file_path = dir_path / f"ep{episode_num}_sc{scene_num}.jpg"
    
    print(f"Generating anime image for Ep {episode_num}, Scene {scene_num}...")
    
    # Try 3 times to download the image
    with httpx.Client(timeout=60.0) as client:
        for attempt in range(3):
            try:
                response = client.get(url)
                response.raise_for_status()
                file_path.write_bytes(response.content)
                return str(file_path)
            except Exception as e:
                print(f"Attempt {attempt+1} failed: {e}. Retrying in 5 seconds...")
                time.sleep(5)
                
    raise Exception("Failed to generate image after 3 tries.")