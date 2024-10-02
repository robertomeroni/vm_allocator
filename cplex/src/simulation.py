import argparse
import importlib.util
import os
import sys
import math
import numpy as np
import time
from copy import deepcopy
from colorama import Fore, Style
import warnings
from sklearn.exceptions import InconsistentVersionWarning
from collections import defaultdict
import csv

# Suppress the specific InconsistentVersionWarning
warnings.filterwarnings("ignore", category=InconsistentVersionWarning)


# Parse command-line arguments
parser = argparse.ArgumentParser()
parser.add_argument('--config', default='src/config.py', help='Path to the configuration file')
parser.add_argument('--trace', help='Path to the VM trace file')
if '--trace' in sys.argv:
    print("Trace file argument provided")
args = parser.parse_args()

# Dynamically import the config file
spec = importlib.util.spec_from_file_location("config", args.config)
config = importlib.util.module_from_spec(spec)

try:
    spec.loader.exec_module(config)
except FileNotFoundError:
    print(f"Configuration file {args.config} not found.")
    exit(1)
except Exception as e:
    print(f"Error loading configuration file: {e}")
    exit(1)

# Access configuration constants using the config object
INITIAL_VMS_FILE = getattr(config, 'INITIAL_VMS_FILE', None)
INITIAL_PMS_FILE = getattr(config, 'INITIAL_PMS_FILE', None)
PREDICTOR_MODEL_PATH = getattr(config, 'PREDICTOR_MODEL_PATH', None)
POWER_FUNCTION_FILE = getattr(config, 'POWER_FUNCTION_FILE', None)
SIMULATION_INPUT_FOLDER_PATH = getattr(config, 'SIMULATION_INPUT_FOLDER_PATH', None)
OUTPUT_FOLDER_PATH = getattr(config, 'OUTPUT_FOLDER_PATH', None)
MODEL_INPUT_FOLDER_PATH = getattr(config, 'MODEL_INPUT_FOLDER_PATH', None)
MODEL_OUTPUT_FOLDER_PATH = getattr(config, 'MODEL_OUTPUT_FOLDER_PATH', None)
MINI_MODEL_INPUT_FOLDER_PATH = getattr(config, 'MINI_MODEL_INPUT_FOLDER_PATH', None)
ARRIVALS_TRACKING_FILE = getattr(config, 'ARRIVALS_TRACKING_FILE', None)
TIME_STEP = getattr(config, 'TIME_STEP', None)
NEW_VMS_PER_STEP = getattr(config, 'NEW_VMS_PER_STEP', None)
NUM_TIME_STEPS = getattr(config, 'NUM_TIME_STEPS', None)
USE_RANDOM_SEED = getattr(config, 'USE_RANDOM_SEED', None)
SEED_NUMBER = getattr(config, 'SEED_NUMBER', None)
STARTING_STEP = getattr(config, 'STARTING_STEP', None)
PERFORMANCE_MEASUREMENT = getattr(config, 'PERFORMANCE_MEASUREMENT', None)
USE_REAL_DATA = getattr(config, 'USE_REAL_DATA', None)
USE_WORKLOAD_PREDICTOR = getattr(config, 'USE_WORKLOAD_PREDICTOR', None)
WORKLOAD_NAME = getattr(config, 'WORKLOAD_NAME', None)
WORKLOAD_PREDICTION_FILE = getattr(config, 'WORKLOAD_PREDICTION_FILE', None)
WORKLOAD_PREDICTION_MODEL = getattr(config, 'WORKLOAD_PREDICTION_MODEL', None)
SAVE_LOGS = getattr(config, 'SAVE_LOGS', None)
SAVE_VM_AND_PM_SETS = getattr(config, 'SAVE_VM_AND_PM_SETS', None)
MAIN_MODEL_PERIOD = getattr(config, 'MAIN_MODEL_PERIOD', None)
MINI_MODEL_PERIOD = getattr(config, 'MINI_MODEL_PERIOD', None)
MASTER_MODEL = getattr(config, 'MASTER_MODEL', None)
FILTER = getattr(config, 'FILTER', None)

# Set VMS_TRACE_FILE if --trace argument is provided
VMS_TRACE_FILE = args.trace if args.trace else getattr(config, 'VMS_TRACE_FILE', None)
if VMS_TRACE_FILE and not os.path.isabs(VMS_TRACE_FILE) and not os.path.exists(VMS_TRACE_FILE):
    VMS_TRACE_FILE = os.path.join(SIMULATION_INPUT_FOLDER_PATH, VMS_TRACE_FILE)

from logs import log_initial_physical_machines, log_allocation, log_final_net_profit
from vm_generator import generate_new_vms
from utils import load_virtual_machines, load_physical_machines, get_start_time, get_first_vm_arrival_time, get_last_vm_arrival_time, load_configuration, save_power_function, save_vm_sets, save_pm_sets, save_model_input_format, parse_opl_output, parse_power_function, evaluate_piecewise_linear_function, calculate_load, clean_up_model_input_files, load_new_vms, check_overload, check_migration_overload, check_unique_state, check_zero_load, check_migration_correctness, find_migration_times
from allocation import run_opl_model, reallocate_vms, update_physical_machines_state, detect_overload, get_non_allocated_vms, is_fully_on, update_physical_machines_load, deallocate_vms
from mini import save_mini_model_input_format, run_mini_opl_model, parse_mini_opl_output, mini_reallocate_vms
from algorithms import best_fit, guazzone_bfd, shi_allocation, shi_migration
from scaling_manager import launch_scaling_manager
from workload_predictor import track_arrivals
from filter import filter_full_physical_machines
from weights import w_load_cpu, energy, pue, migration

# Check if NO_COLOR environment variable is set
NO_COLOR = os.environ.get('NO_COLOR', '0') == '1'

# Define a function to apply color only if colors are enabled
def color_text(text, color):
    if NO_COLOR:
        return text
    return f"{color}{text}{Style.RESET_ALL}"

if USE_RANDOM_SEED:
    np.random.seed(SEED_NUMBER)
    
# Ensure the directories exist
os.makedirs(OUTPUT_FOLDER_PATH, exist_ok=True)
os.makedirs(MODEL_INPUT_FOLDER_PATH, exist_ok=True)
os.makedirs(MODEL_OUTPUT_FOLDER_PATH, exist_ok=True)


def execute_time_step(active_vms, terminated_vms_in_step, terminated_vms, scheduled_vms, physical_machines):
    num_completed_migrations = 0
    pms_extra_time = {}
    vms_extra_time = {}

    # Update the turning on and turning off time for physical machines
    for pm in physical_machines:
        if pm['s']['state'] == 1 and pm['s']['time_to_turn_on'] > 0:
            pm['s']['time_to_turn_on'] = round(pm['s']['time_to_turn_on'] - TIME_STEP, 10)
            if pm['s']['time_to_turn_on'] < 0:
                pms_extra_time[pm['id']] = round(abs(pm['s']['time_to_turn_on']), 10)
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
                    time_step = TIME_STEP
                    remaining_allocation_time = vm['allocation']['total_time'] - vm['allocation']['current_time']
                    if pm_id in pms_extra_time:
                        time_step = pms_extra_time[pm_id]
                    if time_step > remaining_allocation_time:
                        extra_time = round(time_step - remaining_allocation_time, 10)
                    vm['allocation']['current_time'] += time_step
                    if vm['allocation']['current_time'] >= vm['allocation']['total_time']:
                        vm['allocation']['current_time'] = vm['allocation']['total_time']
                        vm['allocation']['pm'] = -1
                        vm['run']['pm'] = pm_id
                        vm['run']['current_time'] += extra_time * pm_speed
                elif vm['migration']['from_pm'] != -1 and vm['migration']['to_pm'] != -1:
                    from_pm_id = vm['migration']['from_pm']
                    from_pm = next((p for p in physical_machines if p['id'] == from_pm_id), None)
                    if not from_pm:
                        raise ValueError(f"Physical machine with ID {from_pm_id} not found")
                    from_pm_speed = from_pm['features']['speed']
                    vm['run']['current_time'] += TIME_STEP * from_pm_speed
                    remaining_time = vm['migration']['total_time'] - vm['migration']['current_time']
                    if TIME_STEP > remaining_time:
                        extra_time = round(TIME_STEP - remaining_time, 10)
                    vm['migration']['current_time'] += TIME_STEP
                    if vm['migration']['current_time'] >= vm['migration']['total_time'] + vm['migration']['down_time']:
                        num_completed_migrations += 1
                        vm['migration']['current_time'] = 0.0
                        vm['migration']['from_pm'] = -1
                        vm['migration']['to_pm'] = -1
                        vm['run']['current_time'] -= vm['migration']['down_time'] * from_pm_speed
                        vm['run']['pm'] = pm_id
                elif vm['run']['pm'] != -1:
                    vm['run']['current_time'] += TIME_STEP * pm_speed
            if vm['run']['current_time'] >= vm['run']['total_time']:
                active_vms.remove(vm)
                terminated_vms_in_step.append(vm)
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

    return num_completed_migrations

def find_migration_times(active_vms, pm):
    pm_id = pm['id']
    
    # Collect remaining migration times for VMs migrating from pm_id
    source_vm_times = sorted(
        [vm['migration']['total_time'] - vm['migration']['current_time'] 
         for vm in active_vms if vm['migration']['from_pm'] == pm_id], 
        reverse=True
    )
    
    # Collect remaining migration times for VMs migrating to pm_id
    target_vm_times = sorted(
        [vm['migration']['total_time'] - vm['migration']['current_time'] 
         for vm in active_vms if vm['migration']['to_pm'] == pm_id], 
        reverse=True
    )

    # Max and second max times for source VMs
    max_time_source = source_vm_times[0] if source_vm_times else 0
    second_max_time_source = source_vm_times[1] if len(source_vm_times) > 1 else 0

    # Max and second max times for target VMs
    max_time_target = target_vm_times[0] if target_vm_times else 0
    second_max_time_target = target_vm_times[1] if len(target_vm_times) > 1 else 0

    # Compute effective times
    real_time_only_source = max_time_source
    real_time_only_target = max_time_target
    real_time_multiple_source = max_time_source - second_max_time_source
    real_time_multiple_target = max_time_target - second_max_time_target

    # Combined times for both source and target VMs
    combined_times = sorted(source_vm_times + target_vm_times, reverse=True)
    max_combined_time = combined_times[0] if combined_times else 0
    second_max_combined_time = combined_times[1] if len(combined_times) > 1 else 0
    real_time_multiple_source_and_target = max_combined_time - second_max_combined_time

    return (
        real_time_only_source, 
        real_time_only_target, 
        real_time_multiple_source, 
        real_time_multiple_target, 
        real_time_multiple_source_and_target
    )


def calculate_total_costs(active_vms, physical_machines, cpu_load, memory_load):
    migration_energy_consumption = [0.0] * len(physical_machines)
    pm_energy_consumption = [0.0] * len(physical_machines)
    load_energy_consumption = [0.0] * len(physical_machines)
    
    pm_ids = [pm['id'] for pm in physical_machines]
    nb_points, power_function = parse_power_function(POWER_FUNCTION_FILE, pm_ids)

    for pm in physical_machines:
        turning_on_energy = 0.0
        turning_off_energy = 0.0
        real_time_base = 0.0
        real_time_only_source = 0.0
        real_time_only_target = 0.0
        real_time_multiple_source = 0.0
        real_time_multiple_target = 0.0
        real_time_multiple_source_and_target = 0.0
        power_base = 0.0
        power_migration_source = 0.0
        power_migration_target = 0.0
        power_migration_multiple_source = 0.0
        power_migration_multiple_target = 0.0
        power_migration_multiple_source_and_target = 0.0

        if pm['s']['state'] == 1 and pm['s']['time_to_turn_on'] == 0:
            cpu_migration_overhead = 0.0

            migration_overhead_source = False
            migration_overhead_target = False
            multiple_migrations = False
            for vm in active_vms:
                if vm['migration']['from_pm'] == pm['id']:
                    if migration_overhead_source or migration_overhead_target:
                        multiple_migrations = True
                    else:
                        cpu_migration_overhead += migration['energy']['cpu_overhead']['source']
                        migration_overhead_source = True
                    
                if vm['migration']['to_pm'] == pm['id']:
                    if migration_overhead_source or migration_overhead_target:
                        multiple_migrations = True
                    else:
                        cpu_migration_overhead += migration['energy']['cpu_overhead']['target']
                        migration_overhead_target = True

            if multiple_migrations:
                cpu_migration_overhead += migration['energy']['concurrent']
            
            check_migration_overload(cpu_migration_overhead, migration_overhead_source, migration_overhead_target, multiple_migrations)
            
            power_base = evaluate_piecewise_linear_function(power_function[pm['id']], w_load_cpu * cpu_load[pm['id']] + (1 - w_load_cpu) * memory_load[pm['id']])
            power_migration_source = evaluate_piecewise_linear_function(power_function[pm['id']], w_load_cpu * cpu_load[pm['id']] + (1 - w_load_cpu) * memory_load[pm['id']], migration['energy']['cpu_overhead']['source'])  
            power_migration_target = evaluate_piecewise_linear_function(power_function[pm['id']], w_load_cpu * cpu_load[pm['id']] + (1 - w_load_cpu) * memory_load[pm['id']], migration['energy']['cpu_overhead']['target'])  
            power_migration_multiple_source = evaluate_piecewise_linear_function(power_function[pm['id']], w_load_cpu * cpu_load[pm['id']] + (1 - w_load_cpu) * memory_load[pm['id']], migration['energy']['concurrent'] + migration['energy']['cpu_overhead']['source'])
            power_migration_multiple_target = evaluate_piecewise_linear_function(power_function[pm['id']], w_load_cpu * cpu_load[pm['id']] + (1 - w_load_cpu) * memory_load[pm['id']], migration['energy']['concurrent'] + migration['energy']['cpu_overhead']['target'])
            power_migration_multiple_source_and_target = evaluate_piecewise_linear_function(power_function[pm['id']], w_load_cpu * cpu_load[pm['id']] + (1 - w_load_cpu) * memory_load[pm['id']], migration['energy']['concurrent'] + migration['energy']['cpu_overhead']['source'] + migration['energy']['cpu_overhead']['target'])
            
            real_time_only_source, real_time_only_target, real_time_multiple_source, real_time_multiple_target, real_time_multiple_source_and_target = find_migration_times(active_vms, pm)
            real_time_base = max(0, TIME_STEP - real_time_only_source - real_time_only_target - real_time_multiple_source - real_time_multiple_target - real_time_multiple_source_and_target)
        
        elif pm['s']['state'] == 1 and pm['s']['time_to_turn_on'] > 0:
            turning_on_power = evaluate_piecewise_linear_function(power_function[pm['id']], 0) 
            turning_on_energy = turning_on_power * min(TIME_STEP, pm['s']['time_to_turn_on'])

        elif pm['s']['state'] == 0 and pm['s']['time_to_turn_off'] > 0:
            turning_off_power = evaluate_piecewise_linear_function(power_function[pm['id']], 0) 
            turning_off_energy = turning_off_power * min(TIME_STEP, pm['s']['time_to_turn_off'])

        load_energy_consumption = real_time_base * power_base
        pm_energy_consumption[pm['id']] = turning_on_energy + turning_off_energy + load_energy_consumption
        migration_energy_consumption[pm['id']] = real_time_only_source * power_migration_source + real_time_only_target * power_migration_target + real_time_multiple_source * power_migration_multiple_source + real_time_multiple_target * power_migration_multiple_target + real_time_multiple_source_and_target * power_migration_multiple_source_and_target

    pm_costs = sum(pm_energy_consumption) * energy['cost'] * pue
    migration_costs = sum(migration_energy_consumption) * energy['cost'] * pue
    total_costs = pm_costs + migration_costs
    
    return total_costs, pm_costs, migration_costs

def calculate_total_revenue(terminated_vms):
    total_revenue = sum(vm['revenue'] for vm in terminated_vms)
    return total_revenue
      
def simulate_time_steps(initial_vms, initial_pms, num_steps, new_vms_per_step, log_folder_path):
    if USE_REAL_DATA:
        active_vms = []
        virtual_machines_schedule = load_new_vms(VMS_TRACE_FILE)
        first_vm_arrival_time = get_first_vm_arrival_time(VMS_TRACE_FILE)
        last_vm_arrival_time = get_last_vm_arrival_time(VMS_TRACE_FILE)
        starting_step = max(STARTING_STEP, math.ceil(first_vm_arrival_time / TIME_STEP))
    else:
        active_vms = initial_vms.copy()
        starting_step = STARTING_STEP

    old_active_vms = []
    terminated_vms = []
    terminated_vms_in_step = []
    physical_machines = deepcopy(initial_pms)
    initial_physical_machines = deepcopy(initial_pms)
    num_completed_migrations = 0
    num_removed_vms = 0
    max_percentage_of_pms_on = 0
    total_cpu_load = 0.0
    total_memory_load = 0.0
    total_fully_on_pm = 0.0
    total_costs = 0.0
    total_pm_energy_consumption = 0.0
    total_migration_energy_consumption = 0.0

    for pm in physical_machines:
        if pm['s']['state'] == 0:
            pm['s']['time_to_turn_off'] = 0.0
        else:
            pm['s']['time_to_turn_on'] = 0.0

    existing_ids = {vm['id'] for vm in initial_vms}

    if PERFORMANCE_MEASUREMENT:
        performance_log_file = os.path.join(log_folder_path, "performance_log.csv")
        with open(performance_log_file, "w", newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["Step", "Model", "Time"])

    print(f"Initialization done")
    for step in range(starting_step, starting_step + num_steps + 1):
        removed_vms = []
        turned_on_pms = []
        turned_off_pms = []
        scheduled_vms = {}

        use_scaling_manager = False
        is_new_vms_arrival = False
        is_on = [pm['s']['state'] for pm in physical_machines]

        # Get idle power for each physical machine
        pm_ids = [pm['id'] for pm in physical_machines]
        nb_points, power_function = parse_power_function(POWER_FUNCTION_FILE, pm_ids)
        idle_power = [evaluate_piecewise_linear_function(power_function[pm['id']], 0) for pm in physical_machines]

        if USE_REAL_DATA:
            vms_in_step = []
            print("Checking new arrived VMs...")
            
            for vm in virtual_machines_schedule:
                if vm['arrival_time'] <= step * TIME_STEP and vm['arrival_time'] >= STARTING_STEP * TIME_STEP:
                    active_vms.append(vm)
                    vms_in_step.append(vm)
                    virtual_machines_schedule.remove(vm)
                elif vm['arrival_time'] > step * TIME_STEP:
                    break

            track_arrivals(WORKLOAD_NAME, step, TIME_STEP, vms_in_step)
            if len(vms_in_step) > 0:
                is_new_vms_arrival = True
            
            predictions = defaultdict(lambda: defaultdict(dict))
        else:
            # Generate new VMs randomly
            generate_new_vms(active_vms, new_vms_per_step, existing_ids)
        

        for vm in active_vms:
            scheduled_vms[vm['id']] = []

        is_state_changed = is_new_vms_arrival or is_vms_terminated or is_pms_turned_on

        # Determine which model to run
        if MASTER_MODEL:
            model_to_run = MASTER_MODEL
            if MASTER_MODEL == 'mixed':
                if step % MAIN_MODEL_PERIOD == 0 or step == 1:
                    model_to_run = 'main'
                elif (step + 1) % MINI_MODEL_PERIOD == 0:
                    model_to_run = 'mini'
        else:
            model_to_run = 'none'

        # Don't run the model if the state of the system hasn't changed
        if MASTER_MODEL == 'main' or MASTER_MODEL == 'mini' or MASTER_MODEL == 'mixed':
            use_scaling_manager = True

            if not is_state_changed:
                model_to_run = 'none'

        if model_to_run == 'main':
            # Deallocate VMs assigned to turning on physical machines, so that they can be reallocated by the models
            deallocate_vms(active_vms)
            
            physical_machines_on = [pm for pm in physical_machines if pm['s']['state'] == 1 and pm['s']['time_to_turn_on'] <= TIME_STEP]

            if FILTER:
                # Don't pass full physical machines to the model
                physical_machines_on = filter_full_physical_machines(physical_machines_on)

            # Convert into model input format
            vm_model_input_file_path, pm_model_input_file_path = save_model_input_format(active_vms, physical_machines_on, step, MODEL_INPUT_FOLDER_PATH)
            
            # Run CPLEX model
            print(color_text(f"\nRunning main model for time step {step}...", Fore.YELLOW))
            start_time_opl = time.time()
            opl_output = run_opl_model(vm_model_input_file_path, pm_model_input_file_path, step)
            end_time_opl = time.time()

            if PERFORMANCE_MEASUREMENT:
                time_taken = end_time_opl - start_time_opl
                print(f"\nTime taken to run main model: {time_taken} seconds")
                with open(performance_log_file, "a", newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow([step, "main", time_taken])

            # Parse OPL output and reallocate VMs
            parsed_data = parse_opl_output(opl_output)
            new_allocation = parsed_data['new_allocation'] if 'new_allocation' in parsed_data else None
            vm_ids = parsed_data['vm_ids']
            pm_ids = parsed_data['pm_ids']
            is_allocation = parsed_data['is_allocation']
            is_migration = parsed_data['is_migration']
            is_removal = parsed_data['is_removal']

            if new_allocation and vm_ids and pm_ids:
                vm_previous_pm = {
                    vm['id']: vm['run']['pm'] if vm['run']['pm'] != -1 else (
                        vm['migration']['to_pm'] if vm['migration']['to_pm'] != -1 else None
                    )
                    for vm in active_vms
                }
                
                removed_vms = reallocate_vms(active_vms, new_allocation, vm_ids, pm_ids, is_allocation, is_migration, is_removal, vm_previous_pm)
            # Calculate, check and update load
            cpu_load, memory_load = detect_overload(physical_machines, active_vms, scheduled_vms, step, TIME_STEP)
            update_physical_machines_load(physical_machines, cpu_load, memory_load)

        elif model_to_run == 'mini':
            print("Filtering VMs...")
            # Deallocate VMs assigned to turning on physical machines, so that they can be reallocated by the models
            deallocate_vms(active_vms)
            non_allocated_vms = get_non_allocated_vms(active_vms)

            physical_machines_on_and_not_full = []
            

            if non_allocated_vms:   
                min_vm_requested_cpu = min([vm['requested']['cpu'] for vm in non_allocated_vms])
                min_vm_requested_memory = min([vm['requested']['memory'] for vm in non_allocated_vms])
            
                for pm in physical_machines:
                    if pm['s']['state'] == 1 and pm['s']['time_to_turn_on'] <= TIME_STEP:
                        free_cpu = pm['capacity']['cpu'] - pm['s']['load']['cpu'] * pm['capacity']['cpu']
                        free_memory = pm['capacity']['memory'] - pm['s']['load']['memory'] * pm['capacity']['memory']
                        if free_cpu >= min_vm_requested_cpu and free_memory >= min_vm_requested_memory:
                            physical_machines_on_and_not_full.append(pm)

                # Convert into model input format
                mini_vm_model_input_file_path, mini_pm_model_input_file_path = save_mini_model_input_format(non_allocated_vms, physical_machines_on_and_not_full, step, MINI_MODEL_INPUT_FOLDER_PATH)
            
                # Run CPLEX model
                print(color_text(f"\nRunning mini model for time step {step}...", Fore.YELLOW))
                start_time_opl = time.time()
                opl_output = run_mini_opl_model(mini_vm_model_input_file_path, mini_pm_model_input_file_path, MODEL_OUTPUT_FOLDER_PATH, step)
                end_time_opl = time.time()

                if PERFORMANCE_MEASUREMENT:
                    time_taken = end_time_opl - start_time_opl
                    print(f"\nTime taken to run mini model: {time_taken} seconds")
                    with open(performance_log_file, "a", newline='') as f:
                        writer = csv.writer(f)
                        writer.writerow([step, "mini", time_taken])

                # Parse OPL output and reallocate VMs
                parsed_data = parse_mini_opl_output(opl_output)
                partial_allocation = parsed_data['allocation'] if 'allocation' in parsed_data else None
                vm_ids = parsed_data['vm_ids']
                pm_ids = parsed_data['pm_ids']

                mini_reallocate_vms(vm_ids, pm_ids, partial_allocation, active_vms)
            else:
                print(color_text(f"\nNo VMs to allocate for time step {step}...", Fore.YELLOW))
        
        elif model_to_run == 'best_fit':
            deallocate_vms(active_vms)

            # Run best fit algorithm
            print(color_text(f"\nRunning best fit algorithm for time step {step}...", Fore.YELLOW))
            is_on = best_fit(active_vms, physical_machines)
        
        elif model_to_run == 'guazzone':
            deallocate_vms(active_vms)

            # Run Guazzone algorithm
            print(color_text(f"\nRunning Guazzone fit algorithm for time step {step}...", Fore.YELLOW))
            is_on = guazzone_bfd(active_vms, physical_machines, idle_power)
        
        elif model_to_run == 'shi':
            # Deallocate VMs assigned to turning on physical machines, so that they can be reallocated by the models
            deallocate_vms(active_vms)
            non_allocated_vms = get_non_allocated_vms(active_vms)

            # Run SHI algorithm
            print(color_text(f"\nRunning SHI algorithm for time step {step}...", Fore.YELLOW))
            is_on = shi_allocation(non_allocated_vms, physical_machines)
            is_on = shi_migration(active_vms, physical_machines)

        elif model_to_run == 'none':
            print(color_text(f"\nNo model to run for time step {step}...", Fore.YELLOW))

        # Calculate and update load
        cpu_load, memory_load = calculate_load(physical_machines, active_vms, TIME_STEP)
        update_physical_machines_load(physical_machines, cpu_load, memory_load)
        total_cpu_load += sum(cpu_load)
        total_memory_load += sum(memory_load)
        total_fully_on_pm += sum(is_fully_on(pm) for pm in physical_machines)

        # Sanity checks
        print("Checking everything is ok...")
        check_migration_correctness(active_vms)
        check_unique_state(active_vms)
        check_zero_load(active_vms, physical_machines)
        check_overload(active_vms, physical_machines, TIME_STEP)

        non_allocated_vms = get_non_allocated_vms(active_vms)

        if use_scaling_manager:
            print("Launching scaling manager...")
            is_on = launch_scaling_manager(active_vms, non_allocated_vms, physical_machines, idle_power, step, start_time_str, predictions, USE_WORKLOAD_PREDICTOR, WORKLOAD_PREDICTION_MODEL, WORKLOAD_PREDICTION_FILE, TIME_STEP)

        max_percentage_of_pms_on = max(max_percentage_of_pms_on, sum(is_on) / len(physical_machines))
        turned_on_pms, turned_off_pms = update_physical_machines_state(physical_machines, initial_physical_machines, is_on)

        if SAVE_VM_AND_PM_SETS:
            save_vm_sets(active_vms, terminated_vms, step, OUTPUT_FOLDER_PATH)
            save_pm_sets(physical_machines, step, OUTPUT_FOLDER_PATH)

        num_removed_vms += len(removed_vms)

        # Calculate costs and revenue
        print("Calculating costs and revenue...")
        step_total_costs, pm_energy_consumption, migration_energy_consumption = calculate_total_costs(active_vms, physical_machines, cpu_load, memory_load)
        total_revenue = calculate_total_revenue(terminated_vms)
        total_costs += step_total_costs
        total_pm_energy_consumption += pm_energy_consumption
        total_migration_energy_consumption += migration_energy_consumption
        
        # Log current allocation and physical machine load
        print("Logging useful information...")
        log_allocation(step, active_vms, old_active_vms, terminated_vms_in_step, removed_vms, turned_on_pms, turned_off_pms, physical_machines, cpu_load, memory_load, total_revenue, total_costs, log_folder_path)
        old_active_vms = deepcopy(active_vms)
        terminated_vms_in_step = []

        is_vms_terminated = False
        is_pms_turned_on = False

        # Execute time step
        print("Executing time step...")
        num_completed_migrations_in_step = execute_time_step(active_vms, terminated_vms_in_step, terminated_vms, scheduled_vms, physical_machines)
        
        num_completed_migrations += num_completed_migrations_in_step
        pms_turn_on = [pm_id for pm_id in turned_on_pms if physical_machines[pm_id]['s']['time_to_turn_on'] <= TIME_STEP] 
        
        if terminated_vms_in_step:
            is_vms_terminated = True
        
        if len(pms_turn_on) > 0:
            is_pms_turned_on = True

        # Calculate and update load
        print("Calculating and updating physical machines load...")
        cpu_load, memory_load = calculate_load(physical_machines, active_vms, TIME_STEP)
        update_physical_machines_load(physical_machines, cpu_load, memory_load)

        if step * TIME_STEP >= last_vm_arrival_time:
            if len(active_vms) == 0:
                break

    return total_revenue, total_costs, total_pm_energy_consumption, total_migration_energy_consumption, num_completed_migrations, num_removed_vms, max_percentage_of_pms_on, total_cpu_load, total_memory_load, total_fully_on_pm, step - starting_step


if __name__ == "__main__":
    if PERFORMANCE_MEASUREMENT:
        total_start_time = time.time()  # Record the start time

    initial_vms = load_virtual_machines(os.path.expanduser(INITIAL_VMS_FILE))
    initial_pms = load_physical_machines(os.path.expanduser(INITIAL_PMS_FILE))
    log_folder_path = None
    if SAVE_LOGS:
        log_folder_path = log_initial_physical_machines(initial_pms)
    if USE_REAL_DATA:
        start_time_str = get_start_time(WORKLOAD_NAME)
    load_configuration(MODEL_INPUT_FOLDER_PATH)
    save_power_function(os.path.expanduser(INITIAL_PMS_FILE), MODEL_INPUT_FOLDER_PATH)
    total_revenue, total_costs, total_pm_energy_cost, total_migration_energy_cost, num_completed_migrations, num_removed_vms, max_percentage_of_pms_on, total_cpu_load, total_memory_load, total_fully_on_pm, num_steps = simulate_time_steps(initial_vms, initial_pms, NUM_TIME_STEPS, NEW_VMS_PER_STEP, log_folder_path)
    log_final_net_profit(total_revenue, total_costs, total_pm_energy_cost, total_migration_energy_cost, num_completed_migrations, num_removed_vms, max_percentage_of_pms_on, total_cpu_load, total_memory_load, total_fully_on_pm, len(initial_pms), log_folder_path, MASTER_MODEL, USE_RANDOM_SEED, SEED_NUMBER, TIME_STEP, num_steps, USE_REAL_DATA, WORKLOAD_NAME)
    clean_up_model_input_files()

    if PERFORMANCE_MEASUREMENT:
        total_end_time = time.time()  # Record the end time
        total_execution_time = total_end_time - total_start_time  # Calculate the total execution time
        performance_log_file = os.path.join(log_folder_path, "performance_log.csv")
        with open(performance_log_file, "a", newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["Total Execution Time", total_execution_time])  # Log the total execution time
        print(f"Total execution time: {total_execution_time} seconds")

    