from copy import deepcopy
import csv
import time
import math
from collections import defaultdict
from colorama import Fore

from allocation import deallocate_vms, get_non_allocated_vms, get_non_allocated_workload, is_fully_on_next_step, run_opl_model, reallocate_vms, update_physical_machines_load, update_physical_machines_state, detect_overload
from mini import save_mini_model_input_format, parse_mini_opl_output, mini_reallocate_vms
from algorithms import backup_allocation, best_fit, guazzone_bfd, shi_allocation, shi_migration
from filter import filter_full_and_migrating_pms, filter_fragmented_pms, filter_full_pms, filter_vms_on_pms, filter_vms_on_pms_and_non_allocated
from calculate import calculate_load, calculate_load_costs, find_min_extra_time, find_migration_times, get_first_vm_arrival_time, get_last_vm_arrival_time
from pm_manager import launch_pm_manager
from utils import evaluate_piecewise_linear_function, load_new_vms, save_model_input_format, parse_opl_output, get_opl_return_code, is_opl_output_valid, color_text, save_pm_sets, save_vm_sets
from check import check_migration_correctness, check_migration_overload, check_overload, check_unique_state, check_zero_load
from log import log_performance, log_allocation, log_migrations
from vm_generator import generate_new_vms
from weights import w_load_cpu, migration, pue, energy
from config import OUTPUT_FOLDER_PATH, MODEL_INPUT_FOLDER_PATH, MODEL_OUTPUT_FOLDER_PATH, MINI_MODEL_INPUT_FOLDER_PATH, MINI_MODEL_OUTPUT_FOLDER_PATH, SAVE_VM_AND_PM_SETS

try:
    profile # type: ignore
except NameError:
    def profile(func):
        return func

    
def execute_time_step(active_vms, terminated_vms_in_step, terminated_vms, scheduled_vms, physical_machines, pms_to_turn_off_after_migration, initial_physical_machines, time_step):
    num_completed_migrations = 0
    pms_extra_time = {}
    vms_extra_time = {}

    # Update the turning on and turning off time for physical machines
    for pm in physical_machines.values():
        if pm['s']['state'] == 1 and pm['s']['time_to_turn_on'] > 0:
            pm['s']['time_to_turn_on'] = round(pm['s']['time_to_turn_on'] - time_step, 10)
            if pm['s']['time_to_turn_on'] < 0:
                pms_extra_time[pm['id']] = round(abs(pm['s']['time_to_turn_on']), 10)
                pm['s']['time_to_turn_on'] = 0.0
        if pm['s']['state'] == 0 and pm['s']['time_to_turn_off'] > 0:
            pm['s']['time_to_turn_off'] = round(pm['s']['time_to_turn_off'] - time_step, 10)
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
                
                # Allocation case
                if vm['allocation']['pm'] != -1:
                    time_step_pm = time_step
                    remaining_allocation_time = vm['allocation']['total_time'] - vm['allocation']['current_time']
                    if pm_id in pms_extra_time:
                        time_step_pm = pms_extra_time[pm_id]
                    if time_step_pm > remaining_allocation_time:
                        extra_time = round(time_step_pm - remaining_allocation_time, 10)
                    vm['allocation']['current_time'] += time_step_pm
                    # Check if the allocation is completed
                    if vm['allocation']['current_time'] >= vm['allocation']['total_time']:
                        vm['allocation']['current_time'] = vm['allocation']['total_time']
                        vm['allocation']['pm'] = -1
                        vm['run']['pm'] = pm_id
                        vm['run']['current_time'] += extra_time * pm_speed
                # Migration case
                elif vm['migration']['from_pm'] != -1 and vm['migration']['to_pm'] != -1:
                    from_pm_id = vm['migration']['from_pm']
                    from_pm = physical_machines.get(from_pm_id)
                    if not from_pm:
                        raise ValueError(f"Physical machine with ID {from_pm_id} not found")
                    from_pm_speed = from_pm['features']['speed']
                    vm['run']['current_time'] += time_step * from_pm_speed
                    remaining_time = vm['migration']['total_time'] - vm['migration']['current_time']
                    if time_step > remaining_time:
                        extra_time = round(time_step - remaining_time, 10)
                    vm['migration']['current_time'] += time_step
                    # Check if the migration is completed
                    if vm['migration']['current_time'] >= vm['migration']['total_time']:
                        vms_extra_time[vm['id']] = (from_pm_id, extra_time)
                        num_completed_migrations += 1
                        vm['migration']['current_time'] = 0.0
                        vm['migration']['from_pm'] = -1
                        vm['migration']['to_pm'] = -1
                        vm['run']['current_time'] -= vm['migration']['down_time'] * from_pm_speed
                        vm['run']['pm'] = pm_id
                # Run case
                elif vm['run']['pm'] != -1:
                    vm['run']['current_time'] += time_step * pm_speed

            # Check if the VM is terminated
            if vm['run']['current_time'] >= vm['run']['total_time']:
                del active_vms[vm_id]
                terminated_vms_in_step.append(vm)
                terminated_vms.append(vm)

    for vm_id, scheduled_vm_list in scheduled_vms.items():
        if vm_id in vms_extra_time:
            pm_id, migration_extra_time = vms_extra_time[vm_id]
            pm = physical_machines.get(pm_id)
            pm_speed = pm['features']['speed']
            for scheduled_vm in scheduled_vm_list:
                scheduled_vm['allocation']['pm'] = pm_id
                total_time = scheduled_vm['allocation']['total_time']
                current_time = scheduled_vm['allocation']['current_time']
                remaining_time = total_time - current_time
                extra_time = 0.0
                if migration_extra_time > remaining_time:
                    extra_time = round(migration_extra_time - remaining_time, 10)
                scheduled_vm['allocation']['current_time'] += migration_extra_time
                if scheduled_vm['allocation']['current_time'] >= scheduled_vm['allocation']['total_time']:
                    scheduled_vm['allocation']['current_time'] = scheduled_vm['allocation']['total_time']
                    scheduled_vm['allocation']['pm'] = -1
                    scheduled_vm['run']['pm'] = pm_id
                    scheduled_vm['run']['current_time'] += extra_time * pm_speed
                    if scheduled_vm['run']['current_time'] >= scheduled_vm['run']['total_time']:
                        del active_vms[scheduled_vm['id']]
                        terminated_vms_in_step.append(scheduled_vm)
                        terminated_vms.append(scheduled_vm)

    for pm_id in pms_to_turn_off_after_migration:
        # Turn off PM
        pm = physical_machines.get(pm_id)
        initial_pm = initial_physical_machines.get(pm_id)
        pm['s']['time_to_turn_on'] = initial_pm['s']['time_to_turn_on']
        pm['s']['state'] = 0

        # Add extra time
        min_extra_time = find_min_extra_time(vms_extra_time, pm_id)
        pm['s']['time_to_turn_off'] = round(pm['s']['time_to_turn_off'] - min_extra_time, 10)
        if pm['s']['time_to_turn_off'] < 0:
            pm['s']['time_to_turn_off'] = 0.0

    return num_completed_migrations

@profile
def calculate_total_costs(active_vms, physical_machines, pms_to_turn_off_after_migration, power_function_dict, time_step):
    cpu_load, memory_load = calculate_load_costs(physical_machines, active_vms, time_step)

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
                real_time_base = max(0, time_step - real_time_only_source - real_time_only_target - real_time_multiple_source - real_time_multiple_target - real_time_multiple_source_and_target)
            else:
                real_time_only_source = 0
                real_time_only_target = 0
                real_time_multiple_source = 0
                real_time_multiple_target = 0
                real_time_multiple_source_and_target = 0
                real_time_base = time_step
                
        elif state == 1 and time_to_turn_on > 0:
            turning_on_power = evaluate_piecewise_linear_function(power_function_dict[pm_id], 0) 
            turning_on_energy = turning_on_power * min(time_step, time_to_turn_on)

        elif state == 0 and time_to_turn_off > 0:
            turning_off_power = evaluate_piecewise_linear_function(power_function_dict[pm_id], 0) 
            turning_off_energy = turning_off_power * min(time_step, time_to_turn_off)

        if pm_id in pms_to_turn_off_after_migration:
            turning_off_power = evaluate_piecewise_linear_function(power_function_dict[pm_id], 0) 
            turning_off_energy = turning_off_power * min(real_time_base, time_to_turn_off)
            real_time_base = 0

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
def run_main_model(active_vms, physical_machines_on, scheduled_vms, pms_to_turn_off_after_migration, main_model_max_pms, step, time_step, USE_FILTER, MODEL_INPUT_FOLDER_PATH, idle_power,
                   power_function_dict, nb_points, hard_time_limit_main, hard_time_limit_mini, PERFORMANCE_MEASUREMENT, performance_log_file):
    pms_with_migrations = {}

    if USE_FILTER:
        filter_full_and_migrating_pms(active_vms, physical_machines_on)
        filter_fragmented_pms(physical_machines_on, main_model_max_pms)
        filtered_vms = filter_vms_on_pms_and_non_allocated(active_vms, physical_machines_on)

        num_vms = len(filtered_vms)
        num_pms = len(physical_machines_on)

        if num_vms > 0 and num_pms > 0:
            # Convert into model input format
            vm_model_input_file_path, pm_model_input_file_path = save_model_input_format(
                filtered_vms, physical_machines_on, step, MODEL_INPUT_FOLDER_PATH, power_function_dict, nb_points)
    else:
        num_vms = len(active_vms)
        num_pms = len(physical_machines_on)

        if num_vms > 0 and num_pms > 0:
            vm_model_input_file_path, pm_model_input_file_path = save_model_input_format(
                active_vms, physical_machines_on, step, MODEL_INPUT_FOLDER_PATH, power_function_dict, nb_points)

    if num_vms > 0 and num_pms > 0:
        # Run CPLEX model
        print(color_text(f"\nRunning main model for time step {step}...", Fore.YELLOW))
        start_time_opl = time.time()
        opl_output = run_opl_model(vm_model_input_file_path, pm_model_input_file_path, MODEL_INPUT_FOLDER_PATH, MODEL_OUTPUT_FOLDER_PATH, step, "main", hard_time_limit_main)
        end_time_opl = time.time()

        if opl_output is None:
            print(color_text(f"\nOPL main model run exceeded time limit of {hard_time_limit_main} seconds. Exiting.", Fore.RED))
            opl_output_valid = False
        else:
            if PERFORMANCE_MEASUREMENT:
                print(f"\nTime taken to run main model: {end_time_opl - start_time_opl} seconds")

            opl_return_code = get_opl_return_code(opl_output)
            opl_output_valid = is_opl_output_valid(opl_output, opl_return_code)

        if opl_output_valid:
            # Parse OPL output and reallocate VMs
            parsed_data = parse_opl_output(opl_output)
            has_to_be_on = parsed_data.get('has_to_be_on')
            new_allocation = parsed_data.get('new_allocation')
            vm_ids = parsed_data['vm_ids']
            pm_ids = parsed_data['pm_ids']
            is_allocation = parsed_data['is_allocation']
            is_migration = parsed_data['is_migration']
            is_migrating_from = parsed_data['is_migrating_from']

            reallocate_vms(active_vms, new_allocation, vm_ids, pm_ids, is_allocation, is_migration)

            for pm_index, pm_id in enumerate(pm_ids):
                for vm_index, vm_id in enumerate(vm_ids):
                    if is_migrating_from[vm_index][pm_index] == 1:
                        if has_to_be_on[pm_index] == 0:
                            if pm_id not in pms_to_turn_off_after_migration:
                                pms_to_turn_off_after_migration.append(pm_id)
                            vm = active_vms[vm_id]
                            if vm['migration']['total_time'] - vm['migration']['current_time'] >= time_step:
                                pms_to_turn_off_after_migration.remove(pm_id)
                                break
                        else:
                            pms_with_migrations[pm_id] = physical_machines_on[pm_id]
            
            vms_on_pms_with_migrations = filter_vms_on_pms(active_vms, pms_with_migrations)
            
            if pms_with_migrations:
                for vm_on_pm in vms_on_pms_with_migrations.values():
                    migrating_to_pm = vm_on_pm['migration']['to_pm']
                    if migrating_to_pm != -1:
                        pms_with_migrations[migrating_to_pm] = physical_machines_on[migrating_to_pm]
                detect_overload(pms_with_migrations, vms_on_pms_with_migrations, scheduled_vms, step, time_step, power_function_dict, nb_points)
            
            log_performance(step, "main", end_time_opl - start_time_opl, opl_output_valid, num_vms, num_pms, performance_log_file)
            
        else:
            print(color_text(f"Invalid main OPL output for time step {step}...", Fore.RED))
            log_performance(step, "main", end_time_opl - start_time_opl, opl_output_valid, num_vms, num_pms, performance_log_file)
            run_mini_model(active_vms, physical_machines_on, scheduled_vms, step, time_step, MINI_MODEL_INPUT_FOLDER_PATH,
                   MINI_MODEL_OUTPUT_FOLDER_PATH, idle_power, power_function_dict, nb_points, hard_time_limit_mini,
                   PERFORMANCE_MEASUREMENT, performance_log_file)
    else:
        print(color_text(f"\nNo available PMs for time step {step}...", Fore.YELLOW))
    
def run_mini_model(active_vms, physical_machines_on, scheduled_vms, step, time_step, MINI_MODEL_INPUT_FOLDER_PATH,
                   MINI_MODEL_OUTPUT_FOLDER_PATH, idle_power, power_function_dict, nb_points, hard_time_limit_mini,
                   PERFORMANCE_MEASUREMENT, performance_log_file):
    non_allocated_vms = get_non_allocated_workload(active_vms, scheduled_vms)

    if non_allocated_vms:
        filter_full_pms(physical_machines_on)

        if physical_machines_on:
            # Convert into model input format
            mini_vm_model_input_file_path, mini_pm_model_input_file_path = save_mini_model_input_format(
                non_allocated_vms, physical_machines_on, step, MINI_MODEL_INPUT_FOLDER_PATH, power_function_dict, nb_points)

            num_vms = len(non_allocated_vms)
            num_pms = len(physical_machines_on)

            # Run CPLEX model
            print(color_text(f"\nRunning mini model for time step {step}...", Fore.YELLOW))
            start_time_opl = time.time()
            opl_output = run_opl_model(mini_vm_model_input_file_path, mini_pm_model_input_file_path, MINI_MODEL_INPUT_FOLDER_PATH, MINI_MODEL_OUTPUT_FOLDER_PATH, step, "mini", hard_time_limit_mini)
            end_time_opl = time.time()

            if opl_output is None:
                print(color_text(f"\nOPL mini model run exceeded time limit of {hard_time_limit_mini} seconds. Exiting.", Fore.RED))
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
                log_performance(step, "mini", end_time_opl - start_time_opl, opl_output_valid, num_vms, num_pms, performance_log_file)
            else:
                print(color_text(f"\nInvalid mini OPL output for time step {step}...", Fore.RED))
                log_performance(step, "mini", end_time_opl - start_time_opl, opl_output_valid, num_vms, num_pms, performance_log_file)
                run_backup_allocation(active_vms, physical_machines_on, idle_power, step, time_step)

        else:
            print(color_text(f"\nNo available PMs for time step {step}...", Fore.YELLOW))
    else:
        print(color_text(f"\nNo VMs to allocate for time step {step}...", Fore.YELLOW))

def run_backup_allocation(active_vms, physical_machines, idle_power, step, time_step):
    non_allocated_vms = get_non_allocated_vms(active_vms)
    physical_machines_on = {pm_id: pm for pm_id, pm in physical_machines.items()
                            if pm['s']['state'] == 1 and pm['s']['time_to_turn_on'] < time_step}

    print(color_text(f"\nRunning backup allocation for time step {step}...", Fore.YELLOW))
    backup_allocation(non_allocated_vms, physical_machines_on, idle_power)

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
def simulate_time_steps(initial_vms, initial_pms, num_steps, new_vms_per_step, nb_points, power_function_dict, log_folder_path, vms_trace_file, performance_log_file, time_step, master_model, use_filter, use_real_data, print_to_console, starting_step, main_model_max_pms, pm_manager_max_vms, pm_manager_max_pms, hard_time_limit_main, hard_time_limit_mini, performance_measurement):
    if use_real_data:
        active_vms = {}
        virtual_machines_schedule = load_new_vms(vms_trace_file)  # List of VMs sorted by arrival_time
        first_vm_arrival_time = get_first_vm_arrival_time(vms_trace_file)
        last_vm_arrival_time = get_last_vm_arrival_time(vms_trace_file)
        starting_step = max(starting_step, math.ceil(first_vm_arrival_time / time_step))
    else:
        # Ensure initial_vms is a dictionary
        active_vms = initial_vms.copy()
        starting_step = starting_step

    physical_machines = deepcopy(initial_pms)
    initial_physical_machines = deepcopy(initial_pms)

    count_migrations = {}
    cpu_load = {pm_id: 0.0 for pm_id in physical_machines.keys()}
    memory_load = {pm_id: 0.0 for pm_id in physical_machines.keys()}
    turned_on_pms = []
    turned_off_pms = []
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
        writer.writerow(["Step", "Model", "Time", "Status", "Num VMs", "Num PMs"])

    print(f"Initialization done")
    for step in range(starting_step, starting_step + num_steps + 1):
        scheduled_vms = {}
        pms_to_turn_off_after_migration = []

        is_on = {pm_id: pm['s']['state'] for pm_id, pm in physical_machines.items()}

        if use_real_data:
            vms_in_step = []

            while virtual_machines_schedule and virtual_machines_schedule[0]['arrival_time'] <= step * time_step:
                vm = virtual_machines_schedule.pop(0)
                vm_id = vm['id']
                active_vms[vm_id] = vm  # Add VM to active_vms dictionary
                vms_in_step.append(vm)
            
            if len(vms_in_step) > 0:
                is_new_vms_arrival = True

        else:
            # Generate new VMs randomly
            new_vms = generate_new_vms(new_vms_per_step, initial_vm_ids)
            if len(new_vms) > 0:
                is_new_vms_arrival = True
            for vm in new_vms:
                active_vms[vm['id']] = vm
        
        # Determine which model to run
        model_to_run = 'none'

        if master_model:
            model_to_run = master_model

        if master_model in ['main', 'mini', 'hybrid', 'backup']:
            physical_machines_on = {pm_id: pm for pm_id, pm in physical_machines.items() if pm['s']['state'] == 1 and pm['s']['time_to_turn_on'] < time_step}
            
        pms_turn_on = [pm_id for pm_id in turned_on_pms if physical_machines[pm_id]['s']['time_to_turn_on'] < time_step]
        if len(pms_turn_on) > 0:
            is_pms_turned_on = True
            
        is_state_changed = is_new_vms_arrival or is_vms_terminated or is_migration_completed or is_pms_turned_on

        if not is_state_changed:
            model_to_run = 'none'

        # Call the appropriate model function
        if model_to_run == 'main':
            run_main_model(
                active_vms, physical_machines_on, scheduled_vms, pms_to_turn_off_after_migration, main_model_max_pms, 
                step, time_step, use_filter, MODEL_INPUT_FOLDER_PATH, idle_power, power_function_dict, nb_points, 
                hard_time_limit_main, hard_time_limit_mini, performance_measurement, performance_log_file)

        elif model_to_run == 'hybrid':
            run_mini_model(
                active_vms, physical_machines_on, scheduled_vms, step, time_step, MINI_MODEL_INPUT_FOLDER_PATH,
                MINI_MODEL_OUTPUT_FOLDER_PATH, idle_power, power_function_dict, nb_points, hard_time_limit_mini,
                performance_measurement, performance_log_file)
            
            run_main_model(
                active_vms, physical_machines_on, scheduled_vms, pms_to_turn_off_after_migration, main_model_max_pms,
                step, time_step, use_filter, MODEL_INPUT_FOLDER_PATH, idle_power, power_function_dict, nb_points,
                hard_time_limit_main, hard_time_limit_mini, performance_measurement, performance_log_file)

        elif model_to_run == 'mini':
            run_mini_model(
                active_vms, physical_machines_on, scheduled_vms, step, time_step, MINI_MODEL_INPUT_FOLDER_PATH,
                MINI_MODEL_OUTPUT_FOLDER_PATH, idle_power, power_function_dict, nb_points, hard_time_limit_mini,
                performance_measurement, performance_log_file)

        elif model_to_run == 'backup':
            run_backup_allocation(active_vms, physical_machines_on, idle_power, step, time_step)

        elif model_to_run == 'best_fit':
            turned_on_pms, turned_off_pms = run_best_fit(active_vms, physical_machines, initial_physical_machines, step)

        elif model_to_run == 'guazzone':
            turned_on_pms, turned_off_pms = run_guazzone(active_vms, physical_machines, initial_physical_machines, idle_power, step)

        elif model_to_run == 'shi':
            turned_on_pms, turned_off_pms = run_shi(active_vms, physical_machines, initial_physical_machines, step)

        elif model_to_run == 'none':
            print(color_text(f"\nNo model to run for time step {step}...", Fore.YELLOW))

        if master_model in ['main', 'mini', 'hybrid', 'backup']:
            # Calculate and update load
            cpu_load, memory_load = calculate_load(physical_machines, active_vms, time_step)
            update_physical_machines_load(physical_machines, cpu_load, memory_load)

            launch_pm_manager(active_vms, physical_machines, is_on, step, time_step, power_function_dict, nb_points, scheduled_vms, pms_to_turn_off_after_migration, performance_log_file, pm_manager_max_vms=pm_manager_max_vms, pm_manager_max_pms=pm_manager_max_pms)
            from allocation import get_non_allocated_workload
            for pm_id, pm in physical_machines.items():
                if pm['s']['state'] == 1 and is_on[pm_id] == 0:
                    non_allocated_vms = get_non_allocated_workload(active_vms, scheduled_vms)
                    
                    if len(non_allocated_vms) > 0:
                        for non_allocated_vm in non_allocated_vms.values():
                            if non_allocated_vm['requested']['cpu'] <= pm['capacity']['cpu'] and non_allocated_vm['requested']['memory'] <= pm['capacity']['memory']:
                                print(f"PM {pm_id} is getting turned off but VM {non_allocated_vm['id']} can be allocated on it")
            turned_on_pms, turned_off_pms = update_physical_machines_state(physical_machines, initial_physical_machines, is_on)

        if model_to_run != 'none':
            is_new_vms_arrival = False
            is_vms_terminated = False
            is_migration_completed = False
            is_pms_turned_on = False

            log_migrations(active_vms, count_migrations, terminated_vms_in_step, log_folder_path, step, starting_step + num_steps)

            # Calculate and update load
            cpu_load, memory_load = calculate_load(physical_machines, active_vms, time_step)
            update_physical_machines_load(physical_machines, cpu_load, memory_load)

        if SAVE_VM_AND_PM_SETS:
            save_vm_sets(active_vms, terminated_vms, step, OUTPUT_FOLDER_PATH)
            save_pm_sets(physical_machines, step, OUTPUT_FOLDER_PATH)

                
        # Calculate costs and revenue
        step_total_costs, pm_energy_consumption, migration_energy_consumption = calculate_total_costs(active_vms, physical_machines, pms_to_turn_off_after_migration, power_function_dict, time_step)
        total_revenue = calculate_total_revenue(terminated_vms)
        total_costs += step_total_costs
        total_pm_energy_consumption += pm_energy_consumption
        total_migration_energy_consumption += migration_energy_consumption

        # Log current allocation and physical machine load
        log_allocation(step, active_vms, terminated_vms_in_step, turned_on_pms, turned_off_pms, physical_machines, cpu_load, memory_load, total_revenue, total_costs, print_to_console, log_folder_path)
        terminated_vms_in_step = []

        # Execute time step
        num_completed_migrations_in_step = execute_time_step(active_vms, terminated_vms_in_step, terminated_vms, scheduled_vms, physical_machines, pms_to_turn_off_after_migration, initial_physical_machines, time_step)

        num_completed_migrations += num_completed_migrations_in_step
        
        if num_completed_migrations_in_step > 0:
            is_migration_completed = True
        if terminated_vms_in_step:
            is_vms_terminated = True

        # Calculate and update load
        cpu_load, memory_load = calculate_load(physical_machines, active_vms, time_step)
        update_physical_machines_load(physical_machines, cpu_load, memory_load)
        total_cpu_load += sum(cpu_load.values())
        total_memory_load += sum(memory_load.values())
        total_fully_on_pm += sum(is_fully_on_next_step(pm, time_step) for pm in physical_machines.values())
        max_percentage_of_pms_on = max(max_percentage_of_pms_on, sum(is_on.values()) / len(physical_machines) * 100)

        # Sanity checks
        check_migration_correctness(active_vms)
        check_unique_state(active_vms)
        check_zero_load(active_vms, physical_machines)
        check_overload(active_vms, physical_machines, time_step)
        
        if use_real_data and step * time_step >= last_vm_arrival_time:
            if len(active_vms) == 0:
                break

    return total_revenue, total_costs, total_pm_energy_consumption, total_migration_energy_consumption, num_completed_migrations, max_percentage_of_pms_on, total_cpu_load, total_memory_load, total_fully_on_pm, step - starting_step


