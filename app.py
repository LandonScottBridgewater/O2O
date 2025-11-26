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


with open(get_project("O2O") / "config.yaml", 'r') as f:
    config = yaml.safe_load(f)
 
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

    def add_file(self, metadata, filepath=None):
        '''
        Copies file from file path to new file path in data structure of DataHandler.
        '''
        if "filepath" not in metadata or not metadata["filepath"] or not filepath:
            raise KeyError("Metadata must include a valid 'filepath'.")

        id = self.generate_id()
        original_path = Path(filepath or metadata["filepath"])
        new_file = self.data / f"{id}{original_path.suffix}"
        shutil.copy(original_path, new_file)
        metadata["filepath"] = str(new_file)
        metadata["id"] = id

        self.cur.execute(
            "REPLACE INTO files (id, metadata) VALUES (?, ?)",
            (id, json.dumps(metadata))
        )
        self.conn.commit()
        return id

    def move_file(self, metadata, filepath=None):
        '''
        Moves file from file path to new file path in data structure of DataHandler.
        '''
        original_path = Path(filepath or metadata["filepath"])
        if not original_path.exists():
            alt_path = original_path.with_suffix(".mp3")
            if alt_path.exists():
                original_path = alt_path
            else:
                print(f"⚠️ Skipping missing file: {metadata['filepath']}")
                return
            
        id = metadata.get("id") or self.generate_id()

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
            (id, json.dumps(metadata))
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

        with open(self.data / "metadata_info.json", "w") as f:
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
        metadata = self.search(id) or {}
        metadata.update(new_data)
        self.update_metadata(id, metadata)

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
        ''''
        skip_existing_result can be passed in user input or in the result data as a boolean under the key 'skip_existing_result'.
        
        Result data parameters will override function parameters.
        '''

        existing = self.data_handler.list_matching_pairs("link", result["link"])

        if result['skip_existing_result']:
            skip_existing_result = result['skip_existing_result']

        if existing and skip_existing_result:
            print(f"Skipping result. (already exists): {result['link']}")
            return

        if result["platform"] == "youtube":
            filepath = download_youtube(result["link"], self.media_folder, uuid4())
        else:
            filepath = download_soundcloud(result["link"], self.media_folder, uuid4())

        result["filepath"] = str(filepath)
        result["date_extracted"] = date.today().isoformat()

        self.data_handler.move_file(result)

        return f"Downloaded: {result}"
    
    def download_results(self,results, skip_existing_results=True):
        for result in results:
            self.download_result(result,skip_existing_results)
        return "Downloaded Results!"
    
    def review_results(self, results):
        print(f"\nFound {len(results)} candidate songs:")
        approved = []

        for i, song in enumerate(results, 1):
            print(f"\n[{i}/{len(results)}]")
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
    
    def compare_results(self):
        pass

    def query_artist(self, 
                     artist_name, 
                     st_model, 
                     manual_review=True, 
                     max_results=400, 
                     minimum_duration_seconds=60,
                     maximum_duration_seconds=390,
                     filtered_substrings=["beat", "slowed", "reverb", "free"]):

        if manual_review:
            results = self.review_results(query_artist(self, 
                     artist_name, 
                     st_model,
                     max_results=max_results, 
                     minimum_duration_seconds=minimum_duration_seconds,
                     maximum_duration_seconds=maximum_duration_seconds,
                     filtered_substrings=filtered_substrings))
        else:
            results = query_artist(self, 
                     artist_name, 
                     st_model,
                     max_results=max_results, 
                     minimum_duration_seconds=minimum_duration_seconds,
                     maximum_duration_seconds=maximum_duration_seconds,
                     filtered_substrings=filtered_substrings)
            
        return results

    def query_for_single_ugc(self, st_model, query):
        pass

    def query_movie(self,query):
        pass

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
        # in the future, implement pagination for support past
        # the max. of 50 playlists for a user
        playlists = []

        request = self.youtube.playlists().list(
            part="id,snippet,contentDetails",
            mine=True,
            maxResults=50
        )
        response = request.execute()["items"]
        
        for playlist in response:
            playlists.append({
                "uuid": uuid4(),
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
        """
        Fetch all videos from a given YouTube playlist. 

        Minimal metadata gathered for basic usage.

        Args:
            playlist_id (str): The YouTube playlist ID.

        Returns:
            List[dict]: A list of videos with metadata (title, videoId, link, publishedAt, etc.).
        """

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
                content_details = item["contentDetails"]
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

with open(get_project("O2O") / "data_m.json","w") as f:
    json.dump(YouTubeAccount().get_playlists(),f,indent=4)

if __name__ == '__main__':

    def ui():

        inputs = {
            "path":input("type O2O-dedicated path:").strip(),
            "use":""
            }
        print("1 = Query discography from artist query")
        print("2 = download discography from artist query")
        print("3 = Download a YouTube channel's playlists' videos")
        print("4 = Download a YouTube video")

        inputs["use"] = int(input("type the option to preform the associated function:").strip())

        data_handler = DataHandler(inputs['path'])
        print(data_handler.list_all_files())

        qt = QueryTool(data_handler)
        st_model = SentenceTransformer("all-MiniLM-L6-v2")

        if inputs['use'] == 1: # query discography from artist query
            qt.query_artist(artist_name=input("type in the artist name:").strip(),
                            st_model=st_model,
                            manual_review=input("Type 'Y' to manually review each song, or 'N' to not:").strip() == 'Y',
                            max_results=int(input('type in the maximum amount of songs to query:').strip()),
                            minimum_duration_seconds=int(input('type in the minimum duration in seconds to query:').strip()),
                            maximum_duration_seconds=int(input('type in the maximum duration in seconds to query:').strip()))

        elif inputs['use'] == 2: # download discography from artist query
            results = qt.query_artist(inputs["artist"], 
                                    st_model, 
                                    manual_review=inputs["manual_review"])
            qt.download_results(results)
        elif inputs["use"] == 3:
            print("This option 3 downloads the videos of all your YouTube channel's playlists.")

            to_proceed = input("type 'Y' to proceed, type 'N' to exit:").strip() == 'Y'
            have_prints = input("type 'Y' to have console print the processes being ran, or type 'N' for it to not:").strip() == 'Y' 

            if to_proceed:

                yt = YouTubeAccount()

                print('Querying playlists...') if have_prints else None
                playlists = yt.get_playlists()

                videos = []
                for playlist in playlists:
                    videos.append(yt.get_playlist_videos(playlist))
                    
                print('Queried playlists!') if have_prints else None
                for video in videos:
                    print(f'Processing {video} ...')
                    video_fp = download_youtube(url=video["link"],
                                        output_parent_dir=data_handler.project_path,
                                        file_name=video["title"]
                                        )
                    data_handler.move_file(video,video_fp)
                    print('Processed!')
            else:
                ui()
        elif inputs["use"] == 4:
            link = input("Enter the video link:").strip()
            print("Leave blank to default to Downloads folder.")
            file_directory_to_upload = input("Enter the video file directory to add to:").strip()
            print("Leave blank for automatic name.")
            file_name = input("Enter what the file should be named:")

            print(download_youtube(link,file_directory_to_upload,file_name))