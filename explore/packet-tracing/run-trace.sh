#!/bin/bash
# Run this script as root on the receiving node

# 1. Setup
mount -t debugfs none /sys/kernel/debug &>/dev/null
cd /sys/kernel/debug/tracing
echo 0 > tracing_on
echo nop > current_tracer
echo > trace
echo function_graph > current_tracer
echo > set_graph_function

# 2. Apply filters
echo "ip_*" > set_graph_function
# ... add other filters as before ...
echo "vxlan_*" >> set_graph_function 2>/dev/null

echo "Tracer configured. Starting trace..."
echo "Run your 'ping' or other network command from the sender now."

# 3. Trace
echo 1 > tracing_on
sleep 10 # Trace for 10 seconds
echo 0 > tracing_on

echo "Trace complete."

# 4. Save the output to a file in the user's home directory or /tmp
# Assuming the script is run with 'sudo', find the original user's home dir
ORIGINAL_USER=$(logname)
HOME_DIR=$(getent passwd $ORIGINAL_USER | cut -d: -f6)
OUTPUT_FILE="${HOME_DIR:-/tmp}/ftrace_output.log"

echo "Saving trace to ${OUTPUT_FILE}..."
cat trace > "${OUTPUT_FILE}"
echo "Done."
