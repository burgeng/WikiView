import requests
from bs4 import BeautifulSoup
from collections import deque
import networkx as nx
import json
from urllib.parse import unquote
from networkx.algorithms.community import greedy_modularity_communities
import math
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

"""
Compute the communities within the graph, 
"""
def compute_community_weighted_layout(G):
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
            H.add_edge(center, node, weight=4.5) # high-weight edge that will pull connected nodes closer together 

    # get positions of nodes treating edges as rsprings, higher weight = tighter spring
    pos = nx.spring_layout(
        H,
        k=0.8,
        iterations=300,
        seed=42,
        weight="weight"
    )

    # Remove fake center nodes from final position map
    pos = {
        node: coords
        for node, coords in pos.items()
        if not str(node).startswith("__community_")
    }

    return pos, community_map

def export_graph_to_json(G, filename="wiki_graph.json"):

    # Compute PageRank
    pagerank = nx.pagerank(G)

    # Compute graph layout positions
    pos = nx.spring_layout(
        G,
        k=0.5,
        iterations=100,
        seed=42
    )

    data = {
        "nodes": [],
        "links": []
    }

    pos, community_map = compute_community_weighted_layout(G)

    # Add nodes
    for node in G.nodes():

        x, y = pos[node]
        print(SEED_LABEL, ": ", node)
        data["nodes"].append({
            "id": node,
            "label": unquote(node).replace("_", " "),
            "url": f"https://en.wikipedia.org/wiki/{node}",
            "pagerank": pagerank.get(node, 0),
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
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            indent=2,
            ensure_ascii=False
        )

    print(f"Exported graph to {filename}")


def add_communities(G):
    undirected = G.to_undirected()
    communities = greedy_modularity_communities(undirected)

    community_map = {}

    for i, community in enumerate(communities):
        for node in community:
            community_map[node] = i

    return community_map

def prune_low_degree_nodes(G, min_total_degree=2):
    """
    Removes nodes whose total degree is below min_total_degree.
    For directed graphs, total degree = in_degree + out_degree.
    """

    nodes_to_remove = [
        node
        for node in G.nodes()
        if G.in_degree(node) + G.out_degree(node) < min_total_degree
    ]

    print(f"Removing {len(nodes_to_remove)} low-degree nodes")

    G_pruned = G.copy()
    G_pruned.remove_nodes_from(nodes_to_remove)

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
def get_links(title, max_links=20):

    url = f"https://en.wikipedia.org/wiki/{title}"

    try:
        response = requests.get(url, timeout=10, headers=headers)
        print(f"Response for title {title}: {response}")
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

            links.add(page)

            if len(links) >= max_links:
                break

        return list(links)

    except Exception as e:
        print(f"Error fetching {title}: {e}")
        return []


"""
Breadth-first search wikipedia crawler.

@param seed: seed page
@param depth: number of hops away from seed page to expand to
@param man_links_per_page: max number of links to consider per page
"""
def crawl_wikipedia(seed, depth=2, max_links_per_page=20):

    # Directed graph
    G = nx.DiGraph()

    # BFS queue (double-ended queue)
    queue = deque()

    # Track visited pages
    visited = set()

    # Start with seed page
    queue.append((seed, 0))
    visited.add(seed)

    # while there are page(s) in the queue
    while queue:

        current_page, current_depth = queue.popleft()

        print(f"[Depth {current_depth}] Crawling: {current_page}")

        # Stop expanding beyond depth limit
        if current_depth >= depth:
            continue

        # Get outgoing links from current_page
        links = get_links(
            current_page,
            max_links=max_links_per_page
        )

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
if len(sys.argv) != 2:
    print("Usage:\tcrawl_wikipedia.py <seed page>")
    sys.exit(1)

SEED_LABEL = sys.argv[1]

G = crawl_wikipedia(
    seed=str(SEED_LABEL),
    depth=4,
    max_links_per_page=20
)

G = prune_low_degree_nodes(G, min_total_degree=1)

export_graph_to_json(G, "wiki_graph.json")

print()
print("Done.")
print("Nodes:", G.number_of_nodes())
print("Edges:", G.number_of_edges())