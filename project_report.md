# Project Report: Central/Eastern United States Graph Route Study

CS503-01

Purdue University Northwest

April 2026

## Contributors

| Class ID | Contributor Name | Email | Detailed Contributions |
|---|---|---|---|
|  |  |  | Python graph algorithms, city dataset, route calculations, performance monitoring, graph visualizations, and report writing. |

## Table of Contents

Abstract

I. Introduction

II. Data Collection

III. Graph Construction

IV. Graph Algorithms

V. Travel Risk, Fuel, and Date Calculations

VI. Performance Monitoring and Results

VII. Discussion

VIII. Conclusion

Acknowledge

References

Appendix

## Abstract

This project studies graph algorithms through a highway route problem in the Central and Eastern United States. Each city is represented as a graph node, and edges are created only between cities located in neighboring states. The project implements Breadth-First Search, Depth-First Search, Prim's algorithm, Kruskal's algorithm, Dijkstra's algorithm, and Bellman-Ford in Python. The program also estimates distance, weather travel risk, elevation-adjusted travel distance, gasoline consumption, best travel date, and algorithm performance.

## I. Introduction

The purpose of this project is to connect graph theory with a realistic route example. The system models selected cities as nodes and neighboring-state highway connections as weighted edges. This design allows traversal algorithms to demonstrate reachability, minimum spanning tree algorithms to compare network-wide connectivity, and Dijkstra's algorithm to calculate a point-to-point shortest route.

The project also supports Linux evaluation by printing terminal results and measuring runtime, CPU usage, memory usage, and disk usage for each algorithm.

## II. Data Collection

The dataset includes one city for every U.S. state that has territory in the Central or Eastern time zones, plus Washington, DC. Each city record includes state, time zone, latitude, longitude, and elevation.

Weather risk is modeled for January 1, 2026 through March 30, 2026. The project uses the required risk scale: sun/cloud equals 1, rain equals 5, and snow/ice equals 10. The current program uses deterministic sample weather data so the project can run without external API access. For a final production dataset, Weather Underground historical data can replace the sample weather function.

Distances are estimated from latitude and longitude using the haversine formula and a highway-distance multiplier. Google Maps driving distances can replace these estimates if official route data is collected manually or through an approved API.

## III. Graph Construction

The graph is undirected and weighted. A city is connected to another city only if their states are neighboring states. If state A borders state B, every selected city in state A connects to every selected city in state B.

The generated graph visualizations are saved as PNG and SVG files. The SVG files include real U.S. state outlines from GeoJSON, city labels, edge mileage labels, and highlighted algorithm result edges.

## IV. Graph Algorithms

BFS visits nodes level by level from the start city and is used to show reachability.

DFS follows a branch deeply before backtracking and is used to show structural exploration.

Prim's algorithm builds a minimum spanning tree by growing outward from the starting city.

Kruskal's algorithm builds a minimum spanning tree by sorting edges and adding the next shortest edge that does not create a cycle.

Dijkstra's algorithm calculates the shortest weighted route between the selected start city and destination city when all edge weights are non-negative.

Bellman-Ford also calculates a shortest route between two cities. It is slower than Dijkstra on this dataset, but it is useful to compare because it can support negative edge weights in other graph problems.

## V. Travel Risk, Fuel, and Date Calculations

For an edge between two cities, the travel risk is the average of the two city weather risks on the travel date.

The baseline gasoline efficiency is 45 miles per gallon. Elevation adjustment uses:

```text
tan(theta) = elevation_difference_in_miles / map_distance
real_distance = map_distance * (1 + tan(theta))
gasoline = real_distance / 45
```

The travel schedule assumes a maximum of 8 driving hours per day at 75 miles per hour, so the maximum driving distance is 600 miles per day.

The best travel date is the date with the lowest accumulated travel risk over the selected route.

## VI. Performance Monitoring and Results

The program measures elapsed time, CPU usage, peak memory usage, disk reads, and disk writes for BFS, DFS, Prim, Kruskal, and Dijkstra. The terminal output is saved to:

```text
output/terminal_output.txt
```

The graph result images are saved to:

```text
output/full_graph.svg
output/bfs_graph.svg
output/dfs_graph.svg
output/prim_mst.svg
output/kruskal_mst.svg
output/dijkstra_route.svg
output/bellman_ford_route.svg
```

PNG versions are also generated for the same graph results.

## VII. Discussion

The neighboring-state rule makes the graph more realistic than connecting cities only by nearest distance. It forces routes to move across state borders in a controlled way. BFS and DFS are useful for showing traversal behavior, but they do not minimize weighted distance. Prim and Kruskal produce the same minimum spanning tree distance, which confirms that both algorithms are solving the same network-wide optimization problem. Dijkstra and Bellman-Ford return the same shortest distances on this positive-weight graph, while Dijkstra is generally faster.

## VIII. Conclusion

This project demonstrates how graph algorithms can be applied to a travel route problem with weather risk, distance, elevation, gasoline usage, and performance monitoring. The Python implementation can be executed on a Linux server and produces terminal output plus visual graph artifacts for each algorithm.

## Acknowledge

The project uses Python standard libraries and a public U.S. states GeoJSON file for state outlines.

## References

Weather Underground historical weather: https://www.wunderground.com/history/

Google Maps distance reference: https://www.google.com/maps

PublicaMundi U.S. states GeoJSON dataset: https://github.com/PublicaMundi/MappingAPI

Python documentation: https://docs.python.org/3/

## Appendix

Example command:

```bash
python city_route.py --start Chicago --end Miami
```

Random city subset command:

```bash
python city_route.py --start Dallas --end Boston --random 15 --seed 3
```
