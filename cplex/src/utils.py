import math
import numpy as np
import pandas as pd
import os
import re
import json
import ast
from datetime import datetime, timedelta
from config import MODEL_INPUT_FOLDER_PATH, POWER_FUNCTION_FILE, WORKLOAD_START_TIMES_FILE
from weights import price, migration, pue, energy, w_concurrent_migrations, w_load_cpu, migration_penalty

try:
    profile # type: ignore
except NameError:
    def profile(func):
        return func

@profile
def load_json_file(file_path):
    if not os.path.exists(file_path):
        raise ValueError(f"File {file_path} not found.")
    with open(file_path, 'r') as file:
        data = json.load(file)
    return data

def load_new_vms(vms_trace_file_path):
    if not os.path.exists(vms_trace_file_path):
        raise ValueError(f"File {vms_trace_file_path} not found. Please provide a file with real VMs or set REAL_DATA to False.")
    with open(vms_trace_file_path, 'r') as file:
        real_vms = json.load(file)  # Load VMs from JSON file
    
    # Convert real_vms to the format expected by the simulation
    new_vms = []
    for vm in real_vms:
        requested_cpu = int(vm['requested_processors'])
        requested_memory = int(vm['requested_memory'])
        run_total_time = vm['run_time']
        revenue = (requested_cpu * price['cpu'] + requested_memory * price['memory']) * run_total_time
        migration_first_round_time = requested_memory / migration['time']['network_bandwidth']
        migration_down_time = migration['time']['resume_vm_on_target'] + migration_first_round_time * migration['time']['memory_dirty_rate'] / migration['time']['network_bandwidth']
        migration_total_time = migration_first_round_time + migration_down_time


        new_vm = {
            'id': vm['job_number'],
            'requested': {
                'cpu': requested_cpu,
                'memory': requested_memory,
            },
            'allocation': {
                'current_time': 0.0,
                'total_time': min(vm['run_time'] * 0.01, 5),
                'pm': -1
            },
            'run': {
                'current_time': 0.0,
                'total_time': vm['run_time'],
                'pm': -1
            },
            'migration': {
                'current_time': 0.0,
                'total_time': migration_total_time,
                'down_time': migration_down_time,
                'from_pm': -1,
                'to_pm': -1
            },
            'arrival_time': vm['submit_time'],
            'revenue': revenue
        }
        new_vms.append(new_vm)
    
    sorted_vms = sorted(new_vms, key=lambda x: x['arrival_time'])
    
    return sorted_vms

def load_virtual_machines(file_path):
    if not os.path.exists(file_path):
        return {}
    with open(file_path, 'r') as file:
        data = file.read()
    try:
        vm_lines = data.split('virtual_machines = {')[1].split('};')[0].strip().split('\n')
    except IndexError:
        print()
        raise ValueError(f"Error in loading virtual machines: Check the format of {file_path}")

    vms = {}
    for line in vm_lines:
        line = line.strip().strip('<').strip('>')
        parts = [part.strip().strip('<').strip('>') for part in line.split(',')]
        vm = {
            'id': int(parts[0]),
            'requested': {
                'cpu': int(parts[1]),
                'memory': int(parts[2])
            },
            'allocation': {
                'current_time': float(parts[3]),
                'total_time': float(parts[4]),
                'pm': int(parts[5])
            },
            'run': {
                'current_time': float(parts[6]),
                'total_time': float(parts[7]),
                'pm': int(parts[8])
            },
            'migration': {
                'current_time': float(parts[9]),
                'total_time': float(parts[10]),
                'down_time': float(parts[11]),
                'from_pm': int(parts[12]),
                'to_pm': int(parts[13])
            },
        }
        vms[vm['id']] = vm  # Store VM in dictionary keyed by ID
    return vms

def load_physical_machines(file_path):
    if not os.path.exists(file_path):
        print(f"File {file_path} not found. Please provide an initial Physical Machines file.")
        return {}

    with open(file_path, 'r') as file:
        data = file.read()

    try:
        pm_section = data.split('physical_machines = {')[1].split('};')[0].strip().split('\n')
    except IndexError:
        print()
        raise ValueError(f"Error in loading physical machines: Check the format of {file_path}")

    pms = {}
    for line in pm_section:
        line = line.strip().strip('<').strip('>')
        parts = [part.strip().strip('<').strip('>') for part in line.split(',')]
        pm = {
            'id': int(parts[0]),
            'capacity': {
                'cpu': int(parts[1]),
                'memory': int(parts[2])
            },
            'features': {
                'speed': float(parts[3])
            },
            's': {
                'time_to_turn_on': float(parts[4]),
                'time_to_turn_off': float(parts[5]),
                'load': {
                    'cpu': float(parts[6]),
                    'memory': float(parts[7])
                },
                'state': int(parts[8])
            }
        }
        pms[pm['id']] = pm  # Store PM in dictionary keyed by ID

    normalize_speed(pms)  # Ensure this function works with dictionaries

    return pms


def get_start_time(workload_name):
    with open(WORKLOAD_START_TIMES_FILE, 'r') as file:
        data = json.load(file)
    return data[workload_name]

def get_first_vm_arrival_time(vms_trace_file_path):
    if not os.path.exists(vms_trace_file_path):
        raise ValueError(f"File {vms_trace_file_path} not found. Please provide a file with real VMs or set REAL_DATA to False.")
    with open(vms_trace_file_path, 'r') as file:
        real_vms = json.load(file)  # Load VMs from JSON file
    return real_vms[0]['submit_time']

def get_last_vm_arrival_time(vms_trace_file_path):
    if not os.path.exists(vms_trace_file_path):
        raise ValueError(f"File {vms_trace_file_path} not found. Please provide a file with real VMs or set REAL_DATA to False.")
    with open(vms_trace_file_path, 'r') as file:
        real_vms = json.load(file)  # Load VMs from JSON file
    return real_vms[-1]['submit_time']

def get_exact_time(start_time_str, step, time_step):
    start_time = datetime.strptime(start_time_str, '%a %b %d %H:%M:%S %Z %Y')
    return start_time + timedelta(seconds=step * time_step)

def get_real_cpu_and_memory(step, start_time_str, aggregated, time_step):
    # Compute index_step for all indices using vectorized operations
    index_steps = aggregated.index.map(lambda idx: convert_to_step(idx, start_time_str, time_step))
    
    # Create a boolean mask where index_steps match the desired step
    mask = index_steps == step
    
    # Select the rows where the mask is True
    rows = aggregated.loc[mask]
    
    if not rows.empty:
        # Return the 'cpu' and 'memory' values from the first matching row
        return rows.iloc[0]['cpu'], rows.iloc[0]['memory']
    else:
        print(f"No real data workload found for step {step}")
        return None, None

def convert_to_step(actual_datetime, start_time_str, time_step):
    start_time = datetime.strptime(start_time_str, '%a %b %d %H:%M:%S %Z %Y')
    step = (actual_datetime - start_time).total_seconds() / time_step
    return math.ceil(step)

def load_configuration(folder_path, epgap):
    weights_data = f"""
epgap = {epgap};

price = <{price['cpu']}, {price['memory']}>;

energy = <{energy['cost']}, {energy['limit']}>;

PUE = {pue};

migration = <
              <{migration['time']['network_bandwidth']}, 
               {migration['time']['resume_vm_on_target']}, 
               {migration['time']['memory_dirty_rate']}>, 
              <<{migration['energy']['cpu_overhead']['source']}, 
               {migration['energy']['cpu_overhead']['target']}>,
               {migration['energy']['concurrent']}>
            >;

w_concurrent_migrations = {w_concurrent_migrations};

migration_penalty = {migration_penalty};

w_load_cpu = {w_load_cpu};
"""

    # Ensure the model input folder exists
    os.makedirs(folder_path, exist_ok=True)

    # Define the path to the weights.dat file
    weights_file_path = os.path.join(folder_path, 'weights.dat')

    # Write the configuration to the weights.dat file
    with open(weights_file_path, 'w') as file:
        file.write(weights_data)

def convert_to_serializable(obj):
    """Recursively convert numpy types to native Python types."""
    if isinstance(obj, np.int64) or isinstance(obj, np.int32):
        return int(obj)
    elif isinstance(obj, np.float64) or isinstance(obj, np.float32):
        return float(obj)
    elif isinstance(obj, dict):
        return {key: convert_to_serializable(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_to_serializable(item) for item in obj]
    return obj

def save_vm_sets(active_vms, terminated_vms, step, output_folder_path):
    active_file_path = os.path.join(output_folder_path, f'active_vms_t{step}.json')
    terminated_file_path = os.path.join(output_folder_path, f'terminated_vms_t{step}.json')
    
    # Convert data to serializable format before saving
    active_vms_serializable = convert_to_serializable(active_vms)
    terminated_vms_serializable = convert_to_serializable(terminated_vms)
    
    with open(active_file_path, 'w') as file:
        json.dump(active_vms_serializable, file, indent=4)
    with open(terminated_file_path, 'w') as file:
        json.dump(terminated_vms_serializable, file, indent=4)

def save_pm_sets(pms, step, output_folder_path):
    file_path = os.path.join(output_folder_path, f'pms_t{step}.json')
    
    # Convert data to serializable format before saving
    pms_serializable = convert_to_serializable(pms)
    
    with open(file_path, 'w') as file:
        json.dump(pms_serializable, file, indent=4)

def save_power_function(file_path):
    if not os.path.exists(file_path):
        print(f"File {file_path} not found.")
        return

    with open(file_path, 'r') as file:
        data = file.read()

    try:
        power_function_section = data.split('power_function = [')[1].split('];')[0].strip() + '];'
        nb_points_section = data.split('nb_points = ')[1].split(';')[0].strip() + ';'
    except IndexError:
        print()
        raise ValueError(f"Error in loading power function or nb_points: Check the format of {file_path}")

    with open(POWER_FUNCTION_FILE, 'w') as file:
        file.write('nb_points = ' + nb_points_section + '\n\n')
        file.write('power_function = [\n')
        file.write(power_function_section)
        file.write('\n')

def parse_power_function(file_path, pm_ids):
    with open(file_path, 'r') as file:
        data = file.read()

    # Extract nb_points
    nb_points_match = re.search(r'nb_points\s*=\s*(\d+);', data)
    if nb_points_match:
        nb_points = int(nb_points_match.group(1))
    else:
        raise ValueError("Could not find nb_points in the file.")

    # Extract power_function data
    power_function_match = re.search(r'power_function\s*=\s*\[\s*(.*?)\s*\];', data, re.DOTALL)
    if power_function_match:
        power_function_str = power_function_match.group(1)
    else:
        raise ValueError("Could not find power_function in the file.")

    # Clean and convert the string to a valid Python literal
    power_function_str_clean = power_function_str.replace('<', '[').replace('>', ']')
    power_function_str_clean = power_function_str_clean.replace(';', ',').replace('\n', '').replace(' ', '')

    # Ensure the string is properly enclosed in brackets
    power_function_str_clean = '[' + power_function_str_clean + ']'

    try:
        # Safely evaluate the string to a Python object
        power_function_data = ast.literal_eval(power_function_str_clean)
    except Exception as e:
        raise ValueError(f"Error parsing power_function data: {e}")

    # Map PM IDs to their corresponding power functions
    piecewise_linear_functions = dict(zip(pm_ids, power_function_data))

    return nb_points, piecewise_linear_functions

def convert_power_function_to_model_input_format(pms, power_function_dict, nb_points):
    output_content = '\n\nnb_points = ' + str(nb_points) + ';\n\n'
    output_content += 'power_function = [\n'
    for pm_id in pms:
        row = power_function_dict[pm_id]
        row_str = '  [' + ', '.join(f'<{x[0]}, {x[1]}>' for x in row) + '],\n'
        output_content += row_str
    output_content = output_content.rstrip(',\n') + '\n];\n'  # Remove the last comma and newline, close the list

    return output_content

def convert_vms_to_model_input_format(vms):
    formatted_vms = "virtual_machines = {\n"
    for vm in vms.values():
        formatted_vms += f"  <{vm['id']}, <{vm['requested']['cpu']}, {vm['requested']['memory']}>, <{vm['allocation']['current_time']}, {vm['allocation']['total_time']}, {vm['allocation']['pm']}>, <{vm['run']['current_time']}, {vm['run']['total_time']}, {vm['run']['pm']}>, <{vm['migration']['current_time']}, {vm['migration']['total_time']}, {vm['migration']['down_time']}, {vm['migration']['from_pm']}, {vm['migration']['to_pm']}>>,\n"
    formatted_vms = formatted_vms.rstrip(",\n") + "\n};"
    return formatted_vms

def convert_pms_to_model_input_format(pms):
    formatted_pms = "physical_machines = {\n"
    for pm in pms.values():
        formatted_pms += f"  <{pm['id']}, <{pm['capacity']['cpu']}, {pm['capacity']['memory']}>, <{pm['features']['speed']}>, <{pm['s']['time_to_turn_on']}, {pm['s']['time_to_turn_off']}, <{pm['s']['load']['cpu']}, {pm['s']['load']['memory']}>, {pm['s']['state']}>>, \n"
    formatted_pms = formatted_pms.rstrip(",\n") + "\n};"
    return formatted_pms

def save_model_input_format(vms, pms, step, model_input_folder_path, power_function_dict, nb_points):
    # Ensure the directory exists
    os.makedirs(model_input_folder_path, exist_ok=True)
    
    # Construct file paths
    base_filename = f'_t{step}.dat'
    vm_filename = 'virtual_machines' + base_filename
    pm_filename = 'physical_machines' + base_filename
    vm_model_input_file_path = os.path.join(model_input_folder_path, vm_filename)
    pm_model_input_file_path = os.path.join(model_input_folder_path, pm_filename)
    
    # Convert data to the required format
    formatted_vms = convert_vms_to_model_input_format(vms)
    formatted_pms = convert_pms_to_model_input_format(pms)
    formatted_power_function = convert_power_function_to_model_input_format(pms, power_function_dict, nb_points)
    
    # Write formatted VMs to file
    with open(vm_model_input_file_path, 'w', encoding='utf-8') as vm_file:
        vm_file.write(formatted_vms)
    
    # Write formatted PMs and power function to file
    with open(pm_model_input_file_path, 'w', encoding='utf-8') as pm_file:
        pm_file.write(formatted_pms)
        pm_file.write(formatted_power_function)
    
    return vm_model_input_file_path, pm_model_input_file_path

def parse_opl_output(output):
    parsed_data = {}
    
    patterns = {
        'has_to_be_on': re.compile(r'has_to_be_on = \[(.*?)\];', re.DOTALL),
        'new_allocation': re.compile(r'new_allocation = \[\[(.*?)\]\];', re.DOTALL),
        'is_migrating_from': re.compile(r'is_migrating_from = \[\[(.*?)\]\];', re.DOTALL),
        'vm_ids': re.compile(r'Virtual Machines IDs: \[(.*?)\]'),
        'pm_ids': re.compile(r'Physical Machines IDs: \[(.*?)\]'),
        'is_allocation': re.compile(r'is_allocation = \[(.*?)\];', re.DOTALL),
        'is_migration': re.compile(r'is_migration = \[(.*?)\];', re.DOTALL),
    }
    
    for key, pattern in patterns.items():
        match = pattern.search(output)
        if match:
            if key in ['new_allocation'] or key in ['is_migrating_from']:
                parsed_data[key] = parse_matrix(match.group(1))
            else:
                parsed_data[key] = [int(num) if num.isdigit() else float(num) for num in match.group(1).strip().split()]
    
    return parsed_data

def get_opl_return_code(output):
    pattern = r'main returns\s+([-+]?\d+)'

    # Search for the pattern in the input string
    match = re.search(pattern, output)
    
    if match:
        return int(match.group(1))
    else:
        return None
    
def is_opl_output_valid(output, return_code):
    if return_code != 0:
        return False

    output_lower = output.lower()
    time_limit_exceeded_keyword = "time limit exceeded"
    no_solution_keyword = "no solution"
    
    if time_limit_exceeded_keyword in output_lower or no_solution_keyword in output_lower:
        return False
    return True

def count_non_valid_entries(performance_log_file):
    non_valid_entries = 0
    total_entries = 0
    
    with open(performance_log_file, 'r') as file:
        for line in file:
            if "main" in line or "mini" in line:
                total_entries += 1
                if "not valid" in line:
                    non_valid_entries += 1
    return non_valid_entries, total_entries
    
def parse_matrix(matrix_str):
    return [
        [int(num) if num.isdigit() else float(num) for num in row.strip().split()]
        for row in matrix_str.strip().split(']\n             [')
    ]

def find_two_largest(times):
    max_time = second_max_time = 0
    for time in times:
        if time > max_time:
            second_max_time = max_time
            max_time = time
        elif time > second_max_time:
            second_max_time = time
    return max_time, second_max_time

def find_min_extra_time(vms_extra_time, pm_id):
    """
    Returns the minimum extra_time for the given pm_id from the vms_extra_time dictionary.

    Parameters:
    - vms_extra_time (dict): Dictionary with VM IDs as keys and tuples (from_pm_id, extra_time) as values.
    - pm_id (str): The pm_id to filter by.

    Returns:
    - float: The minimum extra_time for the specified pm_id.
    - None: If the pm_id is not found in any of the entries.
    """
    # Extract extra_time values where from_pm_id matches pm_id
    extra_times = [
        extra_time 
        for from_pm_id, extra_time in vms_extra_time.values() 
        if from_pm_id == pm_id
    ]
    
    if not extra_times:
        raise ValueError(f"pm id {pm_id} to turn off after migration completed, but no migration completed found")
    
    # Return the minimum extra_time
    return min(extra_times)

def evaluate_piecewise_linear_function(piecewise_function, x_value, migration_overhead=False):
    """
    Evaluate a piecewise linear function at a given x_value.
    """
    if migration_overhead:
        max_migration_overhead = migration['energy']['cpu_overhead']['source'] + migration['energy']['cpu_overhead']['target'] + migration['energy']['concurrent']
        if x_value <= 1 + max_migration_overhead:
            x0, y0 = piecewise_function[-2]
            x1, y1 = piecewise_function[-1]

            return y0 + (y1 - y0) * (x_value - x0) / (x1 - x0)
    
    else:   
        for i in range(len(piecewise_function) - 1):
            x0, y0 = piecewise_function[i]
            x1, y1 = piecewise_function[i + 1]
        
            if x0 <= x_value <= x1:
                return y0 + (y1 - y0) * (x_value - x0) / (x1 - x0)
        
    raise ValueError(f"x_value {x_value} is out of bounds for the piecewise linear function. Migration Overhead is {migration_overhead}")

def round_down(value):
    return math.floor(value * 1000000) / 1000000

def normalize_speed(pms, target_mean=1):
    speeds = [pm['features']['speed'] for pm in pms.values()]
    current_mean = sum(speeds) / len(speeds)
    scaling_factor = target_mean / current_mean

    # Normalize the speeds by multiplying each speed by the scaling factor
    for pm in pms.values():
        pm['features']['speed'] *= scaling_factor

    return pms

def find_migration_times(active_vms, pm):
    pm_id = pm['id']
    
    # Get remaining times for migrations from pm (source)
    source_times = [vm['migration']['total_time'] - vm['migration']['current_time'] 
                    for vm in active_vms if vm['migration']['from_pm'] == pm_id]
    
    # Get remaining times for migrations to pm (target)
    target_times = [vm['migration']['total_time'] - vm['migration']['current_time'] 
                    for vm in active_vms if vm['migration']['to_pm'] == pm_id]
    
    # All unique event times when migrations end
    event_times = sorted(set(source_times + target_times))
    
    # Initialize counts
    n_source_running = len(source_times)
    n_target_running = len(target_times)
    
    # Create a dictionary of events to track migrations ending
    events = {}
    for t in source_times:
        events.setdefault(t, {'source': 0, 'target': 0})
        events[t]['source'] += 1
    for t in target_times:
        events.setdefault(t, {'source': 0, 'target': 0})
        events[t]['target'] += 1
    
    # Sort the event times
    sorted_event_times = sorted(events.keys())
    
    # Initialize variables
    intervals = []
    prev_time = 0
    
    # Process each interval between events
    for t in sorted_event_times:
        # Duration of the current interval
        duration = t - prev_time
        
        # Record the interval and counts
        intervals.append((prev_time, t, n_source_running, n_target_running))
        
        # Update counts based on events at time t
        n_source_running -= events[t]['source']
        n_target_running -= events[t]['target']
        
        # Move to the next time
        prev_time = t
    
    # Compute the durations for each condition
    real_time_only_source = 0
    real_time_only_target = 0
    real_time_multiple_source = 0
    real_time_multiple_target = 0
    real_time_multiple_source_and_target = 0
    
    for start, end, n_source, n_target in intervals:
        duration = end - start
        if n_source > 0 and n_target == 0:
            if n_source == 1:
                real_time_only_source += duration
            elif n_source > 1:
                real_time_multiple_source += duration
        elif n_source == 0 and n_target > 0:
            if n_target == 1:
                real_time_only_target += duration
            elif n_target > 1:
                real_time_multiple_target += duration
        elif n_source > 0 and n_target > 0:
            real_time_multiple_source_and_target += duration
        # If both n_source and n_target are zero, do nothing
    
    return (
        real_time_only_source,
        real_time_only_target,
        real_time_multiple_source,
        real_time_multiple_target,
        real_time_multiple_source_and_target
    )

def calculate_features(step, start_time_str, time_step):
    start_time = datetime.strptime(start_time_str, '%a %b %d %H:%M:%S %Z %Y')
    current_time = start_time + timedelta(seconds=step * time_step)

    hour = current_time.hour
    day_of_week = current_time.weekday()
    data = {
        'hour': [hour],
        'day_of_week': [day_of_week]
    }
    workload_ts = pd.DataFrame(data, index=[current_time])
    return workload_ts


def calculate_load(physical_machines, active_vms, time_step, pm_manager=False):
    cpu_load = {pm_id: 0.0 for pm_id in physical_machines.keys()}
    memory_load = {pm_id: 0.0 for pm_id in physical_machines.keys()}

    for vm in active_vms.values():
        pm_id = vm['allocation']['pm'] if vm['allocation']['pm'] != -1 else (
            vm['migration']['to_pm'] if vm['migration']['to_pm'] != -1 else vm['run']['pm']
        )
        
        if pm_id != -1:
            pm = physical_machines.get(pm_id)
            if pm and (pm['s']['state'] == 1 and pm['s']['time_to_turn_on'] < time_step or pm_manager):
                cpu_load[pm_id] += vm['requested']['cpu'] / pm['capacity']['cpu']
                memory_load[pm_id] += vm['requested']['memory'] / pm['capacity']['memory']

        if vm['migration']['from_pm'] != -1:
            from_pm_id = vm['migration']['from_pm']
            from_pm = physical_machines.get(from_pm_id)
            if from_pm:
                cpu_load[from_pm_id] += vm['requested']['cpu'] / from_pm['capacity']['cpu']
                memory_load[from_pm_id] += vm['requested']['memory'] / from_pm['capacity']['memory']
        
    for pm_id in cpu_load.keys():
        if cpu_load[pm_id] > 1:
            cpu_load[pm_id] = round_down(cpu_load[pm_id])
        if memory_load[pm_id] > 1:
            memory_load[pm_id] = round_down(memory_load[pm_id])

    return cpu_load, memory_load

def calculate_load_costs(physical_machines, active_vms, time_step):
    cpu_load_precise = {pm_id: 0.0 for pm_id in physical_machines.keys()}
    memory_load_precise = {pm_id: 0.0 for pm_id in physical_machines.keys()}

    for vm in active_vms.values():
        pm_id = vm['allocation']['pm'] if vm['allocation']['pm'] != -1 else (
            vm['migration']['to_pm'] if vm['migration']['to_pm'] != -1 else vm['run']['pm']
        )
        remaining_run_time = vm['allocation']['total_time'] - vm['allocation']['current_time'] + vm['run']['total_time'] - vm['run']['current_time']
        remaining_migration_time = vm['migration']['total_time'] - vm['migration']['current_time']
        
        if remaining_run_time < 0 or remaining_migration_time < 0:
            raise ValueError(f"Remaining run time or migration time is negative for VM {vm['id']}")
        
        run_time_weight = remaining_run_time / time_step if remaining_run_time < time_step else 1
        migration_time_weight = remaining_migration_time / time_step if remaining_migration_time < time_step else 1

        if pm_id != -1:
            pm = physical_machines.get(pm_id)
            if pm and pm['s']['state'] == 1 and pm['s']['time_to_turn_on'] < time_step:
                cpu_load_precise[pm_id] += run_time_weight * vm['requested']['cpu'] / pm['capacity']['cpu']
                memory_load_precise[pm_id] += run_time_weight * vm['requested']['memory'] / pm['capacity']['memory']

        if vm['migration']['from_pm'] != -1:
            from_pm_id = vm['migration']['from_pm']
            from_pm = physical_machines.get(from_pm_id)
            if from_pm:
                cpu_load_precise[from_pm_id] += migration_time_weight * vm['requested']['cpu'] / from_pm['capacity']['cpu']
                memory_load_precise[from_pm_id] += migration_time_weight * vm['requested']['memory'] / from_pm['capacity']['memory']
        
    for pm_id in physical_machines.keys():
        if cpu_load_precise[pm_id] > 1:
            cpu_load_precise[pm_id] = round_down(cpu_load_precise[pm_id])
        elif cpu_load_precise[pm_id] < 0:
            raise ValueError(f"CPU load for PM {pm_id} is negative: {cpu_load_precise[pm_id]}")
        if memory_load_precise[pm_id] > 1:
            memory_load_precise[pm_id] = round_down(memory_load_precise[pm_id])
        elif memory_load_precise[pm_id] < 0:
            raise ValueError(f"Memory load for PM {pm_id} is negative: {memory_load_precise[pm_id]}")

    return cpu_load_precise, memory_load_precise

@profile
def calculate_future_load(physical_machines, active_vms, time_window, time_step):
    import math

    # Precompute future time windows
    num_steps = math.ceil(time_window / time_step)
    future_time_windows = [(step * time_step) for step in range(1, num_steps + 1)]
    num_pms = len(physical_machines)
    future_loads = [([0.0] * num_pms, [0.0] * num_pms) for _ in future_time_windows]

    # Precompute data for each VM
    vm_data_list = []
    for vm in active_vms.values():
        # Determine the PM ID for the VM
        pm_id = vm['allocation']['pm']
        if pm_id == -1:
            pm_id = vm['migration']['to_pm']
            if pm_id == -1:
                pm_id = vm['run']['pm']
                if pm_id == -1:
                    continue  # Skip if PM ID is still -1

        pm = physical_machines[pm_id]
        pm_state = pm['s']['state']
        pm_time_to_turn_on = pm['s']['time_to_turn_on']
        pm_speed = pm['features']['speed']
        pm_cpu_capacity = pm['capacity']['cpu']
        pm_memory_capacity = pm['capacity']['memory']

        vm_cpu_load = vm['requested']['cpu'] / pm_cpu_capacity
        vm_memory_load = vm['requested']['memory'] / pm_memory_capacity

        remaining_time = (
            pm_time_to_turn_on
            + (
                (vm['allocation']['total_time'] - vm['allocation']['current_time'])
                + (vm['run']['total_time'] - vm['run']['current_time'])
            )
            / pm_speed
        )
        if vm['migration']['to_pm'] != -1:
            remaining_time += vm['migration']['total_time'] - vm['migration']['current_time']

        from_pm_id = vm['migration']['from_pm']
        if from_pm_id != -1:
            from_pm = physical_machines[from_pm_id]
            from_pm_cpu_load = vm['requested']['cpu'] / from_pm['capacity']['cpu']
            from_pm_memory_load = vm['requested']['memory'] / from_pm['capacity']['memory']
        else:
            from_pm_cpu_load = from_pm_memory_load = 0.0

        vm_data_list.append({
            'pm_id': pm_id,
            'pm_state': pm_state,
            'pm_time_to_turn_on': pm_time_to_turn_on,
            'remaining_time': remaining_time,
            'vm_cpu_load': vm_cpu_load,
            'vm_memory_load': vm_memory_load,
            'from_pm_id': from_pm_id,
            'from_pm_cpu_load': from_pm_cpu_load,
            'from_pm_memory_load': from_pm_memory_load,
        })

    # Compute loads for each future time window
    for idx, actual_time_window in enumerate(future_time_windows):
        cpu_load, memory_load = future_loads[idx]
        for vm_data in vm_data_list:
            pm_id = vm_data['pm_id']
            if vm_data['pm_state'] == 1 and vm_data['pm_time_to_turn_on'] < actual_time_window:
                if actual_time_window < vm_data['remaining_time']:
                    cpu_load[pm_id] += vm_data['vm_cpu_load']
                    memory_load[pm_id] += vm_data['vm_memory_load']
            if vm_data['from_pm_id'] != -1:
                cpu_load[vm_data['from_pm_id']] += vm_data['from_pm_cpu_load']
                memory_load[vm_data['from_pm_id']] += vm_data['from_pm_memory_load']

    return future_loads


def clean_up_model_input_files():
    try:
        os.remove(os.path.join(MODEL_INPUT_FOLDER_PATH, 'virtual_machines.dat'))
        os.remove(os.path.join(MODEL_INPUT_FOLDER_PATH, 'physical_machines.dat'))
    except FileNotFoundError:
        pass