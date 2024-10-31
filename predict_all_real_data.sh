#!/bin/bash

# Loop through each JSON file in the directory
for filepath in /home/roberto/job/workload_logs/json/part2/*.json; do
  # Extract the filename without the directory and extension
  filename=$(basename -- "$filepath")
  workload_name="${filename%.*}"

  # Run the Python script with the workload name
  python src/machine_learning_models.py --workload "$workload_name"
done