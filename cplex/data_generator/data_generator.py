import numpy as np
import os
import sys
import argparse
# from config import (
# from config_speed1_on import (
# from config_speed1_off_big import (
from config_scalability_test import (
    data_folder_path, pm_cpu_capacity, pm_memory_capacity, pm_speed_range, pm_time_to_turn_on_range, pm_time_to_turn_off_range,
    vm_requested_cpu, vm_requested_memory, execution_time_range, allocation_time_range, default_num_physical_machines, 
    default_num_virtual_machines, state_percentage, running_percentage, migration_time_memory_dirty_rate, migration_time_network_bandwidth, migration_time_resume_vm_on_target
)

def calculate_power_consumption(cpu_cores, memory_gb):
    coefficients = {
        100: (83.0644746, 6.0964415, 0.5139661),
        90: (82.5614426, 5.5197877, 0.4595581),
        80: (81.6742473, 4.6824576, 0.3533578),
        70: (81.9473742, 4.1679360, 0.2691661),
        60: (82.3141742, 3.6856765, 0.2224509),
        50: (80.3144091, 3.2768073, 0.1894818),
        40: (77.0713074, 2.9314441, 0.1659522),
        30: (73.2398958, 2.5875709, 0.1535889),
        20: (71.1406676, 2.2450947, 0.1411264),
        10: (67.2681725, 1.8924068, 0.1295687),
        0: (54.49687195, 1.10934463, 0.09091585),
    }
    
    power_consumption = []
    for load, (intercept, core_coeff, memory_coeff) in sorted(coefficients.items()):
        power = intercept + (core_coeff * cpu_cores) + (memory_coeff * memory_gb)
        power_consumption.append((load / 100.0, round(power, 2)))
    
    return power_consumption

def generate_latency_matrix(n, latency_range):
    latency_matrix = []
    for i in range(n):
        latencies = []
        for j in range(n):
            if i == j:
                latencies.append(0.0)
            else:
                latencies.append(round(np.random.uniform(latency_range[0], latency_range[1]), 2))
        latency_matrix.append(latencies)
    return latency_matrix

def generate_physical_machines(n, cpu_capacity, memory_capacity, speed_range, time_to_turn_on_range, time_to_turn_off_range, state_percentage):
    if n == 0:
        return []
    physical_machines = []
    num_on = int(n * state_percentage / 100)
    state_list = [1] * num_on + [0] * (n - num_on)
    np.random.shuffle(state_list)
    
    for i in range(n):
        id = i
        cpu = np.random.choice(cpu_capacity)
        memory = np.random.choice(memory_capacity)
        capacity = (cpu, memory)
        speed = np.random.beta(1, 5)
        speed = speed * (speed_range[1] - speed_range[0]) + speed_range[0]
        features = (speed,)
        state = (
            round(np.random.uniform(time_to_turn_on_range[0], time_to_turn_on_range[1]), 1), 
            round(np.random.uniform(time_to_turn_off_range[0], time_to_turn_off_range[1]), 1), 
            (0.0, 0.0),  # Initialize loads to 0
            state_list[i]
        )
        power_consumption = calculate_power_consumption(cpu, memory)
        physical_machines.append((id, capacity, features, state, power_consumption))
    return physical_machines

def generate_virtual_machines(n, pm_count, requested_cpu, requested_memory, execution_time_range, allocation_time_range, physical_machines, running_percentage):
    if n == 0:
        return []
    virtual_machines = []
    on_pms = [pm for pm in physical_machines if pm[3][3] == 1]  # List of ON physical machines
    num_running = int(n * running_percentage / 100)

    for i in range(n):
        id = i
        requested = (np.random.choice(requested_cpu), np.random.choice(requested_memory))
        
        if i < num_running:
            suitable_pms = [pm for pm in on_pms if pm[1][0] >= requested[0] and pm[1][1] >= requested[1]]
            if suitable_pms:
                allocated_pm = np.random.choice(suitable_pms)[0]
                total_execution_time = round(np.random.uniform(execution_time_range[0], execution_time_range[1]), 1)
                current_execution_time = round(np.random.uniform(0, total_execution_time), 1)
                run = (current_execution_time, total_execution_time, allocated_pm)
            else:
                run = (0.0, round(np.random.uniform(execution_time_range[0], execution_time_range[1]), 1), -1)
        else:
            total_execution_time = round(np.random.uniform(execution_time_range[0], execution_time_range[1]), 1)
            run = (0.0, total_execution_time, -1)
        
        allocation_time = round(np.random.uniform(allocation_time_range[0], allocation_time_range[1]), 1)
        allocation = (0.0, allocation_time, -1)
        migration_first_round_time = requested[1] / migration_time_network_bandwidth
        migration_down_time = migration_time_resume_vm_on_target + migration_first_round_time * migration_time_memory_dirty_rate / migration_time_network_bandwidth
        migration_total_time = migration_first_round_time + migration_down_time
        migration = (0.0, migration_total_time, migration_down_time, -1, -1)
        virtual_machines.append((id, requested, allocation, run, migration))
    return virtual_machines

def update_physical_machine_loads(physical_machines, virtual_machines):
    # Initialize loads to 0
    pm_loads = {pm[0]: {"cpu_load": 0.0, "memory_load": 0.0} for pm in physical_machines}
    
    # Update loads based on running VMs
    for vm in virtual_machines:
        allocated_pm = vm[3][2]
        if allocated_pm != -1:
            pm_loads[allocated_pm]["cpu_load"] += vm[1][0]
            pm_loads[allocated_pm]["memory_load"] += vm[1][1]
    
    # Update physical machines with the new loads
    updated_physical_machines = []
    for pm in physical_machines:
        id, capacity, features, state, power_consumption = pm
        cpu_load = pm_loads[id]["cpu_load"]
        memory_load = pm_loads[id]["memory_load"]
        updated_state = (state[0], state[1], (cpu_load, memory_load), state[3])
        updated_physical_machines.append((id, capacity, features, updated_state, power_consumption))
    
    return updated_physical_machines

def format_physical_machines(physical_machines):
    legend = "// <id, capacity (cpu, memory), features (speed), state (time_to_turn_on, time_to_turn_off, load (cpu_load, memory_load), state)>\n"
    formatted_physical_machines = legend + "\nphysical_machines = {\n"
    for pm in physical_machines:
        formatted_physical_machines += (
            f"  <{pm[0]}, <{pm[1][0]}, {pm[1][1]}>, <{pm[2][0]}>, <{pm[3][0]}, {pm[3][1]}, <{pm[3][2][0]}, {pm[3][2][1]}>, {pm[3][3]}>>,\n"
        )
    formatted_physical_machines = formatted_physical_machines.rstrip(",\n") + "\n};"
    return formatted_physical_machines

def format_virtual_machines(virtual_machines):
    legend = "// <id, requested (cpu, memory), allocation (current_time, total_time, pm), run (current_time, total_time, pm), migration (current_time, total_time, from_pm, to_pm), group>\n"
    formatted_virtual_machines = legend + "\nvirtual_machines = {\n"
    for vm in virtual_machines:
        formatted_virtual_machines += f"  <{vm[0]}, <{vm[1][0]}, {vm[1][1]}>, <{vm[2][0]}, {vm[2][1]}, {vm[2][2]}>, <{vm[3][0]}, {vm[3][1]}, {vm[3][2]}>, <{vm[4][0]}, {vm[4][1]}, {vm[4][2]}, {vm[4][3]}, {vm[4][4]}>>,\n"
    formatted_virtual_machines = formatted_virtual_machines.rstrip(",\n") + "\n};"
    return formatted_virtual_machines

def format_latency_matrix(latency_matrix):
    formatted_latency = "latency = [\n"
    for row in latency_matrix:
        formatted_latency += "  [" + ", ".join(map(str, row)) + "],\n"
    formatted_latency = formatted_latency.rstrip(",\n") + "\n];"
    return formatted_latency

def format_power_function(physical_machines):
    formatted_power_function = "nb_points = 11;\n\n"
    formatted_power_function += "power_function = [\n"
    for pm in physical_machines:
        points = ", ".join(f"<{point[0]}, {point[1]}>" for point in pm[4])
        formatted_power_function += f"  [{points}],\n"
    formatted_power_function = formatted_power_function.rstrip(",\n") + "\n];"
    return formatted_power_function

def generate_unique_filename(base_path, base_name, extension):
    version = 1
    while True:
        file_name = f"{base_name}_v{version}.{extension}"
        file_path = os.path.join(base_path, file_name)
        if not os.path.exists(file_path):
            return file_path
        version += 1

def get_terminal_input(prompt, default):
    user_input = input(f"{prompt} [{default}]: ")
    return int(user_input) if user_input else default

import argparse

parser = argparse.ArgumentParser(description='Generate data for physical and virtual machines.')
parser.add_argument('--terminal', action='store_true', help='Use terminal input for number of machines')
parser.add_argument('--simulation', nargs=2, metavar=('NUM_PHYSICAL_MACHINES', 'OUTPUT_FILE'), help='Run simulation with specified number of physical machines and output file')
parser.add_argument('--scalability_test', nargs=2, metavar=('NUM_PHYSICAL_MACHINES', 'NUM_VIRTUAL_MACHINES'), help='Run scalability test with specified number of physical and virtual machines')
args = parser.parse_args()

if args.terminal:
    num_physical_machines = get_terminal_input("Number of physical machines", default_num_physical_machines)
    num_virtual_machines = get_terminal_input("Number of virtual machines", default_num_virtual_machines)
    output_folder = data_folder_path
elif args.simulation:
    num_physical_machines = int(args.simulation[0]) if args.simulation[0] else default_num_physical_machines
    num_virtual_machines = 0
    output_file = args.simulation[1]
    output_folder = os.path.dirname(output_file)  # Use the directory of the provided file path
elif args.scalability_test:
    num_physical_machines = int(args.scalability_test[0]) if args.scalability_test[0] else default_num_physical_machines
    num_virtual_machines = int(args.scalability_test[1]) if args.scalability_test[1] else default_num_virtual_machines
    output_folder = os.path.join(data_folder_path, 'scalability_test')
else:
    num_physical_machines = default_num_physical_machines
    num_virtual_machines = default_num_virtual_machines
    output_folder = data_folder_path

# latency_matrix = generate_latency_matrix(num_physical_machines, latency_range)
physical_machines = generate_physical_machines(num_physical_machines, pm_cpu_capacity, pm_memory_capacity, pm_speed_range, pm_time_to_turn_on_range, pm_time_to_turn_off_range, state_percentage)
virtual_machines = generate_virtual_machines(num_virtual_machines, num_physical_machines, vm_requested_cpu, vm_requested_memory, execution_time_range, allocation_time_range, physical_machines, running_percentage)

physical_machines = update_physical_machine_loads(physical_machines, virtual_machines)

# Ensure the output folder exists
output_folder = os.path.expanduser(output_folder)
os.makedirs(output_folder, exist_ok=True)

if physical_machines:
    formatted_physical_machines = format_physical_machines(physical_machines)
    # formatted_latency_matrix = format_latency_matrix(latency_matrix)
    formatted_power_function = format_power_function(physical_machines)
    
    if args.simulation:
        pm_file_path = output_file
    elif args.scalability_test:
        pm_file_path = os.path.join(output_folder, f"physical_machines.dat")
    else:
        pm_base_name = f"physical_machines_{num_physical_machines}"
        pm_file_path = generate_unique_filename(output_folder, pm_base_name, 'dat')
    
    with open(pm_file_path, 'w') as pm_file:
        pm_file.write(formatted_physical_machines)
        pm_file.write("\n\n")
        # pm_file.write(formatted_latency_matrix)
        # pm_file.write("\n\n")
        pm_file.write(formatted_power_function)
    
    print(f"Physical machines data saved to {pm_file_path}")

if virtual_machines:
    formatted_virtual_machines = format_virtual_machines(virtual_machines)
    
    vm_base_name = f"virtual_machines_{num_virtual_machines}"
    
    if args.scalability_test:
        vm_file_path = os.path.join(output_folder, f"virtual_machines.dat")
    else:
        vm_file_path = generate_unique_filename(output_folder, vm_base_name, 'dat')
    
    with open(vm_file_path, 'w') as vm_file:
        vm_file.write(formatted_virtual_machines)
    
    print(f"Virtual machines data saved to {vm_file_path}")
