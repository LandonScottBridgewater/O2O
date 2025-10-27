import json
import sqlite3
from uuid import uuid4
from pathlib import Path
from datetime import date
from download_sources import download_youtube, download_soundcloud
from query_sources import query_artist
import shutil
from sentence_transformers import SentenceTransformer

class DataHandler:
    def __init__(self, project_path):
        project_path = Path(project_path)
        self.data = project_path / "data"
        self.data.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(project_path / "data.db")
        self.cur = self.conn.cursor()
        self.cur.execute("""
            CREATE TABLE IF NOT EXISTS files (
                id TEXT PRIMARY KEY,
                metadata JSON
            )
        """)
        self.conn.commit()

    def __del__(self):
        if hasattr(self, "conn"):
            self.conn.close()

    def search(self, id):
        row = self.cur.execute("SELECT metadata FROM files WHERE id = ?", (id,)).fetchone()
        return json.loads(row[0]) if row else None

    def generate_id(self):
        id = str(uuid4())
        if self.search(id):
            return self.generate_id()
        return id

    def add_file(self, metadata):
        if "filepath" not in metadata or not metadata["filepath"]:
            raise KeyError("Metadata must include a valid 'filepath'.")

        id = self.generate_id()
        original_path = Path(metadata["filepath"])
        new_file = self.data / f"{id}{original_path.suffix}"
        shutil.copy(original_path, new_file)
        metadata["filepath"] = str(new_file)

        self.cur.execute(
            "REPLACE INTO files (id, metadata) VALUES (?, ?)",
            (id, json.dumps(metadata))
        )
        self.conn.commit()
        return id

    def move_file(self, metadata):
        original_path = Path(metadata["filepath"])
        if not original_path.exists():
            # try .mp3 fallback if yt-dlp converted the file
            alt_path = original_path.with_suffix(".mp3")
            if alt_path.exists():
                original_path = alt_path
            else:
                print(f"⚠️ Skipping missing file: {metadata['filepath']}")
                return

        new_file = self.data / f"{uuid4()}{original_path.suffix}"

        try:
            shutil.move(str(original_path), str(new_file))
        except OSError:
            # cross-device move — fall back to copy+unlink
            shutil.copy2(str(original_path), str(new_file))
            original_path.unlink(missing_ok=True)

        metadata["filepath"] = str(new_file)

        self.cur.execute(
            "REPLACE INTO files (id, metadata) VALUES (?, ?)",
            (self.generate_id(), json.dumps(metadata))
        )
        self.conn.commit()
        return "File transferred!"


    def delete_file(self, id):
        metadata = self.search(id)
        if not metadata:
            return

        file_path = Path(metadata["filepath"])
        if file_path.exists():
            file_path.unlink()

        self.cur.execute("DELETE FROM files WHERE id = ?", (id,))
        self.conn.commit()
        return "File Deleted."
    
    def delete_files(self, ids):
        for id in ids:
            self.delete_file(id)

    def list_matching_pairs(self, key, value):
        query = f"SELECT id, metadata FROM files WHERE json_extract(metadata, '$.{key}') = ?"
        rows = self.cur.execute(query, (value,)).fetchall()
        return [(row[0], json.loads(row[1])) for row in rows]

    def list_matching_keys(self, key: str):
        query = f"SELECT id, metadata FROM files WHERE json_extract(metadata, '$.{key}') IS NOT NULL"
        rows = self.cur.execute(query).fetchall()
        return [(row[0], json.loads(row[1])) for row in rows]

    def list_matching_values(self, value: str):
        query = "SELECT id, metadata FROM files WHERE metadata LIKE ?"
        rows = self.cur.execute(query, (f"%{value}%",)).fetchall()
        return [(row[0], json.loads(row[1])) for row in rows]

    def list_all_files(self):
        rows = self.cur.execute("SELECT id, metadata FROM files").fetchall()
        return [(row[0], json.loads(row[1])) for row in rows]

    def export_metadata_to_json(self):
        raw_data = self.list_all_files()
        processed_data = {}
        for song in raw_data:
            processed_data[song[0]] = song[1]

        with open(Path(project) / "metadata_info.json", "w") as f:
            json.dump(processed_data,f,indent=4)


    def update_metadata(self, id, new_metadata: dict):
        existing = self.search(id)
        if not existing:
            raise KeyError(f"No file found for id: {id}")

        existing.update(new_metadata)
        self.cur.execute(
            "REPLACE INTO files (id, metadata) VALUES (?, ?)",
            (id, json.dumps(existing))
        )
        self.conn.commit()
        return existing
    
    def add_metadata(self, id, new_data):
        metadata = self.search(id)
        metadata.update(new_data)
        self.update_metadata(id, metadata)


class MediaDownloader:
    def __init__(self, data_handler):
        self.data_handler = data_handler
        self.media_folder = Path(f"dev/shm/{uuid4()}")
        self.media_folder.mkdir(parents=True, exist_ok=True)

    def review_queries(self, songs):
        print(f"\nFound {len(songs)} candidate songs:")
        approved = []

        for i, song in enumerate(songs, 1):
            print(f"\n[{i}/{len(songs)}]")
            print(f"Title: {song.get('title')}")
            print(f"Artist: {song.get('artist')}")
            print(f"Link: {song.get('link')}")
            print(f"Platform: {song.get('platform')}")
            choice = input("Approve (y), skip (n), or edit (e)? [y/n/e]: ").strip().lower()

            if choice == "y":
                approved.append(song)
            elif choice == "e":
                song["title"] = input(f"New title [{song['title']}]: ") or song["title"]
                song["artist"] = input(f"New artist [{song['artist']}]: ") or song["artist"]
                approved.append(song)
            else:
                print("Skipped.")

        return approved


    def download_artist(self, artist_name, st_model, manual_review=True):

        if manual_review:
            songs = self.review_queries(query_artist(artist_name, st_model))
        else:
            songs = query_artist(artist_name, st_model)

        for song in songs:
            existing = self.data_handler.list_matching_pairs("link", song["link"])
            if existing:
                print(f"Skipping (already exists): {song['link']}")
                continue

            if song["platform"] == "youtube":
                filepath = download_youtube(song["link"], self.media_folder, uuid4())
            else:
                filepath = download_soundcloud(song["link"], self.media_folder, uuid4())

            song["filepath"] = str(filepath)
            song["date_extracted"] = date.today().isoformat()

            self.data_handler.move_file(song)

        return "Complete!"

if __name__ == '__main__':

    project = input("type path:").strip()
    artist = input("type artist:").strip()
  
    data_handler = DataHandler(project)

    print(data_handler.list_all_files())

    media_dl = MediaDownloader(data_handler)

    st_model = SentenceTransformer("all-MiniLM-L6-v2")

    media_dl.download_artist(artist, st_model, manual_review=False)
