import os
import numpy as np
from copy import deepcopy
from config import INITIAL_VMS_FILE, INITIAL_PMS_FILE, POWER_FUNCTION_FILE, OUTPUT_FOLDER_PATH, MODEL_INPUT_FOLDER_PATH, MODEL_OUTPUT_FOLDER_PATH, MINI_MODEL_INPUT_FOLDER_PATH, TIME_STEP, NEW_VMS_PER_STEP, NUM_TIME_STEPS, USE_RANDOM_SEED, SAVE_LOGS, MAIN_MODEL_PERIOD, MINI_MODEL_PERIOD
from logs import log_initial_physical_machines, log_allocation, log_final_net_profit
from vm_generator import generate_new_vms
from utils import load_virtual_machines, load_physical_machines, load_configuration, save_latency_matrix, save_power_function, save_vm_sets, save_model_input_format, parse_opl_output, parse_power_function, evaluate_piecewise_linear_function, clean_up_model_input_files
from allocation import run_opl_model, reallocate_vms, update_physical_machines_state, check_overload, update_physical_machines_load, calculate_load, deallocate_vms
from mini import save_mini_model_input_format, run_mini_opl_model, parse_mini_opl_output, mini_reallocate_vms
from colorama import Fore, Style
from weights import w_load_cpu, energy, pue, migration

if USE_RANDOM_SEED:
    np.random.seed(42)

# Ensure the directories exist
os.makedirs(OUTPUT_FOLDER_PATH, exist_ok=True)
os.makedirs(MODEL_INPUT_FOLDER_PATH, exist_ok=True)
os.makedirs(MODEL_OUTPUT_FOLDER_PATH, exist_ok=True)

def execute_time_step(active_vms, terminated_vms, scheduled_vms, physical_machines):
    vms_extra_time = {}

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

    for vm_index, vm in enumerate(active_vms[:]):
        pm_id = vm['allocation']['pm'] if vm['allocation']['pm'] != -1 else (vm['migration']['to_pm'] if vm['migration']['to_pm'] != -1 else vm['run']['pm'])
        if pm_id != -1:
            pm = next((p for p in physical_machines if p['id'] == pm_id), None)
            if pm and pm['s']['state'] and pm['s']['time_to_turn_on'] == 0:
                pm_speed = pm['features']['speed']
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
                        vm['run']['current_time'] += extra_time * pm_speed
                elif vm['migration']['from_pm'] != -1 and vm['migration']['to_pm'] != -1:
                    remaining_time = vm['migration']['total_time'] - vm['migration']['current_time']
                    if TIME_STEP > remaining_time:
                        extra_time = round(TIME_STEP - remaining_time, 10)
                    vm['migration']['current_time'] += TIME_STEP
                    vm['run']['current_time'] += TIME_STEP * pm_speed * migration['penalty']
                    if vm['migration']['current_time'] >= vm['migration']['total_time']:
                        vms_extra_time[vm['id']] = (vm['migration']['from_pm'], extra_time)
                        vm['migration']['current_time'] = 0.0
                        vm['migration']['from_pm'] = -1
                        vm['migration']['to_pm'] = -1
                        vm['run']['current_time'] += extra_time * pm_speed
                        vm['run']['pm'] = pm_id
                elif vm['run']['pm'] != -1:
                    vm['run']['current_time'] += TIME_STEP * pm_speed
            if vm['run']['current_time'] >= vm['run']['total_time']:
                active_vms.remove(vm)
                terminated_vms.append(vm)

    for vm_id in scheduled_vms:  
        if vm_id in vms_extra_time:
            pm_id, migration_extra_time = vms_extra_time[vm_id]
            for scheduled_vm in scheduled_vms[vm_id]:
                scheduled_vm['allocation']['pm'] = pm_id
                remaining_time = scheduled_vm['allocation']['total_time'] - scheduled_vm['allocation']['current_time']
                if migration_extra_time > remaining_time:
                    extra_time = round(migration_extra_time - remaining_time, 10)
                scheduled_vm['allocation']['current_time'] += migration_extra_time
                if scheduled_vm['allocation']['current_time'] >= scheduled_vm['allocation']['total_time']:
                    scheduled_vm['allocation']['current_time'] = scheduled_vm['allocation']['total_time']
                    scheduled_vm['allocation']['pm'] = -1
                    scheduled_vm['run']['pm'] = pm_id
                    scheduled_vm['run']['current_time'] += extra_time * pm_speed

def calculate_total_costs(active_vms, physical_machines, cpu_load, memory_load):
    migration_energy_consumption = [0.0] * len(active_vms)
    load_energy_consumption = [0.0] * len(physical_machines)

    cpu_power = 0.0
    memory_power = 0.0
    turning_on_energy = 0.0
    turning_off_energy = 0.0
    
    pm_ids = [pm['id'] for pm in physical_machines]
    nb_points, power_function = parse_power_function(POWER_FUNCTION_FILE, pm_ids)

    for pm in physical_machines:
        cpu_power = 0.0
        memory_power = 0.0
        turning_on_energy = 0.0
        turning_off_energy = 0.0

        if pm['s']['state'] == 1 and pm['s']['time_to_turn_on'] == 0:
            cpu_power = w_load_cpu * evaluate_piecewise_linear_function(power_function[pm['id']], cpu_load[pm['id']])  
            memory_power = (1 - w_load_cpu) * evaluate_piecewise_linear_function(power_function[pm['id']], memory_load[pm['id']])
        
        elif pm['s']['state'] == 1 and pm['s']['time_to_turn_on'] > 0:
            turning_on_power = evaluate_piecewise_linear_function(power_function[pm['id']], 0) 
            turning_on_energy = turning_on_power * min(TIME_STEP, pm['s']['time_to_turn_on'])

        elif pm['s']['state'] == 0 and pm['s']['time_to_turn_off'] > 0:
            turning_off_power = evaluate_piecewise_linear_function(power_function[pm['id']], 0) 
            turning_off_energy = turning_off_power * min(TIME_STEP, pm['s']['time_to_turn_off'])

        load_energy_consumption[pm['id']] = (cpu_power + memory_power) * TIME_STEP + turning_on_energy + turning_off_energy
    
    for i, vm in enumerate(active_vms):
        if vm['migration']['from_pm'] != -1 and vm['migration']['to_pm'] != -1:
            migration_total_energy = migration['energy']['offset'] + migration['energy']['coefficient'] * vm['requested']['memory']
            migration_energy_per_second = migration_total_energy / vm['migration']['total_time']
            remaining_migration_time = vm['migration']['total_time'] - vm['migration']['current_time']
            migration_energy_consumption[i] = migration_energy_per_second * min(TIME_STEP, remaining_migration_time)

    total_energy_consumption = sum(load_energy_consumption) + sum(migration_energy_consumption)
    costs = total_energy_consumption * energy['cost'] * pue
    
    return costs


def calculate_total_profit(terminated_vms):
    total_profit = sum(vm['profit'] for vm in terminated_vms)
    return total_profit
      
def simulate_time_steps(initial_vms, initial_pms, num_steps, new_vms_per_step, log_folder_path):
    active_vms = initial_vms.copy()
    old_active_vms = []
    terminated_vms = []
    physical_machines = deepcopy(initial_pms)
    initial_physical_machines = deepcopy(initial_pms)
    total_costs = 0.0

    
    for pm in physical_machines:
        if pm['s']['state'] == 0:
            pm['s']['time_to_turn_off'] = 0.0
        else:
            pm['s']['time_to_turn_on'] = 0.0

    existing_ids = {vm['id'] for vm in initial_vms}

    for step in range(1, num_steps + 1):
        removed_vms = []
        turned_on_pms = []
        turned_off_pms = []
        scheduled_vms = {}
        for vm in active_vms:
            scheduled_vms[vm['id']] = []

        # Generate new VMs
        generate_new_vms(active_vms, new_vms_per_step, existing_ids)
    
        if step % MAIN_MODEL_PERIOD == 0:
            model_to_run = 'main'
        elif step % MINI_MODEL_PERIOD + 1 == 0:
            model_to_run = 'mini'
        else:
            model_to_run = 'none'

        if model_to_run == 'main':
            # Convert into model input format
            vm_model_input_file_path, pm_model_input_file_path = save_model_input_format(active_vms, physical_machines, step, MODEL_INPUT_FOLDER_PATH)
            
            # Run CPLEX model
            print(f"\n{Fore.YELLOW}{Style.BRIGHT}Running main model for time step {step}...{Style.RESET_ALL}\n")
            opl_output = run_opl_model(vm_model_input_file_path, pm_model_input_file_path, step)

            # Parse OPL output and reallocate VMs
            parsed_data = parse_opl_output(opl_output)
            new_allocation = parsed_data['new_allocation'] if 'new_allocation' in parsed_data else None
            vm_ids = parsed_data['vm_ids']
            pm_ids = parsed_data['pm_ids']
            is_allocation = parsed_data['is_allocation']
            is_migration = parsed_data['is_migration']
            is_removal = parsed_data['is_removal']
            is_on = parsed_data['is_on']

            if new_allocation and vm_ids and pm_ids:
                vm_previous_pm = {
                    vm['id']: vm['run']['pm'] if vm['run']['pm'] != -1 else (
                        vm['migration']['to_pm'] if vm['migration']['to_pm'] != -1 else None
                    )
                    for vm in active_vms
                }
                
                removed_vms = reallocate_vms(active_vms, new_allocation, vm_ids, pm_ids, is_allocation, is_migration, is_removal, vm_previous_pm)
        
        elif model_to_run == 'mini':
            non_allocated_vms = [vm for vm in active_vms if (vm['allocation']['pm'] == -1 and vm['run']['pm'] == -1 and vm['migration']['from_pm'] == -1 and vm['migration']['to_pm'] == -1)]

            # Convert into model input format
            mini_vm_model_input_file_path, mini_pm_model_input_file_path = save_mini_model_input_format(non_allocated_vms, physical_machines, step, MINI_MODEL_INPUT_FOLDER_PATH)
            
            # Run CPLEX model
            print(f"\n{Fore.YELLOW}{Style.BRIGHT}Running mini model for time step {step}...{Style.RESET_ALL}\n")
            opl_output = run_mini_opl_model(mini_vm_model_input_file_path, mini_pm_model_input_file_path, MODEL_OUTPUT_FOLDER_PATH, step)

            # Parse OPL output and reallocate VMs
            parsed_data = parse_mini_opl_output(opl_output)
            partial_allocation = parsed_data['allocation'] if 'allocation' in parsed_data else None
            vm_ids = parsed_data['vm_ids']
            pm_ids = parsed_data['pm_ids']

            mini_reallocate_vms(vm_ids, pm_ids, partial_allocation, active_vms)
        
        if model_to_run == 'none':
            print(f"\n{Fore.YELLOW}{Style.BRIGHT}No model to run for time step {step}...{Style.RESET_ALL}\n")
            
            is_on = [pm['s']['state'] for pm in physical_machines]
        
        turned_on_pms, turned_off_pms = update_physical_machines_state(physical_machines, initial_physical_machines, is_on)

        # Calculate, check and update load
        cpu_load, memory_load = check_overload(physical_machines, active_vms, scheduled_vms, step)
        update_physical_machines_load(physical_machines, cpu_load, memory_load)
        
        save_vm_sets(active_vms, terminated_vms, step, OUTPUT_FOLDER_PATH)

        # Calculate costs and profit
        total_costs += calculate_total_costs(active_vms, physical_machines, cpu_load, memory_load)
        total_profit = calculate_total_profit(terminated_vms)

        # Log current allocation and physical machine load
        log_allocation(step, active_vms, old_active_vms, terminated_vms, removed_vms, turned_on_pms, turned_off_pms, physical_machines, cpu_load, memory_load, total_profit, total_costs, log_folder_path)
        old_active_vms = deepcopy(active_vms)

        # Execute time step
        execute_time_step(active_vms, terminated_vms, scheduled_vms, physical_machines)
        
        # Deallocate VMs assigned to turning on physical machines, so that they can be reallocated by the models
        deallocate_vms(active_vms)
        
        # Calculate and update load
        cpu_load, memory_load = calculate_load(physical_machines, active_vms)
        update_physical_machines_load(physical_machines, cpu_load, memory_load)

    return total_profit, total_costs


if __name__ == "__main__":
    initial_vms = load_virtual_machines(os.path.expanduser(INITIAL_VMS_FILE))
    initial_pms, latency_matrix = load_physical_machines(os.path.expanduser(INITIAL_PMS_FILE))
    log_folder_path = None
    if SAVE_LOGS:
        log_folder_path = log_initial_physical_machines(initial_pms)
    load_configuration(MODEL_INPUT_FOLDER_PATH)
    save_latency_matrix(latency_matrix, MODEL_INPUT_FOLDER_PATH)
    save_power_function(os.path.expanduser(INITIAL_PMS_FILE), MODEL_INPUT_FOLDER_PATH)
    total_profit, total_costs = simulate_time_steps(initial_vms, initial_pms, NUM_TIME_STEPS, NEW_VMS_PER_STEP, log_folder_path)
    log_final_net_profit(total_profit, total_costs, log_folder_path)
    clean_up_model_input_files()
