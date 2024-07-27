import random
import os
import sys
from config import (
    pm_config, vm_config, default_values, data_folder_path,
    pm_cpu_capacity, pm_memory_capacity, pm_speed_range, pm_max_energy_consumption_range, pm_time_to_turn_on_range, pm_time_to_turn_off_range,
    vm_requested_cpu, vm_requested_memory, execution_time_range, vm_expected_profit_range, migration_time_range, allocation_time_range,
    default_num_physical_machines, default_num_virtual_machines, state_percentage, running_percentage
)

def generate_physical_machines(n, cpu_capacity, memory_capacity, speed_range, max_energy_consumption_range, time_to_turn_on_range, time_to_turn_off_range, state_percentage):
    if n == 0:
        return []
    physical_machines = []
    num_on = int(n * state_percentage / 100)
    state_list = [1] * num_on + [0] * (n - num_on)
    random.shuffle(state_list)
    
    for i in range(n):
        id = i
        capacity = (random.choice(cpu_capacity), random.choice(memory_capacity))
        features = (round(random.uniform(speed_range[0], speed_range[1]), 1), round(random.uniform(max_energy_consumption_range[0], max_energy_consumption_range[1]), 1))
        state = (round(random.uniform(time_to_turn_on_range[0], time_to_turn_on_range[1]), 1), round(random.uniform(time_to_turn_off_range[0], time_to_turn_off_range[1]), 1), state_list[i])
        physical_machines.append((id, capacity, features, state))
    return physical_machines

def generate_virtual_machines(n, pm_count, requested_cpu, requested_memory, execution_time_range, expected_profit_range, migration_time_range, allocation_time_range, physical_machines, running_percentage):
    if n == 0:
        return []
    virtual_machines = []
    on_pms = [pm for pm in physical_machines if pm[3][2] == 1]  # List of ON physical machines
    num_running = int(n * running_percentage / 100)

    for i in range(n):
        id = i
        requested = (random.choice(requested_cpu), random.choice(requested_memory))
        
        if i < num_running:
            suitable_pms = [pm for pm in on_pms if pm[1][0] >= requested[0] and pm[1][1] >= requested[1]]
            if suitable_pms:
                allocated_pm = random.choice(suitable_pms)[0]
                total_execution_time = round(random.uniform(execution_time_range[0], execution_time_range[1]), 1)
                current_execution_time = round(random.uniform(0, total_execution_time), 1)
                run = (current_execution_time, total_execution_time, allocated_pm)
            else:
                run = (0.0, round(random.uniform(execution_time_range[0], execution_time_range[1]), 1), -1)
        else:
            total_execution_time = round(random.uniform(execution_time_range[0], execution_time_range[1]), 1)
            run = (0.0, total_execution_time, -1)
        
        allocation_time = round(random.uniform(allocation_time_range[0], allocation_time_range[1]), 1)
        allocation = (0.0, allocation_time, -1)
        migration = (0.0, round(random.uniform(migration_time_range[0], migration_time_range[1]), 1), -1, -1)
        group = random.randint(1, 10)  # Assuming groups are numbered from 1 to 10
        expected_profit = round(random.uniform(expected_profit_range[0], expected_profit_range[1]), 2)
        virtual_machines.append((id, requested, allocation, run, migration, group, expected_profit))
    return virtual_machines

def format_physical_machines(physical_machines):
    legend = "// <id, capacity (cpu, memory), features (speed, max_energy_consumption), state (time_to_turn_on, time_to_turn_off, state)>\n"
    formatted_physical_machines = legend + "\nphysical_machines = {\n"
    for pm in physical_machines:
        formatted_physical_machines += f"  <{pm[0]}, <{pm[1][0]}, {pm[1][1]}>, <{pm[2][0]}, {pm[2][1]}>, <{pm[3][0]}, {pm[3][1]}, {pm[3][2]}>>,\n"
    formatted_physical_machines = formatted_physical_machines.rstrip(",\n") + "\n};"
    return formatted_physical_machines

def format_virtual_machines(virtual_machines):
    legend = "// <id, requested (cpu, memory), allocation (current_time, total_time, pm), run (current_time, total_time, pm), migration (current_time, total_time, from_pm, to_pm), group, expected_profit>\n"
    formatted_virtual_machines = legend + "\nvirtual_machines = {\n"
    for vm in virtual_machines:
        formatted_virtual_machines += f"  <{vm[0]}, <{vm[1][0]}, {vm[1][1]}>, <{vm[2][0]}, {vm[2][1]}, {vm[2][2]}>, <{vm[3][0]}, {vm[3][1]}, {vm[3][2]}>, <{vm[4][0]}, {vm[4][1]}, {vm[4][2]}, {vm[4][3]}>, {vm[5]}, {vm[6]}>,\n"
    formatted_virtual_machines = formatted_virtual_machines.rstrip(",\n") + "\n};"
    return formatted_virtual_machines

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

if len(sys.argv) > 1 and sys.argv[1] == '--terminal':
    num_physical_machines = get_terminal_input("Number of physical machines", default_num_physical_machines)
    num_virtual_machines = get_terminal_input("Number of virtual machines", default_num_virtual_machines)
else:
    num_physical_machines = default_num_physical_machines
    num_virtual_machines = default_num_virtual_machines

physical_machines = generate_physical_machines(num_physical_machines, pm_cpu_capacity, pm_memory_capacity, pm_speed_range, pm_max_energy_consumption_range, pm_time_to_turn_on_range, pm_time_to_turn_off_range, state_percentage)
virtual_machines = generate_virtual_machines(num_virtual_machines, num_physical_machines, vm_requested_cpu, vm_requested_memory, execution_time_range, vm_expected_profit_range, migration_time_range, allocation_time_range, physical_machines, running_percentage)

if physical_machines:
    formatted_physical_machines = format_physical_machines(physical_machines)
    base_path = os.path.expanduser(data_folder_path)
    os.makedirs(base_path, exist_ok=True)
    pm_base_name = f"physical_machines_{num_physical_machines}"
    pm_file_path = generate_unique_filename(base_path, pm_base_name, 'dat')
    with open(pm_file_path, 'w') as pm_file:
        pm_file.write(formatted_physical_machines)
    print(f"Physical machines data saved to {pm_file_path}")

if virtual_machines:
    formatted_virtual_machines = format_virtual_machines(virtual_machines)
    base_path = os.path.expanduser(data_folder_path)
    os.makedirs(base_path, exist_ok=True)
    vm_base_name = f"virtual_machines_{num_virtual_machines}"
    vm_file_path = generate_unique_filename(base_path, vm_base_name, 'dat')
    with open(vm_file_path, 'w') as vm_file:
        vm_file.write(formatted_virtual_machines)
    print(f"Virtual machines data saved to {vm_file_path}")
