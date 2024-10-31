#!/bin/bash

# Define the ranges for parameters to be modified
USE_RANDOM_SEED_VALUES=(True)
SEED_NUMBER_VALUES=($(seq 1 1))  # This creates a range from 1 to 20
NEW_VMS_PER_STEP_VALUES=(1)
MASTER_MODEL_VALUES=(
                    'main' 
                    'hybrid'
                    'mini'
                    # 'first_fit'
                    'best_fit' 
                    'guazzone'
                    'shi'
                    )
WORKLOAD_NAME_VALUES=(
  'Chameleon-New-2020'
  # 'Chameleon-Legacy-2020'
  'LLNL-Thunder-2007'
  'METACENTRUM-2009'
  'METACENTRUM-2013'
  'PIK-IPLEX-2009'
  'TU-Delft-2007'
  'UniLu-Gaia-2014'
  # 'Intel-NetbatchA-2012'
  # 'Azure-2020'
)

# CPLEX parameters
hard_time_limit_main_factor=2
hard_time_limit_mini_factor=2

# Weights
migration_penalty_values=(1)
w_concurrent_migrations_values=(0.5)

TOTAL_TESTS=$(( ${#USE_RANDOM_SEED_VALUES[@]} * ${#SEED_NUMBER_VALUES[@]} * ${#WORKLOAD_NAME_VALUES[@]} * ${#MASTER_MODEL_VALUES[@]} * ${#NEW_VMS_PER_STEP_VALUES[@]} *  ${#migration_penalty_values[@]} * ${#w_concurrent_migrations_values[@]} ))
CURRENT_TEST=0

# Function to set NUM_TIME_STEPS and TIME_STEP based on WORKLOAD_NAME
function set_time_parameters() {
  case "$WORKLOAD_NAME" in
    "Azure-2020")
      TIME_STEP=5
      NUM_TIME_STEPS=10000
      ;;
    "Chameleon-Legacy-2020")
      TIME_STEP=5000
      NUM_TIME_STEPS=70000
      ;;
    "Chameleon-New-2020")
      TIME_STEP=500
      NUM_TIME_STEPS=500000
      ;;
    "Intel-NetbatchA-2012")
      TIME_STEP=5
      NUM_TIME_STEPS=700
      ;;
    "LLNL-Thunder-2007")
      TIME_STEP=50
      NUM_TIME_STEPS=5000
      ;;
    "METACENTRUM-2009")
      TIME_STEP=80
      NUM_TIME_STEPS=15000
      ;;
    "METACENTRUM-2013")
      TIME_STEP=3
      NUM_TIME_STEPS=10000
      ;;
    "PIK-IPLEX-2009")
      TIME_STEP=20
      NUM_TIME_STEPS=20000
      ;;
    "TU-Delft-2007")
      TIME_STEP=50
      NUM_TIME_STEPS=50000
      ;;
    "UniLu-Gaia-2014")
      TIME_STEP=40
      NUM_TIME_STEPS=30000
      ;;
      
    *)
      TIME_STEP=500  # Default value
      NUM_TIME_STEPS=10000  # Default value
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
mkdir -p log_tests/txt

ORIGINAL_CONFIG_FILE="src/config.py"
ORIGINAL_WEIGHTS_FILE="src/weights.py"

# Generate a timestamp for the results file
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

# File to store final results
RESULTS_FILE="log_tests/txt/final_results_${TIMESTAMP}.txt"

clear; 

# Loop through each combination of parameters
for USE_RANDOM_SEED in "${USE_RANDOM_SEED_VALUES[@]}"; do
  for SEED_NUMBER in "${SEED_NUMBER_VALUES[@]}"; do
    for WORKLOAD_NAME in "${WORKLOAD_NAME_VALUES[@]}"; do
      set_time_parameters
      for MASTER_MODEL in "${MASTER_MODEL_VALUES[@]}"; do
        for NEW_VMS_PER_STEP in "${NEW_VMS_PER_STEP_VALUES[@]}"; do
          for w_concurrent_migrations in "${w_concurrent_migrations_values[@]}"; do
            for migration_penalty in "${migration_penalty_values[@]}"; do               

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

              hard_time_limit_main=$((TIME_STEP / hard_time_limit_main_factor))
              hard_time_limit_mini=$((TIME_STEP / hard_time_limit_mini_factor))

              # Modify the copied config file with the new parameter values
              sed -i "s/^PRINT_TO_CONSOLE = .*/PRINT_TO_CONSOLE = False/" "$TEMP_CONFIG_FILE"
              sed -i "s/^USE_RANDOM_SEED = .*/USE_RANDOM_SEED = $USE_RANDOM_SEED/" "$TEMP_CONFIG_FILE"
              sed -i "s/^SEED_NUMBER = .*/SEED_NUMBER = $SEED_NUMBER/" "$TEMP_CONFIG_FILE"
              sed -i "s/^TIME_STEP = .*/TIME_STEP = $TIME_STEP/" "$TEMP_CONFIG_FILE"
              sed -i "s/^NEW_VMS_PER_STEP = .*/NEW_VMS_PER_STEP = $NEW_VMS_PER_STEP/" "$TEMP_CONFIG_FILE"
              sed -i "s/^NUM_TIME_STEPS = .*/NUM_TIME_STEPS = $NUM_TIME_STEPS/" "$TEMP_CONFIG_FILE"
              sed -i "s/^MASTER_MODEL = .*/MASTER_MODEL = '$MASTER_MODEL'/" "$TEMP_CONFIG_FILE"
              sed -i "s/^WORKLOAD_NAME = .*/WORKLOAD_NAME = '$WORKLOAD_NAME'/" "$TEMP_CONFIG_FILE"

              sed -i "s/^HARD_TIME_LIMIT_MAIN = .*/HARD_TIME_LIMIT_MAIN = $hard_time_limit_main/" "$TEMP_CONFIG_FILE"
              sed -i "s/^HARD_TIME_LIMIT_MINI = .*/HARD_TIME_LIMIT_MINI = $hard_time_limit_mini/" "$TEMP_CONFIG_FILE"

              sed -i "s/^w_concurrent_migrations = .*/w_concurrent_migrations = $w_concurrent_migrations/" "$ORIGINAL_WEIGHTS_FILE"
              sed -i "s/^migration_penalty = .*/migration_penalty = $migration_penalty/" "$ORIGINAL_WEIGHTS_FILE"

              # Define output log file for capturing run.sh output
              OUTPUT_LOG_FILE="$TEMP_DIR/output_${USE_RANDOM_SEED}_${SEED_NUMBER}_${WORKLOAD_NAME}_${TIME_STEP}_${NEW_VMS_PER_STEP}_${NUM_TIME_STEPS}_${MASTER_MODEL}.log"

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
              TOTAL_PM_ENERGY_COST=$(grep "Total PM Energy Cost" "$CLEANED_OUTPUT_LOG_FILE" | tail -n 1 | awk -F': ' '{print $2}')
              TOTAL_MIGRATION_ENERGY_COST=$(grep "Total Migration Energy Cost" "$CLEANED_OUTPUT_LOG_FILE" | tail -n 1 | awk -F': ' '{print $2}')
              COMPLETED_MIGRATIONS=$(grep "Completed migrations" "$CLEANED_OUTPUT_LOG_FILE" | tail -n 1 | awk -F': ' '{print $2}')
              MAX_PERCENTAGE_OF_PMS_ON=$(grep "Max percentage of PMs on" "$CLEANED_OUTPUT_LOG_FILE" | tail -n 1 | awk -F': ' '{print $2}')
              AVERAGE_NUMBER_OF_PMS_ON=$(grep "Average number of PMs on" "$CLEANED_OUTPUT_LOG_FILE" | tail -n 1 | awk -F': ' '{print $2}')
              AVERAGE_PM_LOADS=$(grep "Average PM loads" "$CLEANED_OUTPUT_LOG_FILE" | tail -n 1 | awk -F': ' '{print $2}')
              NON_VALID_ENTRIES=$(grep "Non-valid entries" "$CLEANED_OUTPUT_LOG_FILE" | tail -n 1 | awk -F': ' '{print $2}')
              FINAL_NET_PROFIT=$(grep "Final Net Profit" "$CLEANED_OUTPUT_LOG_FILE" | tail -n 1 | awk -F': ' '{print $2}')
              
              # Save the results and configuration parameters to the results file
              echo "Test $CURRENT_TEST of $TOTAL_TESTS" >> "$RESULTS_FILE"
              echo "Time taken for this configuration: ${DURATION} seconds" >> "$RESULTS_FILE"
              echo "USE_RANDOM_SEED=$USE_RANDOM_SEED, SEED_NUMBER=$SEED_NUMBER, NEW_VMS_PER_STEP=$NEW_VMS_PER_STEP" >> "$RESULTS_FILE"
              echo "migration_penalty=$migration_penalty, w_concurrent_migrations=$w_concurrent_migrations" >> "$RESULTS_FILE"
              echo "------------------------------------------" >> "$RESULTS_FILE"
              echo "WORKLOAD_NAME=$WORKLOAD_NAME" >> "$RESULTS_FILE"
              echo "MASTER_MODEL=$MASTER_MODEL" >> "$RESULTS_FILE"
              echo "TIME_STEP=$TIME_STEP" >> "$RESULTS_FILE"
              echo "NUM_TIME_STEPS=$NUM_TIME_STEPS" >> "$RESULTS_FILE"
              echo "Non-valid entries: $NON_VALID_ENTRIES" >> "$RESULTS_FILE"
              echo "------------------------------------------" >> "$RESULTS_FILE"
              echo "Completed migrations: $COMPLETED_MIGRATIONS" >> "$RESULTS_FILE"
              echo "Max percentage of PMs on: $MAX_PERCENTAGE_OF_PMS_ON" >> "$RESULTS_FILE"
              echo "Average number of PMs on: $AVERAGE_NUMBER_OF_PMS_ON" >> "$RESULTS_FILE"
              echo "Average PM loads: $AVERAGE_PM_LOADS" >> "$RESULTS_FILE"
              echo "------------------------------------------" >> "$RESULTS_FILE"
              echo "Total Revenue: $TOTAL_REVENUE" >> "$RESULTS_FILE"
              echo "Total PM Energy Cost: $TOTAL_PM_ENERGY_COST" >> "$RESULTS_FILE"
              echo "Total Migration Energy Cost: $TOTAL_MIGRATION_ENERGY_COST" >> "$RESULTS_FILE"
              echo "Total Costs: $TOTAL_COSTS" >> "$RESULTS_FILE"
              echo "" >> "$RESULTS_FILE"
              echo "Final Net Profit: $FINAL_NET_PROFIT" >> "$RESULTS_FILE"
              echo "=============================" >> "$RESULTS_FILE"

              echo "Test $CURRENT_TEST of $TOTAL_TESTS"
              echo "Time taken for this configuration: ${DURATION} seconds"
              echo "USE_RANDOM_SEED=$USE_RANDOM_SEED, SEED_NUMBER=$SEED_NUMBER, NEW_VMS_PER_STEP=$NEW_VMS_PER_STEP"
              echo "migration_penalty=$migration_penalty, w_concurrent_migrations=$w_concurrent_migrations"
              echo "------------------------------------------"
              echo "WORKLOAD_NAME=$WORKLOAD_NAME" 
              echo "MASTER_MODEL=$MASTER_MODEL"
              echo "TIME_STEP=$TIME_STEP"
              echo "NUM_TIME_STEPS=$NUM_TIME_STEPS"
              echo "Non-valid entries: $NON_VALID_ENTRIES"
              echo "------------------------------------------"
              echo "Completed migrations: $COMPLETED_MIGRATIONS"
              echo "Max percentage of PMs on: $MAX_PERCENTAGE_OF_PMS_ON"
              echo "Average number of PMs on: $AVERAGE_NUMBER_OF_PMS_ON"
              echo "Average PM loads: $AVERAGE_PM_LOADS"
              echo "------------------------------------------"
              echo "Total Revenue: $TOTAL_REVENUE"
              echo "Total PM Energy Cost: $TOTAL_PM_ENERGY_COST"
              echo "Total Migration Energy Cost: $TOTAL_MIGRATION_ENERGY_COST"
              echo "Total Costs: $TOTAL_COSTS"
              echo ""
              echo "Final Net Profit: $FINAL_NET_PROFIT"
              echo "============================="
                    
            done
          done
        done
      done
    done
  done
done

# Clean up temporary directory after testing
rm -rf "$TEMP_DIR"

echo "All results have been saved to $RESULTS_FILE"

python analyze_test_results.py --file "$RESULTS_FILE"
