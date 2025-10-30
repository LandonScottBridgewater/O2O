# O2O (Online to Offline)

**The goal** of this project is to make downloading online media seamless.

---


## Requirements
  
- YouTube API Key (for YouTube queries)  

---

### Installation

```bash
git clone https://github.com/LandonScottBridgewater/O2O.git
cd O2O
pip install -r requirements.txt
```

### Main Usage

Add a 'cookies.txt' file of YouTube in the project to download from YouTube without errors. I personally used https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc, but you may use any tool to get a Netscape HTTP Cookie File for YouTube.

Add the environment variable 'YOUTUBE_API_KEY' from Google's YouTube Data v3 API.

Linux/macOS:

```bash
export YOUTUBE_API_KEY="" # enter api key
python3 ./app.py
```

Windows:

```bash
set YOUTUBE_API_KEY= # enter api key
python app.py
```

---

### My Motive

The reason I created this was because I lost thousands of songs I downloaded when I accidentally deleted my local music storage. So, I created this script to easily download online media to local storage.

It uses semantic similarity clustering via Sentence Transformers to group similar media and automatically pick the original media without using external labels. 

For instance, if it is given a song and a slowed and reverb version of the song, it will pick the original on its own.

--- 

### query_sources.py

This script scrapes online data raw for processing.

### `query_artist(artist)` 

This function contains a preset of parameters for query_media() to find a link to each song of an artist's discography just by typing in their artist name.

-

### `query_media(platforms, query, max_results, minimum_duration_seconds, maximum_duration_seconds,filtered_substrings=[])`

This function allows you to select which platforms to check, the duration of the desired queries, and filter out results if it contains certain substrings.

Returns a list of arrays with each array holding song information such as 'title' and 'link.'

-

### `query_soundcloud` & `query_youtube` --> `query_filter`

Results from `query_soundcloud` & `query_youtube` send their results to `query_filter` which applies the filter and sort the results. 

For music, this will output the canonical/official version of a song based on the title and channel without verification. 
Most heuristics rely on official sources, but this approach works for even niche media.

### app.py

This script manages the high-level user and the database system. The files are named by their ID + file extension for easy look up. The reason I created this structure is because I have noticed each time I make a small change to the data structure, it becomes very tedious to manage filepaths. Instead, I used IDs which have metadata and the unique file name linked to the ID. 

### `class DataHandler`

This manages the sqlite database of IDs & json.

### `class MediaDownloader`

This class retrieves the files using query_sources.py and moves the files into DataHandler's data structure.

---

**Author:** Landon Scott Bridgewater  
**License:** MIT
