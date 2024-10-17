import os
import shutil
import subprocess
from copy import deepcopy
from config import MODEL_INPUT_FOLDER_PATH, MODEL_OUTPUT_FOLDER_PATH, MAIN_MODEL_PATH, MIGRATION_SCHEDULE_FOLDER_PATH
from utils import calculate_load
from mini import save_mini_model_input_format, run_mini_opl_model, parse_mini_opl_output, mini_reallocate_vms


def run_opl_model(vm_model_input_file_path, pm_model_input_file_path, step, hard_time_limit_main):
    # Copy the input files to the required path
    shutil.copy(vm_model_input_file_path, os.path.join(MODEL_INPUT_FOLDER_PATH, 'virtual_machines.dat'))
    shutil.copy(pm_model_input_file_path, os.path.join(MODEL_INPUT_FOLDER_PATH, 'physical_machines.dat'))
    
    try:
        # Run the OPL model with a timeout
        result = subprocess.run(
            ['oplrun', os.path.expanduser(MAIN_MODEL_PATH)],
            capture_output=True,
            text=True,
            timeout=hard_time_limit_main
        )
        
        # Save the OPL model output
        output_file_path = os.path.join(MODEL_OUTPUT_FOLDER_PATH, f'opl_output_t{step}.txt')
        with open(output_file_path, 'w') as file:
            file.write(result.stdout)
        
        return result.stdout
    
    except subprocess.TimeoutExpired:
        return None

def reallocate_vms(vms, new_allocation, vm_ids, pm_ids, is_allocation, is_migration, is_removal):
    migrated_vms = []
    removed_vms = []

    # Create a mapping of VM IDs to their previous PM
    vm_migration_from_pm = {}

    for vm_index, vm_id in enumerate(vm_ids):
        if is_migration[vm_index] == 1:
            vm = vms[vm_id]

            if vm['run']['pm'] != -1:
                vm_migration_from_pm[vm_id] = vm['run']['pm']
                migrated_vms.append({'id': vm_id, 'from_pm': vm_migration_from_pm[vm_id], 'to_pm': -1})
            elif vm['migration']['from_pm'] != -1:
                vm_migration_from_pm[vm_id] = vm['migration']['from_pm']

    # Process the new allocations
    for vm_index, vm_id in enumerate(vm_ids):
        vm = vms[vm_id]  # Access the VM directly using its ID
        
        # Reset VMs' allocation, migration, and run PMs
        vm['allocation']['pm'] = -1
        vm['migration']['from_pm'] = -1
        vm['migration']['to_pm'] = -1
        vm['run']['pm'] = -1
        
        for pm_index, pm_id in enumerate(pm_ids):
            if new_allocation[vm_index][pm_index] == 1:
                if is_allocation[vm_index] == 1:
                    vm['allocation']['pm'] = pm_id
                elif is_migration[vm_index] == 1:
                    vm['migration']['from_pm'] = vm_migration_from_pm[vm_id]
                    vm['migration']['to_pm'] = pm_id
                    for migration in migrated_vms:
                        if migration['id'] == vm_id:
                            migration['to_pm'] = pm_id
                else:
                    vm['run']['pm'] = pm_id
                break  # Allocation found for this VM, move to the next VM

        if is_removal[vm_index] == 1:
            # Remove VM from vms and add it to removed_vms
            removed_vm = vms[vm_id]
            removed_vms.append(removed_vm)

    # Reset current times for VMs not allocated or migrating
    for vm in vms.values():
        if vm['migration']['from_pm'] == -1 or vm['migration']['to_pm'] == -1:
            vm['migration']['current_time'] = 0.0
        if (vm['allocation']['pm'] == -1 and
            vm['run']['pm'] == -1 and
            vm['migration']['from_pm'] == -1 and
            vm['migration']['to_pm'] == -1):
            vm['allocation']['current_time'] = 0.0
            vm['run']['current_time'] = 0.0
            vm['migration']['current_time'] = 0.0

    return removed_vms

def deallocate_vms(active_vms):
    for vm in active_vms.values():
        if vm['allocation']['pm'] != -1 and vm['allocation']['current_time'] == 0:
            vm['allocation']['pm'] = -1
            
def update_physical_machines_state(physical_machines, initial_physical_machines, is_on):
    turned_on_pms = []
    turned_off_pms = []

    for pm in physical_machines.values():
        state = is_on.get(pm['id'], pm['s']['state'])
        # Check if the state or the transition times need to be updated
        if pm['s']['state'] != state:
            initial_pm = initial_physical_machines.get(pm['id'])
            if state == 1:  # Machine is being turned on
                pm['s']['time_to_turn_off'] = initial_pm['s']['time_to_turn_off']
                pm['s']['state'] = 1
                turned_on_pms.append(pm['id'])
            else:  # Machine is being turned off
                pm['s']['time_to_turn_on'] = initial_pm['s']['time_to_turn_on']
                pm['s']['state'] = 0
                turned_off_pms.append(pm['id'])
        elif pm['s']['state'] == 1 and pm['s']['time_to_turn_on'] > 0:
            turned_on_pms.append(pm['id'])
        elif pm['s']['state'] == 0 and pm['s']['time_to_turn_off'] > 0:
            turned_off_pms.append(pm['id'])
    return turned_on_pms, turned_off_pms

def update_physical_machines_load(physical_machines, cpu_load, memory_load):
    for pm in physical_machines.values():
        pm['s']['load']['cpu'] = cpu_load[pm['id']]
        pm['s']['load']['memory'] = memory_load[pm['id']]

def is_fully_on_next_step(pm, time_step):
    return pm['s']['state'] == 1 and pm['s']['time_to_turn_on'] < time_step

def get_non_allocated_vms(active_vms):
    return {vm['id']: vm for vm in active_vms.values() if vm['allocation']['pm'] == -1 and vm['run']['pm'] == -1 and vm['migration']['from_pm'] == -1 and vm['migration']['to_pm'] == -1}

def get_non_allocated_workload(active_vms):
    non_allocated_vms = {}
    total_non_allocated_cpu = 0
    total_non_allocated_memory = 0

    for vm in active_vms.values():
        if (vm['allocation']['pm'] == -1 and 
            vm['run']['pm'] == -1 and 
            vm['migration']['from_pm'] == -1 and 
            vm['migration']['to_pm'] == -1):
            non_allocated_vms[vm['id']] = vm
            total_non_allocated_cpu += vm['requested']['cpu']
            total_non_allocated_memory += vm['requested']['memory']

    return non_allocated_vms, total_non_allocated_cpu, total_non_allocated_memory

def schedule_migration(physical_machines, active_vms, pm, step, vms_to_allocate, scheduled_vms, time_step, power_function_dict, nb_points):
    migrating_vms = [vm for vm in active_vms.values() if vm['migration']['from_pm'] == pm['id']]
    pm_dict = {pm['id']: pm}
    physical_machines_schedule = deepcopy(pm_dict)
    
    cpu_load, memory_load = calculate_load(pm_dict, active_vms, time_step)
    update_physical_machines_load(pm_dict, cpu_load, memory_load)

    for vm in migrating_vms:
        migrating_to_pm = physical_machines[vm['migration']['to_pm']]
        if vms_to_allocate and migrating_to_pm['s']['state'] == 1 and migrating_to_pm['s']['time_to_turn_on'] < time_step and vm['migration']['total_time'] - vm['migration']['current_time'] < time_step:
            filename = f"{step}_pm{pm['id']}_vm{vm['id']}"
            
            cpu_overload = vm['requested']['cpu'] / physical_machines[pm['id']]['capacity']['cpu']
            memory_overload = vm['requested']['memory'] / physical_machines[pm['id']]['capacity']['memory']

            physical_machines_schedule[pm['id']]['s']['load']['cpu'] -= cpu_overload
            physical_machines_schedule[pm['id']]['s']['load']['memory'] -= memory_overload

            schedule_migration_folder_path = os.path.join(MIGRATION_SCHEDULE_FOLDER_PATH, f"schedule/step_{step}/pm_{pm['id']}")
            os.makedirs(schedule_migration_folder_path, exist_ok=True)

            # Convert into model input format
            mini_vm_model_input_file_path, mini_pm_model_input_file_path = save_mini_model_input_format(vms_to_allocate, physical_machines_schedule, filename, schedule_migration_folder_path, power_function_dict, nb_points)
            
            # Run mini OPL model
            opl_output = run_mini_opl_model(mini_vm_model_input_file_path, mini_pm_model_input_file_path, schedule_migration_folder_path, filename)
            
            parsed_data = parse_mini_opl_output(opl_output)
            partial_allocation = parsed_data['allocation']
            vm_ids = parsed_data['vm_ids']
            
            # Assign a VM to a completed VM migration
            for vm_index, vm_id in enumerate(vm_ids):
                if partial_allocation[vm_index][0] == 1:
                    scheduled_vms[vm['id']].append(active_vms[vm_id])
                    del vms_to_allocate[vm_id]

                    # Update the scheduled load of the physical machine
                    cpu_scheduled_load = active_vms[vm_id]['requested']['cpu'] / physical_machines[pm['id']]['capacity']['cpu']
                    memory_scheduled_load = active_vms[vm_id]['requested']['memory'] / physical_machines[pm['id']]['capacity']['memory']
                    physical_machines_schedule[pm['id']]['s']['load']['cpu'] += cpu_scheduled_load
                    physical_machines_schedule[pm['id']]['s']['load']['memory'] += memory_scheduled_load
                    
                    print(f"VM {vm_ids[vm_index]} scheduled on PM {pm['id']} after VM {vm['id']} migration.")
                    
def solve_overload(pm, physical_machines, active_vms, scheduled_vms, step, time_step, power_function_dict, nb_points):
    vms_to_allocate = {}
    pm_dict = {pm['id']: pm}

    for vm in active_vms.values():
        if vm['allocation']['pm'] == pm['id'] and vm['allocation']['current_time'] == 0:
            vm['allocation']['pm'] = -1
            vms_to_allocate[vm['id']] = vm
    
    cpu_load, memory_load = calculate_load(pm_dict, active_vms, time_step)
    update_physical_machines_load(pm_dict, cpu_load, memory_load)

    physical_machines_schedule = deepcopy({pm['id']: pm})
    
    # Convert into model input format
    mini_vm_model_input_file_path, mini_pm_model_input_file_path = save_mini_model_input_format(vms_to_allocate, physical_machines_schedule, step, MIGRATION_SCHEDULE_FOLDER_PATH, power_function_dict, nb_points)
    
    # Run mini OPL model
    opl_output = run_mini_opl_model(mini_vm_model_input_file_path, mini_pm_model_input_file_path, MIGRATION_SCHEDULE_FOLDER_PATH, step)
    
    parsed_data = parse_mini_opl_output(opl_output)
    partial_allocation = parsed_data['allocation']
    vm_ids = parsed_data['vm_ids']
    pm_ids = parsed_data['pm_ids']
    
    # Reallocate VMs
    mini_reallocate_vms(vm_ids, pm_ids, partial_allocation, active_vms)

    for vm_id in list(vms_to_allocate.keys()):  # Iterate over a copy of the keys
        vm = vms_to_allocate[vm_id]
        if vm['allocation']['pm'] != -1:
            del vms_to_allocate[vm['id']]
            pm['s']['load']['cpu'] += vm['requested']['cpu'] / pm['capacity']['cpu']
            pm['s']['load']['memory'] += vm['requested']['memory'] / pm['capacity']['memory']
    
    if vms_to_allocate:
        schedule_migration(physical_machines, active_vms, pm, step, vms_to_allocate, scheduled_vms, time_step, power_function_dict, nb_points)

def detect_overload(physical_machines, active_vms, scheduled_vms, step, time_step, power_function_dict, nb_points):
    cpu_load, memory_load = calculate_load(physical_machines, active_vms, time_step)
    for pm in physical_machines.values():
        pm_dict = {pm['id']: pm}
        if cpu_load[pm['id']] > 1 or memory_load[pm['id']] > 1:
            solve_overload(pm, physical_machines, active_vms, scheduled_vms, step, time_step, power_function_dict, nb_points)
        cpu_load_pm, memory_load_pm = calculate_load(pm_dict, active_vms, time_step)

        if cpu_load_pm[pm['id']] > 1 or memory_load_pm[pm['id']] > 1:
            print()
            print(f"Error on PM {pm['id']}:")
            print (f"CPU load: {cpu_load[pm['id']]}")
            print (f"Memory load: {memory_load[pm['id']]}")
            print()
            for vm in active_vms.values():
                if vm['allocation']['pm'] == pm['id']:
                    print(f"VM {vm['id']} allocated on PM {pm['id']}.")
            raise ValueError(f"Cannot proceed: Overload detected on PM {pm['id']}.")
        
    return cpu_load, memory_load