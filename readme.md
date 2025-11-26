# O2O (Online to Offline)

**The goal** of this project is to make downloading online media seamless.

---


## Requirements

- Python 3
- Requirements.txt
- YouTube API Key (for YouTube queries)
- YouTube OAuth Token (until this project is out of beta & I release verify the google api service for OAuth)

---

### Installation

```bash
git clone https://github.com/LandonScottBridgewater/O2O.git
cd O2O
pip install -r requirements.txt
```

### Main Usage

```bash
python3 ./app.py
```

---

### My Motive

The reason I created this was because I lost thousands of songs I downloaded when I accidentally deleted my local music storage. So, I created this script to easily download online media to local storage.

It uses semantic similarity clustering via Sentence Transformers to group similar media and automatically pick the original media without using external labels. 

For instance, if it is given a song and a slowed and reverb version of the song, it will pick the original on its own.

--- 

## Docs

### `query_sources.py`

### `query_artist(artist)` 

This function contains a preset of parameters for `query_media()` to find a link to each song of an artist's discography just by typing in their artist name.

-

### `query_media(platforms, query, max_results, minimum_duration_seconds, maximum_duration_seconds,filtered_substrings=[])`

This function allows you to select which platforms to check, the duration of the desired queries, and filter out results if it contains certain substrings.

Returns a list of arrays with each array holding song information such as 'title' and 'link.'

-

### `query_soundcloud` & `query_youtube` --> `query_filter`

Results from `query_soundcloud` & `query_youtube` send their results to `query_filter` which applies the filter and sort the results. 

For music, this will output the canonical/official version of a song based on the title and channel without verification. 
Most heuristics rely on official sources, but this approach works for even niche media.

### `app.py`

### `class DataHandler`

Manages how the media files and data are stored.


### `class QueryTool`

Interface to query automation from user input. 

A `result` of `DataHandler` is a json containing metadata. 

({
'title':'First Fake Result!',
'link':'https//:platform.com/fakeresult1'
},
{
title:'Second Fake Result!',
'link':'https//:platform.com/fakeresult2'
})


#### `__init__(data_handler, temp_dir=None)`

`data_handler` is your initialized `DataHandler`.
`temp_dir` is the directory which files will be temporarily stored before moving into `DataHandler`'s data structure.


#### `download_result(result, skip_existing_results=True)`

This downloads `result`.

`skip_existing_results` checks if the there is the same link in any existing downloads' metadata. If it finds a match, it will not download.

`skip_existing_result` can be passed in user input or in the result data as a boolean under the key `'skip_existing_result'`.

Result data parameters will override function parameters.

#### `download_results(self,results, skip_existing_results=True)`

Passes a for loop over `download_result`.

#### `review_results(self, results)`

Enables manual review by the user for each result.

#### `query_artist(self, 
                  artist_name, 
                  st_model, 
                  manual_review=True, 
                  max_results=400, 
                  minimum_duration_seconds=60,
                  maximum_duration_seconds=390,
                  filtered_substrings=["beat", "slowed", "reverb", "free"])`
                  
Connects `app.py` to `query_sources.py`'s `query_artist`.


### `class YouTubeAccount`

Integrates your Google account to retrieve your YouTube playlists. 

#### `__init__(self)`

Redirects you to your Google account for external authorization.

#### `get_playlists(self)`

Retrieves all your playlists.

#### `get_playlist_videos(self)`

Fetch all videos from a given YouTube playlist. 

Minimal metadata gathered for basic usage.

Args:
    playlist_id (str): The YouTube playlist ID.

Returns:
    List[dict]: A list of videos with metadata (title, videoId, link, publishedAt, etc.).
