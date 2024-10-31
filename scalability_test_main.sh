#!/bin/bash

main_file="main_scalability_test.mod"
log_dir="logs_scalability_tests/main"
output_dir="${log_dir}/output"
results_file="${log_dir}/scalability_test_results.csv"

# Define the ranges for physical and virtual machines
physical_machines=($(seq 10 20 110))  # Adjust the range as needed
virtual_machines=($(seq 10 100 1010))  # Adjust the range as needed

# Clean logs directory
rm -rf $log_dir/*

# Create logs directory if it doesn't exist
mkdir -p $log_dir
mkdir -p $output_dir

# Initialize results file
echo "Physical Machines,Virtual Machines,Time (s),Main Return Code" > $results_file

# Run scalability tests
for num_physical_machines in "${physical_machines[@]}"
do
    python3 data_generator/data_generator.py --scalability_test $num_physical_machines 0
    for num_virtual_machines in "${virtual_machines[@]}"
    do
        echo "Running test with Physical Machines: $num_physical_machines, Virtual Machines: $num_virtual_machines"

        # Generate data for the current combination
        python3 data_generator/data_generator.py --scalability_test 0 $num_virtual_machines

        if [ $? -ne 0 ]; then
            echo "Data generation failed for Physical Machines: $num_physical_machines, Virtual Machines: $num_virtual_machines" >&2
            continue
        fi

        # Measure the time taken by oplrun
        start_time=$(date +%s.%N)
        # Run oplrun and capture output and exit code
        opl_output=$(oplrun model/$main_file 2>&1);
        end_time=$(date +%s.%N)

        # Calculate the elapsed time
        elapsed_time=$(echo "$end_time - $start_time" | bc)

        # Extract "main returns X" from opl_output
        main_return_line=$(echo "$opl_output" | grep "main returns")

        # Extract the return code (X) from the line
        main_return_code=$(echo "$main_return_line" | awk '{print $3}')

        # If main_return_code is empty, set it to "N/A"
        if [ -z "$main_return_code" ]; then
            main_return_code="N/A"
        fi

        # Store the time results and main return code into the results file
        echo "$num_physical_machines,$num_virtual_machines,$elapsed_time,$main_return_code" >> $results_file

        # Store the full output into a log file
	    log_file="${output_dir}/${num_physical_machines}_${num_virtual_machines}.log"
        echo "$opl_output" > "$log_file"

        # Optionally, print the current result to stdout
        echo "Result: Time = $elapsed_time seconds, Main Return Code = $main_return_code"
        echo "Log saved to $log_file"
        echo "----------------------------------------"
    done
done
