#!/bin/bash

# Initialize variables
NUM_PMS=0
CONFIG_FILE="src/config.py"  # Default config file
TRACE_FILE=""                # Trace file
PROFILE=0                    
DEBUG=0

# Parse the command-line arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    -P)
      NUM_PMS=$2
      shift 2  # Shift past the flag and its argument
      ;;
    --config)
      CONFIG_FILE=$2
      shift 2  # Shift past the flag and its argument
      ;;
    --trace)
      TRACE_FILE=$2
      shift 2  # Shift past the flag and its argument
      ;;
    --profile)
      PROFILE=1
      shift    # Shift past the flag
      ;;
    -*)
      echo "Invalid option: $1" >&2
      exit 1
      ;;
    *)
      shift  # Skip unrecognized arguments
      ;;
  esac
done

# Print the config file in use
echo "Running with config file: $CONFIG_FILE"

# Print the trace file if provided
if [ -n "$TRACE_FILE" ]; then
  echo "Using trace file: $TRACE_FILE"
fi

# Print profiling status
if [ "$PROFILE" -eq 1 ]; then
  echo "Profiling is enabled. Simulation will run with line_profiler."
fi

# Set environment variable to disable color output
export NO_COLOR=1

# Clean up previous simulation files
rm -rf ./simulation/model_input_main         \
       ./simulation/model_output_main        \
       ./simulation/model_input_mini         \
       ./simulation/model_output_mini        \
       ./simulation/model_input_migration    \
       ./simulation/model_output_migration   \
       ./simulation/pm_manager               \
       ./simulation/migration_schedule       \
       ./simulation/simulation_output

# Import the necessary variables from the Python config file
INITIAL_PMS_FILE=$(python3 -c "
import os
import sys
import importlib.util
try:
    spec = importlib.util.spec_from_file_location('config', '$CONFIG_FILE')
    config = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(config)
    print(config.INITIAL_PMS_FILE)
except Exception as e:
    print(f'Error loading config: {e}', file=sys.stderr)
    exit(1)
")

# Check if INITIAL_PMS_FILE was successfully fetched
if [ -z "$INITIAL_PMS_FILE" ]; then
    echo "Error: Failed to retrieve INITIAL_PMS_FILE from the configuration."
    exit 1
fi

# Function to launch main.py with or without profiling
launch_simulation() {
    if [ "$PROFILE" -eq 1 ]; then
        # Check if kernprof is installed
        if ! command -v kernprof &> /dev/null; then
            echo "Error: kernprof (line_profiler) is not installed."
            echo "Install it using: pip install line_profiler"
            exit 1
        fi

        profile_folder="profiling"
        profile_file="simulation_$(date +%Y%m%d%H%M%S).lprof"
        
        # Create the profile folder if it doesn't exist
        mkdir -p "$profile_folder"

        # Launch main.py with line_profiler
        echo "Launching main.py with line_profiler..."
        kernprof -l src/main.py --config "$CONFIG_FILE" --trace "$TRACE_FILE"

        # Check if profiling was successful
        if [ $? -ne 0 ]; then
            echo "Error: Profiling main.py failed."
            exit 1
        fi

        # Move the profiling results to the logs folder
        mv main.py.lprof "$profile_folder/$profile_file"

        # Inspect the profiling results
        python3 -m line_profiler -rmt "$profile_folder/$profile_file"
    else
        # Launch main.py normally
        python3 src/main.py --config "$CONFIG_FILE" --trace "$TRACE_FILE"
    fi
}

# Use the number of PMs from the -P flag if provided, otherwise ask the user
if [ "$NUM_PMS" -gt 0 ]; then
    echo "Generating $NUM_PMS physical machines..."
    python3 src/main.py --config "$CONFIG_FILE" --trace "$TRACE_FILE" --generate-pms "$NUM_PMS"
else 
    if [ -f "$INITIAL_PMS_FILE" ]; then
        echo "Initial PM file found: $INITIAL_PMS_FILE"
        launch_simulation
    else
        echo "Initial PM file not found at $INITIAL_PMS_FILE."
        echo -n "How many physical machines do you want to simulate? "
        read num_pms

        if ! [[ "$num_pms" =~ ^[0-9]+$ ]]; then
            echo "Error: Please enter a valid number of physical machines."
            exit 1
        fi

        # Launch the data generator with the user-provided input
        echo "Generating $num_pms physical machines..."
        python3 src/main.py --config "$CONFIG_FILE" --trace "$TRACE_FILE" --generate-pms "$num_pms"
    fi
fi
