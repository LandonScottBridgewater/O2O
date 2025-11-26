from O2O.query_sources import query_artist
from query_lyrics import query_lyrics_of_artist_query

# Fetch songs for a specific artist
artist_name = input("Type in an artist:")
songs = query_artist(artist_name)

# Add lyrics
songs_with_lyrics = query_lyrics_of_artist_query(songs)

# Optional: print results
for song in songs_with_lyrics:
    print(f"{song['title']} - {song['artist']}")
    print(song.get("lyrics", "No lyrics"))
    print("-" * 50)
