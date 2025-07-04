from tmdbv3api import TMDb, Movie
from tvdb_api import Tvdb
import requests
import re
import glob
import os

# Initialize TMDb
tmdb = TMDb()
tmdb.api_key = 'TMDBAPI'
movie_api = Movie()

# Initialize TVDb
tvdb = Tvdb(apikey='TVDBAPI')

# File path and file patterns
file_path = 'unmatched_assets.log'  # Replace with your actual file path
file_patterns = ['movies*.txt', 'series*.txt', 'collections*.txt', 'anime_series*.txt', 'anime_movies*.txt']

def is_anime(genres):
    return any('anime' in genre.lower() for genre in genres)

def get_tmdb_link(movie_name, year):
    search_results = movie_api.search(movie_name)
    for result in search_results:
        if result['release_date'][:4] == str(year):
            keywords = [keyword['name'] for keyword in movie_api.keywords(result['id'])['keywords']]
            return f"https://www.themoviedb.org/movie/{result['id']}", is_anime(keywords)
    return None, False

def get_tvdb_link(series_name, year):
    search_results = tvdb.search(series_name)
    for result in search_results:
        if result['firstAired'][:4] == str(year):
            series_details = tvdb[result['id']]
            genres = series_details['genre']
            return f"https://www.thetvdb.com/series/{result['slug']}", is_anime(genres)
    return None, False

def get_collection_link(collection_name):
    url = f"https://api.themoviedb.org/3/search/collection?api_key={tmdb.api_key}&query={collection_name}"
    response = requests.get(url)
    if response.status_code == 200:
        search_results = response.json()
        if search_results['results']:
            return f"https://www.themoviedb.org/collection/{search_results['results'][0]['id']}"
    return None

def read_assets_from_file(file_path):
    with open(file_path, 'r') as file:
        lines = file.readlines()

    # Skip all lines until encountering the first line of only underscores.
    start_index = 0
    for idx, line in enumerate(lines):
        if re.match(r'^_+$', line.strip()):
            start_index = idx
            break
    lines = lines[start_index:]
    
    movies = set()
    series = set()
    collections = set()
    in_collections = False  # Flag for collection block

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Check for a collections header and enable collection mode if found.
        if 'Unmatched Collections' in line:
            in_collections = True
            i += 1
            continue

        if in_collections:
            # Process only timestamped lines for collection entries.
            collection_match = re.match(
                r'^\d{2}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2}\s+(?:AM|PM)\s+INFO:\s+(.*)$',
                line
            )
            if collection_match:
                content = collection_match.group(1)
                # Skip header-like or decorative lines.
                if content and not content.startswith('***') and not content.startswith('|'):
                    collections.add(content)
            else:
                # If the line no longer matches a collections line, exit collection mode.
                in_collections = False
        else:
            # Process movies and series lines.
            movie_match = re.match(
                r'^\d{2}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2}\s+(?:AM|PM)\s+INFO:\s+(.*) \((\d{4})\)$',
                line
            )
            if movie_match:
                # Check if the next line(s) indicate season information.
                if (i + 1 < len(lines) and re.match(
                    r'^\d{2}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2}\s+(?:AM|PM)\s+INFO:\s+Season:',
                    lines[i+1].strip())
                ):
                    series_name, year = movie_match.groups()
                    missing_seasons = []
                    # Gather consecutive season lines.
                    while (i + 1 < len(lines) and re.match(
                        r'^\d{2}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2}\s+(?:AM|PM)\s+INFO:\s+Season:',
                        lines[i+1].strip())
                    ):
                        i += 1
                        season_match = re.match(
                            r'^\d{2}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2}\s+(?:AM|PM)\s+INFO:\s+Season:\s*(\d+)$',
                            lines[i].strip()
                        )
                        if season_match:
                            missing_seasons.append(season_match.group(1))
                    series.add((series_name, year, tuple(missing_seasons)))
                else:
                    movies.add(movie_match.groups())
            else:
                # Attempt to match series headers with explicit missing poster notes.
                series_match = re.match(
                    r'^\d{2}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2}\s+(?:AM|PM)\s+INFO:\s+(.*) \((\d{4})\) \(Seasons listed below have missing posters\)$',
                    line
                )
                if series_match:
                    series_name, year = series_match.groups()
                    missing_seasons = []
                    while (i + 1 < len(lines) and re.match(
                        r'^\d{2}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2}\s+(?:AM|PM)\s+INFO:\s+Season:',
                        lines[i+1].strip())
                    ):
                        i += 1
                        season_match = re.match(
                            r'^\d{2}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2}\s+(?:AM|PM)\s+INFO:\s+Season:\s*(\d+)$',
                            lines[i].strip()
                        )
                        if season_match:
                            missing_seasons.append(season_match.group(1))
                    series.add((series_name, year, tuple(missing_seasons)))
        i += 1
    return movies, series, collections

def write_to_files(items, item_type):
    file_count = 1
    item_count = 0
    file_content = []

    for item in items:
        if item_type in ('movies', 'anime_movies'):
            file_content.append(f"{item[0]} ({item[1]})\ntmdb: {item[2][0]}\n\n")
        elif item_type == 'collections':
            file_content.append(f"{item}\ntmdb: {get_collection_link(item)}\n\n")
        elif item_type in ('series', 'anime_series'):
            file_content.append(f"{item[0]} ({item[1]})\ntvdb: {item[2][0]}\n")
            if item[3]:
                file_content.append(f"Missing seasons: {', '.join(item[3])}\n\n")
            else:
                file_content.append('\n')
        
        item_count += 1

        if item_count == 5:
            with open(f"{item_type}-{file_count}.txt", 'w') as f:
                f.writelines(file_content)
            file_count += 1
            item_count = 0
            file_content = []

    if file_content:
        with open(f"{item_type}-{file_count}.txt", 'w') as f:
            f.writelines(file_content)

def main():
    movies, series, collections = read_assets_from_file(file_path)

    movie_items = [(movie_name, year, get_tmdb_link(movie_name, year)) for movie_name, year in movies]
    series_items = [(series_name, year, get_tvdb_link(series_name, year), missing_seasons)
                    for series_name, year, missing_seasons in series]
    collection_items = [(collection_name, '', get_collection_link(collection_name))
                        for collection_name in collections]

    anime_movies = [item for item in movie_items if item[2][1]]
    anime_series = [item for item in series_items if item[2][1]]

    non_anime_movies = [item for item in movie_items if not item[2][1]]
    non_anime_series = [item for item in series_items if not item[2][1]]

    for movie_name, year, (link, is_anime) in non_anime_movies:
        if link:
            print(f"Movie - {movie_name} ({year}): {link}")
        else:
            print(f"Movie - {movie_name} ({year}): Not found")

    for movie_name, year, (link, is_anime) in anime_movies:
        if link:
            print(f"Anime Movie - {movie_name} ({year}): {link}")
        else:
            print(f"Anime Movie - {movie_name} ({year}): Not found")

    for series_name, year, (link, is_anime), missing_seasons in non_anime_series:
        if link:
            print(f"Series - {series_name} ({year}): {link}")
            if missing_seasons:
                print(f"  Missing seasons: {', '.join(missing_seasons)}")
        else:
            print(f"Series - {series_name} ({year}): Not found")
            if missing_seasons:
                print(f"  Missing seasons: {', '.join(missing_seasons)}")

    for series_name, year, (link, is_anime), missing_seasons in anime_series:
        if link:
            print(f"Anime - {series_name} ({year}): {link}")
            if missing_seasons:
                print(f"  Missing seasons: {', '.join(missing_seasons)}")
        else:
            print(f"Anime - {series_name} ({year}): Not found")
            if missing_seasons:
                print(f"  Missing seasons: {', '.join(missing_seasons)}")

    for collection_name, _, link in collection_items:
        if link:
            print(f"Collection - {collection_name}: {link}")
        else:
            print(f"Collection - {collection_name}: Missing poster")

    write_to_files(non_anime_movies, 'movies')
    write_to_files(non_anime_series, 'series')
    write_to_files(collection_items, 'collections')
    write_to_files(anime_movies, 'anime_movies')
    write_to_files(anime_series, 'anime_series')

if __name__ == "__main__":
    # Remove existing output files based on the defined patterns before processing.
    for pattern in file_patterns:
        for file in glob.glob(pattern):
            os.remove(file)
    main()