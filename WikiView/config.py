import os
from dotenv import load_dotenv
import json
import csv
from dataclasses import dataclass

@dataclass
class Config:
    max_depth: int
    max_links: int
    base_url: str
    robots_url: str
    user_agent: str
    blocked_pages: list[str]

def load_config() -> Config:
    load_dotenv()

    crawl_param_file = os.getenv("CRAWL_PARAM_FILE")
    blocked_pages_file = os.getenv("BLOCKED_PAGES")
    base_url = os.getenv("BASE_URL")
    robots_url = os.getenv("ROBOTS_URL")
    user_agent = os.getenv("USER_AGENT")

    # Load the crawl parameters (json)
    with open(crawl_param_file) as f:
        crawl_params = json.load(f)
        max_depth = crawl_params["max_depth"]
        max_links = crawl_params["max_links"]

    # Load the blocked pages (csv)
    blocked_pages_list = []
    with open(blocked_pages_file) as f:
        blocked_pages = csv.reader(f)
        for p in blocked_pages:
            blocked_pages_list.append(p)
    
    return Config(
        max_depth = max_depth,
        max_links = max_links,
        base_url = base_url,
        robots_url = robots_url,
        user_agent = user_agent,
        blocked_pages = blocked_pages_list
    )