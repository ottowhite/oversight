import requests
import os
import hashlib
import time
from typing import Optional, Dict, Any, Union
from requests_html import HTMLSession

semantic_scholar_rate_limit_sleep_time: int = 2
other_rate_limit_sleep_time: int = 5

DEBUG: bool = False

def get_cached_webpage(
    url: str, 
    params: Optional[Dict[str, Any]] = None, 
    headers: Optional[Dict[str, str]] = None, 
    cache_dir: str = ".cache", 
    response_type: str = "html", 
    target_url: str = "other", 
    pre_render: bool = False
) -> str:
    """
    Get webpage content from cache or download it if not cached.
    Returns the webpage content as a string.
    """
    global semantic_scholar_rate_limit_sleep_time
    global other_rate_limit_sleep_time

    assert response_type in ["html", "json"], f"Invalid response type: {response_type}"
    assert target_url in ["semantic_scholar", "other"], f"Invalid target URL: {target_url}"

    # Create cache directory if it doesn't exist
    os.makedirs(cache_dir, exist_ok=True)
    if DEBUG:
        print(f"Retrieving webpage {url}")
    
    # Create a unique filename based on the URL and params if present
    if params:
        hash_input: str = url + str(params)
    else:
        hash_input = url
    url_hash: str = hashlib.md5(hash_input.encode()).hexdigest()

    if response_type == "html":
        cache_file: str = os.path.join(cache_dir, f"{url_hash}.html")
    else:
        cache_file = os.path.join(cache_dir, f"{url_hash}.json")
    if DEBUG:
        print(f"Cache file: {cache_file}")

    # Check if cache exists
    if os.path.exists(cache_file):
        if DEBUG:
            print("Using cached webpage...")
        with open(cache_file, 'r', encoding='utf-8') as f:
            return f.read()

    # Wait 2s on the retrieve path to avoid being blocked by the server
    if target_url == "semantic_scholar":
        print(f"Sleeping for {semantic_scholar_rate_limit_sleep_time}s...")
        time.sleep(semantic_scholar_rate_limit_sleep_time)
    else:
        print(f"Sleeping for {other_rate_limit_sleep_time}s...")
        time.sleep(other_rate_limit_sleep_time)
    
    # Download the webpage if cache doesn't exist
    if DEBUG:
        print("Downloading webpage...")

    if target_url == "other":
        if headers is None:
            headers = {}

        headers['User-Agent'] = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"

    if pre_render:
        session: HTMLSession = HTMLSession()
        response = session.get(url, headers=headers, params=params)
        response.html.render()
        response_text_raw = response.html.raw_html
        response_text: str = response_text_raw.decode('utf-8') if isinstance(response_text_raw, bytes) else str(response_text_raw)
    else:
        response = requests.get(url, headers=headers, params=params)
        response_text = response.text


    if response.status_code != 200:
        if response.status_code == 429:
            # Rate limit exceeded
            if target_url == "semantic_scholar":
                print(f"Rate limited at {semantic_scholar_rate_limit_sleep_time}s, doubling the sleep time to {2 * semantic_scholar_rate_limit_sleep_time}s.")
                semantic_scholar_rate_limit_sleep_time *= 2
            else:
                print(f"Rate limited at {other_rate_limit_sleep_time}s, doubling the sleep time to {2 * other_rate_limit_sleep_time}s.")
                other_rate_limit_sleep_time *= 2

            return get_cached_webpage(url, params, headers, cache_dir, response_type, target_url, pre_render)

        raise Exception(f"Failed to retrieve the webpage: Status code {response.status_code}, output: {response_text!r}")
    
    # Save to cache
    with open(cache_file, 'w', encoding='utf-8') as f:
        f.write(response_text)
    
    return response_text