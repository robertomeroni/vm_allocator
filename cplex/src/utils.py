import math
import numpy as np
import os
import re
import json
import datetime
from config import MODEL_INPUT_FOLDER_PATH, LOGS_FOLDER_PATH
from weights import main_time_step, time_window, price, migration, network_bandwidth, pue, energy, w_load_cpu

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
                'from_pm': int(parts[11]),
                'to_pm': int(parts[12])
            },
            'group': int(parts[13].strip('>'))
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
        latency_section = data.split('latency = [')[1].split('];')[0].strip().split('\n')
    except IndexError:
        print()
        raise ValueError(f"Error in loading physical machines or latency matrix: Check the format of {file_path}")

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

    latency_matrix = []
    for line in latency_section:
        row = [float(value.strip()) for value in line.strip().replace('[', '').replace(']', '').split(',') if value.strip()]
        latency_matrix.append(row)
    
    normalize_speed(pms)

    return pms, latency_matrix

def load_configuration(folder_path):
    weights_data = f"""
main_time_step = {main_time_step};

time_window = {time_window};

price = <{price['cpu']}, {price['memory']}>;

energy = <{energy['cost']}, {energy['limit']}>;

PUE = {pue};

network_bandwidth = {network_bandwidth};

migration_energy_parameters = <{migration['energy']['offset']}, {migration['energy']['coefficient']}>;

migration_penalty = {migration['penalty']};

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

def save_latency_matrix(latency_matrix, model_input_folder_path):
    latency_file_path = os.path.join(model_input_folder_path, 'latency.dat')
    with open(latency_file_path, 'w') as file:
        file.write('latency = [\n')
        for row in latency_matrix:
            file.write('  [' + ', '.join(map(str, row)) + '],\n')
        file.write('];\n')

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

    power_function_file_path = os.path.join(model_input_folder_path, 'power_consumption.dat')
    with open(power_function_file_path, 'w') as file:
        file.write('nb_points = ' + nb_points_section + '\n\n')
        file.write('power_function = [\n')
        file.write(power_function_section)
        file.write('\n')


def convert_vms_to_model_input_format(vms):
    formatted_vms = "virtual_machines = {\n"
    for vm in vms:
        formatted_vms += f"  <{vm['id']}, <{vm['requested']['cpu']}, {vm['requested']['memory']}>, <{vm['allocation']['current_time']}, {vm['allocation']['total_time']}, {vm['allocation']['pm']}>, <{vm['run']['current_time']}, {vm['run']['total_time']}, {vm['run']['pm']}>, <{vm['migration']['current_time']}, {vm['migration']['total_time']}, {vm['migration']['from_pm']}, {vm['migration']['to_pm']}>, {vm['group']}>,\n"
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
    
    with open(vm_model_input_file_path, 'w') as file:
        file.write(formatted_vms)
    
    with open(pm_model_input_file_path, 'w') as file:
        file.write(formatted_pms)
    
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
        'cpu_load': re.compile(r'cpu_load = \[(.*?)\]'),
        'memory_load': re.compile(r'memory_load = \[(.*?)\]'),
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

def evaluate_piecewise_linear_function(piecewise_function, x_value):
    """
    Evaluate a piecewise linear function at a given x_value.
    """
    for i in range(len(piecewise_function) - 1):
        x0, y0 = piecewise_function[i]
        x1, y1 = piecewise_function[i + 1]
        
        if x0 <= x_value <= x1:
            return y0 + (y1 - y0) * (x_value - x0) / (x1 - x0)
        
    print()
    raise ValueError(f"x_value {x_value} is out of bounds for the piecewise linear function.")

def round_down(value):
    return math.floor(value * 10000) / 10000

def normalize_speed(pms, target_mean=1):
    speeds = [pm['features']['speed'] for pm in pms]
    current_mean = sum(speeds) / len(speeds)
    scaling_factor = target_mean / current_mean

    # Normalize the speeds by multiplying each speed by the scaling factor
    for pm in pms:
        pm['features']['speed'] *= scaling_factor

    return pms


def check_migration_correctness(active_vms):
    for vm in active_vms:
        if vm['migration']['from_pm'] != -1 and vm['migration']['to_pm'] == -1 or vm['migration']['from_pm'] == -1 and vm['migration']['to_pm'] != -1:
            print()
            raise ValueError(f"VM {vm['id']} has an incorrect migration state: {vm['migration']}.")
        elif vm['migration']['from_pm'] == vm['migration']['to_pm'] and vm['migration']['from_pm'] != -1:
            print()
            raise ValueError(f"VM {vm['id']} is migrating to the same PM {vm['migration']['to_pm']}.")
        
def clean_up_model_input_files():
    try:
        os.remove(os.path.join(MODEL_INPUT_FOLDER_PATH, 'virtual_machines.dat'))
        os.remove(os.path.join(MODEL_INPUT_FOLDER_PATH, 'physical_machines.dat'))
    except FileNotFoundError:
        pass