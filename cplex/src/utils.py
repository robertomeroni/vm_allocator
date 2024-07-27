import os
import re
import json
from config import MODEL_INPUT_FOLDER_PATH

def load_virtual_machines(file_path):
    if not os.path.exists(file_path):
        print(f"File {file_path} not found. Initializing an empty set of virtual machines.")
        return []
    with open(file_path, 'r') as file:
        data = file.read()
    try:
        vm_lines = data.split('virtual_machines = {')[1].split('};')[0].strip().split('\n')
    except IndexError:
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
            'group': int(parts[13]),
            'expected_profit': float(parts[14].strip('>'))
        }
        vms.append(vm)
    return vms

def load_physical_machines(file_path):
    if not os.path.exists(file_path):
        print(f"File {file_path} not found. Initializing an empty set of physical machines.")
        return []
    with open(file_path, 'r') as file:
        data = file.read()
    try:
        pm_lines = data.split('physical_machines = {')[1].split('};')[0].strip().split('\n')
    except IndexError:
        raise ValueError(f"Error in loading physical machines: Check the format of {file_path}")
    
    pms = []
    for line in pm_lines:
        line = line.strip().strip('<').strip('>')
        parts = [part.strip().strip('<').strip('>') for part in line.split(',')]
        pm = {
            'id': int(parts[0]),
            'capacity': {
                'cpu': int(parts[1]),
                'memory': int(parts[2])
            },
            'features': {
                'speed': float(parts[3]),
                'max_energy_consumption': float(parts[4])
            },
            's': {
                'time_to_turn_on': float(parts[5]),
                'time_to_turn_off': float(parts[6]),
                'state': int(parts[7].strip('>'))
            }
        }
        pms.append(pm)
    return pms

def save_vm_sets(active_vms, terminated_vms, step, output_folder_path):
    active_file_path = os.path.join(output_folder_path, f'active_vms_t{step}.json')
    terminated_file_path = os.path.join(output_folder_path, f'terminated_vms_t{step}.json')
    with open(active_file_path, 'w') as file:
        json.dump(active_vms, file, indent=4)
    with open(terminated_file_path, 'w') as file:
        json.dump(terminated_vms, file, indent=4)

def convert_vms_to_model_input_format(vms):
    formatted_vms = "virtual_machines = {\n"
    for vm in vms:
        formatted_vms += f"  <{vm['id']}, <{vm['requested']['cpu']}, {vm['requested']['memory']}>, <{vm['allocation']['current_time']}, {vm['allocation']['total_time']}, {vm['allocation']['pm']}>, <{vm['run']['current_time']}, {vm['run']['total_time']}, {vm['run']['pm']}>, <{vm['migration']['current_time']}, {vm['migration']['total_time']}, {vm['migration']['from_pm']}, {vm['migration']['to_pm']}>, {vm['group']}, {vm['expected_profit']}>,\n"
    formatted_vms = formatted_vms.rstrip(",\n") + "\n};"
    return formatted_vms

def convert_pms_to_model_input_format(pms):
    formatted_pms = "physical_machines = {\n"
    for pm in pms:
        formatted_pms += f"  <{pm['id']}, <{pm['capacity']['cpu']}, {pm['capacity']['memory']}>, <{pm['features']['speed']}, {pm['features']['max_energy_consumption']}>, <{pm['s']['time_to_turn_on']}, {pm['s']['time_to_turn_off']}, {pm['s']['state']}>>, \n"
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
        'is_removal': re.compile(r'is_removal = \[(.*?)\];', re.DOTALL),
        'cpu_load': re.compile(r'cpu_load = \[(.*?)\];', re.DOTALL),
        'memory_load': re.compile(r'memory_load = \[(.*?)\];', re.DOTALL)
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

def clean_up_model_input_files():
    try:
        os.remove(os.path.join(MODEL_INPUT_FOLDER_PATH, 'virtual_machines.dat'))
        os.remove(os.path.join(MODEL_INPUT_FOLDER_PATH, 'physical_machines.dat'))
    except FileNotFoundError:
        pass