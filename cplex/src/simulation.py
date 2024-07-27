import os
import shutil
import subprocess
import random
from copy import deepcopy
from config import BASE_PATH, INITIAL_VMS_FILE, INITIAL_PMS_FILE, OUTPUT_FOLDER_PATH, MODEL_INPUT_FOLDER_PATH, MODEL_OUTPUT_FOLDER_PATH, MAIN_MODEL_PATH, TIME_STEP, NEW_VMS_PER_STEP, NUM_TIME_STEPS, USE_RANDOM_SEED
from logs import log_initial_physical_machines, log_allocation
from vm_generator import generate_new_vms
from utils import load_virtual_machines, load_physical_machines, save_vm_sets, save_model_input_format, parse_opl_output, clean_up_model_input_files

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

def reallocate_vms(active_vms, new_allocation, vm_ids, pm_ids, is_allocation, is_migration, is_removal, vm_previous_pm):
    old_vms = deepcopy(active_vms)
    migrated_vms = []
    removed_vms = []
    
    for vm in active_vms:
        # Default to not allocated, not migrating, and not running
        vm['allocation']['pm'] = -1
        vm['migration']['to_pm'] = -1
        vm['run']['pm'] = -1

    for vm_index, vm_id in enumerate(vm_ids):
        for pm_index in range(len(pm_ids)):
            if new_allocation[vm_index][pm_index] == 1:
                for vm in active_vms:
                    if vm['id'] == vm_id:
                        if is_allocation[vm_index] == 1:
                            vm['allocation']['pm'] = pm_ids[pm_index]
                        elif is_migration[vm_index] == 1:
                            if vm['migration']['current_time'] == 0:
                                vm['migration']['from_pm'] = vm_previous_pm[vm_id]
                                vm['migration']['to_pm'] = pm_ids[pm_index]
                            else:
                                vm['migration']['to_pm'] = pm_ids[pm_index]
                        else:
                            vm['run']['pm'] = pm_ids[pm_index]
                        if vm_previous_pm[vm_id] != -1 and vm_previous_pm[vm_id] != pm_ids[pm_index]:
                            migrated_vms.append({'id': vm_id, 'from_pm': vm_previous_pm[vm_id], 'to_pm': pm_ids[pm_index]})
                        break
        if is_removal[vm_index] == 1:
            for vm in active_vms:
                if vm['id'] == vm_id:
                    removed_vms.append(vm)
                    break    

    for vm in active_vms:
        if vm['migration']['from_pm'] == -1 or vm['migration']['to_pm'] == -1:
            vm['migration']['current_time'] = 0.0
        if vm['allocation']['pm'] == -1 and vm['run']['pm'] == -1 and vm['migration']['from_pm'] == -1 and vm['migration']['to_pm'] == -1:
            vm['allocation']['current_time'] = 0.0
            vm['run']['current_time'] = 0.0
            vm['migration']['current_time'] = 0.0

    return migrated_vms, removed_vms


def flatten_is_on(is_on):
    if isinstance(is_on[0], list):
        return [state for sublist in is_on for state in sublist]
    return is_on

def update_physical_machines_state(physical_machines, initial_physical_machines, is_on):
    turned_on_pms = []
    turned_off_pms = []

    # Flatten the is_on list
    is_on_flat = flatten_is_on(is_on)
    
    for i, pm in enumerate(physical_machines):
        state = is_on_flat[i]  # Get the state for the current physical machine

        # Check if the state or the transition times need to be updated
        if pm['s']['state'] != state or (pm['s']['state'] == 1 and pm['s']['time_to_turn_on'] > 0) or (pm['s']['state'] == 0 and pm['s']['time_to_turn_off'] > 0):
            initial_pm = next(p for p in initial_physical_machines if p['id'] == pm['id'])
            if state == 1:  # Machine is being turned on
                pm['s']['time_to_turn_off'] = initial_pm['s']['time_to_turn_off']
                pm['s']['state'] = 1
                turned_on_pms.append(pm['id'])
            else:  # Machine is being turned off
                pm['s']['time_to_turn_on'] = initial_pm['s']['time_to_turn_on']
                pm['s']['state'] = 0
                turned_off_pms.append(pm['id'])

    return turned_on_pms, turned_off_pms

def execute_time_step(active_vms, terminated_vms, physical_machines):
    # Update the turning on and turning off time for physical machines
    for pm in physical_machines:
        if pm['s']['state'] == 1 and pm['s']['time_to_turn_on'] > 0:
            pm['s']['time_to_turn_on'] = round(pm['s']['time_to_turn_on'] - TIME_STEP, 10)
            if pm['s']['time_to_turn_on'] < 0:
                pm['s']['time_to_turn_on'] = 0.0
        if pm['s']['state'] == 0 and pm['s']['time_to_turn_off'] > 0:
            pm['s']['time_to_turn_off'] = round(pm['s']['time_to_turn_off'] - TIME_STEP, 10)
            if pm['s']['time_to_turn_off'] < 0:
                pm['s']['time_to_turn_off'] = 0.0

    for vm in active_vms[:]:
        pm_id = vm['allocation']['pm'] if vm['allocation']['pm'] != -1 else (vm['migration']['to_pm'] if vm['migration']['to_pm'] != -1 else vm['run']['pm'])

        if pm_id != -1:
            pm = next((p for p in physical_machines if p['id'] == pm_id), None)
            if pm and pm['s']['state'] and pm['s']['time_to_turn_on'] == 0:
                extra_time = 0.0
                if vm['allocation']['pm'] != -1:
                    remaining_time = vm['allocation']['total_time'] - vm['allocation']['current_time']
                    if TIME_STEP > remaining_time:
                        extra_time = round(TIME_STEP - remaining_time, 10)
                    vm['allocation']['current_time'] += TIME_STEP
                    if vm['allocation']['current_time'] >= vm['allocation']['total_time']:
                        vm['allocation']['current_time'] = vm['allocation']['total_time']
                        vm['allocation']['pm'] = -1
                        vm['run']['pm'] = pm_id
                        vm['run']['current_time'] += extra_time
                elif vm['migration']['from_pm'] != -1 and vm['migration']['to_pm'] != -1:
                    remaining_time = vm['migration']['total_time'] - vm['migration']['current_time']
                    if TIME_STEP > remaining_time:
                        extra_time = round(TIME_STEP - remaining_time, 10)
                    vm['migration']['current_time'] += TIME_STEP
                    if vm['migration']['current_time'] >= vm['migration']['total_time']:
                        vm['migration']['current_time'] = 0.0
                        vm['migration']['from_pm'] = -1
                        vm['migration']['to_pm'] = -1
                        if vm['allocation']['current_time'] > 0 and vm['allocation']['current_time'] < vm['allocation']['total_time']:
                            vm['allocation']['pm'] = pm_id
                            vm['allocation']['current_time'] = min(vm['allocation']['current_time'] + extra_time, vm['allocation']['total_time'])
                        elif vm['run']['current_time'] > 0:
                            vm['run']['pm'] = pm_id
                            vm['run']['current_time'] += extra_time
                elif vm['run']['pm'] != -1:
                    vm['run']['current_time'] += TIME_STEP
            if vm['run']['current_time'] >= vm['run']['total_time']:
                active_vms.remove(vm)
                terminated_vms.append(vm)
        
def simulate_time_steps(initial_vms, initial_pms, num_steps, new_vms_per_step):
    active_vms = initial_vms.copy()
    terminated_vms = []
    physical_machines = deepcopy(initial_pms)
    initial_physical_machines = deepcopy(initial_pms)
    
    # Set remaining time to turn off to 0 if the machine is off, and time to turn on to 0 if the machine is on
    for pm in physical_machines:
        if pm['s']['state'] == 0:
            pm['s']['time_to_turn_off'] = 0.0
        else:
            pm['s']['time_to_turn_on'] = 0.0

    existing_ids = {vm['id'] for vm in initial_vms}

    # Log initial state of physical machines
    log_initial_physical_machines(physical_machines, BASE_PATH)

    for step in range(1, num_steps + 1):
        migrated_vms = []
        removed_vms = []
        turned_on_pms = []
        turned_off_pms = []

        # Generate new VMs
        generate_new_vms(active_vms, new_vms_per_step, existing_ids)

        save_vm_sets(active_vms, terminated_vms, step, OUTPUT_FOLDER_PATH)
        vm_model_input_file_path, pm_model_input_file_path = save_model_input_format(active_vms, physical_machines, step, MODEL_INPUT_FOLDER_PATH)
        opl_output = run_opl_model(vm_model_input_file_path, pm_model_input_file_path, step)

        # Parse OPL output and reallocate VMs
        parsed_data = parse_opl_output(opl_output)
        new_allocation = parsed_data['new_allocation']
        vm_ids = parsed_data['vm_ids']
        pm_ids = parsed_data['pm_ids']
        is_allocation = parsed_data['is_allocation']
        is_migration = parsed_data['is_migration']
        is_removal = parsed_data['is_removal']
        is_on = parsed_data['is_on']
        cpu_load = parsed_data['cpu_load']
        memory_load = parsed_data['memory_load']
        
        if new_allocation and vm_ids and pm_ids and is_on:
            vm_previous_pm = {
                vm['id']: vm['run']['pm'] if vm['run']['pm'] != -1 else (
                    vm['migration']['to_pm'] if vm['migration']['to_pm'] != -1 else vm['allocation']['pm']
                )
                for vm in active_vms
            }
            migrated_vms, removed_vms = reallocate_vms(active_vms, new_allocation, vm_ids, pm_ids, is_allocation, is_migration, is_removal, vm_previous_pm)
            turned_on_pms, turned_off_pms = update_physical_machines_state(physical_machines, initial_physical_machines, is_on)

        # Log current allocation and physical machine load
        log_allocation(step, active_vms, terminated_vms, migrated_vms, removed_vms, turned_on_pms, turned_off_pms, physical_machines, BASE_PATH, cpu_load, memory_load)

        # Execute time step
        execute_time_step(active_vms, terminated_vms, physical_machines)

        save_vm_sets(active_vms, terminated_vms, step, OUTPUT_FOLDER_PATH)
    

if __name__ == "__main__":
    initial_vms = load_virtual_machines(os.path.expanduser(INITIAL_VMS_FILE))
    initial_pms = load_physical_machines(os.path.expanduser(INITIAL_PMS_FILE))
    simulate_time_steps(initial_vms, initial_pms, NUM_TIME_STEPS, NEW_VMS_PER_STEP)
    clean_up_model_input_files()
