import os
import time

from allocation import get_non_allocated_workload, get_pms_on_schedule, run_opl_model, update_physical_machines_load
from mini import save_mini_model_input_format, parse_mini_opl_output
from log import log_performance
from filter import filter_dict_randomly, filter_full_pms, split_dict
from calculate import calculate_load
from config import PM_MANAGER_INPUT_FOLDER_PATH, PM_MANAGER_OUTPUT_FOLDER_PATH

try:
    profile # type: ignore
except NameError:
    def profile(func):
        return func

def allocate_vms(vm_ids, pm_ids, allocation, non_allocated_vms, physical_machines_off, is_on, time_step):
    vms_to_deallocate_in_subset = []

    for vm_index, vm_id in enumerate(vm_ids):
        for pm_index, pm_id in enumerate(pm_ids):
            if allocation[vm_index][pm_index] == 1:
                is_on[pm_id] = 1
                vm = non_allocated_vms.get(vm_id)
                pm = physical_machines_off.get(pm_id)
                vm['allocation']['pm'] = pm_id
                if pm['s']['time_to_turn_on'] >= time_step:
                    vms_to_deallocate_in_subset.append(vm_id)
    
    return vms_to_deallocate_in_subset

@profile
def pm_manager(non_allocated_vms, physical_machines_off, step, power_function_dict, nb_points, performance_log_file, is_on, time_step, pm_manager_input_folder_path=PM_MANAGER_INPUT_FOLDER_PATH, pm_manager_output_folder_path=PM_MANAGER_OUTPUT_FOLDER_PATH):
    # Convert into model input format
    mini_vm_model_input_file_path, mini_pm_model_input_file_path = save_mini_model_input_format(
        non_allocated_vms, physical_machines_off, step, pm_manager_input_folder_path, power_function_dict, nb_points)

    num_vms = len(non_allocated_vms)
    num_pms = len(physical_machines_off)

    start_time_opl = time.time()
    opl_output = run_opl_model(mini_vm_model_input_file_path, mini_pm_model_input_file_path, PM_MANAGER_INPUT_FOLDER_PATH, pm_manager_output_folder_path, step, "pm_manager")
    end_time_opl = time.time()

    # Parse OPL output and reallocate VMs
    parsed_data = parse_mini_opl_output(opl_output)
    partial_allocation = parsed_data.get('allocation')
    vm_ids = parsed_data['vm_ids']
    pm_ids = parsed_data['pm_ids']
    vms_to_deallocate_in_subset = allocate_vms(vm_ids, pm_ids, partial_allocation, non_allocated_vms, physical_machines_off, is_on, time_step)
    log_performance(step, "pm_manager", end_time_opl - start_time_opl, True, num_vms, num_pms, performance_log_file)

    return vms_to_deallocate_in_subset

@profile
def launch_pm_manager(active_vms, physical_machines, is_on, step, time_step, power_function_dict, nb_points, scheduled_vms, pms_to_turn_off_after_migration, performance_log_file, input_folder_path=PM_MANAGER_INPUT_FOLDER_PATH, output_folder_path=PM_MANAGER_OUTPUT_FOLDER_PATH, pm_manager_max_vms=None, pm_manager_max_pms=None):
    # Get non-allocated VMs
    non_allocated_vms = get_non_allocated_workload(active_vms, scheduled_vms)
    pms_on_schedule = get_pms_on_schedule(active_vms, scheduled_vms)

    physical_machines_off = {}

    for pm_id, pm in physical_machines.items():
        s = pm['s']
        state = s['state']
        time_to_turn_on = s['time_to_turn_on']
        time_to_turn_off = s['time_to_turn_off']
        load_cpu = s['load']['cpu']
        load_memory = s['load']['memory']

        if state == 1:
            if time_to_turn_on < time_step:
                if load_cpu <= 0 and load_memory <= 0 and pm_id not in pms_on_schedule:
                    is_on[pm_id] = 0  # Turn off PMs that are on but have nothing allocated
            else:
                physical_machines_off[pm_id] = pm  
        elif state == 0 and time_to_turn_off <= 0:
            physical_machines_off[pm_id] = pm  # PM is off

    for pm_id in pms_to_turn_off_after_migration:
        print(f" PM {pm_id} will be turned off after migrations")
        if pm_id in physical_machines_off:
            del physical_machines_off[pm_id]

   # Call scaling manager if there are non-allocated VMs and off PMs
    if physical_machines_off and non_allocated_vms:
        vms_to_deallocate = []

        # Determine PM subset
        if pm_manager_max_pms and len(physical_machines_off) > pm_manager_max_pms:
            physical_machines_off_subset = filter_dict_randomly(physical_machines_off, pm_manager_max_pms)
        else:
            physical_machines_off_subset = physical_machines_off.copy()
            
        # Determine VM subsets
        if pm_manager_max_vms and len(non_allocated_vms) > pm_manager_max_vms:
            non_allocated_vms_subsets = split_dict(non_allocated_vms, pm_manager_max_vms)
        else:
            non_allocated_vms_subsets = [non_allocated_vms]

        for index, vm_subset in enumerate(non_allocated_vms_subsets):
            pm_manager_input_folder_path = os.path.join(input_folder_path, f"step_{step}/subset_{index}")
            pm_manager_output_folder_path = os.path.join(output_folder_path, f"step_{step}/subset_{index}")

            os.makedirs(pm_manager_input_folder_path, exist_ok=True)
            os.makedirs(pm_manager_output_folder_path, exist_ok=True)
            
            # Calculate loads and update PMs
            cpu_load, memory_load = calculate_load(physical_machines_off_subset, non_allocated_vms, time_step, pm_manager=True)
            update_physical_machines_load(physical_machines_off_subset, cpu_load, memory_load)
            len_physical_machines_off_subset = len(physical_machines_off_subset)
            filter_full_pms(physical_machines_off_subset)
            # Check if we need to add more PMs
            if pm_manager_max_pms and len(physical_machines_off_subset) < len_physical_machines_off_subset:
                # Get PMs not in the subset
                remaining_pms = {pm_id: pm for pm_id, pm in physical_machines_off.items() if pm_id not in physical_machines_off_subset}
                if remaining_pms:
                    # Determine how many PMs we need to add
                    num_to_add = pm_manager_max_pms - len(physical_machines_off_subset)
                    # Randomly select PMs from remaining_pms
                    pms_to_add = filter_dict_randomly(remaining_pms, num_to_add)
                    # Add to subset
                    physical_machines_off_subset.update(pms_to_add)
                
            # Call the scaling manager
            vms_to_deallocate_in_subset = pm_manager(
                vm_subset,
                physical_machines_off_subset,
                step,
                power_function_dict,
                nb_points,
                performance_log_file,
                is_on,
                time_step,
                pm_manager_input_folder_path,
                pm_manager_output_folder_path
            )
            vms_to_deallocate.extend(vms_to_deallocate_in_subset)

        for vm_id in vms_to_deallocate:
            vm = non_allocated_vms.get(vm_id)
            vm['allocation']['pm'] = -1

