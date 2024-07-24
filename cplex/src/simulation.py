import os
import shutil
import subprocess
import random
from copy import deepcopy
from config import BASE_PATH, INITIAL_VMS_FILE, INITIAL_PMS_FILE, OUTPUT_FOLDER_PATH, MODEL_INPUT_FOLDER_PATH, MODEL_OUTPUT_FOLDER_PATH, MAIN_MODEL_PATH, TIME_STEP, NEW_VMS_PER_STEP, NUM_TIME_STEPS, USE_RANDOM_SEED
from logs import log_initial_physical_machines, log_allocation
from vm_generator import generate_new_vms
from utils import load_virtual_machines, load_physical_machines, save_vm_sets, save_model_input_format, parse_opl_output

if USE_RANDOM_SEED:
    random.seed(42)

# Ensure the directories exist
os.makedirs(OUTPUT_FOLDER_PATH, exist_ok=True)
os.makedirs(MODEL_INPUT_FOLDER_PATH, exist_ok=True)
os.makedirs(MODEL_OUTPUT_FOLDER_PATH, exist_ok=True)

def run_opl_model(vm_model_input_file_path, pm_model_input_file_path, step):
    # Copy the input files to the required path
    shutil.copy(vm_model_input_file_path, os.path.join(MODEL_INPUT_FOLDER_PATH, 'virtual_machines.dat'))
    shutil.copy(pm_model_input_file_path, os.path.join(MODEL_INPUT_FOLDER_PATH, 'physical_machines.dat'))
    
    # Run the OPL model
    result = subprocess.run(['oplrun', os.path.expanduser(MAIN_MODEL_PATH)], capture_output=True, text=True)
    
    # Save the OPL model output
    output_file_path = os.path.join(MODEL_OUTPUT_FOLDER_PATH, f'opl_output_t{step}.txt')
    with open(output_file_path, 'w') as file:
        file.write(result.stdout)
    
    return result.stdout

def simulate_time_steps(initial_vms, initial_pms, num_steps, new_vms_per_step):
    active_vms = initial_vms.copy()
    terminated_vms = []
    physical_machines = deepcopy(initial_pms)
    initial_physical_machines = deepcopy(initial_pms)
    
    # Set remaining time to turn off to 0 if the machine is off, and time to turn on to 0 if the machine is on
    for pm in physical_machines:
        if pm['state'] == 0:
            pm['time_to_turn_off'] = 0
        else:
            pm['time_to_turn_on'] = 0

    existing_ids = {vm['id'] for vm in initial_vms}

    # Log initial state of physical machines
    log_initial_physical_machines(physical_machines, BASE_PATH)

    for step in range(1, num_steps + 1):
        migrated_vms = []
        killed_vms = []
        turned_on_pms = []
        turned_off_pms = []

        # Generate new VMs
        generate_new_vms(active_vms, new_vms_per_step, existing_ids)

        save_vm_sets(active_vms, terminated_vms, step, OUTPUT_FOLDER_PATH)
        vm_model_input_file_path, pm_model_input_file_path = save_model_input_format(active_vms, physical_machines, step, MODEL_INPUT_FOLDER_PATH)
        opl_output = run_opl_model(vm_model_input_file_path, pm_model_input_file_path, step)

        # Parse OPL output and reallocate VMs
        new_allocation, vm_ids, pm_ids, is_on = parse_opl_output(opl_output)
        if new_allocation and vm_ids and pm_ids and is_on:
            vm_previous_pm = {vm['id']: vm['running_on_pm'] for vm in active_vms}
            migrated_vms, killed_vms = reallocate_vms(active_vms, new_allocation, vm_ids, pm_ids, vm_previous_pm)
            turned_on_pms, turned_off_pms = update_physical_machines_state(physical_machines, initial_physical_machines, is_on)

        # Log current allocation and physical machine load
        log_allocation(step, active_vms, terminated_vms, migrated_vms, killed_vms, turned_on_pms, turned_off_pms, physical_machines, BASE_PATH)

        # Execute time step
        execute_time_step(active_vms, terminated_vms, physical_machines)

        save_vm_sets(active_vms, terminated_vms, step, OUTPUT_FOLDER_PATH)
    
    clean_up_model_input_files()

def reallocate_vms(active_vms, new_allocation, vm_ids, pm_ids, vm_previous_pm):
    migrated_vms = []
    killed_vms = []
    for vm in active_vms:
        vm['running_on_pm'] = -1  # Default to not allocated
    for vm_index, vm_id in enumerate(vm_ids):
        for pm_index, is_allocated in enumerate(new_allocation[vm_index]):
            if is_allocated == 1:
                for vm in active_vms:
                    if vm['id'] == vm_id:
                        vm['running_on_pm'] = pm_ids[pm_index]
                        if vm_previous_pm[vm_id] != -1 and vm_previous_pm[vm_id] != pm_ids[pm_index]:
                            migrated_vms.append({'id': vm_id, 'from_pm': vm_previous_pm[vm_id], 'to_pm': pm_ids[pm_index]})
                        break
    for vm in active_vms:
        if vm['running_on_pm'] == -1 and vm_previous_pm[vm['id']] != -1:
            vm['current_execution_time'] = 0
            killed_vms.append(vm)
    return migrated_vms, killed_vms

def update_physical_machines_state(physical_machines, initial_physical_machines, is_on):
    turned_on_pms = []
    turned_off_pms = []
    for pm, state in zip(physical_machines, is_on):
        if pm['state'] != state or (pm['state'] == 1 and pm['time_to_turn_on'] > 0) or (pm['state'] == 0 and pm['time_to_turn_off'] > 0):
            initial_pm = next(p for p in initial_physical_machines if p['id'] == pm['id'])
            if state == 1:  # Machine is being turned on
                pm['time_to_turn_off'] = initial_pm['time_to_turn_off']
                pm['state'] = 1 
                turned_on_pms.append(pm['id'])
            else:  # Machine is being turned off
                pm['time_to_turn_on'] = initial_pm['time_to_turn_on']
                pm['state'] = 0  
                turned_off_pms.append(pm['id'])
    return turned_on_pms, turned_off_pms

def execute_time_step(active_vms, terminated_vms, physical_machines):
    # Update the turning on and turning off time for physical machines
    for pm in physical_machines:
        if pm['state'] == 1 and pm['time_to_turn_on'] > 0:
            pm['time_to_turn_on'] -= TIME_STEP
            if pm['time_to_turn_on'] < 0:
                pm['time_to_turn_on'] = 0
        if pm['state'] == 0 and pm['time_to_turn_off'] > 0:
            pm['time_to_turn_off'] -= TIME_STEP
            if pm['time_to_turn_off'] < 0:
                pm['time_to_turn_off'] = 0
    
    for vm in active_vms[:]:
        pm_id = vm['running_on_pm']
        if pm_id != -1:
            pm = next((p for p in physical_machines if p['id'] == pm_id), None)
            if pm and pm['state'] and pm['time_to_turn_on'] == 0:
                vm['current_execution_time'] += TIME_STEP
        if vm['current_execution_time'] >= vm['total_execution_time']:
            active_vms.remove(vm)
            terminated_vms.append(vm)

def clean_up_model_input_files():
    try:
        os.remove(os.path.join(MODEL_INPUT_FOLDER_PATH, 'virtual_machines.dat'))
        os.remove(os.path.join(MODEL_INPUT_FOLDER_PATH, 'physical_machines.dat'))
    except FileNotFoundError:
        pass

if __name__ == "__main__":
    initial_vms = load_virtual_machines(os.path.expanduser(INITIAL_VMS_FILE))
    initial_pms = load_physical_machines(os.path.expanduser(INITIAL_PMS_FILE))
    simulate_time_steps(initial_vms, initial_pms, NUM_TIME_STEPS, NEW_VMS_PER_STEP)
