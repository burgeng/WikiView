console.log("app.js loaded");
console.log("cytoscape is:", typeof cytoscape);

document.addEventListener("DOMContentLoaded", () => {
  fetch("wiki_graph.json")
    .then(response => {
      console.log("JSON response:", response.status);
      if (!response.ok) {
        throw new Error(`Could not load JSON: ${response.status}`);
      }
      return response.json();
    })
    .then(graph => {
      console.log("Loaded graph:", graph);
      console.log("Nodes:", graph.nodes.length);
      console.log("Links:", graph.links.length);

      const container = document.getElementById("cy");

      if (!container) {
        throw new Error("No #cy container found in HTML");
      }

      function communityColor(community) {
        if (community === undefined || community === null || community < 0) {
          return "#999";
        }

        const hue = (community * 137.508) % 360;
        return `hsl(${hue}, 70%, 55%)`;
      }

      const elements = [];

      for (const node of graph.nodes) {
        console.log(node.x, node.y);
        elements.push({
          data: {
            id: node.id,
            label: node.label,
            pagerank: node.pagerank,
            url: node.url,
            community: node.community,
            color: communityColor(node.community),
            isSeed: node.isSeed
          },

          position: {
            x: node.x,
            y: node.y
          }
        });
      }

      for (const link of graph.links) {
        elements.push({
          data: {
            source: link.source,
            target: link.target
          }
        });
      }

      const cy = cytoscape({
        container: container,
        elements: elements,

        style: [
          {
            selector: "node",
            style: {
              "label": "data(label)",

              "background-color": "data(color)",

              "font-size": 10,
              "text-valign": "center",
              "text-halign": "center",
              "width": 25,
              "height": 25,
              "font-size": 10,
              "font-weight": "normal",
              "text-valign": "center",
              "text-halign": "center"
            }
          },
          {
            selector: "node[?isSeed]",
            style: {
              "width": 90,
              "height": 90,
              "font-size": 18,
              "font-weight": "bold",
              "border-width": 6,
              "border-color": "#000",
              "z-index": 999
            }
          },
          {
            selector: "edge",
            style: {
              "width": 1,
              "line-color": "#aaa",
              "target-arrow-color": "#aaa",
              "target-arrow-shape": "triangle",
              "curve-style": "bezier"
            }
          }
        ],

        layout: {
          name: "preset"
        }
      });

      cy.fit();
      cy.center();

      const dijkstra = cy.elements().dijkstra({
        root: "",
        directed: true
      });
      const path = dijkstra.pathTo(end);

      cy.on("dblclick", "node", function(event) {
        const url = event.target.data("url");
        window.open(url, "_blank");
      });
    })
    .catch(error => {
      console.error("Graph render failed:", error);
    });
});