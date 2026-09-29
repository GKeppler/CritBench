"""Task-weighted v2 summaries with shared-fixture cluster uncertainty.

Controls are reported separately. Overlapping fixture sets form connected
components, so a cross-fixture task cannot create a fictitious independent
cluster. One cluster cannot estimate between-fixture uncertainty (NaN).
"""
from math import nan, sqrt


def summarize(rows):
    headline = [r for r in rows if not r['floor_control']]
    controls = [r for r in rows if r['floor_control']]
    avg = lambda xs: sum(xs) / len(xs) if xs else nan
    mean = avg([r['score'] for r in headline])
    clusters = []
    for row in headline:
        fixtures = set(row['fixture_ids'])
        if not fixtures:
            raise ValueError('v2 metric requires fixture provenance')
        joined = [row]
        remaining = []
        for keys, members in clusters:
            if fixtures & keys:
                fixtures |= keys
                joined.extend(members)
            else:
                remaining.append((keys, members))
        # Existing components are disjoint, so one pass suffices: any overlap
        # with a newly merged key would already have joined those components.
        clusters = remaining + [(fixtures, joined)]
    n, g = len(headline), len(clusters)
    # Cluster-robust SE of the task-weighted mean with G/(G-1) correction.
    se = (sqrt(g / (g - 1) * sum(sum(r['score'] - mean for r in members)**2
                                for _, members in clusters)) / n
          if g > 1 else nan)
    return {
        'headline_mean': mean,
        'headline_full_success': avg([float(r['success']) for r in headline]),
        'fixture_cluster_stderr': se,
        'fixture_clusters': g,
        'headline_n': n,
        'floor_mean': avg([r['score'] for r in controls]),
        'floor_full_success': avg([float(r['success']) for r in controls]),
        'floor_n': len(controls),
    }
