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

try:
    profile # type: ignore
except NameError:
    def profile(func):
        return func

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
MINI_MODEL_OUTPUT_FOLDER_PATH = getattr(config, 'MINI_MODEL_OUTPUT_FOLDER_PATH', None)
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
PRINT_TO_CONSOLE = getattr(config, 'PRINT_TO_CONSOLE', None)
SAVE_LOGS = getattr(config, 'SAVE_LOGS', None)
SAVE_VM_AND_PM_SETS = getattr(config, 'SAVE_VM_AND_PM_SETS', None)
MAIN_MODEL_PERIOD = getattr(config, 'MAIN_MODEL_PERIOD', None)
MINI_MODEL_PERIOD = getattr(config, 'MINI_MODEL_PERIOD', None)
MASTER_MODEL = getattr(config, 'MASTER_MODEL', None)
USE_FILTER = getattr(config, 'USE_FILTER', None)
HARD_TIME_LIMIT_MAIN = getattr(config, 'HARD_TIME_LIMIT_MAIN', None)
HARD_TIME_LIMIT_MINI = getattr(config, 'HARD_TIME_LIMIT_MINI', None)

# Set VMS_TRACE_FILE if --trace argument is provided
VMS_TRACE_FILE = args.trace if args.trace else getattr(config, 'VMS_TRACE_FILE', None)
if VMS_TRACE_FILE and not os.path.isabs(VMS_TRACE_FILE) and not os.path.exists(VMS_TRACE_FILE):
    VMS_TRACE_FILE = os.path.join(SIMULATION_INPUT_FOLDER_PATH, VMS_TRACE_FILE)

from logs import create_log_folder, log_initial_physical_machines, log_allocation, log_migrations, log_final_net_profit, log_performance
from vm_generator import generate_new_vms
from utils import load_virtual_machines, load_physical_machines, get_start_time, get_first_vm_arrival_time, get_last_vm_arrival_time, load_configuration, save_power_function, save_vm_sets, save_pm_sets, save_model_input_format, parse_opl_output, get_opl_return_code, is_opl_output_valid, count_non_valid_entries, parse_power_function, evaluate_piecewise_linear_function, calculate_load, calculate_load_costs, clean_up_model_input_files, load_new_vms, find_migration_times
from allocation import run_opl_model, reallocate_vms, update_physical_machines_state, detect_overload, get_non_allocated_vms, get_non_allocated_workload, is_fully_on_next_step, update_physical_machines_load, deallocate_vms
from mini import save_mini_model_input_format, run_mini_opl_model, parse_mini_opl_output, mini_reallocate_vms
from algorithms import best_fit, guazzone_bfd, shi_allocation, shi_migration, first_fit, worst_fit, backup_allocation
from scaling_manager import launch_scaling_manager
from workload_predictor import track_arrivals
from filter import filter_full_pms, filter_full_and_migrating_pms, filter_fragmented_pms, filter_vms_on_pms
from check import check_overload, check_unique_state, check_zero_load, check_migration_correctness, check_migration_overload
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
os.makedirs(MINI_MODEL_INPUT_FOLDER_PATH, exist_ok=True)
os.makedirs(MINI_MODEL_OUTPUT_FOLDER_PATH, exist_ok=True)


def execute_time_step(active_vms, terminated_vms_in_step, terminated_vms, scheduled_vms, physical_machines):
    num_completed_migrations = 0
    pms_extra_time = {}
    vms_extra_time = {}

    # Update the turning on and turning off time for physical machines
    for pm in physical_machines.values():
        if pm['s']['state'] == 1 and pm['s']['time_to_turn_on'] > 0:
            pm['s']['time_to_turn_on'] = round(pm['s']['time_to_turn_on'] - TIME_STEP, 10)
            if pm['s']['time_to_turn_on'] < 0:
                pms_extra_time[pm['id']] = round(abs(pm['s']['time_to_turn_on']), 10)
                pm['s']['time_to_turn_on'] = 0.0
        if pm['s']['state'] == 0 and pm['s']['time_to_turn_off'] > 0:
            pm['s']['time_to_turn_off'] = round(pm['s']['time_to_turn_off'] - TIME_STEP, 10)
            if pm['s']['time_to_turn_off'] < 0:
                pm['s']['time_to_turn_off'] = 0.0

    for vm_id in list(active_vms.keys()):
        vm = active_vms[vm_id]
        pm_id = vm['allocation']['pm'] if vm['allocation']['pm'] != -1 else (
            vm['migration']['to_pm'] if vm['migration']['to_pm'] != -1 else vm['run']['pm']
        )

        if pm_id != -1:
            pm = physical_machines.get(pm_id)
            if pm and pm['s']['state'] == 1 and pm['s']['time_to_turn_on'] == 0:
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
                    from_pm = physical_machines.get(from_pm_id)
                    if not from_pm:
                        raise ValueError(f"Physical machine with ID {from_pm_id} not found")
                    from_pm_speed = from_pm['features']['speed']
                    vm['run']['current_time'] += TIME_STEP * from_pm_speed
                    remaining_time = vm['migration']['total_time'] - vm['migration']['current_time']
                    if TIME_STEP > remaining_time:
                        extra_time = round(TIME_STEP - remaining_time, 10)
                    vm['migration']['current_time'] += TIME_STEP
                    if vm['migration']['current_time'] >= vm['migration']['total_time']:
                        num_completed_migrations += 1
                        vm['migration']['current_time'] = 0.0
                        vm['migration']['from_pm'] = -1
                        vm['migration']['to_pm'] = -1
                        vm['run']['current_time'] -= vm['migration']['down_time'] * from_pm_speed
                        vm['run']['pm'] = pm_id
                elif vm['run']['pm'] != -1:
                    vm['run']['current_time'] += TIME_STEP * pm_speed
            if vm['run']['current_time'] >= vm['run']['total_time']:
                del active_vms[vm_id]
                terminated_vms_in_step.append(vm)
                terminated_vms.append(vm)

    for vm_id, scheduled_vm_list in scheduled_vms.items():
        if vm_id in vms_extra_time:
            pm_id, migration_extra_time = vms_extra_time[vm_id]
            pm = physical_machines.get(pm_id)
            pm_speed = pm['features']['speed'] if pm else 1.0
            for scheduled_vm in scheduled_vm_list:
                scheduled_vm['allocation']['pm'] = pm_id
                remaining_time = scheduled_vm['allocation']['total_time'] - scheduled_vm['allocation']['current_time']
                extra_time = 0.0
                if migration_extra_time > remaining_time:
                    extra_time = round(migration_extra_time - remaining_time, 10)
                scheduled_vm['allocation']['current_time'] += migration_extra_time
                if scheduled_vm['allocation']['current_time'] >= scheduled_vm['allocation']['total_time']:
                    scheduled_vm['allocation']['current_time'] = scheduled_vm['allocation']['total_time']
                    scheduled_vm['allocation']['pm'] = -1
                    scheduled_vm['run']['pm'] = pm_id
                    scheduled_vm['run']['current_time'] += extra_time * pm_speed

    return num_completed_migrations

@profile
def find_migration_times(vms_from, vms_to):
    """
    Calculate migration time durations based on VMs migrating from and to a PM.

    Parameters:
    - vms_from (list): List of VM dictionaries migrating from the PM.
    - vms_to (list): List of VM dictionaries migrating to the PM.

    Returns:
    - tuple: (real_time_only_source, real_time_only_target,
              real_time_multiple_source, real_time_multiple_target,
              real_time_multiple_source_and_target)
    """
    # Extract remaining times for source and target migrations
    source_times = [vm['migration']['total_time'] - vm['migration']['current_time'] for vm in vms_from]
    target_times = [vm['migration']['total_time'] - vm['migration']['current_time'] for vm in vms_to]

    # Create a list of events: (time, type_flag)
    # type_flag: 0 for source, 1 for target
    events = [(t, 0) for t in source_times] + [(t, 1) for t in target_times]

    # Sort events by time
    events.sort()

    # Initialize counts of running migrations
    n_source_running = len(source_times)
    n_target_running = len(target_times)

    # Initialize previous time marker
    prev_time = 0

    # Initialize result variables
    real_time_only_source = 0
    real_time_only_target = 0
    real_time_multiple_source = 0
    real_time_multiple_target = 0
    real_time_multiple_source_and_target = 0

    # Iterate through each event to calculate durations
    for t, event_type in events:
        duration = t - prev_time

        # Categorize the duration based on active migrations
        if n_source_running > 0 and n_target_running == 0:
            if n_source_running == 1:
                real_time_only_source += duration
            else:
                real_time_multiple_source += duration
        elif n_source_running == 0 and n_target_running > 0:
            if n_target_running == 1:
                real_time_only_target += duration
            else:
                real_time_multiple_target += duration
        elif n_source_running > 0 and n_target_running > 0:
            real_time_multiple_source_and_target += duration
        # If both n_source_running and n_target_running are zero, do nothing

        # Update counts based on the event type
        if event_type == 0:
            n_source_running -= 1
        else:
            n_target_running -= 1

        # Update the previous time marker
        prev_time = t

    return (
        real_time_only_source,
        real_time_only_target,
        real_time_multiple_source,
        real_time_multiple_target,
        real_time_multiple_source_and_target
    )

@profile
def calculate_total_costs(active_vms, physical_machines, power_function_dict):
    cpu_load, memory_load = calculate_load_costs(physical_machines, active_vms, TIME_STEP)

    # Initialize variables
    migration_energy_consumption = {pm_id: 0.0 for pm_id in physical_machines}
    pm_energy_consumption = {pm_id: 0.0 for pm_id in physical_machines}
    
    # Preprocess migration data
    pm_migrations_from = defaultdict(list)
    pm_migrations_to = defaultdict(list)
    
    for vm in active_vms.values():
        from_pm_id = vm['migration']['from_pm']
        to_pm_id = vm['migration']['to_pm']
        if from_pm_id != -1:
            pm_migrations_from[from_pm_id].append(vm)
        if to_pm_id != -1:
            pm_migrations_to[to_pm_id].append(vm)
    
    for pm_id, pm in physical_machines.items():
        # Initialize variables for this PM
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

        state = pm['s']['state']
        time_to_turn_on = pm['s']['time_to_turn_on']
        time_to_turn_off = pm['s']['time_to_turn_off']

        if state == 1 and time_to_turn_on == 0:
            cpu_migration_overhead = 0.0
            migration_overhead_source = False
            migration_overhead_target = False
            multiple_migrations = False

            # Calculate base load power
            load = w_load_cpu * cpu_load.get(pm_id, 0.0) + (1 - w_load_cpu) * memory_load.get(pm_id, 0.0)
            power_base = evaluate_piecewise_linear_function(power_function_dict[pm_id], load)

            # Get lists of VMs migrating from/to this PM
            vms_from = pm_migrations_from.get(pm_id, [])
            vms_to = pm_migrations_to.get(pm_id, [])

            num_migrations = len(vms_from) + len(vms_to)

            # Determine migration overheads
            if num_migrations > 0:
                if num_migrations > 1:
                    cpu_migration_overhead += migration['energy']['concurrent']
                    multiple_migrations = True
                if vms_from:
                    cpu_migration_overhead += migration['energy']['cpu_overhead']['source']
                    migration_overhead_source = True
                if vms_to:
                    cpu_migration_overhead += migration['energy']['cpu_overhead']['target']
                    migration_overhead_target = True

                check_migration_overload(cpu_migration_overhead, migration_overhead_source, migration_overhead_target, multiple_migrations)
                    
                
                if migration_overhead_source:
                    power_migration_source = evaluate_piecewise_linear_function(
                        power_function_dict[pm_id], load + migration['energy']['cpu_overhead']['source'], migration_overhead_source
                    )
                if migration_overhead_target:
                    power_migration_target = evaluate_piecewise_linear_function(
                        power_function_dict[pm_id], load + migration['energy']['cpu_overhead']['target'], migration_overhead_target
                    )
                if migration_overhead_source and multiple_migrations:
                    power_migration_multiple_source = evaluate_piecewise_linear_function(
                        power_function_dict[pm_id], load + migration['energy']['concurrent'] + migration['energy']['cpu_overhead']['source'], migration_overhead_source or multiple_migrations
                    )
                if migration_overhead_target and multiple_migrations:
                    power_migration_multiple_target = evaluate_piecewise_linear_function(
                        power_function_dict[pm_id], load + migration['energy']['concurrent'] + migration['energy']['cpu_overhead']['target'], migration_overhead_target or multiple_migrations
                    )
                if migration_overhead_source and migration_overhead_target:
                    power_migration_multiple_source_and_target = evaluate_piecewise_linear_function(
                        power_function_dict[pm_id], load + migration['energy']['concurrent'] + migration['energy']['cpu_overhead']['source'] + migration['energy']['cpu_overhead']['target'], migration_overhead_source or migration_overhead_target or multiple_migrations
                    )
                    
                real_time_only_source, real_time_only_target, real_time_multiple_source, real_time_multiple_target, real_time_multiple_source_and_target = find_migration_times(vms_from, vms_to)
                real_time_base = max(0, TIME_STEP - real_time_only_source - real_time_only_target - real_time_multiple_source - real_time_multiple_target - real_time_multiple_source_and_target)
            else:
                real_time_only_source = 0
                real_time_only_target = 0
                real_time_multiple_source = 0
                real_time_multiple_target = 0
                real_time_multiple_source_and_target = 0
                real_time_base = TIME_STEP
                
        elif state == 1 and time_to_turn_on > 0:
            turning_on_power = evaluate_piecewise_linear_function(power_function_dict[pm_id], 0) 
            turning_on_energy = turning_on_power * min(TIME_STEP, time_to_turn_on)

        elif state == 0 and time_to_turn_off > 0:
            turning_off_power = evaluate_piecewise_linear_function(power_function_dict[pm_id], 0) 
            turning_off_energy = turning_off_power * min(TIME_STEP, time_to_turn_off)

        base_load_energy = real_time_base * power_base
        pm_energy_consumption[pm_id] = turning_on_energy + turning_off_energy + base_load_energy
        migration_energy_consumption[pm_id] = (
            real_time_only_source * power_migration_source +
            real_time_only_target * power_migration_target +
            real_time_multiple_source * power_migration_multiple_source +
            real_time_multiple_target * power_migration_multiple_target +
            real_time_multiple_source_and_target * power_migration_multiple_source_and_target
        )

    # Calculate total costs
    pm_costs = sum(pm_energy_consumption.values()) * energy['cost'] * pue
    migration_costs = sum(migration_energy_consumption.values()) * energy['cost'] * pue
    total_costs = pm_costs + migration_costs

    return total_costs, pm_costs, migration_costs

def calculate_total_revenue(terminated_vms):
    total_revenue = sum(vm['revenue'] for vm in terminated_vms)
    return total_revenue

@profile
def run_main_model(active_vms, physical_machines_on, scheduled_vms, step, TIME_STEP, USE_FILTER, MODEL_INPUT_FOLDER_PATH, idle_power,
                   power_function_dict, nb_points, HARD_TIME_LIMIT_MAIN, PERFORMANCE_MEASUREMENT, performance_log_file):
    
    if USE_FILTER:
        filter_full_and_migrating_pms(active_vms, physical_machines_on)
        filter_fragmented_pms(physical_machines_on)
        filtered_vms = filter_vms_on_pms(active_vms, physical_machines_on)

        # Convert into model input format
        vm_model_input_file_path, pm_model_input_file_path = save_model_input_format(
            filtered_vms, physical_machines_on, step, MODEL_INPUT_FOLDER_PATH, power_function_dict, nb_points)
    else:
        vm_model_input_file_path, pm_model_input_file_path = save_model_input_format(
            active_vms, physical_machines_on, step, MODEL_INPUT_FOLDER_PATH, power_function_dict, nb_points)

    if physical_machines_on:
        # Run CPLEX model
        print(color_text(f"\nRunning main model for time step {step}...", Fore.YELLOW))
        start_time_opl = time.time()
        opl_output = run_opl_model(vm_model_input_file_path, pm_model_input_file_path, step, HARD_TIME_LIMIT_MAIN)
        end_time_opl = time.time()

        if opl_output is None:
            print(color_text(f"\nOPL main model run exceeded time limit of {HARD_TIME_LIMIT_MAIN} seconds. Exiting.", Fore.RED))
            opl_output_valid = False
        else:
            if PERFORMANCE_MEASUREMENT:
                print(f"\nTime taken to run main model: {end_time_opl - start_time_opl} seconds")

            opl_return_code = get_opl_return_code(opl_output)
            opl_output_valid = is_opl_output_valid(opl_output, opl_return_code)

        if opl_output_valid:
            # Parse OPL output and reallocate VMs
            parsed_data = parse_opl_output(opl_output)
            new_allocation = parsed_data.get('new_allocation')
            vm_ids = parsed_data['vm_ids']
            pm_ids = parsed_data['pm_ids']
            is_allocation = parsed_data['is_allocation']
            is_migration = parsed_data['is_migration']
            reallocate_vms(active_vms, new_allocation, vm_ids, pm_ids,
                                         is_allocation, is_migration)
            cpu_load, memory_load = detect_overload(
                physical_machines_on, active_vms, scheduled_vms, step, TIME_STEP, power_function_dict, nb_points)
            
            log_performance(step, "main", end_time_opl - start_time_opl, opl_output_valid, performance_log_file)
            update_physical_machines_load(physical_machines_on, cpu_load, memory_load)
        else:
            print(color_text(f"Invalid main OPL output for time step {step}...", Fore.RED))
            log_performance(step, "main", end_time_opl - start_time_opl, opl_output_valid, performance_log_file)
            run_mini_model(active_vms, physical_machines_on, step, TIME_STEP, MINI_MODEL_INPUT_FOLDER_PATH,
                   MINI_MODEL_OUTPUT_FOLDER_PATH, idle_power, power_function_dict, nb_points, HARD_TIME_LIMIT_MINI,
                   PERFORMANCE_MEASUREMENT, performance_log_file)
    else:
        print(color_text(f"\nNo available PMs for time step {step}...", Fore.YELLOW))

def run_mini_model(active_vms, physical_machines_on, step, TIME_STEP, MINI_MODEL_INPUT_FOLDER_PATH,
                   MINI_MODEL_OUTPUT_FOLDER_PATH, idle_power, power_function_dict, nb_points, HARD_TIME_LIMIT_MINI,
                   PERFORMANCE_MEASUREMENT, performance_log_file):
    non_allocated_vms = get_non_allocated_vms(active_vms)

    if non_allocated_vms:
        filter_full_pms(physical_machines_on)

        if physical_machines_on:
            # Convert into model input format
            mini_vm_model_input_file_path, mini_pm_model_input_file_path = save_mini_model_input_format(
                non_allocated_vms, physical_machines_on, step, MINI_MODEL_INPUT_FOLDER_PATH, power_function_dict, nb_points)

            # Run CPLEX model
            print(color_text(f"\nRunning mini model for time step {step}...", Fore.YELLOW))
            start_time_opl = time.time()
            opl_output = run_mini_opl_model(mini_vm_model_input_file_path, mini_pm_model_input_file_path,
                                            MINI_MODEL_OUTPUT_FOLDER_PATH, step, HARD_TIME_LIMIT_MINI)
            end_time_opl = time.time()

            if opl_output is None:
                print(color_text(f"\nOPL mini model run exceeded time limit of {HARD_TIME_LIMIT_MINI} seconds. Exiting.", Fore.RED))
                opl_output_valid = False
            else:
                if PERFORMANCE_MEASUREMENT:
                    print(f"\nTime taken to run mini model: {end_time_opl - start_time_opl} seconds")

                opl_return_code = get_opl_return_code(opl_output)
                opl_output_valid = is_opl_output_valid(opl_output, opl_return_code)

            if opl_output_valid:
                # Parse OPL output and reallocate VMs
                parsed_data = parse_mini_opl_output(opl_output)
                partial_allocation = parsed_data.get('allocation')
                vm_ids = parsed_data['vm_ids']
                pm_ids = parsed_data['pm_ids']

                mini_reallocate_vms(vm_ids, pm_ids, partial_allocation, active_vms)
                log_performance(step, "mini", end_time_opl - start_time_opl, opl_output_valid, performance_log_file)
            else:
                print(color_text(f"\nInvalid mini OPL output for time step {step}...", Fore.RED))
                log_performance(step, "mini", end_time_opl - start_time_opl, opl_output_valid, performance_log_file)
                run_backup_allocation(active_vms, physical_machines_on, idle_power, step, TIME_STEP)

        else:
            print(color_text(f"\nNo available PMs for time step {step}...", Fore.YELLOW))
    else:
        print(color_text(f"\nNo VMs to allocate for time step {step}...", Fore.YELLOW))

def run_backup_allocation(active_vms, physical_machines, idle_power, step, TIME_STEP):
    non_allocated_vms = get_non_allocated_vms(active_vms)
    physical_machines_on = {pm_id: pm for pm_id, pm in physical_machines.items()
                            if pm['s']['state'] == 1 and pm['s']['time_to_turn_on'] < TIME_STEP}

    print(color_text(f"\nRunning backup allocation for time step {step}...", Fore.YELLOW))
    backup_allocation(non_allocated_vms, physical_machines_on, idle_power)


def run_first_fit(active_vms, physical_machines, initial_physical_machines, step):
    deallocate_vms(active_vms)

    # Run first fit algorithm
    print(color_text(f"\nRunning first fit algorithm for time step {step}...", Fore.YELLOW))
    is_on = first_fit(active_vms, physical_machines)
    turned_on_pms, turned_off_pms = update_physical_machines_state(physical_machines, initial_physical_machines, is_on)

    return turned_on_pms, turned_off_pms


def run_worst_fit(active_vms, physical_machines, initial_physical_machines, step):
    deallocate_vms(active_vms)

    # Run worst fit algorithm
    print(color_text(f"\nRunning worst fit algorithm for time step {step}...", Fore.YELLOW))
    is_on = worst_fit(active_vms, physical_machines)
    turned_on_pms, turned_off_pms = update_physical_machines_state(physical_machines, initial_physical_machines, is_on)
    return turned_on_pms, turned_off_pms


def run_best_fit(active_vms, physical_machines, initial_physical_machines, step):
    deallocate_vms(active_vms)

    # Run best fit algorithm
    print(color_text(f"\nRunning best fit algorithm for time step {step}...", Fore.YELLOW))
    is_on = best_fit(active_vms, physical_machines)
    turned_on_pms, turned_off_pms = update_physical_machines_state(physical_machines, initial_physical_machines, is_on)
    return turned_on_pms, turned_off_pms


def run_guazzone(active_vms, physical_machines, initial_physical_machines, idle_power, step):
    deallocate_vms(active_vms)

    # Run Guazzone algorithm
    print(color_text(f"\nRunning Guazzone fit algorithm for time step {step}...", Fore.YELLOW))
    is_on = guazzone_bfd(active_vms, physical_machines, idle_power)
    turned_on_pms, turned_off_pms = update_physical_machines_state(physical_machines, initial_physical_machines, is_on)
    return turned_on_pms, turned_off_pms


def run_shi(active_vms, physical_machines, initial_physical_machines, step):
    # Deallocate VMs assigned to turning on physical machines, so that they can be reallocated by the models
    deallocate_vms(active_vms)
    non_allocated_vms = get_non_allocated_vms(active_vms)

    # Run SHI algorithm
    print(color_text(f"\nRunning SHI algorithm for time step {step}...", Fore.YELLOW))
    is_on = shi_allocation(non_allocated_vms, physical_machines)
    is_on = shi_migration(active_vms, physical_machines)
    turned_on_pms, turned_off_pms = update_physical_machines_state(physical_machines, initial_physical_machines, is_on)
    return turned_on_pms, turned_off_pms


@profile
def simulate_time_steps(initial_vms, initial_pms, num_steps, new_vms_per_step, nb_points, power_function_dict, log_folder_path, performance_log_file):
    if USE_REAL_DATA:
        active_vms = {}
        virtual_machines_schedule = load_new_vms(VMS_TRACE_FILE)  # List of VMs sorted by arrival_time
        first_vm_arrival_time = get_first_vm_arrival_time(VMS_TRACE_FILE)
        last_vm_arrival_time = get_last_vm_arrival_time(VMS_TRACE_FILE)
        starting_step = max(STARTING_STEP, math.ceil(first_vm_arrival_time / TIME_STEP))
    else:
        # Ensure initial_vms is a dictionary
        active_vms = initial_vms.copy()
        starting_step = STARTING_STEP

    physical_machines = deepcopy(initial_pms)
    initial_physical_machines = deepcopy(initial_pms)

    old_active_vms = {}
    count_migrations = {}
    cpu_load = {pm_id: 0.0 for pm_id in physical_machines.keys()}
    memory_load = {pm_id: 0.0 for pm_id in physical_machines.keys()}
    terminated_vms = []
    terminated_vms_in_step = []
    is_new_vms_arrival = False
    is_vms_terminated = False
    is_migration_completed = False
    is_pms_turned_on = False
    num_completed_migrations = 0
    max_percentage_of_pms_on = 0
    total_cpu_load = 0.0
    total_memory_load = 0.0
    total_fully_on_pm = 0.0
    total_costs = 0.0
    total_pm_energy_consumption = 0.0
    total_migration_energy_consumption = 0.0

    for pm in physical_machines.values():
        if pm['s']['state'] == 0:
            pm['s']['time_to_turn_off'] = 0.0
        else:
            pm['s']['time_to_turn_on'] = 0.0

    initial_vm_ids = set(initial_vms.keys())
    pm_ids = list(physical_machines.keys())
    
    # Get idle power for each physical machine
    idle_power = {pm_id: evaluate_piecewise_linear_function(power_function_dict[pm_id], 0) for pm_id in pm_ids}
    
    with open(performance_log_file, "w", newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["Step", "Model", "Time", "Status"])

    print(f"Initialization done")
    for step in range(starting_step, starting_step + num_steps + 1):
        turned_on_pms = []
        turned_off_pms = []
        scheduled_vms = {}

        is_on = {pm_id: pm['s']['state'] for pm_id, pm in physical_machines.items()}

        if USE_REAL_DATA:
            vms_in_step = []

            while virtual_machines_schedule and virtual_machines_schedule[0]['arrival_time'] <= step * TIME_STEP:
                vm = virtual_machines_schedule.pop(0)
                vm_id = vm['id']
                active_vms[vm_id] = vm  # Add VM to active_vms dictionary
                vms_in_step.append(vm)
            
            if len(vms_in_step) > 0:
                is_new_vms_arrival = True

            if USE_WORKLOAD_PREDICTOR:
                track_arrivals(WORKLOAD_NAME, step, TIME_STEP, vms_in_step)

            predictions = defaultdict(lambda: defaultdict(dict))
        else:
            # Generate new VMs randomly
            new_vms = generate_new_vms(new_vms_per_step, initial_vm_ids)
            if len(new_vms) > 0:
                is_new_vms_arrival = True
            for vm in new_vms:
                active_vms[vm['id']] = vm
            track_arrivals(WORKLOAD_NAME, step, TIME_STEP, new_vms)
            predictions = defaultdict(lambda: defaultdict(dict))

        for vm_id in active_vms:
            scheduled_vms[vm_id] = []
        
        non_allocated_vms, total_non_allocated_cpu, total_non_allocated_memory = get_non_allocated_workload(active_vms)

        # Determine which model to run
        model_to_run = 'none'

        if MASTER_MODEL:
            model_to_run = MASTER_MODEL

        if MASTER_MODEL in ['main', 'mini', 'hybrid', 'backup']:
            launch_scaling_manager(active_vms, non_allocated_vms, total_non_allocated_cpu, total_non_allocated_memory, physical_machines, is_on, idle_power, step, start_time_str, predictions, USE_WORKLOAD_PREDICTOR, WORKLOAD_PREDICTION_MODEL, WORKLOAD_PREDICTION_FILE, TIME_STEP)
            turned_on_pms, turned_off_pms = update_physical_machines_state(physical_machines, initial_physical_machines, is_on)
            physical_machines_on = {pm_id: pm for pm_id, pm in physical_machines.items() if pm['s']['state'] == 1 and pm['s']['time_to_turn_on'] < TIME_STEP}
            
        pms_turn_on = [pm_id for pm_id in turned_on_pms if physical_machines[pm_id]['s']['time_to_turn_on'] < TIME_STEP]
        if len(pms_turn_on) > 0:
            is_pms_turned_on = True
            
        is_state_changed = is_new_vms_arrival or is_vms_terminated or is_migration_completed or is_pms_turned_on

        if not is_state_changed:
            model_to_run = 'none'

        # Call the appropriate model function
        if model_to_run == 'main':
            run_main_model(
                active_vms, physical_machines_on, scheduled_vms, step, TIME_STEP, USE_FILTER,
                MODEL_INPUT_FOLDER_PATH, idle_power, power_function_dict, nb_points, HARD_TIME_LIMIT_MAIN,
                PERFORMANCE_MEASUREMENT, performance_log_file)

        elif model_to_run == 'hybrid':
            run_mini_model(
                active_vms, physical_machines_on, step, TIME_STEP, MINI_MODEL_INPUT_FOLDER_PATH,
                MINI_MODEL_OUTPUT_FOLDER_PATH, idle_power, power_function_dict, nb_points, HARD_TIME_LIMIT_MINI,
                PERFORMANCE_MEASUREMENT, performance_log_file)
            
            run_main_model(
                active_vms, physical_machines_on, scheduled_vms, step, TIME_STEP, USE_FILTER,
                MODEL_INPUT_FOLDER_PATH, idle_power, power_function_dict, nb_points, HARD_TIME_LIMIT_MAIN,
                PERFORMANCE_MEASUREMENT, performance_log_file)

        elif model_to_run == 'mini':
            run_mini_model(
                active_vms, physical_machines_on, step, TIME_STEP, MINI_MODEL_INPUT_FOLDER_PATH,
                MINI_MODEL_OUTPUT_FOLDER_PATH, idle_power, power_function_dict, nb_points, HARD_TIME_LIMIT_MINI,
                PERFORMANCE_MEASUREMENT, performance_log_file)

        elif model_to_run == 'backup':
            run_backup_allocation(active_vms, physical_machines_on, idle_power, step, TIME_STEP)

        elif model_to_run == 'first_fit':
            turned_on_pms, turned_off_pms = run_first_fit(active_vms, physical_machines, initial_physical_machines, step)

        elif model_to_run == 'worst_fit':
            turned_on_pms, turned_off_pms = run_worst_fit(active_vms, physical_machines, initial_physical_machines, step)

        elif model_to_run == 'best_fit':
            turned_on_pms, turned_off_pms = run_best_fit(active_vms, physical_machines, initial_physical_machines, step)

        elif model_to_run == 'guazzone':
            turned_on_pms, turned_off_pms = run_guazzone(active_vms, physical_machines, initial_physical_machines, idle_power, step)

        elif model_to_run == 'shi':
            turned_on_pms, turned_off_pms = run_shi(active_vms, physical_machines, initial_physical_machines, step)

        elif model_to_run == 'none':
            print(color_text(f"\nNo model to run for time step {step}...", Fore.YELLOW))

        if model_to_run != 'none':
            is_new_vms_arrival = False
            is_vms_terminated = False
            is_migration_completed = False
            is_pms_turned_on = False

            log_migrations(active_vms, count_migrations, terminated_vms_in_step, log_folder_path, step, starting_step + num_steps)

            # Calculate and update load
            cpu_load, memory_load = calculate_load(physical_machines, active_vms, TIME_STEP)
            update_physical_machines_load(physical_machines, cpu_load, memory_load)

        if SAVE_VM_AND_PM_SETS:
            save_vm_sets(active_vms, terminated_vms, step, OUTPUT_FOLDER_PATH)
            save_pm_sets(physical_machines, step, OUTPUT_FOLDER_PATH)

        # Calculate costs and revenue
        step_total_costs, pm_energy_consumption, migration_energy_consumption = calculate_total_costs(active_vms, physical_machines, power_function_dict)
        total_revenue = calculate_total_revenue(terminated_vms)
        total_costs += step_total_costs
        total_pm_energy_consumption += pm_energy_consumption
        total_migration_energy_consumption += migration_energy_consumption

        # Log current allocation and physical machine load
        log_allocation(step, active_vms, old_active_vms, terminated_vms_in_step, turned_on_pms, turned_off_pms, physical_machines, cpu_load, memory_load, total_revenue, total_costs, PRINT_TO_CONSOLE, log_folder_path)
        old_active_vms = deepcopy(active_vms)
        terminated_vms_in_step = []

        # Execute time step
        num_completed_migrations_in_step = execute_time_step(active_vms, terminated_vms_in_step, terminated_vms, scheduled_vms, physical_machines)

        num_completed_migrations += num_completed_migrations_in_step
        
        if num_completed_migrations_in_step > 0:
            is_migration_completed = True
        if terminated_vms_in_step:
            is_vms_terminated = True

        # Calculate and update load
        cpu_load, memory_load = calculate_load(physical_machines, active_vms, TIME_STEP)
        update_physical_machines_load(physical_machines, cpu_load, memory_load)
        total_cpu_load += sum(cpu_load.values())
        total_memory_load += sum(memory_load.values())
        total_fully_on_pm += sum(is_fully_on_next_step(pm, TIME_STEP) for pm in physical_machines.values())
        max_percentage_of_pms_on = max(max_percentage_of_pms_on, sum(is_on.values()) / len(physical_machines) * 100)

        # Sanity checks
        check_migration_correctness(active_vms)
        check_unique_state(active_vms)
        check_zero_load(active_vms, physical_machines)
        check_overload(active_vms, physical_machines, TIME_STEP)
        
        if USE_REAL_DATA and step * TIME_STEP >= last_vm_arrival_time:
            if len(active_vms) == 0:
                break

    return total_revenue, total_costs, total_pm_energy_consumption, total_migration_energy_consumption, num_completed_migrations, max_percentage_of_pms_on, total_cpu_load, total_memory_load, total_fully_on_pm, step - starting_step


if __name__ == "__main__":
    if PERFORMANCE_MEASUREMENT:
        total_start_time = time.time()  # Record the start time
      
    initial_vms = load_virtual_machines(os.path.expanduser(INITIAL_VMS_FILE))
    initial_pms = load_physical_machines(os.path.expanduser(INITIAL_PMS_FILE))
    log_folder_path = create_log_folder()
    log_initial_physical_machines(initial_pms, log_folder_path)
    performance_log_file = os.path.join(log_folder_path, "performance.csv")
    if USE_REAL_DATA:
        start_time_str = get_start_time(WORKLOAD_NAME)
    load_configuration(MODEL_INPUT_FOLDER_PATH, TIME_STEP)
    load_configuration(MINI_MODEL_INPUT_FOLDER_PATH, TIME_STEP)
    save_power_function(os.path.expanduser(INITIAL_PMS_FILE))
    pm_ids = list(initial_pms.keys())
    nb_points, power_function_dict = parse_power_function(POWER_FUNCTION_FILE, pm_ids)
    total_revenue, total_costs, total_pm_energy_cost, total_migration_energy_cost, num_completed_migrations, max_percentage_of_pms_on, total_cpu_load, total_memory_load, total_fully_on_pm, num_steps = simulate_time_steps(initial_vms, initial_pms, NUM_TIME_STEPS, NEW_VMS_PER_STEP, nb_points, power_function_dict, log_folder_path, performance_log_file)
    non_valid_entries, total_entries = count_non_valid_entries(performance_log_file)
    log_final_net_profit(total_revenue, total_costs, total_pm_energy_cost, total_migration_energy_cost, num_completed_migrations, max_percentage_of_pms_on, total_cpu_load, total_memory_load, total_fully_on_pm, len(initial_pms), non_valid_entries, total_entries, log_folder_path, MASTER_MODEL, USE_RANDOM_SEED, SEED_NUMBER, TIME_STEP, num_steps, USE_REAL_DATA, WORKLOAD_NAME)
    clean_up_model_input_files()

    if PERFORMANCE_MEASUREMENT:
        total_end_time = time.time()  # Record the end time
        total_execution_time = total_end_time - total_start_time  # Calculate the total execution time
        with open(performance_log_file, "a", newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["Total Execution Time", total_execution_time])  # Log the total execution time
        print(f"Total execution time: {total_execution_time} seconds")
