import requests
from bs4 import BeautifulSoup
from collections import deque
import networkx as nx
import urllib.robotparser
from urllib.parse import unquote, urljoin, urlparse, urldefrag
from networkx.algorithms.community import greedy_modularity_communities
import time
import sys

blocked_pages = {
    "Main_Page",
    "Help:Contents",
    "Special:Search"
}

blocked_language_pages = {
    "Chinese_language",
    "Mandarin_Chinese",
    "Pinyin",
    "Standard_Chinese",
    "Traditional_Chinese_characters",
    "Simplified_Chinese_characters",
    "Chinese_characters",
    "Wade%E2%80%93Giles",
    "Cantonese",
    "Jyutping",
    "Hanyu_Pinyin",
    "Literal_translation",
}

ROBOTS_URL = "https://en.wikipedia.org/robots.txt"
BASE = "https://en.wikipedia.org"
USER_AGENT = "WikiGraphBot/0.1 (personal research)"

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

#print("Robots mtime:", rp.mtime())
#print("Can fetch Philadelphia:", rp.can_fetch(USER_AGENT, "https://en.wikipedia.org/wiki/Philadelphia"))
#print("Can fetch as *:", rp.can_fetch("*", "https://en.wikipedia.org/wiki/Philadelphia"))
#print(rp.default_entry)
#print(rp.entries[:3])

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

"""
Compute the communities within the graph, 
"""
def compute_community_weighted_layout(G):
    print("Computing graph layout...")
    start = time.perf_counter()
    undirected = G.to_undirected()

    communities = list(greedy_modularity_communities(undirected))

    community_map = {}
    for i, community in enumerate(communities):
        for node in community:
            community_map[node] = i

    # Create a copy for layout only
    H = undirected.copy()

    # Add invisible community center nodes
    for i, community in enumerate(communities):
        center = f"__community_{i}__"
        H.add_node(center)

        for node in community:
            H.add_edge(center, node, weight=10) # high-weight edge that will pull connected nodes closer together 

    # get positions of nodes treating edges as rsprings, higher weight = tighter spring
    pos = nx.spring_layout(
        H,
        #k=0.8,             # node distance, if none calculated as 1/sqrt(len(nodes))
        iterations=50,
        seed=42,
        weight="weight"
    )

    # Remove fake center nodes from final position map
    pos = {
        node: coords
        for node, coords in pos.items()
        if not str(node).startswith("__community_")
    }

    end = time.perf_counter()
    print(f"Graph creation took {end - start:.2f} seconds")

    return pos, community_map

def export_graph(G, filename="wiki_graph"):

    data = {
        "nodes": [],
        "links": []
    }

    # Testing writing to dedicated viewer format
    nx.write_gexf(G, f"{filename}.gexf")

    """
    pos, community_map = compute_community_weighted_layout(G)

    print("Writing graph to JSON...")
    start = time.perf_counter()
    # Add nodes
    for node in G.nodes():

        x, y = pos[node]
        data["nodes"].append({
            "id": node,
            "label": unquote(node).replace("_", " "),
            "url": f"https://en.wikipedia.org/wiki/{node}",
            "community": community_map.get(node, -1),
            "isSeed": SEED_LABEL == node,
            # precomputed coordinates
            "x": float(pos[node][0] * 8000),
            "y": float(pos[node][1] * 8000)
        })

    # Add directed edges
    for source, target in G.edges():

        data["links"].append({
            "source": source,
            "target": target
        })

    # Write JSON file
    with open(filename, "wb") as f:
        f.write(orjson.dumps(data))

    end  = time.perf_counter()

    print(f"Exported graph to {filename}, took {end - start:.2f} seconds")
    """

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

    soup = BeautifulSoup(html, "html.parser")
    links = set()

    num_links = 0

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

    if parsed.netloc != "en.wikipedia.org":
        return None
    if parsed.query:
        return None
    if not parsed.path.startswith("/wiki/"):
        return None
    
    title = parsed.path.removeprefix("/wiki/")

    if ":" in title:
        return None
    if title in blocked_pages or title in blocked_language_pages:
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
@param man_links_per_page: max number of links to consider per page
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

        #print(f"[Depth {current_depth}] Crawling: {current_page}")

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


# ----------------------------------------
# Run crawler
# ----------------------------------------
if len(sys.argv) != 4:
    print("Usage:\tcrawl_wikipedia.py <seed page> <depth> <max links per page>")
    sys.exit(1)

SEED_LABEL = unquote(sys.argv[1]).strip().replace(" ", "_")
DEPTH = int(sys.argv[2])
MAX_LINKS = int(sys.argv[3])

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