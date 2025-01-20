#!/bin/bash

# Define the ranges for parameters to be modified
USE_REAL_DATA=False

PMS_VALUES=(
            # 1000 
            # 5000 
            # 10000 
            # 15000
            # 20000
            25000
            # 30000
           )
MASTER_MODEL_VALUES=(
                    # 'main' 
                    # 'mini'
                    'hybrid'
                    # 'compound'
                    # 'multilayer'
                    # 'first_fit'
                    # 'best_fit' 
                    # 'shi_OM'
                    # 'shi_AC'
                    # 'shi_PU'
                    # 'lago'
                    )

TIME_STEP=100  
NUM_TIME_STEPS=100 
USE_RANDOM_SEED_VALUES=(True)
SEED_NUMBER_VALUES=($(seq 1 1))  # This creates a range from 1 to 20
NEW_VMS_PER_STEP_VALUES=(500)

# Filter values
MAIN_MODEL_MAX_PMS=20
MINI_MODEL_MAX_PMS=50
MIGRATION_MODEL_MAX_FRAGMENTED_PMS=20
FAILED_MIGRATIONS_LIMIT=5
PM_MANAGER_MAX_PMS=10

WORKLOAD_NAME_VALUES=('synthetic')

TOTAL_TESTS=$(( ${#USE_RANDOM_SEED_VALUES[@]} * ${#SEED_NUMBER_VALUES[@]} * ${#PMS_VALUES[@]} * ${#MASTER_MODEL_VALUES[@]} * ${#NEW_VMS_PER_STEP_VALUES[@]} ))
CURRENT_TEST=0

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
RESULTS_DIR="log_scalability"
RESULTS_FILE="${RESULTS_DIR}/final_results_${TIMESTAMP}.txt"
# Check if the log_scalability directory exists, if not, create it
if [ ! -d "$RESULTS_DIR" ]; then
  mkdir -p "$RESULTS_DIR"
fi

clear; 

# Loop through each combination of parameters
for USE_RANDOM_SEED in "${USE_RANDOM_SEED_VALUES[@]}"; do
  for SEED_NUMBER in "${SEED_NUMBER_VALUES[@]}"; do
    for WORKLOAD_NAME in "${WORKLOAD_NAME_VALUES[@]}"; do
      for MASTER_MODEL in "${MASTER_MODEL_VALUES[@]}"; do
        for PMS in "${PMS_VALUES[@]}"; do
          for NEW_VMS_PER_STEP in "${NEW_VMS_PER_STEP_VALUES[@]}"; do
            NEW_VMS_PER_STEP=$((PMS / 10))
            # Define the temporary config file path
            TEMP_CONFIG_FILE="$TEMP_DIR/config_${USE_RANDOM_SEED}_${SEED_NUMBER}_${WORKLOAD_NAME}_${TIME_STEP}_${NEW_VMS_PER_STEP}_${NUM_TIME_STEPS}_${MASTER_MODEL}.py"

            # Copy the original config file to the temporary config file
            cp "$ORIGINAL_CONFIG_FILE" "$TEMP_CONFIG_FILE"

            # Verify that the config file was copied successfully
            if [ ! -f "$TEMP_CONFIG_FILE" ]; then
              echo "Failed to create temporary config file: $TEMP_CONFIG_FILE"
              exit 1
            fi

            # Modify the copied config file with the new parameter values
            sed -i "s/^PRINT_TO_CONSOLE = .*/PRINT_TO_CONSOLE = False/" "$TEMP_CONFIG_FILE"
            sed -i "s/^SAVE_LOGS = .*/SAVE_LOGS = False/" "$TEMP_CONFIG_FILE"
            sed -i "s/^SAVE_VM_AND_PM_SETS = .*/SAVE_VM_AND_PM_SETS = False/" "$TEMP_CONFIG_FILE"

            sed -i "s/^USE_REAL_DATA = .*/USE_REAL_DATA = $USE_REAL_DATA/" "$TEMP_CONFIG_FILE"
            sed -i "s/^COMPOSITION = .*/COMPOSITION = 'heterogeneous'/" "$TEMP_CONFIG_FILE"
            sed -i "s/^COMPOSITION_SHAPE = .*/COMPOSITION_SHAPE = 'average'/" "$TEMP_CONFIG_FILE"
            sed -i "s/^USE_RANDOM_SEED = .*/USE_RANDOM_SEED = $USE_RANDOM_SEED/" "$TEMP_CONFIG_FILE"
            sed -i "s/^SEED_NUMBER = .*/SEED_NUMBER = $SEED_NUMBER/" "$TEMP_CONFIG_FILE"
            sed -i "s/^TIME_STEP = .*/TIME_STEP = $TIME_STEP/" "$TEMP_CONFIG_FILE"
            sed -i "s/^NEW_VMS_PER_STEP = .*/NEW_VMS_PER_STEP = $NEW_VMS_PER_STEP/" "$TEMP_CONFIG_FILE"
            sed -i "s/^NEW_VMS_PATTERN = .*/NEW_VMS_PATTERN = 'constant'/" "$TEMP_CONFIG_FILE"
            sed -i "s/^NUM_TIME_STEPS = .*/NUM_TIME_STEPS = $NUM_TIME_STEPS/" "$TEMP_CONFIG_FILE"
            sed -i "s/^MASTER_MODEL = .*/MASTER_MODEL = '$MASTER_MODEL'/" "$TEMP_CONFIG_FILE"
            sed -i "s/^WORKLOAD_NAME = .*/WORKLOAD_NAME = '$WORKLOAD_NAME'/" "$TEMP_CONFIG_FILE"

            sed -i "s/^MAIN_MODEL_MAX_PMS = .*/MAIN_MODEL_MAX_PMS = $MAIN_MODEL_MAX_PMS/" "$TEMP_CONFIG_FILE"
            sed -i "s/^MINI_MODEL_MAX_PMS = .*/MINI_MODEL_MAX_PMS = $MINI_MODEL_MAX_PMS/" "$TEMP_CONFIG_FILE"
            sed -i "s/^MIGRATION_MODEL_MAX_FRAGMENTED_PMS = .*/MIGRATION_MODEL_MAX_FRAGMENTED_PMS = $MIGRATION_MODEL_MAX_FRAGMENTED_PMS/" "$TEMP_CONFIG_FILE"
            sed -i "s/^PM_MANAGER_MAX_PMS = .*/PM_MANAGER_MAX_PMS = $PM_MANAGER_MAX_PMS/" "$TEMP_CONFIG_FILE"
            sed -i "s/^FAILED_MIGRATIONS_LIMIT = .*/FAILED_MIGRATIONS_LIMIT = $FAILED_MIGRATIONS_LIMIT/" "$TEMP_CONFIG_FILE"

            sed -i "s/^HARD_TIME_LIMIT_MAIN = .*/HARD_TIME_LIMIT_MAIN = 100000/" "$TEMP_CONFIG_FILE"
            sed -i "s/^HARD_TIME_LIMIT_MINI = .*/HARD_TIME_LIMIT_MINI = 100000/" "$TEMP_CONFIG_FILE"

            # Define output log file for capturing run.sh output
            OUTPUT_LOG_FILE="$TEMP_DIR/output_${USE_RANDOM_SEED}_${SEED_NUMBER}_${WORKLOAD_NAME}_${TIME_STEP}_${NEW_VMS_PER_STEP}_${NEW_VMS_PATTERN}_${NUM_TIME_STEPS}_${MASTER_MODEL}.log"

            CURRENT_TEST=$((CURRENT_TEST + 1))

            echo "Running test $CURRENT_TEST of $TOTAL_TESTS..."
            echo "Master model: $MASTER_MODEL, PMS: $PMS, VMS: $NEW_VMS_PER_STEP"
            echo ""

            # Run the simulation 
            ./run.sh --config "$TEMP_CONFIG_FILE" > "$OUTPUT_LOG_FILE" -P $PMS

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
            
            # Strip non-numeric characters from TOTAL_MODEL_RUNTIME
            TOTAL_MODEL_RUNTIME=$(echo "$TOTAL_MODEL_RUNTIME" | sed 's/[^0-9.]//g')

            if [ -z "$TOTAL_MODEL_RUNTIME" ] || [ -z "$NUM_TIME_STEPS" ]; then
              echo "Error: TOTAL_MODEL_RUNTIME or NUM_TIME_STEPS is not set."
              exit 1
            fi

            if [ "$NUM_TIME_STEPS" -eq 0 ]; then
              echo "Error: NUM_TIME_STEPS is zero, cannot divide by zero."
              exit 1
            fi

            ALLOCATION_RUNTIME_PER_STEP=$(echo "scale=4; $TOTAL_MODEL_RUNTIME / $NUM_TIME_STEPS" | bc)

            # Save the results and configuration parameters to the results file
            echo "Test $CURRENT_TEST of $TOTAL_TESTS" >> "$RESULTS_FILE"
            echo "PMS=$PMS, USE_RANDOM_SEED=$USE_RANDOM_SEED, SEED_NUMBER=$SEED_NUMBER, NEW_VMS_PER_STEP=$NEW_VMS_PER_STEP" >> "$RESULTS_FILE"
            echo "------------------------------------------" >> "$RESULTS_FILE"
            echo "MASTER_MODEL=$MASTER_MODEL" >> "$RESULTS_FILE"
            echo "TIME_STEP=$TIME_STEP" >> "$RESULTS_FILE"
            echo "NUM_TIME_STEPS=$NUM_TIME_STEPS" >> "$RESULTS_FILE"
            echo "------------------------------------------" >> "$RESULTS_FILE"
            echo "Non-valid entries: $NON_VALID_ENTRIES" >> "$RESULTS_FILE"
            echo "Allocation Runtime: $ALLOCATION_RUNTIME_PER_STEP" >> "$RESULTS_FILE"
            echo "------------------------------------------" >> "$RESULTS_FILE"
            echo "Completed migrations: $COMPLETED_MIGRATIONS" >> "$RESULTS_FILE"
            echo "Max percentage of PMs on: $MAX_PERCENTAGE_OF_PMS_ON" >> "$RESULTS_FILE"
            echo "Average number of PMs on: $AVERAGE_NUMBER_OF_PMS_ON" >> "$RESULTS_FILE"
            echo "Average PM loads: $AVERAGE_PM_LOADS" >> "$RESULTS_FILE"
            echo "=============================" >> "$RESULTS_FILE"
            echo "" >> "$RESULTS_FILE"

            echo "Test $CURRENT_TEST of $TOTAL_TESTS"
            echo "PMS=$PMS, USE_RANDOM_SEED=$USE_RANDOM_SEED, SEED_NUMBER=$SEED_NUMBER, NEW_VMS_PER_STEP=$NEW_VMS_PER_STEP"
            echo "------------------------------------------"
            echo "MASTER_MODEL=$MASTER_MODEL"
            echo "TIME_STEP=$TIME_STEP"
            echo "NUM_TIME_STEPS=$NUM_TIME_STEPS"
            echo "------------------------------------------"
            echo "Non-valid entries: $NON_VALID_ENTRIES"
            echo "Allocation Runtime: $ALLOCATION_RUNTIME_PER_STEP"
            echo "------------------------------------------"
            echo "Completed migrations: $COMPLETED_MIGRATIONS"
            echo "Max percentage of PMs on: $MAX_PERCENTAGE_OF_PMS_ON"
            echo "Average number of PMs on: $AVERAGE_NUMBER_OF_PMS_ON"
            echo "Average PM loads: $AVERAGE_PM_LOADS"
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

python plot_scalability_test_results.py "$RESULTS_FILE"


