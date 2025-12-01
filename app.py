import json
import sqlite3
from uuid import uuid4
from pathlib import Path
from datetime import date
from download_sources import download_youtube, download_soundcloud
from query_sources import query_artist
import shutil
from sentence_transformers import SentenceTransformer
import platform
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import yaml
from utils.paths import get_project
import os

with open(get_project("O2O") / "config.yaml", 'r') as f:
    config = yaml.safe_load(f)


class MediaDataHandler:
    """
    Manages how the media files and data are stored.
    """
    def __init__(self, project_path):
        self.project_path = Path(project_path)
        self.data = self.project_path / "data"
        self.data.mkdir(parents=True, exist_ok=True)

        self.conn = sqlite3.connect(self.project_path / "data.db", check_same_thread=False)
        self.cur = self.conn.cursor()

        self.cur.executescript("""
            CREATE TABLE IF NOT EXISTS playlists (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL UNIQUE,
                thumbnail_file_name TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS playlist_media (
                row_id TEXT PRIMARY KEY,
                file_name TEXT NOT NULL,
                title TEXT,
                author TEXT,
                playlist_id TEXT,
                other_metadata JSON,
                FOREIGN KEY (playlist_id)
                    REFERENCES playlists (id)
                    ON DELETE SET NULL
                    ON UPDATE CASCADE
            );
        """)
        self.conn.commit()

        if not self.search("playlists", "title", "All Media"):
            self.create_playlist("All Media")

    def __del__(self):
        self.conn.close()

    def search(self, table, column, value):
        allowed_tables = {"playlist_media", "playlists"}
        allowed_columns = {"row_id", "file_name", "title", "author", "playlist_id", "other_metadata", "id", "thumbnail_file_name"}

        if column not in allowed_columns:
            raise ValueError(f"Invalid column: {column}")
        if table not in allowed_tables:
            raise ValueError(f"Invalid table: {table}")

        query = f"SELECT * FROM {table} WHERE {column} LIKE ?"
        self.cur.execute(query, (f"%{value}%",))
        rows = self.cur.fetchall()

        columns = [desc[0] for desc in self.cur.description]
        return [dict(zip(columns, row)) for row in rows]

    def search_all(self, value):
        tables = {"playlists", "playlist_media"}
        columns = {
            "playlist_media": ["row_id", "file_name", "title", "author", "playlist_id"],
            "playlists": ["id", "title", "thumbnail_file_name"]
        }

        results = {"playlists": [], "playlist_media": []}
        seen_ids = {"playlist_media": set(), "playlists": set()}

        for table in tables:
            for column in columns[table]:
                for item in self.search(table, column, value):
                    key = "row_id" if table == "playlist_media" else "id"
                    if item[key] not in seen_ids[table]:
                        results[table].append(item)
                        seen_ids[table].add(item[key])
        return results

    def upload_media(self, filepath, title='', author='', other_metadata=None):
        other_metadata = {} if not other_metadata else other_metadata
        row_id = str(uuid4())
        file_name = f"{str(uuid4())}{Path(filepath).suffix}"
        dest = self.data / file_name
        shutil.copy2(filepath, dest)

        self.cur.execute("""
            INSERT INTO playlist_media (
                row_id, file_name, title, author, playlist_id, other_metadata
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            row_id,
            file_name,
            title,
            author,
            self.search("playlists", "title", "All Media")[0]["id"],
            json.dumps(other_metadata)
        ))

        self.conn.commit()
        return row_id

    def move_upload_media(self, filepath, title='', author='', other_metadata=None):
        row_id = self.upload_media(filepath, title=title, author=author, other_metadata=other_metadata)
        os.remove(filepath)
        return row_id

    def add_media_to_playlist(self, playlist_id, row_id):
        data = self.search("playlist_media", "row_id", row_id)[0]
        new_row_id = str(uuid4())

        self.cur.execute("""
            INSERT INTO playlist_media (
                row_id, file_name, title, author, playlist_id, other_metadata
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            new_row_id,
            data['file_name'],
            data['title'],
            data['author'],
            playlist_id,
            data['other_metadata']
        ))
        self.conn.commit()
        return new_row_id

    def create_playlist(self, title="Untitled Playlist", thumbnail_file_name="defaultPlaylistThumbnail.jpg"):
        id = str(uuid4())

        def get_unique_title(title):
            if self.search("playlists", "title", title):
                title = f"{title} (1)"
                return get_unique_title(title)
            return title

        self.cur.execute("""
            INSERT INTO playlists (id, title, thumbnail_file_name)
            VALUES (?, ?, ?)
        """, (id, get_unique_title(title), thumbnail_file_name))
        self.conn.commit()
        return id

    def get_all_media(self):
        self.cur.execute("SELECT * FROM playlist_media")
        rows = self.cur.fetchall()
        columns = [desc[0] for desc in self.cur.description]
        return [dict(zip(columns, row)) for row in rows]

    def get_all_playlists(self):
        self.cur.execute("SELECT * FROM playlists")
        rows = self.cur.fetchall()
        columns = [desc[0] for desc in self.cur.description]
        return [dict(zip(columns, row)) for row in rows]

    # --- Added missing methods ---
    def list_matching_pairs(self, column, value):
        """Returns matching media rows by a specific column."""
        return self.search("playlist_media", column, value)

    def move_file(self, result):
        """Move downloaded file into data storage."""
        filepath = Path(result['filepath'])
        return self.move_upload_media(filepath, title=result.get('title', ''), author=result.get('artist', ''), other_metadata=result)


# -----------------------
class QueryTool:
    def __init__(self, data_handler, temp_dir=None):
        self.data_handler = data_handler
        os_name = platform.system()
        if os_name == "Linux":
            self.media_folder = Path(f"/dev/shm/{uuid4()}")
        else:
            if temp_dir:
                self.media_folder = Path(temp_dir) / str(uuid4())
            else:
                raise ValueError("Non-Linux OS detected. You must provide a temp_dir for media downloads.")
        self.media_folder.mkdir(parents=True, exist_ok=True)

    def download_result(self, result, skip_existing_result=True):
        skip_existing_result = result.get('skip_existing_result', skip_existing_result)
        existing = self.data_handler.list_matching_pairs("other_metadata", json.dumps({"link": result.get("link")}))

        if existing and skip_existing_result:
            print(f"Skipping result (already exists): {result['link']}")
            return

        if result["platform"] == "youtube":
            filepath = download_youtube(result["link"], self.media_folder, uuid4())
        else:
            filepath = download_soundcloud(result["link"], self.media_folder, uuid4())

        result["filepath"] = str(filepath)
        result["date_extracted"] = date.today().isoformat()

        self.data_handler.move_upload_media(
            filepath,
            title=result.get("title", ""),
            author=result.get("artist", ""),
            other_metadata=result
        )

        print(f"Downloaded: {result['title']}")

    def download_results(self, results, skip_existing_results=True):
        for result in results:
            self.download_result(result, skip_existing_results)
        return "Downloaded Results!"

    def review_results(self, results):
        approved = []
        for i, song in enumerate(results, 1):
            print(f"[{i}/{len(results)}] {song.get('title')} by {song.get('artist')}")
            choice = input("Approve (y), skip (n), edit (e)? ").strip().lower()
            if choice == "y":
                approved.append(song)
            elif choice == "e":
                song["title"] = input(f"New title [{song['title']}]: ") or song["title"]
                song["artist"] = input(f"New artist [{song['artist']}]: ") or song["artist"]
                approved.append(song)
        return approved

    def query_artist(self, artist_name, st_model, manual_review=True, max_results=400,
                     minimum_duration_seconds=60, maximum_duration_seconds=390,
                     filtered_substrings=["beat", "slowed", "reverb", "free"]):
        if manual_review:
            results = self.review_results(query_artist(self, artist_name, st_model, max_results,
                                                       minimum_duration_seconds, maximum_duration_seconds,
                                                       filtered_substrings))
        else:
            results = query_artist(self, artist_name, st_model, max_results,
                                   minimum_duration_seconds, maximum_duration_seconds,
                                   filtered_substrings)
        return results


# -----------------------
class YouTubeAccount:
    def __init__(self):
        self.SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]
        oauth = config['youtube_data_api_v3']['oauth']
        client_config = {
            "installed": {
                "client_id": oauth['id'],
                "client_secret": oauth['secret'],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost"]
            }
        }
        self.flow = InstalledAppFlow.from_client_config(client_config, self.SCOPES)
        self.credentials = self.flow.run_local_server(port=0, open_browser=True)
        self.youtube = build("youtube", "v3", credentials=self.credentials)

    def get_playlists(self):
        playlists = []
        request = self.youtube.playlists().list(part="id,snippet,contentDetails", mine=True, maxResults=50)
        response = request.execute()["items"]
        for playlist in response:
            playlists.append({
                "uuid": str(uuid4()),
                "kind": playlist["kind"],
                "title": playlist["snippet"]["title"],
                "youtubeId": playlist["id"],
                "link": f"https://www.youtube.com/playlist?list={playlist['id']}",
                "publishedAt": playlist["snippet"]["publishedAt"],
                "channelId": playlist["snippet"]["channelId"],
                "description": playlist["snippet"]["description"]
            })
        return playlists

    def get_playlist_videos(self, playlistJson):
        videos = []
        next_page_token = None
        while True:
            request = self.youtube.playlistItems().list(
                part="snippet,contentDetails",
                playlistId=playlistJson["youtubeId"],
                maxResults=50,
                pageToken=next_page_token
            )
            response = request.execute()

            for item in response.get("items", []):
                snippet = item["snippet"]
                videos.append({
                    "uuid": str(uuid4()),
                    "videoId": snippet["resourceId"]["videoId"],
                    "title": snippet["title"],
                    "playlistId": playlistJson['youtubeId'],
                    "link": f"https://www.youtube.com/watch?v={snippet['resourceId']['videoId']}"
                })

            next_page_token = response.get("nextPageToken")
            if not next_page_token:
                break

        return videos

if __name__ == "__main__":

    def ui():
        inputs = {
            "path": input("Type O2O-dedicated path: ").strip(),
            "use": ""
        }

        print("1 = Query discography from artist query")
        print("2 = Download discography from artist query")
        print("3 = Download a YouTube channel's playlists' videos")
        print("4 = Download a YouTube video to export")

        inputs["use"] = int(input("Type the option to perform the associated function: ").strip())

        data_handler = MediaDataHandler(inputs['path'])
        print(data_handler.get_all_media())

        qt = QueryTool(data_handler)
        st_model = SentenceTransformer("all-MiniLM-L6-v2")

        if inputs['use'] == 1:
            qt.query_artist(
                artist_name=input("Type in the artist name: ").strip(),
                st_model=st_model,
                manual_review=input("Type 'Y' to manually review each song, or 'N' to not: ").strip().upper() == 'Y',
                max_results=int(input("Type in the maximum amount of songs to query: ").strip()),
                minimum_duration_seconds=int(input("Type in the minimum duration in seconds to query: ").strip()),
                maximum_duration_seconds=int(input("Type in the maximum duration in seconds to query: ").strip())
            )

        elif inputs['use'] == 2:
            artist_name = input("Type in the artist name: ").strip()
            manual_review = input("Type 'Y' to manually review each song, or 'N' to not: ").strip().upper() == 'Y'
            results = qt.query_artist(artist_name, st_model, manual_review=manual_review)
            qt.download_results(results)

        elif inputs['use'] == 3:
            proceed = input("Type 'Y' to proceed, 'N' to exit: ").strip().upper() == 'Y'
            if proceed:
                yt = YouTubeAccount()
                playlists = yt.get_playlists()
                videos = [v for playlist in playlists for v in yt.get_playlist_videos(playlist)]
                for video in videos:
                    print(f"Processing: {video['title']}")
                    video_fp = download_youtube(video['link'], data_handler.project_path, video['title'])
                    data_handler.move_upload_media(video_fp, title=video['title'])
                    print("Processed!")
            else:
                return ui()

        elif inputs['use'] == 4:
            link = input("Enter the video link: ").strip()
            output_dir = input("Enter the directory to save the video (leave blank for default): ").strip() or None
            file_name = input("Enter what the file should be named (leave blank for default): ").strip() or None
            video_fp = download_youtube(link, output_dir, file_name)
            data_handler.move_upload_media(video_fp, title=file_name or Path(video_fp).stem)

    ui()
