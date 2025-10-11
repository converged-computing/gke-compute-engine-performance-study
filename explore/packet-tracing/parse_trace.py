import re
import sys
from collections import defaultdict

def parse_function_graph(filepath):
    # ... (the parsing part of the script is the same as the last version) ...
    # Robust regex for process name
    line_regex = re.compile(
        r"^\s*(.+?-\d+)\s+"          # Process name and PID
        r"\[(\d+)\]\s+"              # CPU
        r"(\d+\.\d+):\s+"            # Timestamp
        r"(funcgraph_e\w+):"         # Event type
        r"(.*)$"                     # Rest of the line
    )
    stacks = defaultdict(list)
    function_stats = defaultdict(lambda: {
        "total_time_us": 0.0, "self_time_us": 0.0, "count": 0
    })

    print(f"Parsing '{filepath}'...")
    total_lines = 0; matched_lines = 0
    with open(filepath, 'r') as f:
        for line in f:
            total_lines += 1
            match = line_regex.match(line)
            if not match: continue
            matched_lines += 1
            proc_pid, cpu_str, ts_str, event, rest_of_line = match.groups()
            proc_name = proc_pid.rsplit('-', 1)[0]
            thread_id = (cpu_str, proc_pid)
            timestamp_us = float(ts_str) * 1_000_000

            if event == "funcgraph_entry":
                call_str = rest_of_line.strip()
                if "|" in call_str:
                    call_str = call_str.split('|', 1)[1].strip()
                # More robustly find the function name before the parenthesis
                func_match = re.search(r"(\w+)\s*\((?:\)|.*\)\s*\{?$)", call_str)
                func_name = func_match.group(1) if func_match else call_str.strip()
                
                stacks[thread_id].append({
                    'proc': proc_name, 'func': func_name, 'entry_ts': timestamp_us, 'child_time': 0.0
                })

            elif event == "funcgraph_exit":
                if not stacks[thread_id]: continue
                current_func = stacks[thread_id].pop()
                proc_name, func_name = current_func['proc'], current_func['func']
                total_duration_us = timestamp_us - current_func['entry_ts']
                self_time_us = total_duration_us - current_func['child_time']
                stats_key = (proc_name, func_name)
                stats = function_stats[stats_key]
                stats["total_time_us"] += total_duration_us
                stats["self_time_us"] += self_time_us
                stats["count"] += 1
                if stacks[thread_id]:
                    parent_func = stacks[thread_id][-1]
                    parent_func['child_time'] += total_duration_us
    
    print(f"Parsing complete. Processed {total_lines} lines, matched format on {matched_lines} lines.")
    return function_stats

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: python {sys.argv[0]} <path_to_trace_log>")
        sys.exit(1)

    log_file = sys.argv[1]
    stats = parse_function_graph(log_file)
    
    if not stats:
        print("No function data parsed. Check the log file format.")
        sys.exit(1)

    # --- THE CRITICAL CHANGE IS HERE ---
    # We now sort by 'total_time_us' to see the functions that take the longest overall.
    sorted_stats = sorted(stats.items(), key=lambda item: item[1]['total_time_us'], reverse=True)

    # --- UPDATED REPORT HEADER ---
    print("\n--- Function Profile Report (sorted by TOTAL Time) ---")
    print(f"{'Process Name':<16} | {'Function Name':<35} | {'Total Time (ms)':>15} | {'Self-Time (ms)':>15} | {'Call Count':>12}")
    print("-" * 105)

    for (proc, func), data in sorted_stats[:40]:
        total_time_ms = data['total_time_us'] / 1000
        self_time_ms = data['self_time_us'] / 1000
        print(f"{proc:<16} | {func:<35} | {total_time_ms:15.3f} | {self_time_ms:15.3f} | {data['count']:>12}")
