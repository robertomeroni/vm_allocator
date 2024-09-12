import re
import sys
from collections import defaultdict

# Check if the file path is provided as an argument
if len(sys.argv) != 2:
    print("Usage: python script.py <file_path>")
    sys.exit(1)

file_path = sys.argv[1]

# Initialize dictionaries to store total profits per parameter and model
net_profits_by_model = defaultdict(list)
net_profits_by_time_step = defaultdict(lambda: defaultdict(list))
net_profits_by_new_vms = defaultdict(lambda: defaultdict(list))
net_profits_by_num_time_steps = defaultdict(lambda: defaultdict(list))

# Open and read the txt file
try:
    with open(file_path, "r") as file:
        lines = file.readlines()
except FileNotFoundError:
    print(f"Error: File '{file_path}' not found.")
    sys.exit(1)

# Initialize variables to store parameters
current_model = None
time_step = None
new_vms_per_step = None
num_time_steps = None

for line in lines:
    # Extract the MASTER_MODEL, TIME_STEP, NEW_VMS_PER_STEP, and NUM_TIME_STEPS from each block
    if "MASTER_MODEL=" in line:
        current_model = re.search(r"MASTER_MODEL=([^,]*)", line).group(1).strip() or "undefined"
        time_step = int(re.search(r"TIME_STEP=([0-9]+)", line).group(1))
        new_vms_per_step = int(re.search(r"NEW_VMS_PER_STEP=([0-9]+)", line).group(1))
        num_time_steps = int(re.search(r"NUM_TIME_STEPS=([0-9]+)", line).group(1))

    # Extract the Final Net Profit for each combination of parameters
    if "Final Net Profit" in line:
        try:
            profit = float(re.search(r"\$([0-9.]+)", line).group(1))
            # Store profits by master model
            net_profits_by_model[current_model].append(profit)

            # Store profits by time step, regardless of other parameters
            net_profits_by_time_step[current_model][time_step].append(profit)

            # Store profits by new VMS per step, regardless of other parameters
            net_profits_by_new_vms[current_model][new_vms_per_step].append(profit)

            # Store profits by number of time steps, regardless of other parameters
            net_profits_by_num_time_steps[current_model][num_time_steps].append(profit)
        except AttributeError:
            print(f"Warning: Unable to parse net profit from line: {line.strip()}")

# Calculate total net profits for each master model
total_net_profits_by_model = {model: sum(profits) for model, profits in net_profits_by_model.items()}

# Calculate total net profits for each time step, new VMS per step, and num time steps
total_net_profits_by_time_step = {
    model: {time_step: sum(profits) for time_step, profits in time_steps.items()}
    for model, time_steps in net_profits_by_time_step.items()
}
total_net_profits_by_new_vms = {
    model: {new_vms: sum(profits) for new_vms, profits in new_vms_list.items()}
    for model, new_vms_list in net_profits_by_new_vms.items()
}
total_net_profits_by_num_time_steps = {
    model: {num_time_steps: sum(profits) for num_time_steps, profits in time_steps.items()}
    for model, time_steps in net_profits_by_num_time_steps.items()
}

# Print the results
print("Total Net Profits by Master Model:")
for model, total_profit in total_net_profits_by_model.items():
    print(f"{model}: ${total_profit:.2f}")

print("\nTotal Net Profits by TIME_STEP for each Master Model:")
for model, time_step_profits in total_net_profits_by_time_step.items():
    for time_step, total_profit in time_step_profits.items():
        print(f"Model: {model}, TIME_STEP: {time_step} => Total Profit: ${total_profit:.2f}")

print("\nTotal Net Profits by NEW_VMS_PER_STEP for each Master Model:")
for model, new_vms_profits in total_net_profits_by_new_vms.items():
    for new_vms, total_profit in new_vms_profits.items():
        print(f"Model: {model}, NEW_VMS_PER_STEP: {new_vms} => Total Profit: ${total_profit:.2f}")

print("\nTotal Net Profits by NUM_TIME_STEPS for each Master Model:")
for model, num_time_step_profits in total_net_profits_by_num_time_steps.items():
    for num_time_steps, total_profit in num_time_step_profits.items():
        print(f"Model: {model}, NUM_TIME_STEPS: {num_time_steps} => Total Profit: ${total_profit:.2f}")
