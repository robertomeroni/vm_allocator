#!/bin/bash

# Define the ranges for parameters to be modified
USE_RANDOM_SEED_VALUES=(True)
SEED_NUMBER_VALUES=($(seq 1 1))  # This creates a range from 1 to 20
STARTING_STEP_VALUES=(1)
TIME_STEP_VALUES=(10)
NUM_TIME_STEPS_VALUES=(5000)
NEW_VMS_PER_STEP_VALUES=(1)
MAIN_MODEL_PERIOD_VALUES=(4)
MINI_MODEL_PERIOD_VALUES=(1)
MASTER_MODEL_VALUES=(
                    # 'main' 
                    'mini'
                    # 'mixed'
                    'best_fit' 
                    'guazzone'
                    'shi'
                    )
WORKLOAD_NAME_VALUES=(
                    'KIT-FH2-2016'
                    'UniLu-Gaia-2014'
                    'METACENTRUM-2009'
                    'PIK-IPLEX-2009'
                    'LLNL-Thunder-2007'
                    # 'Intel-NetbatchA-2012'
                    # 'Azure-2020'
                    )
USE_WORKLOAD_PREDICTOR_VALUES=(False)

# CPLEX parameters
CPLEX_TIME_LIMIT_MAIN_VALUES=(600)
CPLEX_OPTIMALITY_GAP_MAIN_VALUES=(0.01)
CPLEX_TIME_LIMIT_MINI_VALUES=(60)
CPLEX_OPTIMALITY_GAP_MINI_VALUES=(0.01)

# Weights
safety_margin_values=(0.7)
step_windows_online_prediction_values=(10)
step_windows_weights_accuracy_values=(30)

TOTAL_TESTS=$(( ${#USE_RANDOM_SEED_VALUES[@]} * ${#SEED_NUMBER_VALUES[@]} * ${#WORKLOAD_NAME_VALUES[@]} * ${#MASTER_MODEL_VALUES[@]} * ${#MAIN_MODEL_PERIOD_VALUES[@]} * ${#MINI_MODEL_PERIOD_VALUES[@]} * ${#NUM_TIME_STEPS_VALUES[@]} * ${#TIME_STEP_VALUES[@]} * ${#STARTING_STEP_VALUES[@]} * ${#NEW_VMS_PER_STEP_VALUES[@]} * ${#USE_WORKLOAD_PREDICTOR_VALUES[@]} * ${#safety_margin_values[@]} * ${#step_windows_online_prediction_values[@]} * ${#step_windows_weights_accuracy_values[@]} * ${#CPLEX_TIME_LIMIT_MAIN_VALUES[@]} * ${#CPLEX_OPTIMALITY_GAP_MAIN_VALUES[@]} * ${#CPLEX_TIME_LIMIT_MINI_VALUES[@]} * ${#CPLEX_OPTIMALITY_GAP_MINI_VALUES[@]} ))
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
RESULTS_FILE="log_tests/final_results_${TIMESTAMP}.txt"

# Initialize the results file
echo "Config Parameters and Results:" > "$RESULTS_FILE"

# Loop through each combination of parameters
for USE_RANDOM_SEED in "${USE_RANDOM_SEED_VALUES[@]}"; do
  for SEED_NUMBER in "${SEED_NUMBER_VALUES[@]}"; do
    for WORKLOAD_NAME in "${WORKLOAD_NAME_VALUES[@]}"; do
      for MASTER_MODEL in "${MASTER_MODEL_VALUES[@]}"; do
        for MAIN_MODEL_PERIOD in "${MAIN_MODEL_PERIOD_VALUES[@]}"; do
          for MINI_MODEL_PERIOD in "${MINI_MODEL_PERIOD_VALUES[@]}"; do
            for NUM_TIME_STEPS in "${NUM_TIME_STEPS_VALUES[@]}"; do
              for TIME_STEP in "${TIME_STEP_VALUES[@]}"; do
                for STARTING_STEP in "${STARTING_STEP_VALUES[@]}"; do
                  for NEW_VMS_PER_STEP in "${NEW_VMS_PER_STEP_VALUES[@]}"; do
                    for USE_WORKLOAD_PREDICTOR in "${USE_WORKLOAD_PREDICTOR_VALUES[@]}"; do
                      for safety_margin in "${safety_margin_values[@]}"; do
                        for step_window_for_online_prediction in "${step_windows_online_prediction_values[@]}"; do
                          for step_window_for_weights_accuracy in "${step_windows_weights_accuracy_values[@]}"; do
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

                                    sed -i "s/^safety_margin = .*/safety_margin = $safety_margin/" "$ORIGINAL_WEIGHTS_FILE"
                                    sed -i "s/^step_window_for_online_prediction = .*/step_window_for_online_prediction = $step_window_for_online_prediction/" "$ORIGINAL_WEIGHTS_FILE"
                                    sed -i "s/^step_window_for_weights_accuracy = .*/step_window_for_weights_accuracy = $step_window_for_weights_accuracy/" "$ORIGINAL_WEIGHTS_FILE"

                                    # Define output log file for capturing run.sh output
                                    OUTPUT_LOG_FILE="$TEMP_DIR/output_${USE_RANDOM_SEED}_${SEED_NUMBER}_${WORKLOAD_NAME}_${TIME_STEP}_${NEW_VMS_PER_STEP}_${NUM_TIME_STEPS}_${STARTING_STEP}_${MASTER_MODEL}_${MAIN_MODEL_PERIOD}_${MINI_MODEL_PERIOD}.log"

                                    CURRENT_TEST=$((CURRENT_TEST + 1))

                                    if [ ! -f "$INITIAL_PMS_FILE" ]; then
                                      echo "Initial PM file not found at $INITIAL_PMS_FILE."
                                      echo "How many physical machines do you want to simulate?"
                                      read NUM_PHYSICAL_MACHINES

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
                                    echo "USE_WORKLOAD_PREDICTOR=$USE_WORKLOAD_PREDICTOR, USE_RANDOM_SEED=$USE_RANDOM_SEED, SEED_NUMBER=$SEED_NUMBER, NEW_VMS_PER_STEP=$NEW_VMS_PER_STEP, MAIN_MODEL_PERIOD=$MAIN_MODEL_PERIOD, MINI_MODEL_PERIOD=$MINI_MODEL_PERIOD" >> "$RESULTS_FILE"
                                    echo "safety_margin=$safety_margin, step_window_for_online_prediction=$step_window_for_online_prediction, step_window_for_weights_accuracy=$step_window_for_weights_accuracy" >> "$RESULTS_FILE"
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
                                    echo "Total Costs: $TOTAL_COSTS" >> "$RESULTS_FILE"
                                    echo "Total PM Energy Cost: $TOTAL_PM_ENERGY_COST" >> "$RESULTS_FILE"
                                    echo "Total Migration Energy Cost: $TOTAL_MIGRATION_ENERGY_COST" >> "$RESULTS_FILE"
                                    echo "" >> "$RESULTS_FILE"
                                    echo "Final Net Profit: $FINAL_NET_PROFIT" >> "$RESULTS_FILE"
                                    echo "=============================" >> "$RESULTS_FILE"

                                    echo "USE_WORKLOAD_PREDICTOR=$USE_WORKLOAD_PREDICTOR, USE_RANDOM_SEED=$USE_RANDOM_SEED, SEED_NUMBER=$SEED_NUMBER, NEW_VMS_PER_STEP=$NEW_VMS_PER_STEP, MAIN_MODEL_PERIOD=$MAIN_MODEL_PERIOD, MINI_MODEL_PERIOD=$MINI_MODEL_PERIOD"
                                    echo "safety_margin=$safety_margin, step_window_for_online_prediction=$step_window_for_online_prediction, step_window_for_weights_accuracy=$step_window_for_weights_accuracy"
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

# Clean up temporary directory after testing
rm -rf "$TEMP_DIR"

echo "All results have been saved to $RESULTS_FILE"

python analyze_test_results.py --file "$RESULTS_FILE"
