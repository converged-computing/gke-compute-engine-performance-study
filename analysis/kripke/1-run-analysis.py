#!/usr/bin/env python3

import numpy as np
import pandas as pd
import io
import argparse
import collections
import json
import os
import pandas
import re
import sys

import seaborn as sns
import matplotlib.pyplot as plt

here = os.path.dirname(os.path.abspath(__file__))
analysis_root = os.path.dirname(here)
root = os.path.dirname(analysis_root)
sys.path.insert(0, analysis_root)

import performance_study as ps

sns.set_theme(style="whitegrid", palette="muted")

def get_parser():
    parser = argparse.ArgumentParser(
        description="Run analysis",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--root",
        help="root directory with experiments",
        default=os.path.join(root, "experiments"),
    )
    parser.add_argument(
        "--out",
        help="directory to save parsed results",
        default=os.path.join(here, "data"),
    )
    return parser


def main():
    """
    Find application result files to parse.
    """
    parser = get_parser()
    args, _ = parser.parse_known_args()

    # Output images and data
    outdir = os.path.abspath(args.out)
    indir = os.path.abspath(args.root)
    if not os.path.exists(outdir):
        os.makedirs(outdir)

    # Find input directories
    files = ps.find_inputs(indir, "kripke")
    if not files:
        raise ValueError(f"There are no input files in {indir}")

    # Saves raw data to file
    df, mpi_df, p_df = parse_data(indir, outdir, files)
    plot_results(df, mpi_df, p_df, outdir)


def parse_kripke_foms(item):
    """
    Figures of Merit
    ================

      Throughput:         2.683674e+10 [unknowns/(second/iteration)]
      Grind time :        3.726235e-11 [(seconds/iteration)/unknowns]
      Sweep efficiency :  17.43900 [100.0 * SweepSubdomain time / SweepSolver time]
      Number of unknowns: 4932501504
    """
    metrics = {}
    for line in item.split("\n"):
        if "Grind time" in line:
            parts = [x for x in line.replace(":", "").split(" ") if x]
            metrics["grind_time_seconds"] = float(parts[2])
    return metrics


def add_metadata(mpi_df, exp):
    mpi_df['experiment'] = exp.experiment
    mpi_df['cloud'] = exp.cloud
    mpi_df['env'] = exp.env
    mpi_df['env_type'] = exp.env_type
    mpi_df['nodes'] = exp.size
    return mpi_df

def parse_data(indir, outdir, files):
    """
    Parse filepaths for environment, etc., and results files for data.
    """
    # metrics here will be wall time and wrapped time
    mpi_dfs = []
    profiler_dfs = []
    p = ps.ResultParser("kripke")

    # For flux we can save jobspecs and other event data
    data = {}

    # It's important to just parse raw data once, and then use intermediate
    for filename in files:
        dirname = os.path.basename(filename)
        if ps.skip_result(dirname, filename):
            continue

        if dirname.startswith('_') or "_results" in filename:
            continue
        # Note that aws eks has kripke-8gpu directories, that just
        # distinguishes when we ran a first set of runs just with 8 and
        # then had the larger cluster working. Both data are good.
        # All of these are consistent across studies
        print(filename)
        exp = ps.ExperimentNameParser(filename, indir)
        if exp.prefix not in data:
            data[exp.prefix] = []

        # Set the parsing context for the result data frame
        p.set_context(exp.cloud, exp.env, exp.env_type, exp.size)
        exp.show()

        # Now we can read each result file to get metrics.
        results = list(ps.get_outfiles(filename))
        for result in results:
            duration = None

            item = ps.read_file(result)
            # These are redundant with the flux export
            if "log-" in result:
                continue

            # If this is a flux run, we have a jobspec and events here
            if "JOBSPEC" in item:
                item, duration, metadata = ps.parse_flux_metadata(item)
                data[exp.prefix].append(metadata)

                metrics = parse_kripke_foms(item)
                for metric, value in metrics.items():
                    p.add_result(metric, value)
                p.add_result("duration", duration)
                continue

            # This is a metadata file that has afew metrics of interest
            if "cali-query" in result and "Gj" in result:
                item = json.loads(item)
                p.add_result('sweep_eff', float(item[0]['sweep_eff']))
                p.add_result('throughput', float(item[0]['throughput']))
                continue

            if "cali-query" in result and "T" in result:
                mpi_df = parse_mpi_timeseries(item)
                mpi_df = add_metadata(mpi_df, exp)
                mpi_dfs.append(mpi_df)
                profiler_df = parse_profiler_output(item)
                profiler_df = add_metadata(profiler_df, exp)
                profiler_dfs.append(profiler_df)
                continue

            print(result)
            print("not accounted for - this should not trigger")
            import IPython
            IPython.embed()

    print("Done parsing kripke results!")
    p.df.to_csv(os.path.join(outdir, "kripke-cpu-grind-time-results.csv"))
    ps.write_json(data, os.path.join(outdir, "kripke-cpu-grind-time-parsed.json"))
    
    # Save other dataframes
    mpi_dfs = pandas.concat(mpi_dfs)
    profiler_dfs = pandas.concat(profiler_dfs)    
    mpi_dfs.to_csv(os.path.join(outdir, "kripke-mpi-results.csv"))
    profiler_dfs.to_csv(os.path.join(outdir, "kripke-profiler-results.csv"))
    return p.df, mpi_dfs, profiler_dfs


def parse_profiler_output(raw_output: str):
    """
    Parses the full hierarchical and timeseries data from an MPI profiler
    output string into a single, comprehensive Pandas DataFrame.
    """
    region_cols = [
        'Min time/rank', 'Max time/rank', 'Avg time/rank', 'Total time', 'Node order',
        'Min time/rank (exc)', 'Max time/rank (exc)', 'Avg time/rank (exc)',
        'Total time (exc)', 'spot.channel', 'Calls/rank (min)', 'Calls/rank (avg)',
        'Calls/rank (max)', 'Calls (total)', 'Collectives (max)', 'Msg size (min)',
        'Msg size (avg)', 'Msgs recvd (avg)', 'Msgs recvd (max)', 'Msgs sent (avg)',
        'Msgs sent (max)'
    ]
    
    data_rows = []
    timeseries_pattern = re.compile(r"timeseries\s+(\d+)\s+(\d+)\s+([\d.]+)\s+([\d.]+)")
    path_stack = [""] 

    for line in io.StringIO(raw_output):
        ts_match = timeseries_pattern.search(line)
        if ts_match:
            full_path = "->".join(filter(None, path_stack))
            rank, iterations, time_s, iter_per_s = ts_match.groups()
            data_rows.append({
                'Type': 'timeseries', 'FullPath': full_path, 'Path': 'timeseries',
                'Level': len(path_stack), 'Rank': int(rank), 'Iterations': int(iterations),
                'Time (s)': float(time_s), 'Iter/s': float(iter_per_s)
            })
            continue

        stripped_line = line.strip()
        if not stripped_line or not re.search(r'\d+\.\d+', stripped_line):
            continue
            
        path = stripped_line.split()[0]
        indentation = len(line) - len(line.lstrip(' '))
        level = indentation // 2

        while len(path_stack) > level + 1: path_stack.pop()
        path_stack[level] = path
        full_path = "->".join(filter(None, path_stack[:level+1]))

        line_match = re.match(r'^\s*(\S+)\s+(.*)', stripped_line)
        if not line_match: continue
            
        _, data_str = line_match.groups()
        data_values = re.findall(r'\S+', data_str)
        
        row_data = {'Type': 'regionprofile', 'FullPath': full_path, 'Path': path, 'Level': level}
        
        for i, col_name in enumerate(region_cols):
            if i < len(data_values):
                try: row_data[col_name] = pd.to_numeric(data_values[i])
                except ValueError: row_data[col_name] = data_values[i]
            else: row_data[col_name] = None
        data_rows.append(row_data)

    return pd.DataFrame(data_rows)

def plot_time_breakdown(df: pd.DataFrame, outdir, level: int = 1, top_n: int = 10):
    """
    Plots the average time spent in the top N functions at a specific hierarchy level.
    
    This answers the question: "Where is my program spending the most time?"
    """
    df = df[df.Type != "timeseries"]
    # Sort by average time and take the top N
    for size in df.nodes.unique():
      subset = df[df.nodes == size]
      plt.figure(figsize=(20, 6))
      subset = subset.sort_values(by="Avg time/rank", ascending=False)
      sns.boxplot(data=subset, y='Path', x='Avg time/rank', palette='viridis', hue="experiment")
      plt.title(f'Kripke Functions by Average Time/Rank (N={size})')
      plt.xlabel('Average Time per Rank (s)')
      plt.ylabel('Function / Path')
      plt.tight_layout()
      plt.savefig(os.path.join(outdir, f"kripke-time-breakdown-{size}.svg"))

def plot_rank_distribution(df: pd.DataFrame, outdir, metric: str = 'Time (s)'):
    """
    Visualizes the distribution of a metric across all MPI ranks.
    
    This answers the question: "Is there a load imbalance between my ranks?"
    """
    # Filter for timeseries data which is per-rank
    df = df[df['Type'] == 'timeseries'].copy()
    fig, axes = plt.subplots(4, 2, figsize=(12, 28))
    i=0
    sizes = sorted(df.nodes.unique())
    for size in sizes:
      subset = df[df.nodes == size]
      # Boxplot to show the overall distribution (median, quartiles, outliers)
      sns.boxplot(data=subset, x=metric, ax=axes[i,0], palette='coolwarm', hue="experiment", legend=None)
      axes[i,0].set_title(f'Overall Distribution of "{metric}" Across All Ranks (Size {size})')
    
      # Line plot to show the performance of each individual rank
      sns.lineplot(data=subset, x='Rank', y=metric, ax=axes[i,1], marker='o', hue="experiment")
      axes[i,1].set_title(f'"{metric}" per Rank')
      if i==2:
          axes[i,1].set_xlabel('MPI Rank')
      else:
          axes[i,1].set_ylabel("")
      axes[i,1].set_ylabel(metric)
      axes[i,1].grid(True, linestyle='--', alpha=0.6)
      i+=1
    
    plt.tight_layout()
    plt.savefig(os.path.join(outdir, "kripke-rank-distribution.svg"))
    plt.savefig(os.path.join(outdir, "kripke-rank-distribution.png"))

def plot_inclusive_exclusive_time(df: pd.DataFrame, outdir, level: int = 2, top_n: int = 10):
    """
    Compares the inclusive vs. exclusive time for top functions.
    
    This answers the question: "Is a function slow because of its own work (exclusive)
    or because of the functions it calls (inclusive)?"
    """
    for level in df.Level.unique():
        subset = df[(df['Type'] == 'regionprofile') & (df['Level'] == level)].copy()
        subset = subset.sort_values(by='Avg time/rank', ascending=False)
    
        # Rename columns for clarity in the plot legend
        subset.rename(columns={
        'Avg time/rank': 'Inclusive Time',
        'Avg time/rank (exc)': 'Exclusive Time'
        }, inplace=True)
    
        # Melt the dataframe to make it "long", which is ideal for seaborn's hue
        melted_df = subset.melt(
        id_vars='Path', 
        value_vars=['Inclusive Time', 'Exclusive Time'],
        var_name='Time Type', 
        value_name='Average Time (s)',
        )
    
        plt.figure(figsize=(10, 6))
        sns.barplot(data=melted_df, y='Path', x='Average Time (s)', hue='Time Type', palette='muted')
        plt.title(f'Inclusive vs. Exclusive Time (Level {level})')
        plt.xlabel('Average Time per Rank (s)')
        plt.ylabel('Function / Path')
        plt.tight_layout()
        plt.savefig(os.path.join(outdir, f"kripke-inclusive-exclusive-time-{level}.svg"))
        plt.savefig(os.path.join(outdir, f"kripke-inclusive-exclusive-time-{level}.png"))

def plot_metric_correlation(df: pd.DataFrame, outdir, x_metric: str, y_metric: str):
    """
    Creates a scatter plot to see the relationship between two metrics.
    
    This can answer questions like: "Does sending more messages correlate with longer times?"
    """    
    subset = df[df['Type'] == 'regionprofile'].dropna(subset=[x_metric, y_metric]).copy()    
    plt.figure(figsize=(10, 6))
    sns.scatterplot(data=subset, x=x_metric, y=y_metric, hue='Path', palette='deep', s=60)
    plt.title(f'Correlation between "{x_metric}" and "{y_metric}"')
    plt.xlabel(x_metric)
    plt.ylabel(y_metric)
    plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left', borderaxespad=0)
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.tight_layout()
    plt.savefig(os.path.join(outdir, "kripke-metric-correlation.svg"))

    # 4. Sort by the new metric and take the top N most "expensive" functions
    for size in subset.nodes.unique():
        ssubset = subset[subset.nodes == size]
        print(ssubset.columns)
        if ssubset.shape[0] == 0:
            continue

        # just normalize by that?
        ssubset['Time per Call (s)'] = ssubset['Total time'] / ssubset['Calls (total)']
    
        # Replace any potential infinite values if they sneak in
        ssubset.replace([np.inf, -np.inf], np.nan, inplace=True)
        ssubset.dropna(subset=['Time per Call (s)'], inplace=True)

        ssubset = ssubset.sort_values(by='Time per Call (s)', ascending=False)
    
        # 5. Create the plot
        plt.figure(figsize=(12, 8))
    
        # A bar plot is best for comparing the cost of different functions
        ax = sns.barplot(data=ssubset, y='Path', x='Time per Call (s)', palette='plasma', hue="experiment")
    
        # Add text labels to the bars for exact values
        ax.bar_label(ax.containers[0], fmt='%.2e', padding=3) # 'e' for scientific notation

        plt.title(f'Most Expensive Functions by Time per Call (N={size})')
        plt.xlabel('Average Time per Call (seconds)')
        plt.ylabel('Function / Path')
        plt.xscale('log') # Log scale is often essential as costs can vary by orders of magnitude
        plt.tight_layout()
    
        os.makedirs(outdir, exist_ok=True)
        output_path = os.path.join(outdir, f"kripke-cost-per-call-size-{size}.svg")
        plt.savefig(output_path)
        plt.tight_layout()

def parse_profiler_output(raw_output):
    """
    Parses the full hierarchical and timeseries data from an MPI profiler
    output string into a single, comprehensive Pandas DataFrame.

    Args:
        raw_output: A string containing the entire profiler output.

    Returns:
        A Pandas DataFrame with all parsed profiler data.
    """
    import pandas as pd
    import io

    # Define the column headers based on the file structure. This is more robust
    # than trying to parse the multi-line header.
    region_cols = [
        'Min time/rank', 'Max time/rank', 'Avg time/rank', 'Total time', 'Node order',
        'Min time/rank (exc)', 'Max time/rank (exc)', 'Avg time/rank (exc)',
        'Total time (exc)', 'spot.channel', 'Calls/rank (min)', 'Calls/rank (avg)',
        'Calls/rank (max)', 'Calls (total)', 'Collectives (max)', 'Msg size (min)',
        'Msg size (avg)', 'Msgs recvd (avg)', 'Msgs recvd (max)', 'Msgs sent (avg)',
        'Msgs sent (max)'
    ]
    
    timeseries_cols = ['Iterations', 'Time (s)', 'Iter/s']

    data_rows = []
    
    # Regex for timeseries lines is specific
    timeseries_pattern = re.compile(r"timeseries\s+(\d+)\s+(\d+)\s+([\d.]+)\s+([\d.]+)")
    
    # A list to keep track of the current path hierarchy based on indentation
    path_stack = [""] 

    for line in io.StringIO(raw_output):
        # --- 1. Handle Timeseries Lines ---
        ts_match = timeseries_pattern.search(line)
        if ts_match:
            full_path = "->".join(filter(None, path_stack))
            rank, iterations, time_s, iter_per_s = ts_match.groups()
            
            data_rows.append({
                'Type': 'timeseries',
                'FullPath': full_path,
                'Path': 'timeseries',
                'Level': len(path_stack),
                'Rank': int(rank),
                'Iterations': int(iterations),
                'Time (s)': float(time_s),
                'Iter/s': float(iter_per_s)
            })
            continue

        # --- 2. Handle Hierarchical Region Profile Lines ---
        
        # Strip leading/trailing whitespace to analyze content
        stripped_line = line.strip()
        if not stripped_line or not re.search(r'\d+\.\d+', stripped_line):
            # Skip header, footer, or lines without floating point numbers (our data marker)
            continue
            
        # The first word is the path/function name
        path = stripped_line.split()[0]
        
        # Calculate indentation level (2 spaces per level is common)
        indentation = len(line) - len(line.lstrip(' '))
        level = indentation // 2

        # Update the path stack to maintain the current hierarchy
        while len(path_stack) > level + 1:
            path_stack.pop()
        if len(path_stack) <= level:
             path_stack.append("") # Should not happen with well-formed input
        path_stack[level] = path
        
        # The full path is the joined stack up to the current level
        full_path = "->".join(filter(None, path_stack[:level+1]))

        # Regex to find the path and the subsequent data values
        # This captures the path and then finds all remaining non-whitespace chunks
        line_match = re.match(r'^\s*(\S+)\s+(.*)', stripped_line)
        if not line_match:
            continue
            
        _, data_str = line_match.groups()
        data_values = re.findall(r'\S+', data_str)
        
        # Create a dictionary for the current row
        row_data = {
            'Type': 'regionprofile',
            'FullPath': full_path,
            'Path': path,
            'Level': level,
        }
        
        # Populate the dictionary by zipping column names with parsed values
        # This handles lines with fewer columns gracefully
        for i, col_name in enumerate(region_cols):
            if i < len(data_values):
                # Try to convert to numeric, otherwise keep as string
                try:
                    row_data[col_name] = pd.to_numeric(data_values[i])
                except ValueError:
                    row_data[col_name] = data_values[i]
            else:
                row_data[col_name] = None
        
        data_rows.append(row_data)

    # Create the final DataFrame from the list of all parsed rows
    df = pd.DataFrame(data_rows)    
    return df


def parse_mpi_timeseries(raw_output):
    """
    Parses the timeseries data from an MPI profiler output string into a
    Pandas DataFrame.

    This function specifically looks for lines containing 'timeseries' and extracts
    the rank and performance metrics.

    Args:
        raw_output: A string containing the entire profiler output.

    Returns:
        A Pandas DataFrame with the parsed timeseries data.
    """
    # A list to store the parsed data from each relevant line
    data_rows = []
    
    # A regex pattern to robustly capture the numbers from the timeseries lines.
    # It looks for the word "timeseries" followed by four number groups.
    # Groups: 1=Rank, 2=Iterations, 3=Time(s), 4=Iter/s
    pattern = re.compile(r"timeseries\s+(\d+)\s+(\d+)\s+([\d.]+)\s+([\d.]+)")
    
    current_path = "unknown"
    
    # Use io.StringIO to treat the multi-line string like a file for easy iteration
    for line in io.StringIO(raw_output):
        line = line.strip()
        
        # Heuristic to find the parent path: if a line is at the far left
        # and does not start with '|-' or spaces, it's likely a path name.
        if not line.startswith(('|-', ' ')):
            current_path = line.split()[0] # e.g., 'solve' or 'main'
            continue
            
        # Search for a match with our timeseries pattern
        match = pattern.search(line)
        
        if match:
            # If a match is found, extract the captured groups
            rank = int(match.group(1))
            iterations = int(match.group(2))
            time_s = float(match.group(3))
            iter_per_s = float(match.group(4))
            
            # Append the extracted data as a dictionary to our list
            data_rows.append({
                'Path': current_path,
                'Rank': rank,
                'Iterations': iterations,
                'Time (s)': time_s,
                'Iter/s': iter_per_s
            })

    # If no data was found, return an empty DataFrame with the expected columns
    if not data_rows:
        return pandas.DataFrame(columns=['Path', 'Rank', 'Iterations', 'Time (s)', 'Iter/s'])
        
    # Convert the list of dictionaries into a Pandas DataFrame
    df = pandas.DataFrame(data_rows)    
    return df

def plot_results(df, mpi_df, p_df, outdir):
    """
    Plot analysis results
    """
    # Make an image outdir
    img_outdir = os.path.join(outdir, "img")
    if not os.path.exists(img_outdir):
        os.makedirs(img_outdir)

    # We are going to put the plots together, and the colors need to match!
    cloud_colors = {}
    for cloud in df.experiment.unique():
        cloud_colors[cloud] = ps.match_color(cloud)

    # Within a setup, compare between experiments for GPU and cpu
    for env in df.env_type.unique():
        subset = df[df.env_type == env]

        # Make a plot for each metric
        for metric in subset.metric.unique():
            metric_df = subset[subset.metric == metric]
            metric = metric.replace('_seconds', '')
            title = " ".join([x.capitalize() for x in metric.split("_")])
            if "grind" not in metric.lower():
                continue

            # Note that the Y label is hard coded because we just have one metric
            ps.make_plot(
                metric_df,
                title=f"Kripke {title} ({env.upper()})",
                ydimension="value",
                plotname=f"kripke-grind-time-{env}",
                xdimension="nodes",
                palette=cloud_colors,
                outdir=img_outdir,
                hue="experiment",
                xlabel="Nodes",
                # hue_order=hue_order,
                order=[4, 8, 16, 32, 64, 128],
                ylabel="(seconds/iteration)/unknowns",
                do_round=False,
                log_scale=True,
                height=3.8,
                width=4,
            )

        print(f"Total number of CPU datum: {metric_df.shape[0]}")

    #import IPython
    #IPython.embed()
    plot_time_breakdown(p_df, img_outdir, level=1)
    
    print("\n--- 2. Generating Rank Distribution Plot ---")
    #plot_rank_distribution(p_df, img_outdir, metric='Time (s)')

    print("\n--- 3. Generating Inclusive vs. Exclusive Time Plot ---")
    # Dive deeper into the `solve` function to see its components
    plot_inclusive_exclusive_time(p_df, img_outdir, level=3)

    print("\n--- 4. Generating Metric Correlation Plot ---")
    # See if there's a relationship between total time and total calls
    plot_metric_correlation(p_df, outdir=img_outdir, x_metric='Calls (total)', y_metric='Total time')


if __name__ == "__main__":
    main()
