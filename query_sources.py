import requests
from sentence_transformers import SentenceTransformer, util
import re
from googleapiclient.discovery import build
import isodate
from unidecode import unidecode
import os

def query_filter(st_model, query, title, channel, duration_seconds, minimum_duration_seconds, maximum_duration_seconds,filtered_substrings):

    filtered_substrings = [i.lower() for i in filtered_substrings]

    if not minimum_duration_seconds < duration_seconds < maximum_duration_seconds or any(sub in unidecode(title).lower() for sub in filtered_substrings):
        return False
    
    title_channel_string = f"{title} {channel}"

    if query.lower() not in title_channel_string.lower():
        emb_query = st_model.encode([query.lower()], convert_to_tensor=True)
        emb_title = st_model.encode([unidecode(title_channel_string).lower()], convert_to_tensor=True)
        sim_score = util.cos_sim(emb_query, emb_title).item()

        if sim_score < .3:
            return False
        
    return True

def query_soundcloud(st_model, query, minimum_duration_seconds, maximum_duration_seconds, filtered_substrings, max_results=400):
    """Search SoundCloud for tracks matching a query."""
    def get_soundcloud_client_id():
        """Automatically fetches a working SoundCloud client_id."""
        headers = {"User-Agent": "Mozilla/5.0"}
        home_url = "https://soundcloud.com"

        try:
            html = requests.get(home_url, headers=headers, timeout=10).text
            js_urls = re.findall(r'src="(https://a-v2\.sndcdn\.com/assets/[^"]+\.js)"', html)
            if not js_urls:
                print("⚠️ Could not find JS URL with client_id")
                return None

            for js_url in js_urls:
                js_code = requests.get(js_url, headers=headers, timeout=10).text
                match = re.search(r'client_id\s*:\s*"([a-zA-Z0-9]{32})"', js_code)
                if match:
                    return match.group(1)

            print("⚠️ client_id not found in JS files")
            return None
        except Exception as e:
            print(f"⚠️ Error fetching client_id: {e}")
            return None
    client_id = get_soundcloud_client_id()
    if not client_id:
        print("❌ No client_id found — cannot query SoundCloud.")
        return []

    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    all_tracks = []
    limit = 50
    offset = 0

    while len(all_tracks) < max_results:
        search_url = (
            f"https://api-v2.soundcloud.com/search/tracks"
            f"?q={requests.utils.quote(query)}"
            f"&client_id={client_id}&limit={limit}&offset={offset}"
        )

        response = requests.get(search_url, headers=headers, timeout=10)
        if response.status_code != 200:
            print(f"⚠️ SoundCloud returned {response.status_code}")
            break

        data = response.json()
        collection = data.get("collection", [])
        if not collection:
            break

        for item in collection:
            title = item.get("title")
            duration_miliseconds = item.get("duration")
            duration_seconds = duration_miliseconds / 1000 if duration_miliseconds else None
            publisher_metadata = item.get("publisher_metadata", {}) or {}
            artist = publisher_metadata.get("artist") or item.get("user", {}).get("username")
            permalink_url = item.get("permalink_url")
            if title and permalink_url:
                if query_filter(st_model=st_model,
                                query=query,
                                title=title,
                                channel=artist,
                                duration_seconds=duration_seconds,
                                minimum_duration_seconds=minimum_duration_seconds,
                                maximum_duration_seconds=maximum_duration_seconds,
                                filtered_substrings=filtered_substrings):
                    all_tracks.append({"title": title, 
                                       "link": permalink_url,
                                       "platform": "soundcloud"})

        print(f"Fetched {len(all_tracks)} tracks so far...")
        offset += limit

    return all_tracks[:max_results]

def query_youtube(st_model, query, minimum_duration_seconds, maximum_duration_seconds, filtered_substrings, max_results=400,api_key=os.getenv("YOUTUBE_API_KEY")):
    if not api_key:
        raise ValueError("Missing YouTube API key. Please set YOUTUBE_API_KEY as an environment variable.")

    youtube = build("youtube", "v3", developerKey=api_key)

    results = []
    request = youtube.search().list(
        q=query,
        part="snippet",
        maxResults=min(max_results, 50),
        type="video"
    )
    response = request.execute()

    while response:
        video_ids = [item['id']['videoId'] for item in response['items']]

        # Now query the videos endpoint to get durations
        video_request = youtube.videos().list(
            part="contentDetails,snippet",
            id=",".join(video_ids)
        )
        video_response = video_request.execute()

        for item in video_response["items"]:
            title = item["snippet"]["title"]
            video_id = item["id"]
            link = f"https://www.youtube.com/watch?v={video_id}"
            channel = item["snippet"]["channelTitle"]
            # Duration is in ISO 8601 format like 'PT4M13S'
            iso_duration = item["contentDetails"]["duration"]
            duration_seconds = isodate.parse_duration(iso_duration).total_seconds()
            if query_filter(st_model=st_model,
                            query=query,
                            title=title, 
                            channel=channel, 
                            duration_seconds=duration_seconds, 
                            minimum_duration_seconds=minimum_duration_seconds, 
                            maximum_duration_seconds=maximum_duration_seconds,
                            filtered_substrings=filtered_substrings):
                results.append({
                    "title": title,
                    "link": link,
                    "platform": "youtube"
                })

            if len(results) >= max_results:
                return results[:max_results]

        if "nextPageToken" in response and len(results) < max_results:
            request = youtube.search().list(
                q=query,
                part="snippet",
                maxResults=min(max_results - len(results), 50),
                type="video",
                pageToken=response["nextPageToken"]
            )
            response = request.execute()
        else:
            break

    return results

def query_media(st_model, platforms, query, max_results, minimum_duration_seconds, maximum_duration_seconds,filtered_substrings=[]):
    """Query both SoundCloud and YouTube for tracks."""
    tracks = []
    if "soundcloud" in platforms:
        tracks.extend(query_soundcloud(st_model=st_model,
                                    query=query, 
                                    max_results=max_results,
                                    filtered_substrings=filtered_substrings,
                                    minimum_duration_seconds=minimum_duration_seconds, 
                                    maximum_duration_seconds=maximum_duration_seconds))
    if "youtube" in platforms:
        tracks.extend(query_youtube(st_model=st_model,
                                    query=query, 
                                    max_results=max_results, 
                                    filtered_substrings=filtered_substrings,
                                    minimum_duration_seconds=minimum_duration_seconds, 
                                    maximum_duration_seconds=maximum_duration_seconds))
    return tracks

def query_artist(artist, st_model):
    tracks = query_media(st_model=st_model,
                         platforms=["youtube","soundcloud"],
                         query=artist,
                         max_results=400,
                         minimum_duration_seconds=60,
                         maximum_duration_seconds=390,
                         filtered_substrings=["beat", "slowed", "reverb", "free"])
    
    for track in tracks:
        track["artist"] = artist

    return tracks

if __name__ == '__main__':

    st_model = SentenceTransformer('all-MiniLM-L6-v2')

    def data_folder_selection():
        print("Enter a filepath for O2O. Leave blank for default.")
        data_folder_1 = input("").strip()

        if not os.path.exists(data_folder_1) and not data_folder_1 == "":
            data_folder_selection()

        return data_folder_1

    data_folder = data_folder_selection()

    print("Type '1' to query an artist")
    print("Type '2' to query media")
    choice = input("").strip()

    if choice == '1':
        artist_name = input("Type in an artist: ").strip()
        print(query_artist(artist_name, st_model))
    else:
        query = input("What is your query? ").strip()

        youtube = input("Do you want to query YouTube? Type 'Y' if so. If not, leave blank: ").strip().upper()
        soundcloud = input("Do you want to query SoundCloud? Type 'Y' if so. If not, leave blank: ").strip().upper()

        max_results = input("How many query results do you want per platform? ").strip()
        max_results = int(max_results) if max_results else 100

        min_dur = input("Minimum duration (seconds, leave blank for none): ").strip()
        minimum_duration_seconds = float(min_dur) if min_dur else 0

        max_dur = input("Maximum duration (seconds, leave blank for none): ").strip()
        maximum_duration_seconds = float(max_dur) if max_dur else 1e9

        filtered_substrings = input("Enter a list of substrings to filter (e.g. ['beat','slowed','reverb']): ").strip()
        try:
            filtered_substrings = eval(filtered_substrings) if filtered_substrings else []
        except Exception:
            print("Invalid list format, ignoring filter.")
            filtered_substrings = []

        platforms = []
        if youtube == "Y":
            platforms.append("youtube")
        if soundcloud == "Y":
            platforms.append("soundcloud")

        results = query_media(
            platforms=platforms,
            query=query,
            max_results=max_results,
            minimum_duration_seconds=minimum_duration_seconds,
            maximum_duration_seconds=maximum_duration_seconds,
            filtered_substrings=filtered_substrings
        )

        for r in results:
            print(f"{r['title']} — {r['link']}")
