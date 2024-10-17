import os, shutil, subprocess, re
from utils import convert_vms_to_model_input_format, convert_pms_to_model_input_format, convert_power_function_to_model_input_format, parse_matrix
from config import MINI_MODEL_INPUT_FOLDER_PATH, MINI_MODEL_PATH

try:
    profile # type: ignore
except NameError:
    def profile(func):
        return func

@profile
def save_mini_model_input_format(vms, pms, step, model_input_folder_path, power_function_dict, nb_points):
    # Ensure the directory exists
    os.makedirs(model_input_folder_path, exist_ok=True)
    
    # Construct file paths
    base_filename = f'_t{step}.dat'
    vm_model_input_file_path = os.path.join(model_input_folder_path, 'virtual_machines' + base_filename)
    pm_model_input_file_path = os.path.join(model_input_folder_path, 'physical_machines' + base_filename)
    
    # Convert data to the required format
    formatted_vms = convert_vms_to_model_input_format(vms)
    formatted_pms = convert_pms_to_model_input_format(pms)
    formatted_power_function = convert_power_function_to_model_input_format(pms, power_function_dict, nb_points)
    
    # Write formatted VMs to file
    with open(vm_model_input_file_path, 'w') as vm_file:
        vm_file.write(formatted_vms)
    
    # Write formatted PMs and power function to file
    with open(pm_model_input_file_path, 'w') as pm_file:
        pm_file.write(formatted_pms)
        pm_file.write(formatted_power_function)
    
    return vm_model_input_file_path, pm_model_input_file_path

def run_mini_opl_model(vm_model_input_file_path, pm_model_input_file_path, model_output_folder_path, step, hard_time_limit_mini=None):
    # Copy the input files to the required path
    shutil.copy(vm_model_input_file_path, os.path.join(MINI_MODEL_INPUT_FOLDER_PATH, 'virtual_machines.dat'))
    shutil.copy(pm_model_input_file_path, os.path.join(MINI_MODEL_INPUT_FOLDER_PATH, 'physical_machines.dat'))
    
    try:
        # Run the OPL model with a timeout
        result = subprocess.run(
            ['oplrun', os.path.expanduser(MINI_MODEL_PATH)],
            capture_output=True,
            text=True,
            timeout=hard_time_limit_mini
        )
        
        # Save the OPL model output
        output_file_path = os.path.join(model_output_folder_path, f'opl_output_t{step}.txt')
        with open(output_file_path, 'w') as file:
            file.write(result.stdout)
        
        return result.stdout

    except subprocess.TimeoutExpired:
        return None

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
        vm = active_vms.get(vm_id)
        if vm:
            vm['allocation']['pm'] = -1
        else:
            print(f"VM ID {vm_id} not found in active VMs.")
            raise ValueError(f"VM ID {vm_id} not found in active VMs.")
        for pm_index in range(len(pm_ids)):
            if allocation[vm_index][pm_index] == 1:
                vm['allocation']['pm'] = pm_ids[pm_index]
                
