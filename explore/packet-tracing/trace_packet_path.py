import re
import sys

def find_and_trace_path(filepath, start_event_keyword, process_filter=None, time_window_ms=5.0):
    """
    Finds the first occurrence of a start event and prints the subsequent
    events on the same thread within a time window to trace a single path.
    This version uses a robust regex to handle various process names like '<idle>-0'.

    Args:
        filepath (str): The path to the trace log file.
        start_event_keyword (str): A simple keyword (like 'icmp_rcv') to find.
        process_filter (str, optional): Only start a trace from this process.
        time_window_ms (float): How many milliseconds after the start event to trace.
    """
    # This regex is much more robust for the process/pid part.
    # It matches any characters non-greedily up to the final "-<digits>"
    line_regex = re.compile(
        r"^\s*(.+?-\d+)\s+"          # Process name and PID (e.g., '<idle>-0')
        r"\[(\d+)\]\s+"              # CPU (e.g., [012])
        r"(\d+\.\d+):\s+"            # Timestamp (e.g., 2901.263784:)
        r"(.*)$"                     # The entire rest of the line
    )

    start_event_found = False
    trace_cpu = None
    start_timestamp = 0.0
    time_window_s = time_window_ms / 1000.0

    lines_matched = 0
    total_lines = 0

    print(f"--- Searching for start event containing '{start_event_keyword}' in '{filepath}' ---\n")

    try:
        with open(filepath, 'r') as f:
            for line_num, line in enumerate(f, 1):
                total_lines += 1
                match = line_regex.match(line)
                if not match:
                    continue
                
                lines_matched += 1
                proc_pid, cpu, ts_str, rest_of_line = match.groups()
                timestamp = float(ts_str)

                if not start_event_found:
                    # Check if this line is our starting trigger
                    if start_event_keyword in rest_of_line:
                        if process_filter and process_filter not in proc_pid:
                            continue

                        start_event_found = True
                        trace_cpu = cpu
                        start_timestamp = timestamp
                        print("--- Found Start Event (Line {}) ---".format(line_num))
                        print(f"PATH TRACE (CPU: {trace_cpu}, Max Duration: {time_window_ms} ms)")
                        print("-" * 60)
                        print(line.strip())
                else:
                    # We have our start event, now we trace subsequent events
                    if cpu == trace_cpu:
                        if timestamp - start_timestamp < time_window_s:
                            print(line.strip())
                        else:
                            print("-" * 60)
                            print(f"--- End of Trace (Time window exceeded after processing {line_num} lines) ---")
                            return

        print(f"\nProcessed {total_lines} total lines, matched format on {lines_matched} lines.")
        if not start_event_found:
            print("Could not find a matching start event in the trace file.")
        else:
            print("-" * 60)
            print("--- End of Trace (End of file reached) ---")
            
    except FileNotFoundError:
        print(f"Error: File not found at '{filepath}'")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(f"Usage: python {sys.argv[0]} <path_to_trace_log> <start_event_keyword> [process_filter]")
        sys.exit(1)

    log_file = sys.argv[1]
    start_keyword = sys.argv[2]
    proc_filter = sys.argv[3] if len(sys.argv) > 3 else None
    
    find_and_trace_path(log_file, start_keyword, proc_filter)
