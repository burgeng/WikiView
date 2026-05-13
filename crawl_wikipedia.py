##### TODO:
# Re-evaluate JSON write format/process, currently bottleneck+annoyingly slow

import requests
from bs4 import BeautifulSoup
from collections import deque
import networkx as nx
import json
from urllib.parse import unquote
from networkx.algorithms.community import greedy_modularity_communities
import orjson
import time
import sys

headers = {
    "User-Agent": "WikiGraphExplorer/1.0 (your_email@example.com)"
}

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

def export_graph_to_json(G, filename="wiki_graph.json"):

    data = {
        "nodes": [],
        "links": []
    }

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

def prune_low_degree_nodes(G, min_total_degree=2):
    """
    Removes nodes whose total degree is below min_total_degree.
    For directed graphs, total degree = in_degree + out_degree.
    """
    start = time.perf_counter()
    print(f"Removing nodes with total degree <= {min_total_degree}")

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

def should_skip_page(page, current_title, seed, block_language_pages=True):
    # Always allow the seed page
    if page == seed:
        return False

    if ":" in page:
        return True

    if "#" in page:
        return True

    if page == current_title:
        return True

    if "(identifier)" in page:
        return True

    if page in blocked_pages:
        return True

    # Skip language/translation pages only when this option is enabled
    if block_language_pages:
        if any(keyword in page for keyword in blocked_language_pages):
            return True

    return False

# ----------------------------------------
# Get Wikipedia links from a page
# ----------------------------------------
def get_links(title, max_links):

    url = f"https://en.wikipedia.org/wiki/{title}"
    if title == SEED_LABEL:
        print("SEED: ", title)

    try:
        response = requests.get(url, timeout=10, headers=headers)
        if response.status_code != 200:
            return []

        soup = BeautifulSoup(response.text, "html.parser")

        links = set()

        for a in soup.select("a[href^='/wiki/']"):

            href = a.get("href")

            # Extract page title
            page = href.split("/wiki/")[1]
            #print("Page: ", page)

            if should_skip_page(
                page,
                current_title=title,
                seed=SEED_LABEL,
                block_language_pages=True
            ):
                #print("Skipping", page)
                continue
            
            if len(links) >= max_links:
                return list(links)
            links.add(page)

        return list(links)

    except Exception as e:
        print(f"Error fetching {title}: {e}")
        return []
    
def page_key(title):
    return unquote(title).strip().replace(" ", "_").lower()

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

    # Start with seed page
    queue.append((seed, 0))
    visited.add(page_key(seed)) # Normalize page name so that we don't visit seed page twice

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
        links = get_links(current_page, max_links)

        for link in links:

            # Add edge to graph
            G.add_edge(current_page, link)

            key = page_key(link)

            # Add unseen pages to BFS queue
            if key not in visited:

                visited.add(key)

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

export_graph_to_json(G, "wiki_graph.json")

print()
print("Done.")
print("Nodes:", G.number_of_nodes())
print("Edges:", G.number_of_edges())