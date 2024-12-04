#!/bin/bash

# Define the ranges for parameters to be modified
USE_REAL_DATA=True
USE_SPEED_ALGORITHM=False

USE_RANDOM_SEED_VALUES=(True)
SEED_NUMBER_VALUES=($(seq 1 1))  # This creates a range from 1 to 20
NEW_VMS_PER_STEP_VALUES=(20)
NEW_VMS_PATTERN_VALUES=(
                        'constant'
                        'poisson'
                        'burst'
                        'heavy_tail'
                        'sinusoidal'
                        'random_spikes'
                        )

MASTER_MODEL_VALUES=(
                    'main' 
                    'mini'
                    'hybrid'
                    'compound'
                    'multilayer'
                    'first_fit'
                    'best_fit' 
                    'guazzone'
                    'shi_OM'
                    'shi_AC'
                    'shi_PU'
                    )
WORKLOAD_NAME_VALUES=(
  # 'Chameleon-New-2020'
  # 'Chameleon-Legacy-2020'
  # 'LLNL-Thunder-2007'
  # 'METACENTRUM-2009'
  # 'PIK-IPLEX-2009'
  # 'RICC-2010'
  # 'TU-Delft-2007'
  # 'UniLu-Gaia-2014'
  # 'Intel-Netbatch-2012-A'
  # 'Intel-Netbatch-2012-B'
  'Intel-Netbatch-2012-C'
  'Intel-Netbatch-2012-D'
  # 'Azure-2020'
)

# Filter values
MAIN_MODEL_MAX_PMS=20
MINI_MODEL_MAX_PMS=50
MIGRATION_MODEL_MAX_FRAGMENTED_PMS=20
FAILED_MIGRATIONS_LIMIT=5
PM_MANAGER_MAX_PMS=10

# CPLEX parameters
hard_time_limit_main_factor=2
hard_time_limit_mini_factor=2

if [ "$USE_REAL_DATA" = "True" ]; then
  USE_RANDOM_SEED_VALUES=(False)
  SEED_NUMBER_VALUES=(1)
  NEW_VMS_PER_STEP_VALUES=(1)
  NEW_VMS_PATTERN_VALUES=('constant')
else
  WORKLOAD_NAME_VALUES=('synthetic')
fi

TOTAL_TESTS=$(( ${#USE_RANDOM_SEED_VALUES[@]} * ${#SEED_NUMBER_VALUES[@]} * ${#WORKLOAD_NAME_VALUES[@]} * ${#MASTER_MODEL_VALUES[@]} * ${#NEW_VMS_PER_STEP_VALUES[@]} * ${#NEW_VMS_PATTERN_VALUES[@]} ))
CURRENT_TEST=0

# Function to set NUM_TIME_STEPS and TIME_STEP based on WORKLOAD_NAME
function set_parameters() {
  case "$WORKLOAD_NAME" in
    "Azure-2020")
      TIME_STEP=5
      NUM_TIME_STEPS=10000
      ;;
    "Chameleon-Legacy-2020")
      TIME_STEP=50
      NUM_TIME_STEPS=700000
      ;;
    "Chameleon-New-2020")
      TIME_STEP=50
      NUM_TIME_STEPS=50000000
      ;;
    "Intel-Netbatch-2012-A")
      TIME_STEP=10
      NUM_TIME_STEPS=5000
      ;;
    "Intel-Netbatch-2012-B")
      TIME_STEP=10
      NUM_TIME_STEPS=5000
      ;;
    "Intel-Netbatch-2012-C")
      TIME_STEP=10
      NUM_TIME_STEPS=5000
      ;;
    "Intel-Netbatch-2012-D")
      TIME_STEP=10
      NUM_TIME_STEPS=5000
      ;;
    "LLNL-Thunder-2007")
      TIME_STEP=50
      NUM_TIME_STEPS=20000
      ;;
    "METACENTRUM-2009")
      TIME_STEP=50
      NUM_TIME_STEPS=100000
      ;;
    "PIK-IPLEX-2009")
      TIME_STEP=50
      NUM_TIME_STEPS=100000
      ;;
    "RICC-2010")
      TIME_STEP=50
      NUM_TIME_STEPS=5000
      ;;
    "TU-Delft-2007")
      TIME_STEP=50
      NUM_TIME_STEPS=150000
      ;;
    "UniLu-Gaia-2014")
      TIME_STEP=50
      NUM_TIME_STEPS=100000
      ;;
      
    *)
      TIME_STEP=20  # Default value
      NUM_TIME_STEPS=1500  # Default value
      ;;
  esac
}

# Create a temporary directory for modified config files
TEMP_DIR=$(mktemp -d)

# Check if the temp directory was created successfully
if [ ! -d "$TEMP_DIR" ]; then
  echo "Failed to create temporary directory."
  exit 1
fi

# Create a log_tests directory if it doesn't exist
mkdir -p log_tests

ORIGINAL_CONFIG_FILE="src/config.py"
ORIGINAL_WEIGHTS_FILE="src/weights.py"

# Generate a timestamp for the results file
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

# File to store final results
RESULTS_FILE="log_tests/final_results_${TIMESTAMP}.txt"

clear; 

# Loop through each combination of parameters
for USE_RANDOM_SEED in "${USE_RANDOM_SEED_VALUES[@]}"; do
  for SEED_NUMBER in "${SEED_NUMBER_VALUES[@]}"; do
    for WORKLOAD_NAME in "${WORKLOAD_NAME_VALUES[@]}"; do
      set_parameters
      for MASTER_MODEL in "${MASTER_MODEL_VALUES[@]}"; do
        for NEW_VMS_PATTERN in "${NEW_VMS_PATTERN_VALUES[@]}"; do
          for NEW_VMS_PER_STEP in "${NEW_VMS_PER_STEP_VALUES[@]}"; do
            INITIAL_PMS_FILE="simulation/simulation_input/physical_machines_${WORKLOAD_NAME}.dat"

            # Define the temporary config file path
            TEMP_CONFIG_FILE="$TEMP_DIR/config_${USE_RANDOM_SEED}_${SEED_NUMBER}_${WORKLOAD_NAME}_${TIME_STEP}_${NEW_VMS_PER_STEP}_${NUM_TIME_STEPS}_${MASTER_MODEL}.py"

            # Copy the original config file to the temporary config file
            cp "$ORIGINAL_CONFIG_FILE" "$TEMP_CONFIG_FILE"

            # Verify that the config file was copied successfully
            if [ ! -f "$TEMP_CONFIG_FILE" ]; then
              echo "Failed to create temporary config file: $TEMP_CONFIG_FILE"
              exit 1
            fi

            hard_time_limit_main=$(echo "scale=2; $TIME_STEP / $hard_time_limit_main_factor" | bc)
            hard_time_limit_mini=$(echo "scale=2; $TIME_STEP / $hard_time_limit_mini_factor" | bc)

            # Modify the copied config file with the new parameter values
            sed -i "s/^PRINT_TO_CONSOLE = .*/PRINT_TO_CONSOLE = False/" "$TEMP_CONFIG_FILE"
            sed -i "s/^SAVE_LOGS = .*/SAVE_LOGS = False/" "$TEMP_CONFIG_FILE"

            sed -i "s/^USE_REAL_DATA = .*/USE_REAL_DATA = $USE_REAL_DATA/" "$TEMP_CONFIG_FILE"
            sed -i "s/^USE_SPEED_ALGORITHM = .*/USE_SPEED_ALGORITHM = $USE_SPEED_ALGORITHM/" "$TEMP_CONFIG_FILE"
            sed -i "s/^USE_RANDOM_SEED = .*/USE_RANDOM_SEED = $USE_RANDOM_SEED/" "$TEMP_CONFIG_FILE"
            sed -i "s/^SEED_NUMBER = .*/SEED_NUMBER = $SEED_NUMBER/" "$TEMP_CONFIG_FILE"
            sed -i "s/^TIME_STEP = .*/TIME_STEP = $TIME_STEP/" "$TEMP_CONFIG_FILE"
            sed -i "s/^NEW_VMS_PER_STEP = .*/NEW_VMS_PER_STEP = $NEW_VMS_PER_STEP/" "$TEMP_CONFIG_FILE"
            sed -i "s/^NEW_VMS_PATTERN = .*/NEW_VMS_PATTERN = '$NEW_VMS_PATTERN'/" "$TEMP_CONFIG_FILE"
            sed -i "s/^NUM_TIME_STEPS = .*/NUM_TIME_STEPS = $NUM_TIME_STEPS/" "$TEMP_CONFIG_FILE"
            sed -i "s/^MASTER_MODEL = .*/MASTER_MODEL = '$MASTER_MODEL'/" "$TEMP_CONFIG_FILE"
            sed -i "s/^WORKLOAD_NAME = .*/WORKLOAD_NAME = '$WORKLOAD_NAME'/" "$TEMP_CONFIG_FILE"

            sed -i "s/^MAIN_MODEL_MAX_PMS = .*/MAIN_MODEL_MAX_PMS = $MAIN_MODEL_MAX_PMS/" "$TEMP_CONFIG_FILE"
            sed -i "s/^MINI_MODEL_MAX_PMS = .*/MINI_MODEL_MAX_PMS = $MINI_MODEL_MAX_PMS/" "$TEMP_CONFIG_FILE"
            sed -i "s/^MIGRATION_MODEL_MAX_FRAGMENTED_PMS = .*/MIGRATION_MODEL_MAX_FRAGMENTED_PMS = $MIGRATION_MODEL_MAX_FRAGMENTED_PMS/" "$TEMP_CONFIG_FILE"
            sed -i "s/^PM_MANAGER_MAX_PMS = .*/PM_MANAGER_MAX_PMS = $PM_MANAGER_MAX_PMS/" "$TEMP_CONFIG_FILE"
            sed -i "s/^FAILED_MIGRATIONS_LIMIT = .*/FAILED_MIGRATIONS_LIMIT = $FAILED_MIGRATIONS_LIMIT/" "$TEMP_CONFIG_FILE"

            sed -i "s/^HARD_TIME_LIMIT_MAIN = .*/HARD_TIME_LIMIT_MAIN = $hard_time_limit_main/" "$TEMP_CONFIG_FILE"
            sed -i "s/^HARD_TIME_LIMIT_MINI = .*/HARD_TIME_LIMIT_MINI = $hard_time_limit_mini/" "$TEMP_CONFIG_FILE"

            # Define output log file for capturing run.sh output
            OUTPUT_LOG_FILE="$TEMP_DIR/output_${USE_RANDOM_SEED}_${SEED_NUMBER}_${WORKLOAD_NAME}_${TIME_STEP}_${NEW_VMS_PER_STEP}_${NEW_VMS_PATTERN}_${NUM_TIME_STEPS}_${MASTER_MODEL}.log"

            CURRENT_TEST=$((CURRENT_TEST + 1))

            # Capture the start time
            START_TIME=$(date +%s)

            if [ ! -f "$INITIAL_PMS_FILE" ]; then
              echo "Initial PM file not found at $INITIAL_PMS_FILE."

              echo "Running test $CURRENT_TEST of $TOTAL_TESTS..."
              echo "Workload name: $WORKLOAD_NAME, Master model: $MASTER_MODEL"
              echo ""

              # Run the simulation with the specified number of physical machines
              ./run.sh -P $NUM_PHYSICAL_MACHINES --config "$TEMP_CONFIG_FILE" > "$OUTPUT_LOG_FILE"
            else 

              echo "Running test $CURRENT_TEST of $TOTAL_TESTS..."
              echo "Workload name: $WORKLOAD_NAME, Master model: $MASTER_MODEL"
              echo ""

              # Run the simulation 
              ./run.sh --config "$TEMP_CONFIG_FILE" > "$OUTPUT_LOG_FILE"
            fi

            # Capture the end time
            END_TIME=$(date +%s)

            # Calculate the duration
            DURATION=$((END_TIME - START_TIME))

            # Clean ANSI escape codes from the output log file and save cleaned output to a temporary file
            CLEANED_OUTPUT_LOG_FILE="${OUTPUT_LOG_FILE}.clean"
            sed -r "s/\x1B\[[0-9;]*[mG]//g" "$OUTPUT_LOG_FILE" > "$CLEANED_OUTPUT_LOG_FILE"

            # Extract the last occurrence of Total Revenue and Total Costs from the cleaned output log file
            TOTAL_REVENUE=$(grep "Total Revenue Gained from Completed VMs" "$CLEANED_OUTPUT_LOG_FILE" | tail -n 1 | awk -F': ' '{print $2}')
            TOTAL_COSTS=$(grep "Total Costs Incurred" "$CLEANED_OUTPUT_LOG_FILE" | tail -n 1 | awk -F': ' '{print $2}')
            TOTAL_PM_LOAD_COST=$(grep "Total PM Load Cost" "$CLEANED_OUTPUT_LOG_FILE" | tail -n 1 | awk -F': ' '{print $2}')
            TOTAL_PM_SWITCH_COST=$(grep "Total PM Switch Cost" "$CLEANED_OUTPUT_LOG_FILE" | tail -n 1 | awk -F': ' '{print $2}')
            TOTAL_MIGRATION_ENERGY_COST=$(grep "Total Migration Cost" "$CLEANED_OUTPUT_LOG_FILE" | tail -n 1 | awk -F': ' '{print $2}')
            COMPLETED_MIGRATIONS=$(grep "Completed migrations" "$CLEANED_OUTPUT_LOG_FILE" | tail -n 1 | awk -F': ' '{print $2}')
            MAX_PERCENTAGE_OF_PMS_ON=$(grep "Max percentage of PMs on" "$CLEANED_OUTPUT_LOG_FILE" | tail -n 1 | awk -F': ' '{print $2}')
            AVERAGE_NUMBER_OF_PMS_ON=$(grep "Average number of PMs on" "$CLEANED_OUTPUT_LOG_FILE" | tail -n 1 | awk -F': ' '{print $2}')
            AVERAGE_PM_LOADS=$(grep "Average PM loads" "$CLEANED_OUTPUT_LOG_FILE" | tail -n 1 | awk -F': ' '{print $2}')
            NON_VALID_ENTRIES=$(grep "Non-valid entries" "$CLEANED_OUTPUT_LOG_FILE" | tail -n 1 | awk -F': ' '{print $2}')
            AVG_WAIT_TIME=$(grep "Average Wait Time" "$CLEANED_OUTPUT_LOG_FILE" | tail -n 1 | awk -F': ' '{print $2}')
            RUNTIME_EFFICIENCY=$(grep "Runtime Efficiency" "$CLEANED_OUTPUT_LOG_FILE" | tail -n 1 | awk -F': ' '{print $2}')
            OVERALL_TIME_EFFICIENCY=$(grep "Overall Time Efficiency" "$CLEANED_OUTPUT_LOG_FILE" | tail -n 1 | awk -F': ' '{print $2}')
            TOTAL_MODEL_RUNTIME=$(grep "Total Model Runtime" "$CLEANED_OUTPUT_LOG_FILE" | tail -n 1 | awk -F': ' '{print $2}')
            FINAL_NET_PROFIT=$(grep "Final Net Profit" "$CLEANED_OUTPUT_LOG_FILE" | tail -n 1 | awk -F': ' '{print $2}')
            
            # Save the results and configuration parameters to the results file
            echo "Test $CURRENT_TEST of $TOTAL_TESTS" >> "$RESULTS_FILE"
            echo "USE_SPEED_ALGORITHM=$USE_SPEED_ALGORITHM, NEW_VMS_PATTERN=$NEW_VMS_PATTERN, USE_RANDOM_SEED=$USE_RANDOM_SEED, SEED_NUMBER=$SEED_NUMBER, NEW_VMS_PER_STEP=$NEW_VMS_PER_STEP" >> "$RESULTS_FILE"
            echo "------------------------------------------" >> "$RESULTS_FILE"
            echo "WORKLOAD_NAME=$WORKLOAD_NAME" >> "$RESULTS_FILE"
            echo "MASTER_MODEL=$MASTER_MODEL" >> "$RESULTS_FILE"
            echo "TIME_STEP=$TIME_STEP" >> "$RESULTS_FILE"
            echo "NUM_TIME_STEPS=$NUM_TIME_STEPS" >> "$RESULTS_FILE"
            echo "------------------------------------------" >> "$RESULTS_FILE"
            echo "Non-valid entries: $NON_VALID_ENTRIES" >> "$RESULTS_FILE"
            echo "Average wait time: $AVG_WAIT_TIME" >> "$RESULTS_FILE"
            echo "Runtime efficiency: $RUNTIME_EFFICIENCY" >> "$RESULTS_FILE"
            echo "Overall time efficiency: $OVERALL_TIME_EFFICIENCY" >> "$RESULTS_FILE"
            echo "Total Model Runtime: $TOTAL_MODEL_RUNTIME" >> "$RESULTS_FILE"
            echo "Time taken for this configuration: ${DURATION} seconds" >> "$RESULTS_FILE"
            echo "------------------------------------------" >> "$RESULTS_FILE"
            echo "Completed migrations: $COMPLETED_MIGRATIONS" >> "$RESULTS_FILE"
            echo "Max percentage of PMs on: $MAX_PERCENTAGE_OF_PMS_ON" >> "$RESULTS_FILE"
            echo "Average number of PMs on: $AVERAGE_NUMBER_OF_PMS_ON" >> "$RESULTS_FILE"
            echo "Average PM loads: $AVERAGE_PM_LOADS" >> "$RESULTS_FILE"
            echo "------------------------------------------" >> "$RESULTS_FILE"
            echo "Total Revenue: $TOTAL_REVENUE" >> "$RESULTS_FILE"
            echo "Total PM Load Cost: $TOTAL_PM_LOAD_COST" >> "$RESULTS_FILE"
            echo "Total PM Switch Cost: $TOTAL_PM_SWITCH_COST" >> "$RESULTS_FILE"
            echo "Total Migration Energy Cost: $TOTAL_MIGRATION_ENERGY_COST" >> "$RESULTS_FILE"
            echo "Total Costs: $TOTAL_COSTS" >> "$RESULTS_FILE"
            echo "" >> "$RESULTS_FILE"
            echo "Final Net Profit: $FINAL_NET_PROFIT" >> "$RESULTS_FILE"
            echo "=============================" >> "$RESULTS_FILE"
            echo "" >> "$RESULTS_FILE"

            echo "Test $CURRENT_TEST of $TOTAL_TESTS"
            echo "USE_SPEED_ALGORITHM=$USE_SPEED_ALGORITHM, NEW_VMS_PATTERN=$NEW_VMS_PATTERN, USE_RANDOM_SEED=$USE_RANDOM_SEED, SEED_NUMBER=$SEED_NUMBER, NEW_VMS_PER_STEP=$NEW_VMS_PER_STEP"
            echo "------------------------------------------"
            echo "WORKLOAD_NAME=$WORKLOAD_NAME" 
            echo "MASTER_MODEL=$MASTER_MODEL"
            echo "TIME_STEP=$TIME_STEP"
            echo "NUM_TIME_STEPS=$NUM_TIME_STEPS"
            echo "------------------------------------------"
            echo "Non-valid entries: $NON_VALID_ENTRIES"
            echo "Average wait time: $AVG_WAIT_TIME"
            echo "Runtime efficiency: $RUNTIME_EFFICIENCY"
            echo "Overall time efficiency: $OVERALL_TIME_EFFICIENCY"
            echo "Total Model Runtime: $TOTAL_MODEL_RUNTIME"
            echo "Time taken for this configuration: ${DURATION} seconds"
            echo "------------------------------------------"
            echo "Completed migrations: $COMPLETED_MIGRATIONS"
            echo "Max percentage of PMs on: $MAX_PERCENTAGE_OF_PMS_ON"
            echo "Average number of PMs on: $AVERAGE_NUMBER_OF_PMS_ON"
            echo "Average PM loads: $AVERAGE_PM_LOADS"
            echo "------------------------------------------"
            echo "Total Revenue: $TOTAL_REVENUE"
            echo "Total PM Load Cost: $TOTAL_PM_LOAD_COST"
            echo "Total PM Switch Cost: $TOTAL_PM_SWITCH_COST"
            echo "Total Migration Energy Cost: $TOTAL_MIGRATION_ENERGY_COST"
            echo "Total Costs: $TOTAL_COSTS"
            echo ""
            echo "Final Net Profit: $FINAL_NET_PROFIT"
            echo "============================="
            echo ""
          done
        done
      done
    done
  done
done

# Clean up temporary directory after testing
rm -rf "$TEMP_DIR"

echo "All results have been saved to $RESULTS_FILE"

if [ "$USE_REAL_DATA" = "True" ]; then
  python analyze_test_results.py --file "$RESULTS_FILE"
else
  python analyze_test_results.py --file "$RESULTS_FILE" --groupby_workload NEW_VMS_PATTERN
fi


