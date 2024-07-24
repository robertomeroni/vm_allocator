import os
import re
import json

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
        parts = line.split(',')
        vm = {
            'id': int(parts[0].strip()),
            'requested_cpu': int(parts[1].strip()),
            'requested_memory': int(parts[2].strip()),
            'current_execution_time': float(parts[3].strip()),
            'total_execution_time': float(parts[4].strip()),
            'running_on_pm': int(parts[5].strip()),
            'expected_profit': float(parts[6].strip().strip('>'))
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
        parts = line.split(',')
        pm = {
            'id': int(parts[0].strip()),
            'cpu_capacity': int(parts[1].strip()),
            'memory_capacity': int(parts[2].strip()),
            'max_energy_consumption': float(parts[3].strip()),
            'time_to_turn_on': float(parts[4].strip()),
            'time_to_turn_off': float(parts[5].strip()),
            'state': int(parts[6].strip().strip('>'))
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
        formatted_vms += f"  <{vm['id']}, {vm['requested_cpu']}, {vm['requested_memory']}, {vm['current_execution_time']}, {vm['total_execution_time']}, {vm['running_on_pm']}, {vm['expected_profit']}>,\n"
    formatted_vms = formatted_vms.rstrip(",\n") + "\n};"
    return formatted_vms

def convert_pms_to_model_input_format(pms):
    formatted_pms = "physical_machines = {\n"
    for pm in pms:
        formatted_pms += f"  <{pm['id']}, {pm['cpu_capacity']}, {pm['memory_capacity']}, {pm['max_energy_consumption']}, {pm['time_to_turn_on']}, {pm['time_to_turn_off']}, {pm['state']}>,\n"
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
    new_allocation_pattern = re.compile(r'new_allocation = \[\[(.*?)\]\];', re.DOTALL)
    vm_ids_pattern = re.compile(r'Virtual Machines IDs: \[(.*?)\]')
    pm_ids_pattern = re.compile(r'Physical Machines IDs: \[(.*?)\]')
    is_on_pattern = re.compile(r'is_on = \[(.*?)\];', re.DOTALL)
    
    new_allocation_match = new_allocation_pattern.search(output)
    vm_ids_match = vm_ids_pattern.search(output)
    pm_ids_match = pm_ids_pattern.search(output)
    is_on_match = is_on_pattern.search(output)

    if new_allocation_match and vm_ids_match and pm_ids_match and is_on_match:
        new_allocation_str = new_allocation_match.group(1)
        vm_ids_str = vm_ids_match.group(1)
        pm_ids_str = pm_ids_match.group(1)
        is_on_str = is_on_match.group(1)

        new_allocation = [
            [int(num) for num in line.split()]
            for line in new_allocation_str.split(']\n             [')
        ]
        vm_ids = [int(num) for num in vm_ids_str.split()]
        pm_ids = [int(num) for num in pm_ids_str.split()]
        is_on = [int(num) for num in is_on_str.split()]

        return new_allocation, vm_ids, pm_ids, is_on
    return None, None, None, None
