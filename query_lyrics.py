from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys

def query_lyrics_for_song(song_name, artist_name):

    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-software-rasterizer")
    
    service = Service("/usr/lib/chromium/")
    driver = webdriver.Chrome(service=service, options=options)
    
    try:
        search_query = f"{song_name} by {artist_name} lyrics"
        driver.get("https://www.google.com")

        search_box = WebDriverWait(driver, 10).until(
            EC.visibility_of_element_located((By.NAME, "q"))
        )
        search_box.send_keys(search_query + Keys.RETURN)

        first_result = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "(//h3)[1]/ancestor::a"))
        )
        first_result.click()


        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

        if "genius.com" in driver.current_url:
            lyrics = driver.find_element(By.XPATH, "//div[@data-lyrics-container='true']").text
        elif "azlyrics.com" in driver.current_url:
            lyrics = driver.find_element(By.XPATH, "//div[not(@class) and not(@id)]").text
        else:
            lyrics = "Lyrics not found or site not supported."

        return lyrics
    
    finally:
        driver.quit()

def query_lyrics_of_artist_query(songs):
    for song in songs:
        song["lyrics"]=query_lyrics_for_song(song["song_name"],song["artist"])
    return songs
