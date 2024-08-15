#!/bin/bash

# Clean up
rm -rf ./simulation/model_input        \
       ./simulation/model_output       \
       ./simulation/simulation_output  \
       ./simulation/overload
clear

# Import the necessary variables from the Python config file
INITIAL_PMS_FILE=$(python3 -c "
import os
from src.config import INITIAL_PMS_FILE
print(INITIAL_PMS_FILE)
")

# Check if the initial pm file exists
if [ -f "$INITIAL_PMS_FILE" ]; then
    echo "Initial PM file found: $INITIAL_PMS_FILE"
    python3 src/simulation.py
else
    # Check if the data generator script exists
    if [ -f "data_generator/data_generator.py" ]; then
        echo "Initial PM file not found at $INITIAL_PMS_FILE."
        echo -n "How many physical machines do you want to simulate? "
        read num_pms

        # Get the directory of the INITIAL_PMS_FILE
        DATA_FOLDER=$(dirname "$INITIAL_PMS_FILE")

        # Launch the data generator with the user-provided input
        echo "Launching data generator..."
        python3 data_generator/data_generator.py --simulation $num_pms "$INITIAL_PMS_FILE"
    else
        echo "Error: Initial PM file not found."
        exit 1
    fi

    # Now, run the simulation after generating the data
    python3 src/simulation.py
fi


