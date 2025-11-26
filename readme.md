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

python3 ./app.py

---

### My Motive

The reason I created this was because I lost thousands of songs I downloaded when I accidentally deleted my local music storage. So, I created this script to easily download online media to local storage.

It uses semantic similarity clustering via Sentence Transformers to group similar media and automatically pick the original media without using external labels. 

For instance, if it is given a song and a slowed and reverb version of the song, it will pick the original on its own.

--- 

### Functions

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

