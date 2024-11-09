import csv
import os
import time
import math
from copy import deepcopy
from colorama import Fore

from allocation import (
    reallocate_vms,
    migration_reallocate_vms,
    deallocate_vms,
    get_vms_on_pm,
    get_non_allocated_vms,
    get_non_allocated_workload,
    is_fully_on_next_step,
    is_allocation_for_all_vms,
    run_opl_model,
    update_physical_machines_load,
    update_physical_machines_state,
    detect_overload,
)
from mini import (
    save_mini_model_input_format,
    parse_mini_opl_output,
    mini_reallocate_vms,
)
from algorithms import (
    backup_allocation,
    first_fit,
    best_fit,
    guazzone_bfd,
    shi_allocation,
    shi_migration,
)
from filter import (
    filter_full_and_migrating_pms,
    filter_fragmented_pms,
    filter_full_pms_dict,
    filter_pms_to_turn_off_after_migration,
    filter_vms_on_pms,
    filter_vms_on_pms_and_non_allocated,
    is_pm_full,
    get_fragmented_pms_list,
    split_dict_sorted,
    sort_key_load,
)
from calculate import (
    calculate_load,
    calculate_total_costs,
    calculate_total_revenue,
    get_first_vm_arrival_time,
    get_last_vm_arrival_time,
    find_min_extra_time,
)
from pm_manager import launch_pm_manager
from utils import (
    evaluate_piecewise_linear_function,
    load_new_vms,
    save_model_input_format,
    parse_opl_output,
    get_opl_return_code,
    is_opl_output_valid,
    color_text,
    save_pm_sets,
    save_vm_sets,
)
from check import (
    check_migration_correctness,
    check_overload,
    check_unique_state,
    check_zero_load,
)
from log import log_performance, log_allocation, log_migrations
from vm_generator import generate_new_vms
from config import (
    OUTPUT_FOLDER_PATH,
    MODEL_INPUT_FOLDER_PATH,
    MODEL_OUTPUT_FOLDER_PATH,
    MINI_MODEL_INPUT_FOLDER_PATH,
    MINI_MODEL_OUTPUT_FOLDER_PATH,
    MIGRATION_MODEL_INPUT_FOLDER_PATH,
    MIGRATION_MODEL_OUTPUT_FOLDER_PATH,
    SAVE_VM_AND_PM_SETS,
)

try:
    profile  # type: ignore
except NameError:

    def profile(func):
        return func


@profile
def run_main_model(
    active_vms,
    physical_machines_on,
    scheduled_vms,
    pms_to_turn_off_after_migration,
    main_model_max_pms,
    mini_model_max_pms,
    step,
    time_step,
    USE_FILTER,
    MODEL_INPUT_FOLDER_PATH,
    idle_power,
    power_function_dict,
    nb_points,
    hard_time_limit_main,
    hard_time_limit_mini,
    performance_log_file,
    master_model,
):
    pms_with_migrations = {}

    if USE_FILTER:
        filter_full_and_migrating_pms(active_vms, physical_machines_on)
        filter_fragmented_pms(physical_machines_on, main_model_max_pms)
        filtered_vms = filter_vms_on_pms_and_non_allocated(
            active_vms, physical_machines_on
        )

        num_vms = len(filtered_vms)
        num_pms = len(physical_machines_on)

        if num_vms > 0 and num_pms > 0:
            # Convert into model input format
            vm_model_input_file_path, pm_model_input_file_path = (
                save_model_input_format(
                    filtered_vms,
                    physical_machines_on,
                    step,
                    MODEL_INPUT_FOLDER_PATH,
                    power_function_dict,
                    nb_points,
                )
            )
    else:
        num_vms = len(active_vms)
        num_pms = len(physical_machines_on)

        if num_vms > 0 and num_pms > 0:
            vm_model_input_file_path, pm_model_input_file_path = (
                save_model_input_format(
                    active_vms,
                    physical_machines_on,
                    step,
                    MODEL_INPUT_FOLDER_PATH,
                    power_function_dict,
                    nb_points,
                )
            )

    if num_vms > 0 and num_pms > 0:
        # Run CPLEX model
        print(color_text(f"\nRunning main model for time step {step}...", Fore.YELLOW))
        start_time_opl = time.time()
        opl_output = run_opl_model(
            vm_model_input_file_path,
            pm_model_input_file_path,
            MODEL_INPUT_FOLDER_PATH,
            MODEL_OUTPUT_FOLDER_PATH,
            step,
            "main",
            hard_time_limit_main,
        )
        end_time_opl = time.time()

        if opl_output is None:
            print(
                color_text(
                    f"\nOPL main model run exceeded time limit of {hard_time_limit_main} seconds. Exiting.",
                    Fore.RED,
                )
            )
            opl_output_valid = False
        else:
            print(
                f"\nTime taken to run main model: {end_time_opl - start_time_opl} seconds"
            )

            opl_return_code = get_opl_return_code(opl_output)
            opl_output_valid = is_opl_output_valid(opl_output, opl_return_code)

        if opl_output_valid:
            # Parse OPL output and reallocate VMs
            parsed_data = parse_opl_output(opl_output)
            has_to_be_on = parsed_data.get("has_to_be_on")
            new_allocation = parsed_data.get("new_allocation")
            vm_ids = parsed_data["vm_ids"]
            pm_ids = parsed_data["pm_ids"]
            is_allocation = parsed_data["is_allocation"]
            is_migration = parsed_data["is_migration"]
            is_migrating_from = parsed_data["is_migrating_from"]

            reallocate_vms(
                active_vms, new_allocation, vm_ids, pm_ids, is_allocation, is_migration
            )

            for pm_index, pm_id in enumerate(pm_ids):
                for vm_index, vm_id in enumerate(vm_ids):
                    if is_migrating_from[vm_index][pm_index] == 1:
                        if has_to_be_on[pm_index] == 0:
                            vm = active_vms[vm_id]
                            remaining_migration_time = (
                                vm["migration"]["total_time"]
                                - vm["migration"]["current_time"]
                            )
                            if (
                                remaining_migration_time
                                > pms_to_turn_off_after_migration.get(pm_id, 0)
                            ):
                                pms_to_turn_off_after_migration[pm_id] = (
                                    remaining_migration_time
                                )
                        else:
                            pms_with_migrations[pm_id] = physical_machines_on[pm_id]

            vms_on_pms_with_migrations = filter_vms_on_pms(
                active_vms, pms_with_migrations
            )

            if pms_with_migrations:
                for vm_on_pm in vms_on_pms_with_migrations.values():
                    migrating_to_pm = vm_on_pm["migration"]["to_pm"]
                    if migrating_to_pm != -1:
                        pms_with_migrations[migrating_to_pm] = physical_machines_on[
                            migrating_to_pm
                        ]
                detect_overload(
                    pms_with_migrations,
                    vms_on_pms_with_migrations,
                    scheduled_vms,
                    time_step,
                )

            log_performance(
                step,
                "main",
                end_time_opl - start_time_opl,
                opl_output_valid,
                num_vms,
                num_pms,
                performance_log_file,
            )

        else:
            print(
                color_text(f"Invalid main OPL output for time step {step}...", Fore.RED)
            )
            log_performance(
                step,
                "main",
                end_time_opl - start_time_opl,
                opl_output_valid,
                num_vms,
                num_pms,
                performance_log_file,
            )
            if master_model != "hybrid":
                launch_mini_model(
                    active_vms,
                    scheduled_vms,
                    physical_machines_on,
                    pms_to_turn_off_after_migration,
                    step,
                    time_step,
                    mini_model_max_pms,
                    idle_power,
                    power_function_dict,
                    nb_points,
                    hard_time_limit_mini,
                    performance_log_file,
                )

    else:
        print(color_text(f"\nNo available PMs for time step {step}...", Fore.YELLOW))


@profile
def run_main_model_simple(
    active_vms,
    physical_machines_on,
    scheduled_vms,
    pms_to_turn_off_after_migration,
    main_model_max_pms,
    mini_model_max_pms,
    step,
    time_step,
    USE_FILTER,
    MODEL_INPUT_FOLDER_PATH,
    idle_power,
    power_function_dict,
    nb_points,
    hard_time_limit_main,
    hard_time_limit_mini,
    performance_log_file,
    master_model,
):
    pms_with_migrations = {}

    if USE_FILTER:
        filter_full_and_migrating_pms(active_vms, physical_machines_on)
        filter_fragmented_pms(physical_machines_on, main_model_max_pms)
        filtered_vms = filter_vms_on_pms_and_non_allocated(
            active_vms, physical_machines_on
        )

        num_vms = len(filtered_vms)
        num_pms = len(physical_machines_on)

        if num_vms > 0 and num_pms > 0:
            # Convert into model input format
            vm_model_input_file_path, pm_model_input_file_path = (
                save_model_input_format(
                    filtered_vms,
                    physical_machines_on,
                    step,
                    MODEL_INPUT_FOLDER_PATH,
                    power_function_dict,
                    nb_points,
                )
            )
    else:
        num_vms = len(active_vms)
        num_pms = len(physical_machines_on)

        if num_vms > 0 and num_pms > 0:
            vm_model_input_file_path, pm_model_input_file_path = (
                save_model_input_format(
                    active_vms,
                    physical_machines_on,
                    step,
                    MODEL_INPUT_FOLDER_PATH,
                    power_function_dict,
                    nb_points,
                )
            )

    if num_vms > 0 and num_pms > 0:
        # Run CPLEX model
        print(color_text(f"\nRunning main model for time step {step}...", Fore.YELLOW))
        start_time_opl = time.time()
        opl_output = run_opl_model(
            vm_model_input_file_path,
            pm_model_input_file_path,
            MODEL_INPUT_FOLDER_PATH,
            MODEL_OUTPUT_FOLDER_PATH,
            step,
            "main_simple",
            hard_time_limit_main,
        )
        end_time_opl = time.time()

        if opl_output is None:
            print(
                color_text(
                    f"\nOPL main model run exceeded time limit of {hard_time_limit_main} seconds. Exiting.",
                    Fore.RED,
                )
            )
            opl_output_valid = False
        else:
            print(
                f"\nTime taken to run main model: {end_time_opl - start_time_opl} seconds"
            )

            opl_return_code = get_opl_return_code(opl_output)
            opl_output_valid = is_opl_output_valid(opl_output, opl_return_code)

        if opl_output_valid:
            # Parse OPL output and reallocate VMs
            parsed_data = parse_opl_output(opl_output)
            has_to_be_on = parsed_data.get("has_to_be_on")
            new_allocation = parsed_data.get("new_allocation")
            vm_ids = parsed_data["vm_ids"]
            pm_ids = parsed_data["pm_ids"]
            is_allocation = parsed_data["is_allocation"]
            is_migration = parsed_data["is_migration"]
            is_migrating_from = parsed_data["is_migrating_from"]

            reallocate_vms(
                active_vms, new_allocation, vm_ids, pm_ids, is_allocation, is_migration
            )

            for pm_index, pm_id in enumerate(pm_ids):
                for vm_index, vm_id in enumerate(vm_ids):
                    if is_migrating_from[vm_index][pm_index] == 1:
                        if has_to_be_on[pm_index] == 0:
                            vm = active_vms[vm_id]
                            remaining_migration_time = (
                                vm["migration"]["total_time"]
                                - vm["migration"]["current_time"]
                            )
                            if (
                                remaining_migration_time
                                > pms_to_turn_off_after_migration.get(pm_id, 0)
                            ):
                                pms_to_turn_off_after_migration[pm_id] = (
                                    remaining_migration_time
                                )
                        else:
                            pms_with_migrations[pm_id] = physical_machines_on[pm_id]

            vms_on_pms_with_migrations = filter_vms_on_pms(
                active_vms, pms_with_migrations
            )

            if pms_with_migrations:
                for vm_on_pm in vms_on_pms_with_migrations.values():
                    migrating_to_pm = vm_on_pm["migration"]["to_pm"]
                    if migrating_to_pm != -1:
                        pms_with_migrations[migrating_to_pm] = physical_machines_on[
                            migrating_to_pm
                        ]
                detect_overload(
                    pms_with_migrations,
                    vms_on_pms_with_migrations,
                    scheduled_vms,
                    time_step,
                )

            log_performance(
                step,
                "main_simple",
                end_time_opl - start_time_opl,
                opl_output_valid,
                num_vms,
                num_pms,
                performance_log_file,
            )

        else:
            print(
                color_text(f"Invalid main OPL output for time step {step}...", Fore.RED)
            )
            log_performance(
                step,
                "main_simple",
                end_time_opl - start_time_opl,
                opl_output_valid,
                num_vms,
                num_pms,
                performance_log_file,
            )
            if master_model != "hybrid":
                launch_mini_model(
                    active_vms,
                    scheduled_vms,
                    physical_machines_on,
                    pms_to_turn_off_after_migration,
                    step,
                    time_step,
                    mini_model_max_pms,
                    idle_power,
                    power_function_dict,
                    nb_points,
                    hard_time_limit_mini,
                    performance_log_file,
                )

    else:
        print(color_text(f"\nNo available PMs for time step {step}...", Fore.YELLOW))


@profile
def run_mini_model(
    active_vms,
    non_allocated_vms,
    physical_machines_on,
    step,
    time_step,
    mini_model_input_folder_path,
    mini_model_output_folder_path,
    idle_power,
    power_function_dict,
    nb_points,
    hard_time_limit_mini,
    performance_log_file,
):
    # Convert into model input format
    mini_vm_model_input_file_path, mini_pm_model_input_file_path = (
        save_mini_model_input_format(
            non_allocated_vms,
            physical_machines_on,
            step,
            mini_model_input_folder_path,
            power_function_dict,
            nb_points,
        )
    )

    num_vms = len(non_allocated_vms)
    num_pms = len(physical_machines_on)

    # Run CPLEX model
    print(color_text(f"\nRunning mini model for time step {step}...", Fore.YELLOW))
    start_time_opl = time.time()
    opl_output = run_opl_model(
        mini_vm_model_input_file_path,
        mini_pm_model_input_file_path,
        MINI_MODEL_INPUT_FOLDER_PATH,
        mini_model_output_folder_path,
        step,
        "mini",
        hard_time_limit_mini,
    )
    end_time_opl = time.time()

    if opl_output is None:
        print(
            color_text(
                f"\nOPL mini model run exceeded time limit of {hard_time_limit_mini} seconds. Exiting.",
                Fore.RED,
            )
        )
        opl_output_valid = False
    else:
        print(
            f"\nTime taken to run mini model: {end_time_opl - start_time_opl} seconds"
        )

        opl_return_code = get_opl_return_code(opl_output)
        opl_output_valid = is_opl_output_valid(opl_output, opl_return_code)

    if opl_output_valid:
        # Parse OPL output and reallocate VMs
        parsed_data = parse_mini_opl_output(opl_output)
        partial_allocation = parsed_data.get("allocation")
        vm_ids = parsed_data["vm_ids"]
        pm_ids = parsed_data["pm_ids"]

        mini_reallocate_vms(vm_ids, pm_ids, partial_allocation, active_vms)
        log_performance(
            step,
            "mini",
            end_time_opl - start_time_opl,
            opl_output_valid,
            num_vms,
            num_pms,
            performance_log_file,
        )
    else:
        print(
            color_text(f"\nInvalid mini OPL output for time step {step}...", Fore.RED)
        )
        log_performance(
            step,
            "mini",
            end_time_opl - start_time_opl,
            opl_output_valid,
            num_vms,
            num_pms,
            performance_log_file,
        )
        run_backup_allocation(
            active_vms, physical_machines_on, idle_power, step, time_step
        )


@profile
def launch_mini_model(
    active_vms,
    scheduled_vms,
    physical_machines_on,
    pms_to_turn_off_after_migration,
    step,
    time_step,
    mini_model_max_pms,
    idle_power,
    power_function_dict,
    nb_points,
    hard_time_limit_mini,
    performance_log_file,
):
    filter_full_pms_dict(physical_machines_on)
    filter_pms_to_turn_off_after_migration(
        physical_machines_on, pms_to_turn_off_after_migration
    )

    if physical_machines_on:
        # Determine PM subset
        if mini_model_max_pms and len(physical_machines_on) > mini_model_max_pms:
            physical_machines_on_subsets = split_dict_sorted(
                physical_machines_on, mini_model_max_pms, sort_key_load
            )
        else:
            physical_machines_on_subsets = [physical_machines_on]

        for index, pm_subset in enumerate(physical_machines_on_subsets):
            non_allocated_vms = get_non_allocated_workload(active_vms, scheduled_vms)

            if non_allocated_vms:
                mini_model_input_folder_path = os.path.join(
                    MINI_MODEL_INPUT_FOLDER_PATH, f"step_{step}/subset_{index}"
                )
                mini_model_output_folder_path = os.path.join(
                    MINI_MODEL_OUTPUT_FOLDER_PATH, f"step_{step}/subset_{index}"
                )

                os.makedirs(mini_model_input_folder_path, exist_ok=True)
                os.makedirs(mini_model_output_folder_path, exist_ok=True)

                run_mini_model(
                    active_vms,
                    non_allocated_vms,
                    pm_subset,
                    step,
                    time_step,
                    mini_model_input_folder_path,
                    mini_model_output_folder_path,
                    idle_power,
                    power_function_dict,
                    nb_points,
                    hard_time_limit_mini,
                    performance_log_file,
                )

                # Calculate and update load
                cpu_load, memory_load = calculate_load(pm_subset, active_vms, time_step)
                update_physical_machines_load(pm_subset, cpu_load, memory_load)

            else:
                break
    else:
        print(color_text(f"\nNo available PMs for time step {step}...", Fore.YELLOW))


@profile
def run_migration_model(
    non_allocated_vms,
    physical_machines_on,
    step,
    migration_model_input_folder_path,
    migration_model_output_folder_path,
    power_function_dict,
    nb_points,
):

    # Convert into model input format
    migration_vm_model_input_file_path, migration_pm_model_input_file_path = (
        save_mini_model_input_format(
            non_allocated_vms,
            physical_machines_on,
            step,
            migration_model_input_folder_path,
            power_function_dict,
            nb_points,
        )
    )

    # Run CPLEX model
    start_time_opl = time.time()
    opl_output = run_opl_model(
        migration_vm_model_input_file_path,
        migration_pm_model_input_file_path,
        MIGRATION_MODEL_INPUT_FOLDER_PATH,
        migration_model_output_folder_path,
        step,
        "migration",
    )
    end_time_opl = time.time()

    # Parse OPL output and reallocate VMs
    parsed_data = parse_mini_opl_output(opl_output)
    partial_allocation = parsed_data.get("allocation")
    vm_ids = parsed_data.get("vm_ids")
    pm_ids = parsed_data.get("pm_ids")

    if partial_allocation is None or vm_ids is None or pm_ids is None:
        raise ValueError("Invalid migration OPL output")
    else:
        return partial_allocation, vm_ids, pm_ids, end_time_opl - start_time_opl


@profile
def launch_migration_model(
    active_vms,
    physical_machines_on,
    pms_to_turn_off_after_migration,
    step,
    time_step,
    migration_model_max_fragmented_pms,
    power_function_dict,
    nb_points,
    performance_log_file,
    failed_migrations_limit=50,
):
    filter_full_and_migrating_pms(active_vms, physical_machines_on)
    fragmented_pms = get_fragmented_pms_list(
        physical_machines_on, limit=migration_model_max_fragmented_pms
    )
    if fragmented_pms:
        fragmented_pms.sort(key=sort_key_load, reverse=True)
        physical_machines_on_without_pm = physical_machines_on.copy()

        migrating_on_pms = []
        failed_migrations = 0
        print(
            color_text(
                f"\nRunning migration model for time step {step}...", Fore.YELLOW
            )
        )
        for pm in fragmented_pms:
            if not is_pm_full(pm) and pm["id"] not in migrating_on_pms:
                max_remaining_run_time = 0

                # Get the vms on the selected PM
                vms_to_allocate = get_vms_on_pm(active_vms, pm["id"])

                vms_to_allocate_list = list(vms_to_allocate.keys())
                for vm_id in vms_to_allocate_list:
                    vm = active_vms[vm_id]
                    remaining_run_time = (
                        vm["run"]["total_time"] - vm["run"]["current_time"]
                    )
                    remaining_migration_time = (
                        vm["migration"]["total_time"] - vm["migration"]["current_time"]
                    )
                    if remaining_run_time < remaining_migration_time:
                        if max_remaining_run_time < remaining_run_time:
                            max_remaining_run_time = remaining_run_time
                        del vms_to_allocate[vm["id"]]

                del physical_machines_on_without_pm[pm["id"]]

                if vms_to_allocate:
                    migration_model_input_folder_path = os.path.join(
                        MIGRATION_MODEL_INPUT_FOLDER_PATH, f"step_{step}/pm_{pm["id"]}"
                    )
                    migration_model_output_folder_path = os.path.join(
                        MIGRATION_MODEL_OUTPUT_FOLDER_PATH, f"step_{step}/pm_{pm["id"]}"
                    )

                    os.makedirs(migration_model_input_folder_path, exist_ok=True)
                    os.makedirs(migration_model_output_folder_path, exist_ok=True)

                    # Try to allocate the VMs on the other PMs
                    partial_allocation, vm_ids, pm_ids, runtime = run_migration_model(
                        vms_to_allocate,
                        physical_machines_on_without_pm,
                        step,
                        migration_model_input_folder_path,
                        migration_model_output_folder_path,
                        power_function_dict,
                        nb_points,
                    )

                    migration_success = is_allocation_for_all_vms(partial_allocation)

                    if migration_success:
                        is_migration, migrating_on_pms = migration_reallocate_vms(
                            vm_ids,
                            pm_ids,
                            partial_allocation,
                            vms_to_allocate,
                            migrating_on_pms,
                        )
                        # Calculate and update load
                        cpu_load, memory_load = calculate_load(
                            physical_machines_on, active_vms, time_step
                        )
                        update_physical_machines_load(
                            physical_machines_on, cpu_load, memory_load
                        )
                        filter_full_pms_dict(physical_machines_on_without_pm)

                        if is_migration:
                            max_remaining_migration_time = max(
                                vm["migration"]["total_time"]
                                - vm["migration"]["current_time"]
                                for vm in vms_to_allocate.values()
                                if vm["migration"]["from_pm"] == pm["id"]
                            )
                            pms_to_turn_off_after_migration[pm["id"]] = (
                                max_remaining_migration_time
                            )
                            if max_remaining_run_time > max_remaining_migration_time:
                                pms_to_turn_off_after_migration[pm["id"]] = (
                                    max_remaining_run_time
                                )
                            print(
                                f"Success: PM {pm["id"]} will be turned off after migrations are completed"
                            )
                    else:
                        failed_migrations += 1

                    log_performance(
                        step,
                        "migration",
                        runtime,
                        migration_success,
                        len(vm_ids),
                        len(pm_ids),
                        performance_log_file,
                    )
                    fragmented_pms.sort(key=sort_key_load, reverse=True)

                    if (
                        failed_migrations > failed_migrations_limit
                        or not physical_machines_on_without_pm
                    ):
                        break


def run_backup_allocation(active_vms, physical_machines, idle_power, step, time_step):
    non_allocated_vms = get_non_allocated_vms(active_vms)
    physical_machines_on = {
        pm_id: pm
        for pm_id, pm in physical_machines.items()
        if pm["s"]["state"] == 1 and pm["s"]["time_to_turn_on"] < time_step
    }

    print(
        color_text(f"\nRunning backup allocation for time step {step}...", Fore.YELLOW)
    )
    backup_allocation(non_allocated_vms, physical_machines_on, idle_power)


def run_first_fit(
    active_vms, physical_machines, initial_physical_machines, step, time_step
):
    cpu_load, memory_load = calculate_load(
        physical_machines, active_vms, time_step, True
    )
    update_physical_machines_load(physical_machines, cpu_load, memory_load)

    # Run best fit algorithm
    print(
        color_text(
            f"\nRunning first fit algorithm for time step {step}...", Fore.YELLOW
        )
    )
    is_on = first_fit(active_vms, physical_machines)
    turned_on_pms, turned_off_pms = update_physical_machines_state(
        physical_machines, initial_physical_machines, is_on
    )
    return turned_on_pms, turned_off_pms


def run_best_fit(
    active_vms, physical_machines, initial_physical_machines, step, time_step
):
    cpu_load, memory_load = calculate_load(
        physical_machines, active_vms, time_step, True
    )
    update_physical_machines_load(physical_machines, cpu_load, memory_load)

    # Run best fit algorithm
    print(
        color_text(f"\nRunning best fit algorithm for time step {step}...", Fore.YELLOW)
    )
    is_on = best_fit(active_vms, physical_machines)
    turned_on_pms, turned_off_pms = update_physical_machines_state(
        physical_machines, initial_physical_machines, is_on
    )
    return turned_on_pms, turned_off_pms


def run_guazzone(
    active_vms,
    physical_machines,
    initial_physical_machines,
    idle_power,
    step,
    time_step,
):
    cpu_load, memory_load = calculate_load(
        physical_machines, active_vms, time_step, True
    )
    update_physical_machines_load(physical_machines, cpu_load, memory_load)

    # Run Guazzone algorithm
    print(
        color_text(
            f"\nRunning Guazzone fit algorithm for time step {step}...", Fore.YELLOW
        )
    )
    is_on = guazzone_bfd(active_vms, physical_machines, idle_power)
    turned_on_pms, turned_off_pms = update_physical_machines_state(
        physical_machines, initial_physical_machines, is_on
    )
    return turned_on_pms, turned_off_pms


def run_shi(
    active_vms, physical_machines, initial_physical_machines, step, time_step, sort_key
):
    cpu_load, memory_load = calculate_load(
        physical_machines, active_vms, time_step, True
    )
    update_physical_machines_load(physical_machines, cpu_load, memory_load)
    non_allocated_vms = get_non_allocated_vms(active_vms)

    # Run SHI algorithm
    print(color_text(f"\nRunning SHI algorithm for time step {step}...", Fore.YELLOW))
    is_on = shi_allocation(non_allocated_vms, physical_machines, sort_key)
    is_on = shi_migration(active_vms, physical_machines, time_step, sort_key)
    turned_on_pms, turned_off_pms = update_physical_machines_state(
        physical_machines, initial_physical_machines, is_on
    )
    return turned_on_pms, turned_off_pms


def execute_time_step(
    active_vms,
    terminated_vms_in_step,
    terminated_vms,
    scheduled_vms,
    physical_machines,
    pms_to_turn_off_after_migration,
    initial_physical_machines,
    time_step,
):
    num_completed_migrations = 0
    pms_extra_time = {}
    vms_extra_time = {}

    # Update the turning on and turning off time for physical machines
    for pm in physical_machines.values():
        if pm["s"]["state"] == 1 and pm["s"]["time_to_turn_on"] > 0:
            pm["s"]["time_to_turn_on"] = round(
                pm["s"]["time_to_turn_on"] - time_step, 10
            )
            if pm["s"]["time_to_turn_on"] < 0:
                pms_extra_time[pm["id"]] = round(abs(pm["s"]["time_to_turn_on"]), 10)
                pm["s"]["time_to_turn_on"] = 0.0
        if pm["s"]["state"] == 0 and pm["s"]["time_to_turn_off"] > 0:
            pm["s"]["time_to_turn_off"] = round(
                pm["s"]["time_to_turn_off"] - time_step, 10
            )
            if pm["s"]["time_to_turn_off"] < 0:
                pm["s"]["time_to_turn_off"] = 0.0

    for vm_id in list(active_vms.keys()):
        vm = active_vms[vm_id]
        pm_id = (
            vm["allocation"]["pm"]
            if vm["allocation"]["pm"] != -1
            else (
                vm["migration"]["to_pm"]
                if vm["migration"]["to_pm"] != -1
                else vm["run"]["pm"]
            )
        )

        if pm_id != -1:
            pm = physical_machines.get(pm_id)
            if pm and pm["s"]["state"] == 1 and pm["s"]["time_to_turn_on"] == 0:
                pm_speed = pm["features"]["speed"]
                extra_time = 0.0

                # Allocation case
                if vm["allocation"]["pm"] != -1:
                    time_step_pm = time_step
                    remaining_allocation_time = (
                        vm["allocation"]["total_time"]
                        - vm["allocation"]["current_time"]
                    )
                    if pm_id in pms_extra_time:
                        time_step_pm = pms_extra_time[pm_id]
                    if time_step_pm > remaining_allocation_time:
                        extra_time = round(time_step_pm - remaining_allocation_time, 10)
                    vm["allocation"]["current_time"] += time_step_pm
                    # Check if the allocation is completed
                    if (
                        vm["allocation"]["current_time"]
                        >= vm["allocation"]["total_time"]
                    ):
                        vm["allocation"]["current_time"] = vm["allocation"][
                            "total_time"
                        ]
                        vm["allocation"]["pm"] = -1
                        vm["run"]["pm"] = pm_id
                        vm["run"]["current_time"] += extra_time * pm_speed
                # Migration case
                elif (
                    vm["migration"]["from_pm"] != -1 and vm["migration"]["to_pm"] != -1
                ):
                    from_pm_id = vm["migration"]["from_pm"]
                    from_pm = physical_machines.get(from_pm_id)
                    if not from_pm:
                        raise ValueError(
                            f"Physical machine with ID {from_pm_id} not found"
                        )
                    from_pm_speed = from_pm["features"]["speed"]
                    vm["run"]["current_time"] += time_step * from_pm_speed
                    remaining_time = (
                        vm["migration"]["total_time"] - vm["migration"]["current_time"]
                    )
                    if time_step > remaining_time:
                        extra_time = round(time_step - remaining_time, 10)
                    vm["migration"]["current_time"] += time_step
                    # Check if the migration is completed
                    if vm["migration"]["current_time"] >= vm["migration"]["total_time"]:
                        vms_extra_time[vm["id"]] = (from_pm_id, extra_time)
                        num_completed_migrations += 1
                        vm["migration"]["current_time"] = 0.0
                        vm["migration"]["from_pm"] = -1
                        vm["migration"]["to_pm"] = -1
                        vm["run"]["current_time"] -= (
                            vm["migration"]["down_time"] * from_pm_speed
                        )
                        vm["run"]["pm"] = pm_id
                # Run case
                elif vm["run"]["pm"] != -1:
                    vm["run"]["current_time"] += time_step * pm_speed

            # Check if the VM is terminated
            if vm["run"]["current_time"] >= vm["run"]["total_time"]:
                del active_vms[vm_id]
                terminated_vms_in_step.append(vm)
                terminated_vms.append(vm)

    for vm_id, scheduled_vm_list in scheduled_vms.items():
        if vm_id in vms_extra_time:
            pm_id, migration_extra_time = vms_extra_time[vm_id]
            pm = physical_machines.get(pm_id)
            pm_speed = pm["features"]["speed"]
            for scheduled_vm in scheduled_vm_list:
                scheduled_vm["allocation"]["pm"] = pm_id
                total_time = scheduled_vm["allocation"]["total_time"]
                current_time = scheduled_vm["allocation"]["current_time"]
                remaining_time = total_time - current_time
                extra_time = 0.0
                if migration_extra_time > remaining_time:
                    extra_time = round(migration_extra_time - remaining_time, 10)
                scheduled_vm["allocation"]["current_time"] += migration_extra_time
                if (
                    scheduled_vm["allocation"]["current_time"]
                    >= scheduled_vm["allocation"]["total_time"]
                ):
                    scheduled_vm["allocation"]["current_time"] = scheduled_vm[
                        "allocation"
                    ]["total_time"]
                    scheduled_vm["allocation"]["pm"] = -1
                    scheduled_vm["run"]["pm"] = pm_id
                    scheduled_vm["run"]["current_time"] += extra_time * pm_speed
                    if (
                        scheduled_vm["run"]["current_time"]
                        >= scheduled_vm["run"]["total_time"]
                    ):
                        del active_vms[scheduled_vm["id"]]
                        terminated_vms_in_step.append(scheduled_vm)
                        terminated_vms.append(scheduled_vm)

    pms_to_turn_off_list = list(pms_to_turn_off_after_migration.items())
    for pm_id, remaining_migration_time in pms_to_turn_off_list:
        if remaining_migration_time < time_step:
            # Turn off PM
            pm = physical_machines.get(pm_id)
            initial_pm = initial_physical_machines.get(pm_id)
            pm["s"]["time_to_turn_on"] = initial_pm["s"]["time_to_turn_on"]
            pm["s"]["state"] = 0
            del pms_to_turn_off_after_migration[pm_id]

            # Add extra time
            extra_time = time_step - remaining_migration_time
            pm["s"]["time_to_turn_off"] = round(
                pm["s"]["time_to_turn_off"] - extra_time, 10
            )
            if pm["s"]["time_to_turn_off"] < 0:
                pm["s"]["time_to_turn_off"] = 0.0
        else:
            pms_to_turn_off_after_migration[pm_id] = (
                remaining_migration_time - time_step
            )

    return num_completed_migrations


@profile
def simulate_time_steps(
    initial_vms,
    initial_pms,
    num_steps,
    new_vms_per_step,
    nb_points,
    power_function_dict,
    log_folder_path,
    vms_trace_file,
    performance_log_file,
    time_step,
    master_model,
    use_filter,
    use_real_data,
    print_to_console,
    starting_step,
    main_model_max_pms,
    mini_model_max_pms,
    migration_model_max_fragmented_pms,
    failed_migrations_limit,
    pm_manager_max_pms,
    hard_time_limit_main,
    hard_time_limit_mini,
    new_vms_pattern,
):

    if use_real_data:
        active_vms = {}
        virtual_machines_schedule = load_new_vms(
            vms_trace_file
        )  # List of VMs sorted by arrival_time
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
    pms_to_turn_off_after_migration = {}
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
        if pm["s"]["state"] == 0:
            pm["s"]["time_to_turn_off"] = 0.0
        else:
            pm["s"]["time_to_turn_on"] = 0.0

    initial_vm_ids = set(initial_vms.keys())
    pm_ids = list(physical_machines.keys())

    # Get idle power for each physical machine
    idle_power = {
        pm_id: evaluate_piecewise_linear_function(power_function_dict[pm_id], 0)
        for pm_id in pm_ids
    }

    with open(performance_log_file, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Step", "Model", "Time", "Status", "Num VMs", "Num PMs"])

    print(f"Initialization done")
    for step in range(starting_step, starting_step + num_steps + 1):
        scheduled_vms = {}

        is_on = {pm_id: pm["s"]["state"] for pm_id, pm in physical_machines.items()}

        if use_real_data:
            vms_in_step = []

            while (
                virtual_machines_schedule
                and virtual_machines_schedule[0]["arrival_time"] <= step * time_step
            ):
                vm = virtual_machines_schedule.pop(0)
                vm_id = vm["id"]
                active_vms[vm_id] = vm  # Add VM to active_vms dictionary
                vms_in_step.append(vm)

            if len(vms_in_step) > 0:
                is_new_vms_arrival = True

        else:
            # Generate new VMs randomly
            new_vms = generate_new_vms(
                new_vms_per_step, initial_vm_ids, pattern=new_vms_pattern, step=step
            )
            if len(new_vms) > 0:
                is_new_vms_arrival = True
            for vm in new_vms:
                active_vms[vm["id"]] = vm

        # Determine which model to run
        model_to_run = "none"

        if master_model:
            model_to_run = master_model

        if master_model in [
            "main",
            "main_simple",
            "mini",
            "hybrid",
            "compound",
            "backup",
        ]:
            physical_machines_on = {
                pm_id: pm
                for pm_id, pm in physical_machines.items()
                if pm["s"]["state"] == 1 and pm["s"]["time_to_turn_on"] < time_step
            }

        pms_turn_on = [
            pm_id
            for pm_id in turned_on_pms
            if physical_machines[pm_id]["s"]["time_to_turn_on"] < time_step
        ]
        if len(pms_turn_on) > 0:
            is_pms_turned_on = True

        is_state_changed = (
            is_new_vms_arrival
            or is_vms_terminated
            or is_migration_completed
            or is_pms_turned_on
        )

        if not is_state_changed:
            model_to_run = "none"

        # Call the appropriate model function
        if model_to_run == "main":
            run_main_model(
                active_vms,
                physical_machines_on,
                scheduled_vms,
                pms_to_turn_off_after_migration,
                main_model_max_pms,
                mini_model_max_pms,
                step,
                time_step,
                use_filter,
                MODEL_INPUT_FOLDER_PATH,
                idle_power,
                power_function_dict,
                nb_points,
                hard_time_limit_main,
                hard_time_limit_mini,
                performance_log_file,
                master_model,
            )

        elif model_to_run == "main_simple":
            run_main_model_simple(
                active_vms,
                physical_machines_on,
                scheduled_vms,
                pms_to_turn_off_after_migration,
                main_model_max_pms,
                mini_model_max_pms,
                step,
                time_step,
                use_filter,
                MODEL_INPUT_FOLDER_PATH,
                idle_power,
                power_function_dict,
                nb_points,
                hard_time_limit_main,
                hard_time_limit_mini,
                performance_log_file,
                master_model,
            )

        elif model_to_run == "hybrid":
            launch_mini_model(
                active_vms,
                scheduled_vms,
                physical_machines_on,
                pms_to_turn_off_after_migration,
                step,
                time_step,
                mini_model_max_pms,
                idle_power,
                power_function_dict,
                nb_points,
                hard_time_limit_mini,
                performance_log_file,
            )

            run_main_model(
                active_vms,
                physical_machines_on,
                scheduled_vms,
                pms_to_turn_off_after_migration,
                main_model_max_pms,
                mini_model_max_pms,
                step,
                time_step,
                use_filter,
                MODEL_INPUT_FOLDER_PATH,
                idle_power,
                power_function_dict,
                nb_points,
                hard_time_limit_main,
                hard_time_limit_mini,
                performance_log_file,
                master_model,
            )

        elif model_to_run == "compound":
            launch_mini_model(
                active_vms,
                scheduled_vms,
                physical_machines_on,
                pms_to_turn_off_after_migration,
                step,
                time_step,
                mini_model_max_pms,
                idle_power,
                power_function_dict,
                nb_points,
                hard_time_limit_mini,
                performance_log_file,
            )

            launch_migration_model(
                active_vms,
                physical_machines_on,
                pms_to_turn_off_after_migration,
                step,
                time_step,
                migration_model_max_fragmented_pms,
                power_function_dict,
                nb_points,
                performance_log_file,
                failed_migrations_limit,
            )

        elif model_to_run == "mini":
            launch_mini_model(
                active_vms,
                scheduled_vms,
                physical_machines_on,
                pms_to_turn_off_after_migration,
                step,
                time_step,
                mini_model_max_pms,
                idle_power,
                power_function_dict,
                nb_points,
                hard_time_limit_mini,
                performance_log_file,
            )

        elif model_to_run == "backup":
            run_backup_allocation(
                active_vms, physical_machines_on, idle_power, step, time_step
            )

        elif model_to_run == "best_fit":
            turned_on_pms, turned_off_pms = run_best_fit(
                active_vms,
                physical_machines,
                initial_physical_machines,
                step,
                time_step,
            )

        elif model_to_run == "first_fit":
            turned_on_pms, turned_off_pms = run_first_fit(
                active_vms,
                physical_machines,
                initial_physical_machines,
                step,
                time_step,
            )

        elif model_to_run == "guazzone":
            turned_on_pms, turned_off_pms = run_guazzone(
                active_vms,
                physical_machines,
                initial_physical_machines,
                idle_power,
                step,
                time_step,
            )

        elif model_to_run == "shi_OM":
            turned_on_pms, turned_off_pms = run_shi(
                active_vms,
                physical_machines,
                initial_physical_machines,
                step,
                time_step,
                "OccupiedMagnitude",
            )

        elif model_to_run == "shi_AC":
            turned_on_pms, turned_off_pms = run_shi(
                active_vms,
                physical_machines,
                initial_physical_machines,
                step,
                time_step,
                "AbsoluteCapacity",
            )

        elif model_to_run == "shi_PU":
            turned_on_pms, turned_off_pms = run_shi(
                active_vms,
                physical_machines,
                initial_physical_machines,
                step,
                time_step,
                "PercentageUtil",
            )

        elif model_to_run == "none":
            print(color_text(f"\nNo model to run for time step {step}...", Fore.YELLOW))

        if master_model in [
            "main",
            "main_simple",
            "mini",
            "hybrid",
            "compound",
            "backup",
        ]:
            # Calculate and update load
            cpu_load, memory_load = calculate_load(
                physical_machines, active_vms, time_step
            )
            update_physical_machines_load(physical_machines, cpu_load, memory_load)

            launch_pm_manager(
                active_vms,
                physical_machines,
                is_on,
                step,
                time_step,
                power_function_dict,
                nb_points,
                scheduled_vms,
                pms_to_turn_off_after_migration,
                performance_log_file,
                pm_manager_max_pms=pm_manager_max_pms,
            )
            turned_on_pms, turned_off_pms = update_physical_machines_state(
                physical_machines, initial_physical_machines, is_on
            )

        if model_to_run != "none":
            is_new_vms_arrival = False
            is_vms_terminated = False
            is_migration_completed = False
            is_pms_turned_on = False

            log_migrations(
                active_vms,
                count_migrations,
                terminated_vms_in_step,
                log_folder_path,
                step,
                starting_step + num_steps,
            )

            # Calculate and update load
            cpu_load, memory_load = calculate_load(
                physical_machines, active_vms, time_step
            )
            update_physical_machines_load(physical_machines, cpu_load, memory_load)

        if SAVE_VM_AND_PM_SETS:
            save_vm_sets(active_vms, terminated_vms, step, OUTPUT_FOLDER_PATH)
            save_pm_sets(physical_machines, step, OUTPUT_FOLDER_PATH)

        # Calculate costs and revenue
        step_total_costs, pm_energy_consumption, migration_energy_consumption = (
            calculate_total_costs(
                active_vms,
                physical_machines,
                pms_to_turn_off_after_migration,
                power_function_dict,
                time_step,
            )
        )
        total_revenue = calculate_total_revenue(terminated_vms)
        total_costs += step_total_costs
        total_pm_energy_consumption += pm_energy_consumption
        total_migration_energy_consumption += migration_energy_consumption

        # Log current allocation and physical machine load
        log_allocation(
            step,
            active_vms,
            terminated_vms_in_step,
            turned_on_pms,
            turned_off_pms,
            physical_machines,
            cpu_load,
            memory_load,
            total_revenue,
            total_costs,
            print_to_console,
            log_folder_path,
        )
        terminated_vms_in_step = []

        # Execute time step
        num_completed_migrations_in_step = execute_time_step(
            active_vms,
            terminated_vms_in_step,
            terminated_vms,
            scheduled_vms,
            physical_machines,
            pms_to_turn_off_after_migration,
            initial_physical_machines,
            time_step,
        )

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
        total_fully_on_pm += sum(
            is_fully_on_next_step(pm, time_step) for pm in physical_machines.values()
        )
        max_percentage_of_pms_on = max(
            max_percentage_of_pms_on, sum(is_on.values()) / len(physical_machines) * 100
        )

        # Sanity checks
        check_migration_correctness(active_vms)
        check_unique_state(active_vms)
        check_zero_load(active_vms, physical_machines)
        check_overload(active_vms, physical_machines, time_step)

        if use_real_data and step * time_step >= last_vm_arrival_time:
            if len(active_vms) == 0:
                break

    return (
        total_revenue,
        total_costs,
        total_pm_energy_consumption,
        total_migration_energy_consumption,
        num_completed_migrations,
        max_percentage_of_pms_on,
        total_cpu_load,
        total_memory_load,
        total_fully_on_pm,
        step - starting_step,
    )
