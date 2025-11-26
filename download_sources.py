import os
from pathlib import Path
import yt_dlp
from utils.paths import get_project

def download_youtube(url, output_parent_dir, file_name=None):
    '''
    Returns filepath of media
    '''
    os.makedirs(output_parent_dir, exist_ok=True)

    outtmpl = str(output_parent_dir / (str(file_name) or "%(title)s.%(ext)s"))

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': outtmpl,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'quiet': False,
        'cookiefile': str(get_project("O2O") / "cookies.txt"),
        'keepvideo':True
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        print(f"Downloading: {url}")
        info = ydl.extract_info(url, download=True)
        # Get final filename
        filepath = ydl.prepare_filename(info)
        # If postprocessor changed extension, replace it
        if 'ext' in info and info.get('postprocessed', False):
            base, _ = os.path.splitext(filepath)
            filepath = base + ".mp3"
    print("Complete.")
    return filepath

def download_soundcloud(url, output_parent_path, file_name=None):
    '''
    Returns filepath of media
    '''
    os.makedirs(output_parent_path, exist_ok=True)

    outtmpl = str(output_parent_path / (str(file_name) or "%(title)s.%(ext)s"))

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': outtmpl,
        'quiet': False,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        print(f"Downloading: {url}")
        info = ydl.extract_info(url, download=True)
        filepath = ydl.prepare_filename(info)
    print("Complete.")
    return filepath


if __name__ == "__main__":

    choice = input("Youtube or SoundCloud? Type Y for Youtube & S for Soundcloud: ").strip().lower()
    output_path = Path(input("Enter download folder: ").strip())
    output_path.mkdir(parents=True, exist_ok=True)

    if choice == "y":
        url = input("Enter a YouTube URL: ").strip()
        file_path = download_youtube(url, output_path)
    elif choice == "s":
        url = input("Enter a SoundCloud URL: ").strip()
        file_path = download_soundcloud(url, output_path)
    
    print(file_path)