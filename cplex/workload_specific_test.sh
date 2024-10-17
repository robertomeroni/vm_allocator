#!/bin/bash

# Define the ranges for parameters to be modified
USE_RANDOM_SEED_VALUES=(True)
SEED_NUMBER_VALUES=($(seq 1 1))  # This creates a range from 1 to 20
STARTING_STEP_VALUES=(1)
NEW_VMS_PER_STEP_VALUES=(1)
MAIN_MODEL_PERIOD_VALUES=(5)
MINI_MODEL_PERIOD_VALUES=(5)
MASTER_MODEL_VALUES=(
                    'main' 
                    # 'hybrid'
                    # 'mini'
                    # 'first_fit'
                    # 'best_fit' 
                    # 'guazzone'
                    # 'shi'
                    )
WORKLOAD_NAME_VALUES=(
  'Chameleon-New-2020'
  'Chameleon-Legacy-2020'
  'LLNL-Thunder-2007'
  # 'METACENTRUM-2009'
  # 'METACENTRUM-2013'
  # 'PIK-IPLEX-2009'
  'TU-Delft-2007'
  'UniLu-Gaia-2014'
  # 'Intel-NetbatchA-2012'
  # 'Azure-2020'
)

USE_WORKLOAD_PREDICTOR_VALUES=(False)
USE_FILTER_VALUES=(True)

# CPLEX parameters
CPLEX_TIME_LIMIT_MAIN_VALUES=(30)
CPLEX_OPTIMALITY_GAP_MAIN_VALUES=(0.01)
CPLEX_TIME_LIMIT_MINI_VALUES=(120)
CPLEX_OPTIMALITY_GAP_MINI_VALUES=(0.01)

# Weights
migration_penalty_values=(0.5 0.6 0.7 0.8 0.9)
safety_margin_values=(0.7)
step_windows_online_prediction_values=(10)
step_windows_weights_accuracy_values=(30)
w_concurrent_migrations_values=(0.5)

TOTAL_TESTS=$(( ${#USE_RANDOM_SEED_VALUES[@]} * ${#SEED_NUMBER_VALUES[@]} * ${#WORKLOAD_NAME_VALUES[@]} * ${#MASTER_MODEL_VALUES[@]} * ${#MAIN_MODEL_PERIOD_VALUES[@]} * ${#MINI_MODEL_PERIOD_VALUES[@]} * ${#STARTING_STEP_VALUES[@]} * ${#NEW_VMS_PER_STEP_VALUES[@]} * ${#USE_WORKLOAD_PREDICTOR_VALUES[@]} * ${#USE_FILTER_VALUES[@]} *  ${#migration_penalty_values[@]} * ${#safety_margin_values[@]} * ${#step_windows_online_prediction_values[@]} * ${#step_windows_weights_accuracy_values[@]} * ${#w_concurrent_migrations_values[@]} * ${#CPLEX_TIME_LIMIT_MAIN_VALUES[@]} * ${#CPLEX_OPTIMALITY_GAP_MAIN_VALUES[@]} * ${#CPLEX_TIME_LIMIT_MINI_VALUES[@]} * ${#CPLEX_OPTIMALITY_GAP_MINI_VALUES[@]} ))
CURRENT_TEST=0

# Function to set NUM_TIME_STEPS and TIME_STEP based on WORKLOAD_NAME
function set_time_parameters() {
  case "$WORKLOAD_NAME" in
    "Azure-2020")
      TIME_STEP=5
      NUM_TIME_STEPS=10000
      ;;
    "Chameleon-Legacy-2020")
      TIME_STEP=50000
      NUM_TIME_STEPS=7000
      ;;
    "Chameleon-New-2020")
      TIME_STEP=5000
      NUM_TIME_STEPS=50000
      ;;
    "Intel-NetbatchA-2012")
      TIME_STEP=5
      NUM_TIME_STEPS=700
      ;;
    "LLNL-Thunder-2007")
      TIME_STEP=500
      NUM_TIME_STEPS=500
      ;;
    "METACENTRUM-2009")
      TIME_STEP=800
      NUM_TIME_STEPS=1500
      ;;
    "METACENTRUM-2013")
      TIME_STEP=30
      NUM_TIME_STEPS=1000
      ;;
    "PIK-IPLEX-2009")
      TIME_STEP=200
      NUM_TIME_STEPS=2000
      ;;
    "TU-Delft-2007")
      TIME_STEP=500
      NUM_TIME_STEPS=5000
      ;;
    "UniLu-Gaia-2014")
      TIME_STEP=400
      NUM_TIME_STEPS=3000
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
        for MAIN_MODEL_PERIOD in "${MAIN_MODEL_PERIOD_VALUES[@]}"; do
          for MINI_MODEL_PERIOD in "${MINI_MODEL_PERIOD_VALUES[@]}"; do
            for STARTING_STEP in "${STARTING_STEP_VALUES[@]}"; do
              for NEW_VMS_PER_STEP in "${NEW_VMS_PER_STEP_VALUES[@]}"; do
                for USE_FILTER in "${USE_FILTER_VALUES[@]}"; do
                  for USE_WORKLOAD_PREDICTOR in "${USE_WORKLOAD_PREDICTOR_VALUES[@]}"; do
                    for safety_margin in "${safety_margin_values[@]}"; do
                      for step_window_for_online_prediction in "${step_windows_online_prediction_values[@]}"; do
                        for step_window_for_weights_accuracy in "${step_windows_weights_accuracy_values[@]}"; do
                          for w_concurrent_migrations in "${w_concurrent_migrations_values[@]}"; do
                            for migration_penalty in "${migration_penalty_values[@]}"; do
                              for cplex_time_limit_main in "${CPLEX_TIME_LIMIT_MAIN_VALUES[@]}"; do
                                for cplex_optimality_gap_main in "${CPLEX_OPTIMALITY_GAP_MAIN_VALUES[@]}"; do
                                  for cplex_time_limit_mini in "${CPLEX_TIME_LIMIT_MINI_VALUES[@]}"; do
                                    for cplex_optimality_gap_mini in "${CPLEX_OPTIMALITY_GAP_MINI_VALUES[@]}"; do
                                      
                                      INITIAL_PMS_FILE="simulation/simulation_input/physical_machines_${WORKLOAD_NAME}.dat"

                                      # Define the temporary config file path
                                      TEMP_CONFIG_FILE="$TEMP_DIR/config_${USE_WORKLOAD_PREDICTOR}_${USE_RANDOM_SEED}_${SEED_NUMBER}_${WORKLOAD_NAME}_${TIME_STEP}_${NEW_VMS_PER_STEP}_${NUM_TIME_STEPS}_${STARTING_STEP}_${MASTER_MODEL}_${MAIN_MODEL_PERIOD}_${MINI_MODEL_PERIOD}.py"

                                      # Copy the original config file to the temporary config file
                                      cp "$ORIGINAL_CONFIG_FILE" "$TEMP_CONFIG_FILE"

                                      # Verify that the config file was copied successfully
                                      if [ ! -f "$TEMP_CONFIG_FILE" ]; then
                                        echo "Failed to create temporary config file: $TEMP_CONFIG_FILE"
                                        exit 1
                                      fi

                                      # Modify the copied config file with the new parameter values
                                      sed -i "s/^USE_RANDOM_SEED = .*/USE_RANDOM_SEED = $USE_RANDOM_SEED/" "$TEMP_CONFIG_FILE"
                                      sed -i "s/^SEED_NUMBER = .*/SEED_NUMBER = $SEED_NUMBER/" "$TEMP_CONFIG_FILE"
                                      sed -i "s/^STARTING_STEP = .*/STARTING_STEP = $STARTING_STEP/" "$TEMP_CONFIG_FILE"
                                      sed -i "s/^TIME_STEP = .*/TIME_STEP = $TIME_STEP/" "$TEMP_CONFIG_FILE"
                                      sed -i "s/^NEW_VMS_PER_STEP = .*/NEW_VMS_PER_STEP = $NEW_VMS_PER_STEP/" "$TEMP_CONFIG_FILE"
                                      sed -i "s/^NUM_TIME_STEPS = .*/NUM_TIME_STEPS = $NUM_TIME_STEPS/" "$TEMP_CONFIG_FILE"
                                      sed -i "s/^MASTER_MODEL = .*/MASTER_MODEL = '$MASTER_MODEL'/" "$TEMP_CONFIG_FILE"
                                      sed -i "s/^MAIN_MODEL_PERIOD = .*/MAIN_MODEL_PERIOD = $MAIN_MODEL_PERIOD/" "$TEMP_CONFIG_FILE"
                                      sed -i "s/^MINI_MODEL_PERIOD = .*/MINI_MODEL_PERIOD = $MINI_MODEL_PERIOD/" "$TEMP_CONFIG_FILE"
                                      sed -i "s/^WORKLOAD_NAME = .*/WORKLOAD_NAME = '$WORKLOAD_NAME'/" "$TEMP_CONFIG_FILE"
                                      sed -i "s/^USE_WORKLOAD_PREDICTOR = .*/USE_WORKLOAD_PREDICTOR = $USE_WORKLOAD_PREDICTOR/" "$TEMP_CONFIG_FILE"
                                      sed -i "s/^USE_FILTER = .*/USE_FILTER = $USE_FILTER/" "$TEMP_CONFIG_FILE"

                                      sed -i "s/^TIME_LIMIT_MAIN = .*/TIME_LIMIT_MAIN = $cplex_time_limit_main/" "$ORIGINAL_WEIGHTS_FILE"
                                      sed -i "s/^OPTIMALITY_GAP_MAIN = .*/OPTIMALITY_GAP_MAIN = $cplex_optimality_gap_main/" "$ORIGINAL_WEIGHTS_FILE"
                                      sed -i "s/^TIME_LIMIT_MINI = .*/TIME_LIMIT_MINI = $cplex_time_limit_mini/" "$ORIGINAL_WEIGHTS_FILE"
                                      sed -i "s/^OPTIMALITY_GAP_MINI = .*/OPTIMALITY_GAP_MINI = $cplex_optimality_gap_mini/" "$ORIGINAL_WEIGHTS_FILE"

                                      sed -i "s/^safety_margin = .*/safety_margin = $safety_margin/" "$ORIGINAL_WEIGHTS_FILE"
                                      sed -i "s/^step_window_for_online_prediction = .*/step_window_for_online_prediction = $step_window_for_online_prediction/" "$ORIGINAL_WEIGHTS_FILE"
                                      sed -i "s/^step_window_for_weights_accuracy = .*/step_window_for_weights_accuracy = $step_window_for_weights_accuracy/" "$ORIGINAL_WEIGHTS_FILE"
                                      sed -i "s/^w_concurrent_migrations = .*/w_concurrent_migrations = $w_concurrent_migrations/" "$ORIGINAL_WEIGHTS_FILE"
                                      sed -i "s/^migration_penalty = .*/migration_penalty = $migration_penalty/" "$ORIGINAL_WEIGHTS_FILE"

                                      # Define output log file for capturing run.sh output
                                      OUTPUT_LOG_FILE="$TEMP_DIR/output_${USE_RANDOM_SEED}_${SEED_NUMBER}_${WORKLOAD_NAME}_${TIME_STEP}_${NEW_VMS_PER_STEP}_${NUM_TIME_STEPS}_${STARTING_STEP}_${MASTER_MODEL}_${MAIN_MODEL_PERIOD}_${MINI_MODEL_PERIOD}.log"

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
                                      REMOVED_VMS=$(grep "Removed VMs" "$CLEANED_OUTPUT_LOG_FILE" | tail -n 1 | awk -F': ' '{print $2}')
                                      MAX_PERCENTAGE_OF_PMS_ON=$(grep "Max percentage of PMs on" "$CLEANED_OUTPUT_LOG_FILE" | tail -n 1 | awk -F': ' '{print $2}')
                                      AVERAGE_NUMBER_OF_PMS_ON=$(grep "Average number of PMs on" "$CLEANED_OUTPUT_LOG_FILE" | tail -n 1 | awk -F': ' '{print $2}')
                                      AVERAGE_PM_LOADS=$(grep "Average PM loads" "$CLEANED_OUTPUT_LOG_FILE" | tail -n 1 | awk -F': ' '{print $2}')
                                      FINAL_NET_PROFIT=$(grep "Final Net Profit" "$CLEANED_OUTPUT_LOG_FILE" | tail -n 1 | awk -F': ' '{print $2}')
                                      
                                      # Save the results and configuration parameters to the results file
                                      echo "Test $CURRENT_TEST of $TOTAL_TESTS" >> "$RESULTS_FILE"
                                      echo "Time taken for this configuration: ${DURATION} seconds" >> "$RESULTS_FILE"
                                      echo "USE_WORKLOAD_PREDICTOR=$USE_WORKLOAD_PREDICTOR, USE_FILTER=$USE_FILTER, USE_RANDOM_SEED=$USE_RANDOM_SEED, SEED_NUMBER=$SEED_NUMBER, NEW_VMS_PER_STEP=$NEW_VMS_PER_STEP, MAIN_MODEL_PERIOD=$MAIN_MODEL_PERIOD, MINI_MODEL_PERIOD=$MINI_MODEL_PERIOD" >> "$RESULTS_FILE"
                                      echo "migration_penalty=$migration_penalty, safety_margin=$safety_margin, step_window_for_online_prediction=$step_window_for_online_prediction, step_window_for_weights_accuracy=$step_window_for_weights_accuracy, w_concurrent_migrations=$w_concurrent_migrations" >> "$RESULTS_FILE"
                                      echo "CPLEX_TIME_LIMIT_MAIN=$cplex_time_limit_main, CPLEX_OPTIMALITY_GAP_MAIN=$cplex_optimality_gap_main, CPLEX_TIME_LIMIT_MINI=$cplex_time_limit_mini, CPLEX_OPTIMALITY_GAP_MINI=$cplex_optimality_gap_mini" >> "$RESULTS_FILE"
                                      echo "------------------------------------------" >> "$RESULTS_FILE"
                                      echo "WORKLOAD_NAME=$WORKLOAD_NAME" >> "$RESULTS_FILE"
                                      echo "MASTER_MODEL=$MASTER_MODEL" >> "$RESULTS_FILE"
                                      echo "TIME_STEP=$TIME_STEP" >> "$RESULTS_FILE"
                                      echo "NUM_TIME_STEPS=$NUM_TIME_STEPS" >> "$RESULTS_FILE"
                                      echo "------------------------------------------" >> "$RESULTS_FILE"
                                      echo "Completed migrations: $COMPLETED_MIGRATIONS" >> "$RESULTS_FILE"
                                      echo "Removed VMs: $REMOVED_VMS" >> "$RESULTS_FILE"
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
                                      echo "USE_WORKLOAD_PREDICTOR=$USE_WORKLOAD_PREDICTOR, USE_FILTER=$USE_FILTER, USE_RANDOM_SEED=$USE_RANDOM_SEED, SEED_NUMBER=$SEED_NUMBER, NEW_VMS_PER_STEP=$NEW_VMS_PER_STEP, MAIN_MODEL_PERIOD=$MAIN_MODEL_PERIOD, MINI_MODEL_PERIOD=$MINI_MODEL_PERIOD"
                                      echo "migration_penalty=$migration_penalty, safety_margin=$safety_margin, step_window_for_online_prediction=$step_window_for_online_prediction, step_window_for_weights_accuracy=$step_window_for_weights_accuracy, w_concurrent_migrations=$w_concurrent_migrations"
                                      echo "CPLEX_TIME_LIMIT_MAIN=$cplex_time_limit_main, CPLEX_OPTIMALITY_GAP_MAIN=$cplex_optimality_gap_main, CPLEX_TIME_LIMIT_MINI=$cplex_time_limit_mini, CPLEX_OPTIMALITY_GAP_MINI=$cplex_optimality_gap_mini"
                                      echo "------------------------------------------"
                                      echo "WORKLOAD_NAME=$WORKLOAD_NAME" 
                                      echo "MASTER_MODEL=$MASTER_MODEL"
                                      echo "TIME_STEP=$TIME_STEP"
                                      echo "NUM_TIME_STEPS=$NUM_TIME_STEPS"
                                      echo "------------------------------------------"
                                      echo "Completed migrations: $COMPLETED_MIGRATIONS"
                                      echo "Removed VMs: $REMOVED_VMS"
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
                      done
                    done
                  done
                done
              done
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
