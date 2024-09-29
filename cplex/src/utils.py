import math
import numpy as np
import pandas as pd
import os
import re
import json
import ast
from collections import defaultdict
from datetime import datetime, timedelta
from config import MODEL_INPUT_FOLDER_PATH, POWER_FUNCTION_FILE, WORKLOAD_START_TIMES_FILE
from weights import main_time_step, time_window, price, migration, pue, energy, w_load_cpu

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
        requested_cpu = vm['requested_processors']
        requested_memory = int(vm['requested_memory'])
        run_total_time = vm['run_time']
        revenue = (requested_cpu * price['cpu'] + requested_memory * price['memory']) * run_total_time
        migration_first_round_time = requested_memory / migration['time']['network_bandwidth']
        migration_down_time = migration['time']['resume_vm_on_target'] + migration_first_round_time * migration['time']['memory_dirty_rate'] / migration['time']['network_bandwidth']
        migration_total_time = migration_first_round_time + migration_down_time


        new_vm = {
            'id': vm['job_number'],
            'requested': {
                'cpu': vm['requested_processors'],
                'memory': vm['requested_memory'],
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
    
    return new_vms

def load_virtual_machines(file_path):
    if not os.path.exists(file_path):
        return []
    with open(file_path, 'r') as file:
        data = file.read()
    try:
        vm_lines = data.split('virtual_machines = {')[1].split('};')[0].strip().split('\n')
    except IndexError:
        print()
        raise ValueError(f"Error in loading virtual machines: Check the format of {file_path}")
    
    vms = []
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
        vms.append(vm)
    return vms

def load_physical_machines(file_path):
    if not os.path.exists(file_path):
        print(f"File {file_path} not found. Please provide an initial Physical Machines file.")
        return [], []

    with open(file_path, 'r') as file:
        data = file.read()

    try:
        pm_section = data.split('physical_machines = {')[1].split('};')[0].strip().split('\n')
    except IndexError:
        print()
        raise ValueError(f"Error in loading physical machines: Check the format of {file_path}")

    pms = []
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
        pms.append(pm)
    
    normalize_speed(pms)

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
    for index, row in aggregated.iterrows():
        index_step = convert_to_step(index, start_time_str, time_step)
        if index_step == step:
            return row['cpu'], row['memory']
    print(f"No real data workload found for step {step}")
    return None, None

def convert_to_step(actual_datetime, start_time_str, time_step):
    start_time = datetime.strptime(start_time_str, '%a %b %d %H:%M:%S %Z %Y')
    step = (actual_datetime - start_time).total_seconds() / time_step
    return math.ceil(step)

def load_configuration(folder_path):
    weights_data = f"""
main_time_step = {main_time_step};

time_window = {time_window};

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
    check_migration_correctness(active_vms)
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

def save_power_function(file_path, model_input_folder_path):
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

def convert_power_function_to_model_input_format(pms):
    if not os.path.exists(POWER_FUNCTION_FILE):
        print(f"File {POWER_FUNCTION_FILE} not found.")
        return

    # Read the data from the input file
    with open(POWER_FUNCTION_FILE, 'r') as f:
        content = f.read()

    ## Extract 'nb_points' and 'power_function' from the content
    lines = content.strip().splitlines()

    # Initialize variables
    nb_points_line = ''
    power_function_content = ''
    inside_power_function = False

    for line in lines:
        line = line.strip()
        if line.startswith('nb_points'):
            nb_points_line = line
        elif line.startswith('power_function'):
            inside_power_function = True
            power_function_content += line + '\n'
        elif inside_power_function:
            power_function_content += line + '\n'
            if '];' in line:
                inside_power_function = False

    # Preprocess the power_function content to make it a valid Python expression
    pf_content = power_function_content.replace('<', '(').replace('>', ')')
    pf_content = pf_content.replace('power_function = ', '')  # Remove the variable assignment
    pf_content = pf_content.rstrip(';\n')  # Remove the semicolon and any trailing newline

    # Parse the string into a Python data structure
    data = ast.literal_eval(pf_content)

    turned_on_pms_rows = [data[pm['id']] for pm in pms]

    output_content = '\n\n' + nb_points_line + '\n\n'  # Include nb_points in the output
    output_content += 'power_function = [\n'
    for row in turned_on_pms_rows:
        row_str = '  [' + ', '.join(f'<{x[0]}, {x[1]}>' for x in row) + '],\n'
        output_content += row_str
    output_content = output_content.rstrip(',\n') + '\n];\n'  # Remove the last comma and newline, close the list

    return output_content

def convert_vms_to_model_input_format(vms):
    formatted_vms = "virtual_machines = {\n"
    for vm in vms:
        formatted_vms += f"  <{vm['id']}, <{vm['requested']['cpu']}, {vm['requested']['memory']}>, <{vm['allocation']['current_time']}, {vm['allocation']['total_time']}, {vm['allocation']['pm']}>, <{vm['run']['current_time']}, {vm['run']['total_time']}, {vm['run']['pm']}>, <{vm['migration']['current_time']}, {vm['migration']['total_time']}, {vm['migration']['down_time']}, {vm['migration']['from_pm']}, {vm['migration']['to_pm']}>>,\n"
    formatted_vms = formatted_vms.rstrip(",\n") + "\n};"
    return formatted_vms

def convert_pms_to_model_input_format(pms):
    formatted_pms = "physical_machines = {\n"
    for pm in pms:
        formatted_pms += f"  <{pm['id']}, <{pm['capacity']['cpu']}, {pm['capacity']['memory']}>, <{pm['features']['speed']}>, <{pm['s']['time_to_turn_on']}, {pm['s']['time_to_turn_off']}, <{pm['s']['load']['cpu']}, {pm['s']['load']['memory']}>, {pm['s']['state']}>>, \n"
    formatted_pms = formatted_pms.rstrip(",\n") + "\n};"
    return formatted_pms

def save_model_input_format(vms, pms, step, model_input_folder_path):
    vm_model_input_file_path = os.path.join(model_input_folder_path, f'virtual_machines_t{step}.dat')
    pm_model_input_file_path = os.path.join(model_input_folder_path, f'physical_machines_t{step}.dat')
    
    formatted_vms = convert_vms_to_model_input_format(vms)
    formatted_pms = convert_pms_to_model_input_format(pms)
    formatted_power_function = convert_power_function_to_model_input_format(pms)
    
    with open(vm_model_input_file_path, 'w') as file:
        file.write(formatted_vms)
    
    with open(pm_model_input_file_path, 'w') as file:
        file.write(formatted_pms)
        file.write(formatted_power_function)
    
    return vm_model_input_file_path, pm_model_input_file_path

def flatten_is_on(is_on):
    if isinstance(is_on[0], list):
        return [state for sublist in is_on for state in sublist]
    return is_on

def parse_opl_output(output):
    parsed_data = {}
    
    patterns = {
        'is_on': re.compile(r'is_on = \[(.*?)\];', re.DOTALL),
        'new_allocation': re.compile(r'new_allocation = \[\[(.*?)\]\];', re.DOTALL),
        'vm_ids': re.compile(r'Virtual Machines IDs: \[(.*?)\]'),
        'pm_ids': re.compile(r'Physical Machines IDs: \[(.*?)\]'),
        'is_allocation': re.compile(r'is_allocation = \[(.*?)\];', re.DOTALL),
        'is_run': re.compile(r'is_run = \[(.*?)\];', re.DOTALL),
        'is_migration': re.compile(r'is_migration = \[(.*?)\];', re.DOTALL),
        'is_removal': re.compile(r'is_removal = \[(.*?)\]'),
        'cpu_load': re.compile(r' cpu_load = \[(.*?)\]'),
        'memory_load': re.compile(r' memory_load = \[(.*?)\]'),
    }
    
    for key, pattern in patterns.items():
        match = pattern.search(output)
        if match:
            if key in ['new_allocation']:
                parsed_data[key] = parse_matrix(match.group(1))
            else:
                parsed_data[key] = [int(num) if num.isdigit() else float(num) for num in match.group(1).strip().split()]
    
    return parsed_data

def parse_matrix(matrix_str):
    return [
        [int(num) if num.isdigit() else float(num) for num in row.strip().split()]
        for row in matrix_str.strip().split(']\n             [')
    ]

def parse_power_function(file_path, pm_ids):
    with open(file_path, 'r') as file:
        data = file.read()

    nb_points_match = re.search(r'nb_points\s*=\s*(\d+);', data)
    if nb_points_match:
        nb_points = int(nb_points_match.group(1))
    else:
        print()
        raise ValueError("Could not find nb_points in the file.")

    power_function_match = re.search(r'power_function\s*=\s*\[\s*(.*?)\s*\];', data, re.DOTALL)
    if power_function_match:
        power_function_str = power_function_match.group(1)
    else:
        print()
        raise ValueError("Could not find power_function in the file.")

    piecewise_linear_functions = {}
    row_pattern = re.compile(r'\[(.*?)\]')
    
    for pm_id, row_match in zip(pm_ids, row_pattern.finditer(power_function_str)):
        row_str = row_match.group(1)
        row = []
        pair_pattern = re.compile(r'<\s*([\d\.]+)\s*,\s*([\d\.]+)\s*>')
        for pair_match in pair_pattern.finditer(row_str):
            x = float(pair_match.group(1))
            y = float(pair_match.group(2))
            row.append((x, y))
        
        piecewise_linear_functions[pm_id] = row

    return nb_points, piecewise_linear_functions

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

def nested_dict():
    return defaultdict(lambda: {'cpu': 0, 'memory': 0})

def round_down(value):
    return math.floor(value * 1000000) / 1000000

def normalize_speed(pms, target_mean=1):
    speeds = [pm['features']['speed'] for pm in pms]
    current_mean = sum(speeds) / len(speeds)
    scaling_factor = target_mean / current_mean

    # Normalize the speeds by multiplying each speed by the scaling factor
    for pm in pms:
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

def calculate_load(physical_machines, active_vms, time_step):
    cpu_load = [0.0] * len(physical_machines)
    memory_load = [0.0] * len(physical_machines)

    for vm in active_vms:
        pm_id = vm['allocation']['pm'] if vm['allocation']['pm'] != -1 else (vm['migration']['to_pm'] if vm['migration']['to_pm'] != -1 else vm['run']['pm'])

        if pm_id != -1:
            if physical_machines[pm_id]['s']['state'] == 1 and physical_machines[pm_id]['s']['time_to_turn_on'] < time_step:
                cpu_load[pm_id] += vm['requested']['cpu'] / physical_machines[pm_id]['capacity']['cpu']
                memory_load[pm_id] += vm['requested']['memory'] / physical_machines[pm_id]['capacity']['memory']
        
        if vm['migration']['from_pm'] != -1:
            from_pm_id = vm['migration']['from_pm']
            
            cpu_load[from_pm_id] += vm['requested']['cpu'] / physical_machines[from_pm_id]['capacity']['cpu']
            memory_load[from_pm_id] += vm['requested']['memory'] / physical_machines[from_pm_id]['capacity']['memory']
        
        cpu_load = [round_down(cpu) for cpu in cpu_load]
        memory_load = [round_down(memory) for memory in memory_load]
        
    return cpu_load, memory_load

def calculate_future_load(physical_machines, active_vms, actual_time_step, time_window, time_step):
    # Initialize a list to store the load for each time step
    future_loads = []

    # Iterate through each future time step
    for future_time_step in range(actual_time_step + 1, actual_time_step + 1 + math.ceil(time_window / time_step)):
        actual_time_window = (future_time_step - actual_time_step) * time_step
        # Initialize load lists for this future time step
        cpu_load = [0.0] * len(physical_machines)
        memory_load = [0.0] * len(physical_machines)

        # Calculate the load for each VM and PM for the current future time step
        for vm in active_vms:
            # Determine the PM for the VM in this time step
            pm_id = vm['allocation']['pm'] if vm['allocation']['pm'] != -1 else (
                vm['migration']['to_pm'] if vm['migration']['to_pm'] != -1 else vm['run']['pm']
            )

            # Check if VM is allocated to a physical machine
            if pm_id != -1:
                # Check if the physical machine is in an active state and will be turned on before this future time step
                if physical_machines[pm_id]['s']['state'] == 1 and physical_machines[pm_id]['s']['time_to_turn_on'] < actual_time_window:
                    remaining_time = physical_machines[pm_id]['s']['time_to_turn_on'] + (vm['allocation']['total_time'] - vm['allocation']['current_time'] + vm['run']['total_time'] - vm['run']['current_time']) / physical_machines[pm_id]['features']['speed']
                    if vm['migration']['to_pm'] != -1:
                        remaining_time += vm['migration']['total_time'] - vm['migration']['current_time'] 
                    if actual_time_window < remaining_time:
                            cpu_load[pm_id] += vm['requested']['cpu'] / physical_machines[pm_id]['capacity']['cpu']
                            memory_load[pm_id] += vm['requested']['memory'] / physical_machines[pm_id]['capacity']['memory']

                # Check if the VM is migrating from a physical machine
                if vm['migration']['from_pm'] != -1:
                    from_pm_id = vm['migration']['from_pm']

                    cpu_load[from_pm_id] += vm['requested']['cpu'] / physical_machines[from_pm_id]['capacity']['cpu']
                    memory_load[from_pm_id] += vm['requested']['memory'] / physical_machines[from_pm_id]['capacity']['memory']

        # Round down the loads for the current future time step
        cpu_load = [round_down(cpu) for cpu in cpu_load]
        memory_load = [round_down(memory) for memory in memory_load]

        # Append the loads for this future time step to the list
        future_loads.append((cpu_load, memory_load))

    return future_loads

def check_unique_state(vms):
    for vm in vms:
        state_count = 0
        if vm['allocation']['pm'] != -1:
            state_count += 1
        if vm['run']['pm'] != -1:
            state_count += 1
        if vm['migration']['from_pm'] != -1 or vm['migration']['to_pm'] != -1:
            state_count += 1
            if vm['migration']['from_pm'] == -1 or vm['migration']['to_pm'] == -1:
                print()
                raise ValueError(f"VM {vm['id']} has an incorrect migration state: {vm['migration']}.")
        if state_count > 1:
            print()
            raise ValueError(f"VM {vm['id']} has multiple states: {vm['allocation']}, {vm['run']}, and {vm['migration']}.")

def check_overload(vms, pms, time_step):
    # update the load of the PMs
    cpu_load, memory_load = calculate_load(pms, vms, time_step)

    for pm in pms:
        if cpu_load[pm['id']] > 1 or memory_load[pm['id']] > 1:
            effective_cpu_load = 0
            effective_memory_load = 0
            for vm in vms:
                if vm['allocation']['pm'] == pm['id'] or vm['run']['pm'] == pm['id'] or vm['migration']['from_pm'] == pm['id'] or vm['migration']['to_pm'] == pm['id']:
                    effective_cpu_load += vm['requested']['cpu'] 
                    effective_memory_load += vm['requested']['memory']
            if effective_cpu_load > pm['capacity']['cpu'] or effective_memory_load > pm['capacity']['memory']:
                print()
                raise ValueError(f"PM {pm['id']} is overloaded: cpu_load {cpu_load[pm['id']]}, memory_load {memory_load[pm['id']]}, effective_cpu_load {effective_cpu_load}, effective_memory_load {effective_memory_load}.")

def check_migration_overload(cpu_migration_overhead, migration_overhead_source, migration_overhead_target, multiple_migrations):
    max_overhead = 0.0

    if migration_overhead_source and not migration_overhead_target and not multiple_migrations:
        max_overhead = migration['energy']['cpu_overhead']['source']
    if not migration_overhead_source and migration_overhead_target and not multiple_migrations:
        max_overhead = migration['energy']['cpu_overhead']['target']
    if migration_overhead_source and not migration_overhead_target and multiple_migrations:
        max_overhead = migration['energy']['cpu_overhead']['source'] + migration['energy']['concurrent']
    if not migration_overhead_source and migration_overhead_target and multiple_migrations:
        max_overhead = migration['energy']['cpu_overhead']['target'] + migration['energy']['concurrent']
    if migration_overhead_source and migration_overhead_target:
        if not multiple_migrations:
            raise ValueError("PM is source and target, but Multiple Migration is set to False.")
        max_overhead = migration['energy']['cpu_overhead']['source'] + migration['energy']['cpu_overhead']['target'] + migration['energy']['concurrent']

    if cpu_migration_overhead > max_overhead:
        raise ValueError(f"CPU migration overhead {cpu_migration_overhead} exceeds the maximum allowed overhead {max_overhead}.")

def check_migration_correctness(active_vms):
    for vm in active_vms:
        if vm['migration']['from_pm'] != -1 and vm['migration']['to_pm'] == -1 or vm['migration']['from_pm'] == -1 and vm['migration']['to_pm'] != -1:
            print()
            raise ValueError(f"VM {vm['id']} has an incorrect migration state: {vm['migration']}.")
        elif vm['migration']['from_pm'] == vm['migration']['to_pm'] and vm['migration']['from_pm'] != -1:
            print()
            raise ValueError(f"VM {vm['id']} is migrating to the same PM {vm['migration']['to_pm']}.")

def check_zero_load(vms, pms):
    for pm in pms:
        if pm['s']['load']['cpu'] == 0 and pm['s']['load']['memory'] == 0:
            if pm['s']['state'] == 1 and pm['s']['time_to_turn_on'] == 0:
                for vm in vms:
                    if vm['allocation']['pm'] == pm['id'] or vm['run']['pm'] == pm['id'] or vm['migration']['from_pm'] == pm['id'] or vm['migration']['to_pm'] == pm['id']:
                        print()
                        raise ValueError(f"VM {vm['id']} is allocated to PM {pm['id']} with zero load: {pm['s']['load']}.")

def clean_up_model_input_files():
    try:
        os.remove(os.path.join(MODEL_INPUT_FOLDER_PATH, 'virtual_machines.dat'))
        os.remove(os.path.join(MODEL_INPUT_FOLDER_PATH, 'physical_machines.dat'))
    except FileNotFoundError:
        pass