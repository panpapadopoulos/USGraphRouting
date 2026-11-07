# Central/Eastern US Graph Route Project

This Python project demonstrates highway route planning with graph algorithms:

- BFS
- DFS
- Prim
- Kruskal
- Dijkstra
- Bellman-Ford

It uses one example city for every US state that has territory in the Central or Eastern time zones, plus Washington, DC. The program calculates map distance, weather travel risk, elevation-adjusted real distance, gasoline use, the best start date, and algorithm performance.

Graph connections follow the project rule: cities connect only when their states are neighboring states. If state A neighbors state B, every selected city in state A connects to every selected city in state B.

## Run

```bash
python3 city_route.py
```

Direct full-run example:

```bash
python3 city_route.py --start Chicago --end Miami
```

Random city subset example:

```bash
python3 city_route.py --start Dallas --end Boston --random 15 --seed 3
```

Print an ASCII graph directly in the terminal:

```bash
python3 city_route.py --start Dallas --end Boston --random 15 --seed 3 --terminal-map
```

The interactive menu includes individual algorithm runs, a run-all option, and comparison reports for BFS vs DFS, Prim vs Kruskal, and Dijkstra vs Bellman-Ford.

Generated PNG map files open automatically while running on a desktop system. SVG files are saved beside them for report-quality viewing. To turn popups off for Linux server testing or batch runs:

```bash
python3 city_route.py --no-open-images
```

Optional packages are `psutil` for richer CPU/disk metrics and `matplotlib` for richer PNG rendering. The project runs without them.

PNG and SVG graphs are generated automatically over real US state outlines from `data/us_states.geojson`. If Matplotlib is installed, the PNGs include city labels, edge mileage labels, titles, and legends. SVG files always include collision-managed city labels and edge mileage labels, even without Matplotlib.

The program writes only graph images and a saved terminal transcript to `output/`:

- `full_graph.png`
- `full_graph.svg`
- `bfs_graph.png`
- `bfs_graph.svg`
- `dfs_graph.png`
- `dfs_graph.svg`
- `prim_mst.png`
- `prim_mst.svg`
- `kruskal_mst.png`
- `kruskal_mst.svg`
- `dijkstra_route.png`
- `dijkstra_route.svg`
- `bellman_ford_route.png`
- `bellman_ford_route.svg`
- `terminal_output.txt`

## Data Notes

The included weather is deterministic example data for January 1 through March 30, 2026. For a final class submission, replace `weather_condition()` in `city_route.py` with history exported from Weather Underground.

The highway distances are estimated from city coordinates by multiplying straight-line distance by 1.18, but only for cities whose states are neighbors. For a final submission requiring Google Maps data, replace `estimate_highway_distance()` or add a real `data/edges.csv` file with Google Maps driving distances.
