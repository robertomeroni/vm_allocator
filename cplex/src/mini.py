import os, shutil, subprocess, re
from utils import convert_vms_to_model_input_format, convert_pms_to_model_input_format, parse_matrix
from config import MINI_MODEL_INPUT_FOLDER_PATH, MODEL_OUTPUT_FOLDER_PATH, MINI_MODEL_PATH

def save_mini_model_input_format(vms, pms, step, model_input_folder_path):
    if not os.path.exists(model_input_folder_path):
        os.makedirs(model_input_folder_path)
        
    vm_model_input_file_path = os.path.join(model_input_folder_path, f'virtual_machines_t{step}.dat')
    pm_model_input_file_path = os.path.join(model_input_folder_path, f'physical_machines_t{step}.dat')
    
    formatted_vms = convert_vms_to_model_input_format(vms)
    formatted_pms = convert_pms_to_model_input_format(pms)
    
    with open(vm_model_input_file_path, 'w') as file:
        file.write(formatted_vms)
    
    with open(pm_model_input_file_path, 'w') as file:
        file.write(formatted_pms)
    
    return vm_model_input_file_path, pm_model_input_file_path

def run_mini_opl_model(vm_model_input_file_path, pm_model_input_file_path, model_output_folder_path, step):
    # Copy the input files to the required path
    shutil.copy(vm_model_input_file_path, os.path.join(MINI_MODEL_INPUT_FOLDER_PATH, 'virtual_machines.dat'))
    shutil.copy(pm_model_input_file_path, os.path.join(MINI_MODEL_INPUT_FOLDER_PATH, 'physical_machines.dat'))
    
    # Run the OPL model
    result = subprocess.run(['oplrun', os.path.expanduser(MINI_MODEL_PATH)], capture_output=True, text=True)
    
    # Save the OPL model output
    output_file_path = os.path.join(model_output_folder_path, f'opl_output_t{step}.txt')
    with open(output_file_path, 'w') as file:
        file.write(result.stdout)
    
    return result.stdout

def parse_mini_opl_output(output):
    parsed_data = {}
    
    patterns = {
        'allocation': re.compile(r'allocation = \[\[(.*?)\]\];', re.DOTALL),
        'vm_ids': re.compile(r'Virtual Machines IDs: \[(.*?)\]'),
        'pm_ids': re.compile(r'Physical Machines IDs: \[(.*?)\]'),
        'cpu_load': re.compile(r'cpu_load = \[(.*?)\]'),
        'memory_load': re.compile(r'memory_load = \[(.*?)\]'),
    }
    
    for key, pattern in patterns.items():
        match = pattern.search(output)
        if match:
            if key in ['allocation']:
                parsed_data[key] = parse_matrix(match.group(1))
            else:
                parsed_data[key] = [int(num) if num.isdigit() else float(num) for num in match.group(1).strip().split()]
    
    return parsed_data

def mini_reallocate_vms(vm_ids, pm_ids, allocation, active_vms):
    for vm_index, vm_id in enumerate(vm_ids):
        for vm in active_vms:
                if vm['id'] == vm_id:
                    vm['allocation']['pm'] = -1
                    
        for pm_index in range(len(pm_ids)):
            if allocation[vm_index][pm_index] == 1:
                for vm in active_vms:
                    if vm['id'] == vm_id:
                        vm['allocation']['pm'] = pm_ids[pm_index]
                
