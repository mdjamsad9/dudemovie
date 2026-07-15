import urllib.request
import re
import json
import time
import sys
import math
import os
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed

# Set console encoding to UTF-8 for Windows compatibility
sys.stdout.reconfigure(encoding='utf-8')

BASE_URL = "https://www.nongorplay.live"
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Referer': 'https://www.nongorplay.live/movies'
}

# Output structure inside the "dudemove" folder
PARENT_DIR = "dudemove"
MOVIES_DIR = os.path.join(PARENT_DIR, "movies")
FILTERS_FILE = os.path.join(PARENT_DIR, "filters.json")
INDEX_FILE = os.path.join(PARENT_DIR, "movies.json")

def clean_val(match):
    if not match:
        return None
    val = match.group(1)
    val = val.replace('\\/', '/')  # Unescape slashes
    if val in ["null", "undefined", ""]:
        return None
    return val

def fetch_watch_details(movie):
    """
    Fetches the watch page for a movie and extracts the streaming URLs.
    Also saves the movie as an individual JSON file in the 'dudemove/movies' directory.
    """
    slug = movie.get('slug')
    movie_id = movie.get('id')
    if not slug:
        return movie
    
    url = f"{BASE_URL}/watch/{slug}"
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        # Add a small delay to prevent rate limits
        time.sleep(0.3)
        
        with urllib.request.urlopen(req, timeout=10) as res:
            html = res.read().decode('utf-8')
            
            # Match stream/download URLs in the script tags
            download_url_match = re.search(r'\\?"download_url\\?":\\?"([^"]+?)\\?"', html)
            download_720_match = re.search(r'\\?"download_url_720\\?":\\?"([^"]+?)\\?"', html)
            download_480_match = re.search(r'\\?"download_url_480\\?":\\?"([^"]+?)\\?"', html)
            
            movie['stream_url_1080p'] = clean_val(download_url_match)
            movie['stream_url_720p'] = clean_val(download_720_match)
            movie['stream_url_480p'] = clean_val(download_480_match)
            
            # Save individual movie details inside the 'dudemove/movies/' folder
            if movie_id:
                individual_file = os.path.join(MOVIES_DIR, f"{movie_id}.json")
                with open(individual_file, "w", encoding="utf-8") as ind_f:
                    json.dump(movie, ind_f, indent=2, ensure_ascii=False)
            
    except Exception as e:
        print(f"Error fetching watch details for '{movie.get('title')}': {e}")
        movie['stream_url_1080p'] = None
        movie['stream_url_720p'] = None
        movie['stream_url_480p'] = None
        
        # Save placeholder details even if failed
        if movie_id:
            individual_file = os.path.join(MOVIES_DIR, f"{movie_id}.json")
            with open(individual_file, "w", encoding="utf-8") as ind_f:
                json.dump(movie, ind_f, indent=2, ensure_ascii=False)
        
    return movie

def get_movies_from_page(page_num):
    """
    Fetches a page of movies from the API.
    """
    url = f"{BASE_URL}/api/movies?page={page_num}&sort=year_desc"
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=10) as res:
            data = json.loads(res.read().decode('utf-8'))
            return data.get('movies', []), data.get('total', 0)
    except Exception as e:
        print(f"Error fetching list page {page_num}: {e}")
        return [], 0

def fetch_and_save_filters():
    """
    Fetches the filter options (genres, countries, languages) and saves them as JSON.
    """
    url = f"{BASE_URL}/api/movies/filters"
    print("Fetching movie filters from API...")
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=10) as res:
            filters = json.loads(res.read().decode('utf-8'))
            
            with open(FILTERS_FILE, "w", encoding="utf-8") as f:
                json.dump(filters, f, indent=2, ensure_ascii=False)
            print(f"Saved filter options to: {FILTERS_FILE}")
            return filters
    except Exception as e:
        print(f"Error fetching filter options: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description="Scrape movies and stream links into dudemove folder.")
    parser.add_argument("--pages", type=int, help="Number of pages to scrape.")
    parser.add_argument("--all", action="store_true", help="Scrape all available pages.")
    args, unknown = parser.parse_known_args()

    print("=" * 60)
    print("            Dudemove Movie & Streaming URL Scraper            ")
    print("=" * 60)
    
    # Create output folders if they don't exist
    os.makedirs(MOVIES_DIR, exist_ok=True)
    
    # Fetch and save filters first
    fetch_and_save_filters()
    
    # 1. Fetch first page to get total movie count
    print("\nConnecting to API to count movies...")
    first_page_movies, total_movies = get_movies_from_page(1)
    
    if not total_movies:
        print("Failed to fetch initial data. Check internet connection or if the site blocked you.")
        return
        
    print(f"Total Movies found on site: {total_movies}")
    movies_per_page = 18
    total_pages = math.ceil(total_movies / movies_per_page)
    print(f"Total Pages to scrape: {total_pages} ({movies_per_page} movies per page)")
    
    # Check arguments first
    if args.all:
        max_pages = total_pages
        print("\nArgument '--all' detected. Scraping all pages.")
    elif args.pages is not None:
        max_pages = args.pages
        print(f"\nArgument '--pages {max_pages}' detected.")
    else:
        # Fall back to interactive mode
        try:
            limit_input = input("\nEnter number of pages to scrape (Press Enter for ALL): ").strip()
            max_pages = int(limit_input) if limit_input else total_pages
        except ValueError:
            max_pages = total_pages
        except Exception:
            max_pages = total_pages
            
    max_pages = min(max_pages, total_pages)
    print(f"Starting scrape for {max_pages} page(s)...")
    
    # 2. Scrape all list pages
    all_movies = []
    for page in range(1, max_pages + 1):
        print(f"[{page}/{max_pages}] Fetching movie list...")
        movies, _ = get_movies_from_page(page)
        all_movies.extend(movies)
        time.sleep(0.5) # respect rate limit
        
    print(f"\nCollected metadata for {len(all_movies)} movies.")
    print("Now fetching streaming/source URLs (this is multithreaded)...")
    print(f"Each movie details will also be saved individually in the '{MOVIES_DIR}/' folder.")
    
    # 3. Fetch stream URLs concurrently
    completed_count = 0
    final_movies = []
    
    # Use ThreadPoolExecutor for fast scraping
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(fetch_watch_details, movie): movie for movie in all_movies}
        
        for future in as_completed(futures):
            movie = future.result()
            final_movies.append(movie)
            completed_count += 1
            
            # Print progress
            sys.stdout.write(f"\rProgress: {completed_count}/{len(all_movies)} movies processed...")
            sys.stdout.flush()
            
    print("\n\nScraping completed!")
    
    # 4. Save index results to JSON file
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(final_movies, f, indent=2, ensure_ascii=False)
        
    print(f"Saved {len(final_movies)} movies with streaming links to: {INDEX_FILE}")
    print(f"Individual movie files are stored in the '{MOVIES_DIR}/' folder.")
    print("=" * 60)

if __name__ == "__main__":
    main()
