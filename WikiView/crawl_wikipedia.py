import requests
from bs4 import BeautifulSoup
from collections import deque
import networkx as nx
import urllib.robotparser
from urllib.parse import unquote, urljoin, urlparse, urldefrag
import time
import sys
from config import load_config

config = load_config()

ROBOTS_URL = config.robots_url
BASE = config.base_url
USER_AGENT = config.user_agent

blocked_pages = config.blocked_pages

DEPTH = config.max_depth
MAX_LINKS = config.max_links

session = requests.Session() # initialize the session
session.headers.update({
    "User-Agent": USER_AGENT,
    "Accept-Encoding": "gzip",
})

robots_resp = session.get(ROBOTS_URL, timeout=10) # fetch the robots.txt
robots_resp.raise_for_status() # check status code is ok

# set up robots.txt autoparsers
rp = urllib.robotparser.RobotFileParser()
rp.set_url(ROBOTS_URL)
rp.parse(robots_resp.text.splitlines())

"""
Respect robots.txt!
"""
def allowed(url: str) -> bool:
    return rp.can_fetch(USER_AGENT, url)

def update_status(pages_crawled, pages_seen, depth, max_depth, queue_size, max_pages, page):
    msg = (
        f"depth={depth:<2}/{max_depth:<2} "
        f"crawled={pages_crawled:<5}/{max_pages:<5} "
        f"seen={pages_seen:<6} "
        f"queue={queue_size:<6} "
        f"page={page[:50]:<50}"
    )

    sys.stdout.write("\r" + msg.ljust(120))
    sys.stdout.flush()

def export_graph(G, filename="wiki_graph"):

    data = {
        "nodes": [],
        "links": []
    }

    # Testing writing to dedicated viewer format
    nx.write_gexf(G, f"{filename}.gexf")

def prune_low_degree_nodes(G, min_total_degree=2):
    """
    Removes nodes whose total degree is below min_total_degree.
    For directed graphs, total degree = in_degree + out_degree.
    """
    start = time.perf_counter()
    print(f"Removing nodes with total degree < {min_total_degree}")

    nodes_to_remove = [
        node
        for node in G.nodes()
        if G.in_degree(node) + G.out_degree(node) < min_total_degree
    ]

    print(f"Removing {len(nodes_to_remove)} low-degree nodes")

    G_pruned = G.copy()
    G_pruned.remove_nodes_from(nodes_to_remove)

    end = time.perf_counter()
    print(f"Time to remove low-degree nodes: {end - start:.2f}")

    return G_pruned

def extract_wiki_links(page: str, max_links: int) -> set[str]:
    html = fetch_page(page)

    if html:
        soup = BeautifulSoup(html, "html.parser")
    links = set()

    num_links = 0

    if soup:
        for a in soup.select("a[href]"):
            url = normalize_wiki_url(a["href"])
            if url is not None:
                links.add(url)
                num_links+=1
                if num_links >= max_links:
                    break

    return links

"""
Keep only canonical /wiki/ links
"""
def normalize_wiki_url(href: str) -> str | None:
    if not href:
        return None

    url = urljoin(BASE, href)
    url, _frag = urldefrag(url)
    parsed = urlparse(url)

    ### Initial criteria for accepting a scraped page
    # If location of linked website is not on english wikipedia, don't add it
    if parsed.netloc != "en.wikipedia.org":
        return None
    # Ignore any page with a query (after '?' in URL); typically wikipedia articles do not have query params
    if parsed.query:
        return None
    # wiki articles' paths start with /wiki/
    if not parsed.path.startswith("/wiki/"):
        return None
    
    # Remove the /wiki/ and keep the url article name
    title = parsed.path.removeprefix("/wiki/")

    # ":" indicates some special page
    if ":" in title:
        return None
    # Finally, check the blocked pages list
    ## TODO: change this top checkfrom parsed file in .env
    if title in blocked_pages:
        return None

    return BASE + parsed.path

def fetch_page(url: str) -> str | None:
    if not allowed(url):
        print(f"Blocked by robots.txt: {url}")
        return None
    
    resp = session.get(url, timeout=10)

    # we got rate limited
    if resp.status_code == 429:
        time.sleep(15)

    if 500 <= resp.status_code <= 600:
        time.sleep(60)
    
    if resp.status_code != 200:
        print(f"Skipping {url}: HTTP {resp.status_code}")
        return None

    return resp.text

"""
Breadth-first search wikipedia crawler.

@param seed: seed page
@param depth: number of hops away from seed page to expand to
@param man_links: max number of links to consider per page
"""
def crawl_wikipedia(seed, depth=2, max_links=50):

    # Directed graph
    G = nx.DiGraph()

    # BFS queue (double-ended queue)
    queue = deque()

    # Track visited pages
    visited = set()

    crawled_count = 0

    #if not good_seed(seed):
    #    return None

    # Start with seed page
    queue.append((seed, 0))
    visited.add(seed) # Normalize page name so that we don't visit seed page twice

    # while there are page(s) in the queue
    while queue:

        current_page, current_depth = queue.popleft()

        crawled_count+=1

        update_status(
            pages_crawled=crawled_count,
            pages_seen=len(visited),
            depth=current_depth,
            max_depth=depth,
            queue_size=len(queue),
            max_pages="∞",
            page=current_page
        )

        # Stop expanding beyond depth limit
        if current_depth >= depth:
            continue

        # Get outgoing links from current_page
        links = extract_wiki_links(current_page, max_links)

        for link in links:

            # Add edge to graph
            G.add_edge(current_page, link)

            # Add unseen pages to BFS queue
            if link not in visited:

                visited.add(link)

                # Add the page link to the queue, with a depth of current_depth+1
                queue.append((link, current_depth + 1))

    return G

"""
Program entry point. 
Will check cli args, initiate a crawl with those parameters, prune low degree nodes, and export the graph.
"""
def main():
    if len(sys.argv) != 2:
        print("Usage:\tcrawl_wikipedia.py <seed page>")
        sys.exit(1)

    SEED_LABEL = unquote(sys.argv[1]).strip().replace(" ", "_")
    #DEPTH = int(sys.argv[2])
    #MAX_LINKS = int(sys.argv[3])

    G = crawl_wikipedia(
        seed=str(SEED_LABEL),
        depth=DEPTH,
        max_links=MAX_LINKS
    )

    G = prune_low_degree_nodes(G, min_total_degree=2)

    export_graph(G, "wiki_graph")

    print()
    print("Done.")
    print("Nodes:", G.number_of_nodes())
    print("Edges:", G.number_of_edges())

if __name__ == "__main__":
    main()