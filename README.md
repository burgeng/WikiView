# WikiView
WikiView is a Python-based Wikipedia hyperlink scraper, paired with a Cytoscape-enabled frontend for visualization of resulting network structures.

### Usage:
1. Generate a corpus of craled Wikipedia articles from a desired starting (seed) article. For example, to start from the article for [Baseball](https://en.wikipedia.org/wiki/Baseball):
```
python ./crawl_wikipedia.py "Baseball"
```
2. View the resulting corpus (`wiki_graph.json`) on the frontend by starting a Python HTTP sevrer:
```
python -m http.server 8000
```
and load it in your web browser by navigating to `localhost:8000`.
