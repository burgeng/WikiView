# WikiView
WikiView is a Python-based Wikipedia hyperlink scraper, paired with an interactive frontend for visualization and exploration of resulting network structures.

### Usage:
Before beginning, ensure you have cloned this repository to your local machine.
* Generate a corpus of craled Wikipedia articles from a desired starting (seed) article. For example, to start from the article for [Baseball](https://en.wikipedia.org/wiki/Baseball):
```
python ./crawl_wikipedia.py "https://en.wikipedia.org/wiki/Baseball" <max. depth> <max. links per page>
```
i.e.
```
python ./crawl_wikipedia.py "https://en.wikipedia.org/wiki/Baseball" 3 20
```
* The corpus `wiki_graph.gexf` (Graph Exchange XML Format) will be generated in the current working directory, which can be uploaded to network visualization tools like [Gephi](https://gephi.org/).
<img width="1704" height="910" alt="image" src="https://github.com/user-attachments/assets/5235c127-8ee9-49b6-b8cb-a8c93961c88c" />
