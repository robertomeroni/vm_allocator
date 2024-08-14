import os
import shutil
import subprocess
from copy import deepcopy
from config import TIME_STEP, MODEL_INPUT_FOLDER_PATH, MODEL_OUTPUT_FOLDER_PATH, MAIN_MODEL_PATH, OVERLOAD_FOLDER_PATH
from utils import flatten_is_on
from mini import save_mini_model_input_format, run_mini_opl_model, parse_mini_opl_output, mini_reallocate_vms


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
        vm['migration']['from_pm'] = -1
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
                            if old_vms[vm_index]['run']['pm'] != -1:
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

    return removed_vms

def deallocate_vms(active_vms):
    for vm in active_vms:
        if vm['allocation']['pm'] != -1 and vm['allocation']['current_time'] == 0:
            vm['allocation']['pm'] = -1
            
def update_physical_machines_state(physical_machines, initial_physical_machines, is_on):
    turned_on_pms = []
    turned_off_pms = []

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

def update_physical_machines_load(physical_machines, cpu_load, memory_load):
    for pm in physical_machines:
        pm['s']['load']['cpu'] = cpu_load[pm['id']]
        pm['s']['load']['memory'] = memory_load[pm['id']]

def fill_other_pms(physical_machines, pm):
    for p in physical_machines:
        if p != pm:
            p['s']['load']['cpu'] = 1
            p['s']['load']['memory'] = 1

def calculate_load(physical_machines, active_vms):
    cpu_load = [0.0] * len(physical_machines)
    memory_load = [0.0] * len(physical_machines)

    for vm in active_vms:
        pm_id = vm['allocation']['pm'] if vm['allocation']['pm'] != -1 else (vm['migration']['to_pm'] if vm['migration']['to_pm'] != -1 else vm['run']['pm'])

        if pm_id != -1:
            if physical_machines[pm_id]['s']['state'] == 1 and physical_machines[pm_id]['s']['time_to_turn_on'] < TIME_STEP:
                cpu_load[pm_id] += vm['requested']['cpu'] / physical_machines[pm_id]['capacity']['cpu']
                memory_load[pm_id] += vm['requested']['memory'] / physical_machines[pm_id]['capacity']['memory']
        
        if vm['migration']['from_pm'] != -1:
            from_pm_id = vm['migration']['from_pm']
            
            cpu_load[from_pm_id] += vm['requested']['cpu'] / physical_machines[from_pm_id]['capacity']['cpu']
            memory_load[from_pm_id] += vm['requested']['memory'] / physical_machines[from_pm_id]['capacity']['memory']
        
        # Round to 2 decimal places
        cpu_load = [round(cpu, 2) for cpu in cpu_load]
        memory_load = [round(memory, 2) for memory in memory_load]
        
    return cpu_load, memory_load

def schedule_overload(physical_machines, active_vms, pm, step, vms_to_allocate, scheduled_vms):
    migrating_vms = [vm for vm in active_vms if vm['migration']['from_pm'] == pm['id']]

    physical_machines_overload = deepcopy(physical_machines)
    fill_other_pms(physical_machines_overload, pm)

    cpu_load, memory_load = calculate_load(physical_machines, active_vms)
    update_physical_machines_load(physical_machines, cpu_load, memory_load)

    for vm in migrating_vms:
        migrating_to_pm = vm['migration']['to_pm']

        if physical_machines[migrating_to_pm]['s']['state'] == 1 and physical_machines[migrating_to_pm]['s']['time_to_turn_on'] < TIME_STEP and vm['migration']['total_time'] - vm['migration']['current_time'] < TIME_STEP:
            filename = f"{step}_pm{pm['id']}_vm{vm['id']}"
            
            physical_machines_overload[pm['id']]['s']['load']['cpu'] -= vm['requested']['cpu'] / physical_machines[pm['id']]['capacity']['cpu']
            physical_machines_overload[pm['id']]['s']['load']['memory'] -= vm['requested']['memory'] / physical_machines[pm['id']]['capacity']['memory']

            schedule_overload_folder_path = os.path.join(OVERLOAD_FOLDER_PATH, f"schedule/step_{step}/pm_{pm['id']}")
            os.makedirs(schedule_overload_folder_path, exist_ok=True)

            # Convert into model input format
            mini_vm_model_input_file_path, mini_pm_model_input_file_path = save_mini_model_input_format(vms_to_allocate, physical_machines_overload, filename, schedule_overload_folder_path)
            
            # Run mini OPL model
            opl_output = run_mini_opl_model(mini_vm_model_input_file_path, mini_pm_model_input_file_path, schedule_overload_folder_path, filename)
            
            parsed_data = parse_mini_opl_output(opl_output)
            partial_allocation = parsed_data['allocation']
            vm_ids = parsed_data['vm_ids']
            
            vm_dict = {vm['id']: vm for vm in active_vms}
            # Assign a VM to a completed VM migration
            for vm_index, vm_id in enumerate(vm_ids):
                if partial_allocation[vm_index][pm['id']] == 1:
                    scheduled_vms[vm['id']].append(vm_dict[vm_id])
                    print(f"VM {vm_ids[vm_index]} scheduled on PM {pm['id']} after VM {vm['id']} migration.")

def solve_overload(pm, physical_machines, active_vms, scheduled_vms, step):
    vms_to_allocate = []
    for vm in active_vms:
        if vm['allocation']['pm'] == pm['id'] and vm['allocation']['current_time'] == 0:
            vm['allocation']['pm'] = -1
            vms_to_allocate.append(vm)
            print(f"VM {vm['id']} removed from PM {pm['id']}.")
    
    cpu_load, memory_load = calculate_load(physical_machines, active_vms)
    update_physical_machines_load(physical_machines, cpu_load, memory_load)

    physical_machines_overload = deepcopy(physical_machines)
    fill_other_pms(physical_machines_overload, pm)
    
    # Convert into model input format
    mini_vm_model_input_file_path, mini_pm_model_input_file_path = save_mini_model_input_format(vms_to_allocate, physical_machines_overload, step, OVERLOAD_FOLDER_PATH)
    
    # Run mini OPL model
    opl_output = run_mini_opl_model(mini_vm_model_input_file_path, mini_pm_model_input_file_path, OVERLOAD_FOLDER_PATH, step)
    
    parsed_data = parse_mini_opl_output(opl_output)
    partial_allocation = parsed_data['allocation']
    vm_ids = parsed_data['vm_ids']
    pm_ids = parsed_data['pm_ids']
    
    # Reallocate VMs
    mini_reallocate_vms(vm_ids, pm_ids, partial_allocation, active_vms)

    for vm in active_vms:
        if vm in vms_to_allocate and vm['allocation']['pm'] != -1:
            print(f"VM {vm['id']} allocated on PM {vm['allocation']['pm']} during overload solving.")
            vms_to_allocate.remove(vm)
    
    if vms_to_allocate:
        schedule_overload(physical_machines, active_vms, pm, step, vms_to_allocate, scheduled_vms)

def check_overload(physical_machines, active_vms, scheduled_vms, step):
    cpu_load, memory_load = calculate_load(physical_machines, active_vms)
    
    for pm in physical_machines:
        if cpu_load[pm['id']] > 1:
            print(f"CPU overload detected on PM {pm['id']}.")
            solve_overload(pm, physical_machines, active_vms, scheduled_vms, step)
        elif memory_load[pm['id']] > 1:
            print(f"Memory overload detected on PM {pm['id']}.")
            solve_overload(pm, physical_machines, active_vms, scheduled_vms, step)
        
        cpu_load, memory_load = calculate_load(physical_machines, active_vms)

        if cpu_load[pm['id']] > 1 or memory_load[pm['id']] > 1:
            print()
            print(f"Error on PM {pm['id']}:")
            print (f"CPU load: {cpu_load[pm['id']]}")
            print (f"Memory load: {memory_load[pm['id']]}")
            print()
            for vm in active_vms:
                if vm['allocation']['pm'] == pm['id']:
                    print(f"VM {vm['id']} allocated on PM {pm['id']}.")
            raise ValueError(f"Cannot proceed: Overload detected on PM {pm['id']}.")
        
    return cpu_load, memory_load