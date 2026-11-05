#!/usr/bin/env python3
"""R158 bounded graph and predecision dynamics features.

Greedy radius-ball cover is a *proxy*, not proof of fractal dimension.
Shannon H here measures checkpoint weight concentration, not solution entropy.
Repeat variability is not a Lyapunov exponent. Only <=1024 conflicts are read.
"""
import collections
import itertools
import math

MAX_N = 5000
MAX_EDGES = 200000


def require(condition, message):
    if not condition:
        raise ValueError('R158_FEATURE_REFUSED ' + message)


def average(values):
    return sum(values) / len(values) if values else 0.0


def entropy(weights):
    values = [max(0., float(x)) for x in weights]
    total = sum(values)
    if total <= 0 or len(values) < 2:
        return 0.
    return -sum((x / total) * math.log(x / total) for x in values if x > 0) / math.log(len(values))


def parse_dimacs(path):
    n = clauses = None
    graph = None
    count = edges = 0
    for line in path.read_text().splitlines():
        t = line.strip()
        if not t or t[0] in 'c%':
            continue
        if t.startswith('p '):
            parts = t.split()
            require(len(parts) == 4 and parts[1] == 'cnf' and n is None, 'DIMACS header')
            n, clauses = int(parts[2]), int(parts[3])
            require(1 <= n <= MAX_N and 0 <= clauses <= 2000000, 'size budget')
            graph = [set() for _ in range(n)]
            continue
        require(graph is not None, 'missing DIMACS header')
        literals = [int(x) for x in t.split()]
        require(literals and literals[-1] == 0 and 0 not in literals[:-1], 'single-line clauses required')
        vertices = sorted({abs(x)-1 for x in literals[:-1]})
        require(all(0 <= v < n for v in vertices), 'variable outside declared range')
        count += 1
        for i, j in itertools.combinations(vertices, 2):
            if j not in graph[i]:
                edges += 1
                require(edges <= MAX_EDGES, 'edge budget')
                graph[i].add(j)
                graph[j].add(i)
    require(graph is not None and count == clauses, 'clause count mismatch')
    return graph


def cover(graph, radius):
    remaining = set(range(len(graph)))
    boxes = 0
    for center in sorted(range(len(graph)), key=lambda i: (-len(graph[i]), i)):
        if center not in remaining:
            continue
        visited = {center}
        frontier = {center}
        for _ in range(radius):
            frontier = {v for u in frontier for v in graph[u]} - visited
            visited.update(frontier)
            if not frontier:
                break
        remaining.difference_update(visited)
        boxes += 1
    require(not remaining, 'incomplete greedy cover')
    return boxes


def modularity(graph):
    degree = [len(g) for g in graph]
    m = sum(degree) / 2.
    if not m:
        return 0.
    labels = list(range(len(graph)))
    for _ in range(5):
        updated = []
        for i, neighbors in enumerate(graph):
            if not neighbors:
                updated.append(labels[i])
                continue
            votes = collections.Counter(labels[j] for j in neighbors)
            highest = max(votes.values())
            updated.append(min(label for label, count in votes.items() if count == highest))
        if updated == labels:
            break
        labels = updated
    internal = 0
    strengths = collections.Counter()
    for i, neighbors in enumerate(graph):
        strengths[labels[i]] += len(neighbors)
        internal += sum(1 for j in neighbors if i < j and labels[i] == labels[j])
    return internal/m - sum((s/(2*m))**2 for s in strengths.values())


def static_features(graph):
    n = len(graph)
    degrees = [len(x) for x in graph]
    radii = (1, 2, 3, 4)
    counts = [cover(graph, r) for r in radii]
    xy = [(math.log(r+1), math.log(k)) for r, k in zip(radii, counts) if k > 1]
    valid = len(xy) >= 3 and len({round(y, 8) for x, y in xy}) >= 3
    dimension = r2 = 0.
    if valid:
        xbar = average([x for x, _ in xy])
        ybar = average([y for _, y in xy])
        slope = sum((x-xbar)*(y-ybar) for x, y in xy) / sum((x-xbar)**2 for x, _ in xy)
        dimension = max(0., -slope)
        denom = sum((y-ybar)**2 for _, y in xy)
        r2 = max(0., 1-sum((y-ybar-slope*(x-xbar))**2 for x, y in xy)/denom) if denom else 0.
    anchors = sorted(range(n), key=lambda i: (-degrees[i], i))[:min(16, n)]
    growth = []
    for i in anchors:
        one = {i} | graph[i]
        two = one | {k for j in one for k in graph[j]}
        growth.append(len(two)/len(one))
    return {
        'graph_degree_entropy': entropy(collections.Counter(degrees).values()),
        'graph_modularity': modularity(graph),
        'graph_growth': average(growth),
        'graph_box_dimension': dimension,
        'graph_box_r2': r2,
        'graph_box_valid': float(valid),
        'graph_mean_degree': average(degrees),
        'box_counts': ','.join(map(str, counts)),
    }


def prefix(trace):
    points = sorted([p for p in trace.get('points', []) if int(p['conflict']) <= 1024],
                    key=lambda p: int(p['conflict']))
    if len(points) < 5 or int(points[-1]['conflict']) != 1024:
        return None
    conflicts = [0] + [int(p['conflict']) for p in points]
    propagations = [0] + [int(p['propagations']) for p in points]
    restarts = [0] + [int(p['restarts']) for p in points]
    rates, increments, glues = [], [], []
    for i, p in enumerate(points, 1):
        dx = conflicts[i]-conflicts[i-1]
        require(dx > 0 and propagations[i] >= propagations[i-1] and restarts[i] >= restarts[i-1],
                'non-monotonic prefix telemetry')
        rates.append((propagations[i]-propagations[i-1])/dx)
        increments.append(restarts[i]-restarts[i-1])
        glues.append(max(0., float(p['glue'])))
    k = len(rates)//2
    return {
        'propagation_entropy': entropy(rates),
        'glue_entropy': entropy(glues),
        'restart_entropy': entropy(increments),
        'propagation_slope': (rates[-1]-rates[0])/max(1., average(rates)),
        'propagation_curvature': ((average(rates[k:])-2*average(rates[k-2:k])+average(rates[:k-2]))
                                  /max(1., average(rates))) if k >= 3 else 0.,
        'glue_slope': (glues[-1]-glues[0])/max(.1, average(glues)),
    }

ENTROPY_KEYS = ('propagation_entropy','glue_entropy','restart_entropy',
                'propagation_slope','propagation_curvature','glue_slope',
                'repeat_trajectory_variability','prefix_valid')
GRAPH_KEYS = ('graph_degree_entropy','graph_modularity','graph_growth',
              'graph_box_dimension','graph_box_r2','graph_box_valid','graph_mean_degree')


def dynamic_features(monitors):
    require(len(monitors) == 3, 'three monitoring repeats required')
    entries = [prefix(t) for t in monitors]
    if any(entry is None for entry in entries):
        return {k: 0. for k in ENTROPY_KEYS}
    results = {k: average([entry[k] for entry in entries]) for k in entries[0]}
    trajectories = [tuple(int(p['propagations']) for p in t['points'] if int(p['conflict']) <= 1024)
                    for t in monitors]
    if len(set(map(len, trajectories))) != 1:
        results.update(repeat_trajectory_variability=0., prefix_valid=0.)
    else:
        scale = max(1., average([abs(x) for values in trajectories for x in values]))
        divergences = [average([abs(a-b) for a, b in zip(x, y)])/scale
                       for x, y in itertools.combinations(trajectories, 2)]
        results.update(repeat_trajectory_variability=average(divergences), prefix_valid=1.)
    return results