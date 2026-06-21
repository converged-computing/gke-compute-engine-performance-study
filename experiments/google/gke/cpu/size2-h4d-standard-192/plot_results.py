#!/usr/bin/env python3
"""
Plot OSU micro-benchmark results (osu_latency, osu_bw, osu_allreduce) as a
function of message size.

This script is written for the result layout used in
converged-computing/gke-compute-engine-performance-study, e.g.

    experiments/google/gke/cpu/size2-h4d-standard-192/results/osu/*.out

A few notes about that data that this parser handles for you:

  * The benchmark a file contains is NOT reliably encoded in its filename.
    Several files named "osu-2-iter-0-*.out" are actually osu_latency OR
    osu_bw runs, and files named "osu-allreduce-*.out" are just `hostname`
    warm-up jobs with no benchmark data. We therefore classify every file by
    the OSU header line it contains ("# OSU MPI <X> Test"), not by its name.

  * Each benchmark was run several times (8x latency, 8x bandwidth,
    5x allreduce). All repeats share the same set of message sizes, so we
    aggregate them: the solid line is the mean across repeats and the shaded
    band is the min-max envelope. Individual runs are drawn faintly on top.

Usage:
    python plot_osu.py                      # looks in ./results/osu
    python plot_osu.py /path/to/results/osu
    python plot_osu.py /path/to/results/osu --outdir plots --show
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

# ---------------------------------------------------------------------------
# Benchmark definitions
# ---------------------------------------------------------------------------
# Maps the text in the OSU header line to a friendly key plus how to plot it.
# `ylabel`  -> y-axis label
# `ylog`    -> use a log scale on y (good for latencies that span decades)
# `lower_is_better` annotates the plot so a reader knows which way is "good".
BENCHMARKS = {
    "latency": {
        "header_match": "MPI Latency Test",
        "title": "osu_latency  (point-to-point latency)",
        "ylabel": "Latency (us)",
        "ylog": True,
        "lower_is_better": True,
        "color": "#1f77b4",
    },
    "bw": {
        "header_match": "MPI Bandwidth Test",
        "title": "osu_bw  (point-to-point bandwidth)",
        "ylabel": "Bandwidth (MB/s)",
        "ylog": False,
        "lower_is_better": False,
        "color": "#2ca02c",
    },
    "allreduce": {
        "header_match": "MPI Allreduce Latency Test",
        "title": "osu_allreduce  (collective latency)",
        "ylabel": "Avg latency (us)",
        "ylog": True,
        "lower_is_better": True,
        "color": "#d62728",
    },
}

# A data row is "<integer size>  <float value>" and nothing else. The .out
# files also contain JOBSPEC / EVENTLOG JSON blocks, which this rejects.
DATA_ROW = re.compile(r"^\s*(\d+)\s+([0-9]*\.?[0-9]+)\s*$")


def classify(text: str) -> str | None:
    """Return the benchmark key for a file's contents, or None if it has no
    recognizable OSU benchmark data (e.g. the `hostname` warm-up jobs)."""
    for line in text.splitlines():
        if line.startswith("# OSU"):
            for key, spec in BENCHMARKS.items():
                if spec["header_match"] in line:
                    return key
    return None


def parse_data(text: str) -> tuple[np.ndarray, np.ndarray]:
    """Extract (sizes, values) arrays from a single .out file's text."""
    sizes, values = [], []
    for line in text.splitlines():
        m = DATA_ROW.match(line)
        if m:
            sizes.append(int(m.group(1)))
            values.append(float(m.group(2)))
    return np.array(sizes, dtype=float), np.array(values, dtype=float)


def collect(results_dir: Path) -> dict[str, list[tuple[np.ndarray, np.ndarray]]]:
    """Walk every .out file and group parsed (sizes, values) runs by benchmark."""
    runs: dict[str, list] = defaultdict(list)
    files = sorted(results_dir.glob("*.out"))
    if not files:
        sys.exit(f"No .out files found in {results_dir}")

    for f in files:
        text = f.read_text(errors="replace")
        key = classify(text)
        if key is None:
            continue  # warm-up / non-benchmark file
        sizes, values = parse_data(text)
        if sizes.size:
            runs[key].append((sizes, values))
    return runs


def aggregate(run_list: list[tuple[np.ndarray, np.ndarray]]):
    """Given repeats that share a size axis, return sizes, mean, min, max, stack.

    Repeats are aligned on their common set of sizes (intersection) so the
    function is robust even if a run is truncated.
    """
    common = set(run_list[0][0].tolist())
    for sizes, _ in run_list[1:]:
        common &= set(sizes.tolist())
    sizes_sorted = np.array(sorted(common), dtype=float)

    stack = []
    for sizes, values in run_list:
        lookup = dict(zip(sizes.tolist(), values.tolist()))
        stack.append([lookup[s] for s in sizes_sorted])
    stack = np.array(stack)  # shape (n_repeats, n_sizes)

    return sizes_sorted, stack.mean(axis=0), stack.min(axis=0), stack.max(axis=0), stack


def plot_benchmark(key: str, run_list, outdir: Path, show: bool) -> Path | None:
    spec = BENCHMARKS[key]
    sizes, mean, lo, hi, stack = aggregate(run_list)

    # Log message-size axis can't show size 0; drop it (latency reports size 0).
    mask = sizes > 0
    sizes_p, mean_p, lo_p, hi_p = sizes[mask], mean[mask], lo[mask], hi[mask]

    fig, ax = plt.subplots(figsize=(9, 5.5))
    color = spec["color"]

    # individual repeats, faint
    for i, row in enumerate(stack):
        ax.plot(
            sizes[mask], row[mask],
            color=color, alpha=0.18, linewidth=1,
            label="individual runs" if i == 0 else None,
        )

    # min-max envelope + mean
    ax.fill_between(sizes_p, lo_p, hi_p, color=color, alpha=0.18, label="min-max range")
    ax.plot(sizes_p, mean_p, color=color, linewidth=2.2, marker="o",
            markersize=4, label=f"mean of {len(stack)} runs")

    ax.set_xscale("log", base=2)
    if spec["ylog"]:
        ax.set_yscale("log")

    ax.set_xlabel("Message size (bytes)")
    ax.set_ylabel(spec["ylabel"])
    direction = "lower is better" if spec["lower_is_better"] else "higher is better"
    ax.set_title(f"{spec['title']}\nh4d-standard-192, size 2  -  {direction}")
    ax.grid(True, which="both", linestyle=":", alpha=0.5)
    ax.legend(frameon=False, fontsize=9)
    fig.tight_layout()

    outdir.mkdir(parents=True, exist_ok=True)
    out = outdir / f"osu_{key}.png"
    fig.savefig(out, dpi=150)
    print(f"  wrote {out}  ({len(stack)} runs, {sizes_p.size} message sizes)")
    if not show:
        plt.close(fig)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("results_dir", nargs="?", default="results/osu",
                    help="directory containing the OSU *.out files "
                         "(default: results/osu)")
    ap.add_argument("--outdir", default="plots", help="where to write PNGs "
                    "(default: plots)")
    ap.add_argument("--show", action="store_true", help="display the figures")
    args = ap.parse_args()

    results_dir = Path(args.results_dir)
    runs = collect(results_dir)

    if not runs:
        sys.exit(f"No recognizable OSU benchmark data in {results_dir}")

    print(f"Parsed {results_dir}:")
    for key in ("latency", "bw", "allreduce"):
        if key in runs:
            plot_benchmark(key, runs[key], Path(args.outdir), args.show)
        else:
            print(f"  (no {key} data found)")

    if args.show:
        plt.show()


if __name__ == "__main__":
    main()
