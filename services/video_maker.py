import asyncio
import edge_tts
import subprocess
import os
from pathlib import Path
from runapi.kling import KlingClient
from services.supabase_client import get_supabase

OUT = Path("outputs")

async def generate_audio(text: str, output_file: Path, voice: str = "en-US-ChristopherNeural"):
    """Generates AI voiceover using Microsoft Edge TTS (Free)."""
    print(f"🎙️ Generating voiceover...")
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(str(output_file))

def upload_image_to_supabase(image_path: Path, project_id: str) -> str:
    """Uploads the local image to Supabase to get a public URL for Kling."""
    sb = get_supabase()
    storage_path = f"{project_id}/anim_frame_{image_path.name}"
    
    with open(image_path, "rb") as f:
        image_bytes = f.read()
        
    sb.storage.from_("uploads").upload(
        storage_path,
        image_bytes,
        {"content-type": "image/png", "upsert": "true"}
    )
    
    public_url = sb.storage.from_("uploads").get_public_url(storage_path)
    return public_url

def animate_with_kling(image_url: str, output_path: Path, scene_description: str):
    """Sends the image to Kling 3.0 with a highly descriptive motion prompt."""
    print(f"✨ Sending image to Kling 3.0 for 3D animation...")
    
    client = KlingClient()
    
    # --- THE MOTION PROMPT ---
    # We combine the scene description with explicit movement instructions.
    # Kling needs to know WHAT moves, not just that it's a "3D animation".
    motion_prompt = (
        f"{scene_description}. "
        "The characters are breathing, blinking, and moving naturally. "
        "Subtle wind blowing through hair and clothes. "
        "Cinematic camera slowly pushing forward. High quality 3D animation style."
    )
    
    result = client.image_to_video.run(
        model="kling-3.0",
        image_url=image_url,
        prompt=motion_prompt,
        duration=5,
        # Adding a negative prompt stops Kling from keeping it too still
        negative_prompt="static, frozen, still image, blurry, deformed"
    )
    
    video_url = result.videos[0].url
    print(f"✅ Kling generated video. Downloading from CDN...")
    
    import httpx
    with httpx.Client(timeout=120.0) as http_client:
        response = http_client.get(video_url)
        response.raise_for_status()
        output_path.write_bytes(response.content)

def add_audio_to_video(video_path: Path, audio_path: Path, output_path: Path):
    """Combines the animated AI video with the voiceover."""
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-c:v", "libx264",
        "-c:a", "aac",
        "-shortest",
        str(output_path)
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

async def build_episode_video(project_id: str, episode_data: dict):
    ep_num = episode_data["number"]
    dir_path = OUT / project_id / "assets" / "videos"
    dir_path.mkdir(parents=True, exist_ok=True)
    img_dir = OUT / project_id / "assets" / "images"
    
    clips = []
    
    for scene in episode_data["scenes"]:
        sc_num = scene["number"]
        
        # 1. Figure out which image to use
        image_path = None
        book_img_num = scene.get("book_image_number", 0)
        
        if book_img_num > 0:
            for ext in ["png", "jpg", "jpeg"]:
                test_path = img_dir / f"book_img_{book_img_num}.{ext}"
                if test_path.exists():
                    image_path = test_path
                    print(f"📖 Using book image {book_img_num} for Scene {sc_num}")
                    break
        
        if not image_path:
            image_path = img_dir / f"ep{ep_num}_sc{sc_num}.jpg"
            if not image_path.exists():
                print(f"⚠️ Missing image for scene {sc_num}, skipping...")
                continue
            print(f"🎨 Using AI image for Scene {sc_num}")

        audio_path = dir_path / f"ep{ep_num}_sc{sc_num}.mp3"
        raw_video_path = dir_path / f"ep{ep_num}_sc{sc_num}_raw.mp4"
        final_scene_path = dir_path / f"ep{ep_num}_sc{sc_num}.mp4"
        
        # 2. Generate Voiceover
        text_to_speak = f"{scene.get('narration', '')}. {scene.get('script', '')}"
        if len(text_to_speak.strip()) < 5:
            text_to_speak = scene.get('visual_prompt', 'The story continues.')
        await generate_audio(text_to_speak, audio_path)
        
        # 3. Animate with Kling
        try:
            public_url = upload_image_to_supabase(image_path, project_id)
            
            # Get the visual prompt from your episode plan to give Kling context
            scene_desc = scene.get("visual_prompt", "The characters in the scene")
            
            animate_with_kling(public_url, raw_video_path, scene_desc)
            
        except Exception as e:
            print(f"❌ Kling Animation failed: {e}")
            print("Falling back to static image (no motion)...")
            cmd = ["ffmpeg", "-y", "-loop", "1", "-i", str(image_path), "-c:v", "libx264", "-t", "5", "-pix_fmt", "yuv420p", str(raw_video_path)]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # 4. Merge Audio and Video
        print(f"🎬 Merging audio and animated video for Scene {sc_num}...")
        add_audio_to_video(raw_video_path, audio_path, final_scene_path)
        clips.append(final_scene_path)
        
    # 5. Stitch all scenes together
    if clips:
        print(f"🔗 Stitching final video...")
        if len(clips) == 1:
            final_output = OUT / project_id / f"Episode_{ep_num}.mp4"
            import shutil
            shutil.copy(clips[0], final_output)
            return str(final_output)
            
        list_file = dir_path / f"ep{ep_num}_list.txt"
        with open(list_file, "w") as f:
            for clip in clips:
                f.write(f"file '{clip.name}'\n")
                
        final_output = OUT / project_id / f"Episode_{ep_num}.mp4"
        cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy", str(final_output)]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"✅ Finished! Video saved to: {final_output}")
        return str(final_output)
        
    return None