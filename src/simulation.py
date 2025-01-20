import csv
import math
import os
import time
from copy import deepcopy

from colorama import Fore

from algorithms import (
    backup_allocation,
    best_fit,
    first_fit,
    load_balancer,
    shi_allocation,
    shi_migration,
    lago,
)
from allocation import (
    detect_overload,
    get_non_allocated_vms,
    get_non_allocated_workload,
    get_vms_on_pm,
    get_vms_on_pms,
    is_allocation_for_all_vms,
    is_fully_on_next_step,
    migration_reallocate_vms,
    reallocate_vms,
    run_opl_model,
    update_physical_machines_load,
    update_physical_machines_state,
)
from calculate import (
    calculate_load,
    calculate_total_costs,
    calculate_total_revenue,
    get_first_vm_arrival_time,
    get_last_vm_arrival_time,
)
from check import (
    check_migration_correctness,
    check_overload,
    check_unique_state,
    check_zero_load,
)
from config import (
    MIGRATION_MODEL_INPUT_FOLDER_PATH,
    MIGRATION_MODEL_OUTPUT_FOLDER_PATH,
    MICRO_MODEL_INPUT_FOLDER_PATH,
    MICRO_MODEL_OUTPUT_FOLDER_PATH,
    MACRO_MODEL_INPUT_FOLDER_PATH,
    MACRO_MODEL_OUTPUT_FOLDER_PATH,
    OUTPUT_FOLDER_PATH,
    SAVE_VM_AND_PM_SETS,
)
from data_generator import generate_new_vms
from filter import (
    filter_fragmented_pms,
    filter_full_and_migrating_pms,
    filter_full_pms_dict,
    filter_migrating_pms,
    filter_pms_to_turn_off_after_migration,
    filter_vms_on_pms,
    filter_vms_on_pms_and_non_allocated,
    get_fragmented_pms_list,
    is_pm_full,
    sort_key_load,
    sort_key_energy_intensity_load,
    split_dict_sorted,
    split_dict_unsorted,
)
from log import log_allocation, log_performance, log_vm_execution_time
from micro import (
    micro_reallocate_vms,
    parse_micro_opl_output,
    save_micro_model_input_format,
)
from pm_manager import launch_pm_manager
from utils import (
    color_text,
    evaluate_piecewise_linear_function,
    get_opl_return_code,
    is_opl_output_valid,
    load_new_vms,
    parse_opl_output,
    save_model_input_format,
    save_pm_sets,
    save_vm_sets,
)
from weights import w_load_cpu, EPSILON

try:
    profile  # type: ignore
except NameError:

    def profile(func):
        return func


@profile
def run_macro_model(
    vms,
    highest_fragmentation_pms,
    physical_machines,
    scheduled_vms,
    pms_to_turn_off_after_migration,
    micro_model_max_pms,
    micro_model_max_vms,
    step,
    time_step,
    MACRO_MODEL_INPUT_FOLDER_PATH,
    idle_power,
    energy_intensity_database,
    nb_points,
    hard_time_limit_macro,
    hard_time_limit_micro,
    performance_log_file,
    master_model,
):
    pms_with_migrations = {}

    num_vms = len(vms)
    num_pms = len(highest_fragmentation_pms)

    if num_vms > 0 and num_pms > 0:
        # Convert into model input format
        vm_model_input_file_path, pm_model_input_file_path = save_model_input_format(
            vms,
            highest_fragmentation_pms,
            step,
            MACRO_MODEL_INPUT_FOLDER_PATH,
            energy_intensity_database,
            nb_points,
        )

        # Run CPLEX model
        print(color_text(f"\nRunning maxi model for time step {step}...", Fore.YELLOW))
        start_time_opl = time.time()
        opl_output = run_opl_model(
            vm_model_input_file_path,
            pm_model_input_file_path,
            MACRO_MODEL_INPUT_FOLDER_PATH,
            MACRO_MODEL_OUTPUT_FOLDER_PATH,
            step,
            "macro",
            hard_time_limit_macro,
        )
        end_time_opl = time.time()

        if opl_output is None:
            print(
                color_text(
                    f"\nOPL macro model run exceeded time limit of {hard_time_limit_macro} seconds. Exiting.",
                    Fore.RED,
                )
            )
            opl_output_valid = False
        else:
            print(
                f"\nTime taken to run macro model: {end_time_opl - start_time_opl} seconds"
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
                vms, new_allocation, vm_ids, pm_ids, is_allocation, is_migration
            )

            for pm_index, pm_id in enumerate(pm_ids):
                for vm_index, vm_id in enumerate(vm_ids):
                    if is_migrating_from[vm_index][pm_index] == 1:
                        if has_to_be_on[pm_index] == 0:
                            vm = vms[vm_id]
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
                            pms_with_migrations[pm_id] = physical_machines[pm_id]

            vms_on_pms_with_migrations = filter_vms_on_pms(vms, pms_with_migrations)

            if pms_with_migrations:
                for vm_on_pm in vms_on_pms_with_migrations.values():
                    migrating_to_pm = vm_on_pm["migration"]["to_pm"]
                    if migrating_to_pm != -1:
                        pms_with_migrations[migrating_to_pm] = physical_machines[
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
                "macro",
                end_time_opl - start_time_opl,
                "",
                num_vms,
                num_pms,
                performance_log_file,
            )

        else:
            print(
                color_text(f"Invalid macro OPL output for time step {step}...", Fore.RED)
            )
            log_performance(
                step,
                "macro",
                end_time_opl - start_time_opl,
                "not valid",
                num_vms,
                num_pms,
                performance_log_file,
            )
            if master_model != "hybrid":
                non_allocated_vms = get_non_allocated_workload(vms, scheduled_vms)

                launch_micro_model(
                    vms,
                    non_allocated_vms,
                    scheduled_vms,
                    highest_fragmentation_pms,
                    pms_to_turn_off_after_migration,
                    step,
                    time_step,
                    micro_model_max_pms,
                    micro_model_max_vms,
                    idle_power,
                    energy_intensity_database,
                    nb_points,
                    hard_time_limit_micro,
                    performance_log_file,
                )

    else:
        print(color_text(f"\nNo available PMs for time step {step}...", Fore.YELLOW))


def launch_macro_model(
    active_vms,
    scheduled_vms,
    physical_machines_on,
    pms_to_turn_off_after_migration,
    macro_model_max_subsets,
    macro_model_max_pms,
    micro_model_max_pms,
    micro_model_max_vms,
    idle_power,
    step,
    time_step,
    energy_intensity_database,
    nb_points,
    hard_time_limit_macro,
    hard_time_limit_micro,
    performance_log_file,
    master_model,
):
    physical_machines = physical_machines_on.copy()

    for _ in range(macro_model_max_subsets):
        if physical_machines_on:
            filter_full_and_migrating_pms(active_vms, physical_machines_on)
            if physical_machines_on:
                highest_fragmentation_pms = filter_fragmented_pms(
                    physical_machines_on, macro_model_max_pms
                )
                filtered_vms = filter_vms_on_pms_and_non_allocated(
                    active_vms, highest_fragmentation_pms, scheduled_vms
                )
                if filtered_vms:
                    run_macro_model(
                        filtered_vms,
                        highest_fragmentation_pms,
                        physical_machines,
                        scheduled_vms,
                        pms_to_turn_off_after_migration,
                        micro_model_max_pms,
                        micro_model_max_vms,
                        step,
                        time_step,
                        MACRO_MODEL_INPUT_FOLDER_PATH,
                        idle_power,
                        energy_intensity_database,
                        nb_points,
                        hard_time_limit_macro,
                        hard_time_limit_micro,
                        performance_log_file,
                        master_model,
                    )
                for pm_id in list(highest_fragmentation_pms.keys()):
                    del physical_machines_on[pm_id]
            else:
                break


@profile
def run_micro_model(
    active_vms,
    non_allocated_vms,
    physical_machines_on,
    step,
    time_step,
    micro_model_input_folder_path,
    micro_model_output_folder_path,
    idle_power,
    energy_intensity_database,
    nb_points,
    hard_time_limit_micro,
    performance_log_file,
):
    # Convert into model input format
    micro_vm_model_input_file_path, micro_pm_model_input_file_path = (
        save_micro_model_input_format(
            non_allocated_vms,
            physical_machines_on,
            step,
            micro_model_input_folder_path,
            energy_intensity_database,
            nb_points,
        )
    )

    num_vms = len(non_allocated_vms)
    num_pms = len(physical_machines_on)

    # Run CPLEX model
    print(color_text(f"\nRunning micro model for time step {step}...", Fore.YELLOW))
    start_time_opl = time.time()
    opl_output = run_opl_model(
        micro_vm_model_input_file_path,
        micro_pm_model_input_file_path,
        MICRO_MODEL_INPUT_FOLDER_PATH,
        micro_model_output_folder_path,
        step,
        "micro",
        hard_time_limit_micro,
    )
    end_time_opl = time.time()

    if opl_output is None:
        print(
            color_text(
                f"\nOPL micro model run exceeded time limit of {hard_time_limit_micro} seconds. Exiting.",
                Fore.RED,
            )
        )
        opl_output_valid = False
    else:
        print(
            f"\nTime taken to run micro model: {end_time_opl - start_time_opl} seconds"
        )

        opl_return_code = get_opl_return_code(opl_output)
        opl_output_valid = is_opl_output_valid(opl_output, opl_return_code)

    if opl_output_valid:
        # Parse OPL output and reallocate VMs
        parsed_data = parse_micro_opl_output(opl_output)
        partial_allocation = parsed_data.get("allocation")
        vm_ids = parsed_data["vm_ids"]
        pm_ids = parsed_data["pm_ids"]

        micro_reallocate_vms(vm_ids, pm_ids, partial_allocation, active_vms)
        log_performance(
            step,
            "micro",
            end_time_opl - start_time_opl,
            "",
            num_vms,
            num_pms,
            performance_log_file,
        )
    else:
        print(
            color_text(f"\nInvalid micro OPL output for time step {step}...", Fore.RED)
        )
        log_performance(
            step,
            "micro",
            end_time_opl - start_time_opl,
            "not valid",
            num_vms,
            num_pms,
            performance_log_file,
        )
        run_backup_allocation(
            active_vms, physical_machines_on, idle_power, step, time_step
        )


@profile
def launch_micro_model(
    active_vms,
    non_allocated_vms,
    scheduled_vms,
    physical_machines_on,
    pms_to_turn_off_after_migration,
    step,
    time_step,
    micro_model_max_pms,
    micro_model_max_vms,
    idle_power,
    energy_intensity_database,
    nb_points,
    hard_time_limit_micro,
    performance_log_file,
):
    if non_allocated_vms:
        if micro_model_max_vms and len(non_allocated_vms) > micro_model_max_vms:
            non_allocated_vms_subsets = split_dict_unsorted(
                non_allocated_vms, micro_model_max_vms
            )
        else:
            non_allocated_vms_subsets = [non_allocated_vms]

        for non_allocated_vms_subset in non_allocated_vms_subsets:
            filter_full_pms_dict(physical_machines_on)
            filter_pms_to_turn_off_after_migration(
                physical_machines_on, pms_to_turn_off_after_migration
            )

            if physical_machines_on:
                # Determine PM subset
                if (
                    micro_model_max_pms
                    and len(physical_machines_on) > micro_model_max_pms
                ):
                    physical_machines_on_subsets = split_dict_sorted(
                        physical_machines_on,
                        micro_model_max_pms,
                        sort_key_energy_intensity_load,
                        energy_intensity_database,
                    )
                else:
                    physical_machines_on_subsets = [physical_machines_on]

                for index, pm_subset in enumerate(physical_machines_on_subsets):
                    if index != 0:
                        non_allocated_vms = get_non_allocated_workload(
                            non_allocated_vms_subset, scheduled_vms
                        )
                    else:
                        non_allocated_vms = non_allocated_vms_subset

                    if non_allocated_vms:
                        micro_model_input_folder_path = os.path.join(
                            MICRO_MODEL_INPUT_FOLDER_PATH, f"step_{step}/subset_{index}"
                        )
                        micro_model_output_folder_path = os.path.join(
                            MICRO_MODEL_OUTPUT_FOLDER_PATH, f"step_{step}/subset_{index}"
                        )

                        os.makedirs(micro_model_input_folder_path, exist_ok=True)
                        os.makedirs(micro_model_output_folder_path, exist_ok=True)

                        run_micro_model(
                            active_vms,
                            non_allocated_vms,
                            pm_subset,
                            step,
                            time_step,
                            micro_model_input_folder_path,
                            micro_model_output_folder_path,
                            idle_power,
                            energy_intensity_database,
                            nb_points,
                            hard_time_limit_micro,
                            performance_log_file,
                        )

                        # Calculate and update load
                        cpu_load, memory_load = calculate_load(
                            pm_subset, active_vms, time_step
                        )
                        update_physical_machines_load(pm_subset, cpu_load, memory_load)

                    else:
                        break
            else:
                print(
                    color_text(
                        f"\nNo available PMs for time step {step}...", Fore.YELLOW
                    )
                )


@profile
def run_migration_model(
    non_allocated_vms,
    physical_machines_on,
    step,
    migration_model_input_folder_path,
    migration_model_output_folder_path,
    energy_intensity_database,
    nb_points,
    hard_time_limit_migration,
):

    # Convert into model input format
    migration_vm_model_input_file_path, migration_pm_model_input_file_path = (
        save_micro_model_input_format(
            non_allocated_vms,
            physical_machines_on,
            step,
            migration_model_input_folder_path,
            energy_intensity_database,
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
        hard_time_limit_migration,
    )
    end_time_opl = time.time()

    if opl_output is None:
        return None, None, None, end_time_opl - start_time_opl

    # Parse OPL output and reallocate VMs
    parsed_data = parse_micro_opl_output(opl_output)
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
    energy_intensity_database,
    nb_points,
    performance_log_file,
    hard_time_limit_migration,
    failed_migrations_limit=50,
):
    filter_full_and_migrating_pms(active_vms, physical_machines_on)
    fragmented_pms = get_fragmented_pms_list(
        physical_machines_on, limit=migration_model_max_fragmented_pms
    )
    if len(fragmented_pms) > 0:
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

                if vms_to_allocate and physical_machines_on_without_pm:
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
                        energy_intensity_database,
                        nb_points,
                        hard_time_limit_migration,
                    )

                    if partial_allocation is None:
                        log_performance(
                            step,
                            "migration",
                            runtime,
                            "time exceeded",
                            len(vms_to_allocate),
                            len(physical_machines_on_without_pm),
                            performance_log_file,
                        )
                        continue

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
                        "success" if migration_success else "",
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


@profile
def run_load_balancer(
    active_vms,
    physical_machines_on,
    pms_to_turn_off_after_migration,
    energy_intensity_database,
    step,
    performance_log_file,
):
    load_balancer_start_time = time.time()

    filter_migrating_pms(active_vms, physical_machines_on)
    filter_pms_to_turn_off_after_migration(
        physical_machines_on, pms_to_turn_off_after_migration
    )
    vms_on_pms = get_vms_on_pms(active_vms, physical_machines_on.keys())

    physical_machines_on = list(physical_machines_on.values())

    # Sort PMs
    physical_machines_on.sort(
        key=lambda pm: w_load_cpu * pm["s"]["load"]["cpu"]
        + (1 - w_load_cpu) * pm["s"]["load"]["memory"],
    )

    middle_index = len(physical_machines_on) // 2

    pm_maxs = reversed(physical_machines_on[-middle_index:])

    for pm_max in pm_maxs:
        for pm_min in physical_machines_on:
            if (
                pm_min["s"]["load"]["cpu"] > 1 - EPSILON
                or pm_min["s"]["load"]["memory"] > 1 - EPSILON
            ):
                break
            if pm_max == pm_min:
                continue
            vms_on_pm_max = vms_on_pms[pm_max["id"]]
            load_balancer(
                vms_on_pm_max, pm_max, pm_min, energy_intensity_database
            )

    load_balancer_end_time = time.time()
    log_performance(
        step,
        "load_balancer",
        load_balancer_end_time - load_balancer_start_time,
        "",
        len(active_vms),
        len(physical_machines_on),
        performance_log_file,
    )


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

def run_lago(
    active_vms,
    physical_machines,
    initial_physical_machines,
    power_function_database,
    step,
    time_step,
):
    cpu_load, memory_load = calculate_load(
        physical_machines, active_vms, time_step, True
    )
    update_physical_machines_load(physical_machines, cpu_load, memory_load)

    # Run best fit algorithm
    print(
        color_text(f"\nRunning Lago algorithm for time step {step}...", Fore.YELLOW)
    )
    is_on = lago(active_vms, physical_machines, power_function_database)
    turned_on_pms, turned_off_pms = update_physical_machines_state(
        physical_machines, initial_physical_machines, is_on
    )
    return turned_on_pms, turned_off_pms

def execute_time_step(
    active_vms,
    completed_migrations_in_step,
    terminated_vms_in_step,
    terminated_vms,
    scheduled_vms,
    physical_machines,
    pms_to_turn_off_after_migration,
    initial_physical_machines,
    speed_function_database,
    vm_execution_time_file,
    time_step,
    step,
):
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
                pm_load = (
                    w_load_cpu * pm["s"]["load"]["cpu"]
                    + (1 - w_load_cpu) * pm["s"]["load"]["memory"]
                )
                pm_speed = evaluate_piecewise_linear_function(
                    speed_function_database[pm["type"]], pm_load
                )
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
                        vm["allocation_step"] = step
                # Migration case
                elif (
                    vm["migration"]["from_pm"] != -1 and vm["migration"]["to_pm"] != -1
                ):
                    from_pm_id = vm["migration"]["from_pm"]
                    from_pm = physical_machines.get(from_pm_id)
                    from_pm_load = (
                        w_load_cpu * from_pm["s"]["load"]["cpu"]
                        + (1 - w_load_cpu) * from_pm["s"]["load"]["memory"]
                    )

                    if not from_pm:
                        raise ValueError(
                            f"Physical machine with ID {from_pm_id} not found"
                        )
                    from_pm_speed = evaluate_piecewise_linear_function(
                        speed_function_database[from_pm["type"]], from_pm_load
                    )
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
                        completed_migrations_in_step.append(vm)
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
                vm["termination_step"] = step + 1
                log_vm_execution_time(vm, vm_execution_time_file, time_step)
                del active_vms[vm_id]
                terminated_vms_in_step.append(vm)
                terminated_vms.append(vm)

    for vm_id, scheduled_vm_list in scheduled_vms.items():
        if vm_id in vms_extra_time:
            pm_id, migration_extra_time = vms_extra_time[vm_id]
            pm = physical_machines.get(pm_id)
            pm_load = (
                w_load_cpu * pm["s"]["load"]["cpu"]
                + (1 - w_load_cpu) * pm["s"]["load"]["memory"]
            )
            pm_speed = evaluate_piecewise_linear_function(
                speed_function_database[pm["type"]], pm_load
            )
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
                    scheduled_vm["allocation_step"] = step
                    if (
                        scheduled_vm["run"]["current_time"]
                        >= scheduled_vm["run"]["total_time"]
                    ):
                        scheduled_vm["termination_step"] = step + 1
                        log_vm_execution_time(
                            scheduled_vm, vm_execution_time_file, time_step
                        )
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

    return completed_migrations_in_step


@profile
def simulate_time_steps(
    initial_vms,
    initial_pms,
    num_steps,
    new_vms_per_step,
    nb_points,
    power_function_database,
    speed_function_database,
    energy_intensity_database,
    log_folder_path,
    vms_trace_file,
    performance_log_file,
    vm_execution_time_file,
    time_step,
    master_model,
    use_load_balancer,
    use_real_data,
    print_to_console,
    save_logs,
    starting_step,
    macro_model_max_subsets,
    macro_model_max_pms,
    micro_model_max_pms,
    micro_model_max_vms,
    migration_model_max_fragmented_pms,
    failed_migrations_limit,
    pm_manager_max_pms,
    hard_time_limit_macro,
    hard_time_limit_micro,
    hard_time_limit_migration,
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

    cpu_load = {pm_id: 0.0 for pm_id in physical_machines.keys()}
    memory_load = {pm_id: 0.0 for pm_id in physical_machines.keys()}
    pms_to_turn_off_after_migration = {}
    turned_on_pms = []
    turned_off_pms = []
    completed_migrations_in_step = []
    terminated_vms = []
    terminated_vms_in_step = []
    is_new_vms_arrival = False
    is_vms_terminated = False
    is_migration_completed = False
    is_pms_turned_on = False
    max_percentage_of_pms_on = 0
    num_completed_migrations = 0
    total_cpu_load = 0.0
    total_memory_load = 0.0
    total_fully_on_pm = 0.0
    total_costs = 0.0
    total_pm_switch_costs = 0.0
    total_pm_load_costs = 0.0
    total_migration_costs = 0.0
    total_model_runtime = 0.0

    for pm in physical_machines.values():
        if pm["s"]["state"] == 0:
            pm["s"]["time_to_turn_off"] = 0.0
        else:
            pm["s"]["time_to_turn_on"] = 0.0

    initial_vm_ids = set(initial_vms.keys())

    # Get idle power for each physical machine
    idle_power = {
        pm_id: evaluate_piecewise_linear_function(
            power_function_database[pm["type"]], 0
        )
        for pm_id, pm in physical_machines.items()
    }

    with open(performance_log_file, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Step", "Model", "Time", "Status", "Num VMs", "Num PMs"])

    with open(vm_execution_time_file, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["VM ID", "Wait Time", "Expected Runtime", "Real Runtime", "Total Time"]
        )

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
                for vm in vms_in_step:
                    vm["arrival_step"] = step
        else:
            # Generate new VMs randomly
            new_vms = generate_new_vms(
                new_vms_per_step, initial_vm_ids, pattern=new_vms_pattern, step=step
            )
            if len(new_vms) > 0:
                is_new_vms_arrival = True
            for vm in new_vms:
                active_vms[vm["id"]] = vm
                vm["arrival_step"] = step

        # Determine which model to run
        model_to_run = "none"

        if master_model:
            model_to_run = master_model

        if master_model in [
            "maxi",
            "mini",
            "hybrid",
            "compound",
            "multilayer",
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
        if model_to_run == "maxi":
            start_time = time.time()
            launch_macro_model(
                active_vms,
                scheduled_vms,
                physical_machines_on,
                pms_to_turn_off_after_migration,
                macro_model_max_subsets,
                macro_model_max_pms,
                micro_model_max_pms,
                micro_model_max_vms,
                idle_power,
                step,
                time_step,
                energy_intensity_database,
                nb_points,
                hard_time_limit_macro,
                hard_time_limit_micro,
                performance_log_file,
                master_model,
            )
            end_time = time.time()

        elif model_to_run == "mini":
            non_allocated_vms = get_non_allocated_workload(active_vms, scheduled_vms)

            start_time = time.time()
            launch_micro_model(
                active_vms,
                non_allocated_vms,
                scheduled_vms,
                physical_machines_on,
                pms_to_turn_off_after_migration,
                step,
                time_step,
                micro_model_max_pms,
                micro_model_max_vms,
                idle_power,
                energy_intensity_database,
                nb_points,
                hard_time_limit_micro,
                performance_log_file,
            )
            end_time = time.time()

        elif model_to_run == "hybrid":
            non_allocated_vms = get_non_allocated_workload(active_vms, scheduled_vms)

            start_time = time.time()
            launch_micro_model(
                active_vms,
                non_allocated_vms,
                scheduled_vms,
                physical_machines_on,
                pms_to_turn_off_after_migration,
                step,
                time_step,
                micro_model_max_pms,
                micro_model_max_vms,
                idle_power,
                energy_intensity_database,
                nb_points,
                hard_time_limit_micro,
                performance_log_file,
            )
            launch_macro_model(
                active_vms,
                scheduled_vms,
                physical_machines_on,
                pms_to_turn_off_after_migration,
                macro_model_max_subsets,
                macro_model_max_pms,
                micro_model_max_pms,
                micro_model_max_vms,
                idle_power,
                step,
                time_step,
                energy_intensity_database,
                nb_points,
                hard_time_limit_macro,
                hard_time_limit_micro,
                performance_log_file,
                master_model,
            )
            end_time = time.time()
        elif model_to_run == "compound":
            physical_machines_on_copy = physical_machines_on.copy()
            non_allocated_vms = get_non_allocated_workload(active_vms, scheduled_vms)

            start_time = time.time()
            launch_micro_model(
                active_vms,
                non_allocated_vms,
                scheduled_vms,
                physical_machines_on,
                pms_to_turn_off_after_migration,
                step,
                time_step,
                micro_model_max_pms,
                micro_model_max_vms,
                idle_power,
                energy_intensity_database,
                nb_points,
                hard_time_limit_micro,
                performance_log_file,
            )

            launch_migration_model(
                active_vms,
                physical_machines_on,
                pms_to_turn_off_after_migration,
                step,
                time_step,
                migration_model_max_fragmented_pms,
                energy_intensity_database,
                nb_points,
                performance_log_file,
                hard_time_limit_migration,
                failed_migrations_limit,
            )

            # If there is any non-allocated VM and any PM scheduled to turn off, try to allocate the VMs on the PMs
            if len(pms_to_turn_off_after_migration) > 0:
                non_allocated_vms = get_non_allocated_workload(
                    active_vms, scheduled_vms
                )
                if len(non_allocated_vms) > 0:
                    available_pms = {
                        pm_id: physical_machines[pm_id]
                        for pm_id in pms_to_turn_off_after_migration.keys()
                    }
                    run_backup_allocation(
                        non_allocated_vms, available_pms, idle_power, step, time_step
                    )

                    for vm in non_allocated_vms.values():
                        pm_id = vm["allocation"]["pm"]
                        if pm_id != -1:
                            available_pms[pm_id]["s"]["load"]["cpu"] += (
                                vm["requested"]["cpu"]
                                / available_pms[pm_id]["capacity"]["cpu"]
                            )
                            available_pms[pm_id]["s"]["load"]["memory"] += (
                                vm["requested"]["memory"]
                                / available_pms[pm_id]["capacity"]["memory"]
                            )
                            if pm_id in pms_to_turn_off_after_migration:
                                del pms_to_turn_off_after_migration[pm_id]
            end_time = time.time()
        elif model_to_run == "multilayer":
            physical_machines_on_copy = physical_machines_on.copy()
            non_allocated_vms = get_non_allocated_workload(active_vms, scheduled_vms)

            start_time = time.time()
            launch_micro_model(
                active_vms,
                non_allocated_vms,
                scheduled_vms,
                physical_machines_on,
                pms_to_turn_off_after_migration,
                step,
                time_step,
                micro_model_max_pms,
                micro_model_max_vms,
                idle_power,
                energy_intensity_database,
                nb_points,
                hard_time_limit_micro,
                performance_log_file,
            )

            launch_migration_model(
                active_vms,
                physical_machines_on,
                pms_to_turn_off_after_migration,
                step,
                time_step,
                migration_model_max_fragmented_pms,
                energy_intensity_database,
                nb_points,
                performance_log_file,
                hard_time_limit_migration,
                failed_migrations_limit,
            )

            # If there is any non-allocated VM and any PM scheduled to turn off, try to allocate the VMs on the PMs
            if len(pms_to_turn_off_after_migration) > 0:
                non_allocated_vms = get_non_allocated_workload(
                    active_vms, scheduled_vms
                )
                if len(non_allocated_vms) > 0:
                    available_pms = {
                        pm_id: physical_machines[pm_id]
                        for pm_id in pms_to_turn_off_after_migration.keys()
                    }
                    run_backup_allocation(
                        non_allocated_vms, available_pms, idle_power, step, time_step
                    )

                    for vm in non_allocated_vms.values():
                        pm_id = vm["allocation"]["pm"]
                        if pm_id != -1:
                            available_pms[pm_id]["s"]["load"]["cpu"] += (
                                vm["requested"]["cpu"]
                                / available_pms[pm_id]["capacity"]["cpu"]
                            )
                            available_pms[pm_id]["s"]["load"]["memory"] += (
                                vm["requested"]["memory"]
                                / available_pms[pm_id]["capacity"]["memory"]
                            )
                            if pm_id in pms_to_turn_off_after_migration:
                                del pms_to_turn_off_after_migration[pm_id]

            if use_load_balancer:
                run_load_balancer(
                    active_vms,
                    physical_machines_on_copy,
                    pms_to_turn_off_after_migration,
                    energy_intensity_database,
                    step,
                    performance_log_file,
                )
            end_time = time.time()
        elif model_to_run == "backup":
            start_time = time.time()
            run_backup_allocation(
                active_vms, physical_machines_on, idle_power, step, time_step
            )
            end_time = time.time()
        elif model_to_run == "best_fit":
            start_time = time.time()
            turned_on_pms, turned_off_pms = run_best_fit(
                active_vms,
                physical_machines,
                initial_physical_machines,
                step,
                time_step,
            )
            end_time = time.time()
        elif model_to_run == "first_fit":
            start_time = time.time()
            turned_on_pms, turned_off_pms = run_first_fit(
                active_vms,
                physical_machines,
                initial_physical_machines,
                step,
                time_step,
            )
            end_time = time.time()
 

        elif model_to_run == "shi_OM":
            start_time = time.time()
            turned_on_pms, turned_off_pms = run_shi(
                active_vms,
                physical_machines,
                initial_physical_machines,
                step,
                time_step,
                "OccupiedMagnitude",
            )
            end_time = time.time()

        elif model_to_run == "shi_AC":
            start_time = time.time()
            turned_on_pms, turned_off_pms = run_shi(
                active_vms,
                physical_machines,
                initial_physical_machines,
                step,
                time_step,
                "AbsoluteCapacity",
            )
            end_time = time.time()

        elif model_to_run == "shi_PU":
            start_time = time.time()
            turned_on_pms, turned_off_pms = run_shi(
                active_vms,
                physical_machines,
                initial_physical_machines,
                step,
                time_step,
                "PercentageUtil",
            )
            end_time = time.time()
        
        elif model_to_run == "lago":
            start_time = time.time()
            turned_on_pms, turned_off_pms = run_lago(
                active_vms,
                physical_machines,
                initial_physical_machines,
                power_function_database,
                step,
                time_step,
            )
            end_time = time.time()

        elif model_to_run == "none":
            print(color_text(f"\nNo model to run for time step {step}...", Fore.YELLOW))

        if master_model in [
            "maxi",
            "mini",
            "hybrid",
            "compound",
            "multilayer",
            "backup",
        ]:
            # Calculate and update load
            cpu_load, memory_load = calculate_load(
                physical_machines, active_vms, time_step
            )
            update_physical_machines_load(physical_machines, cpu_load, memory_load)
            start_time_pm_manager = time.time()
            launch_pm_manager(
                active_vms,
                physical_machines,
                is_on,
                step,
                time_step,
                energy_intensity_database,
                nb_points,
                scheduled_vms,
                pms_to_turn_off_after_migration,
                performance_log_file,
                pm_manager_max_pms=pm_manager_max_pms,
            )
            end_time_pm_manager = time.time()
            total_model_runtime += end_time_pm_manager - start_time_pm_manager

            turned_on_pms, turned_off_pms = update_physical_machines_state(
                physical_machines, initial_physical_machines, is_on
            )

        if model_to_run != "none":
            is_new_vms_arrival = False
            is_vms_terminated = False
            is_migration_completed = False
            is_pms_turned_on = False

            total_model_runtime += end_time - start_time

            # Calculate and update load
            cpu_load, memory_load = calculate_load(
                physical_machines, active_vms, time_step
            )
            update_physical_machines_load(physical_machines, cpu_load, memory_load)

        if SAVE_VM_AND_PM_SETS:
            save_vm_sets(active_vms, terminated_vms, step, OUTPUT_FOLDER_PATH)
            save_pm_sets(physical_machines, step, OUTPUT_FOLDER_PATH)

        # Calculate costs and revenue
        step_total_costs, pm_switch_costs, pm_load_costs, migration_costs = (
            calculate_total_costs(
                active_vms,
                physical_machines,
                completed_migrations_in_step,
                power_function_database,
                speed_function_database,
                time_step,
            )
        )
        total_revenue = calculate_total_revenue(terminated_vms)
        total_costs += step_total_costs
        total_pm_switch_costs += pm_switch_costs
        total_pm_load_costs += pm_load_costs
        total_migration_costs += migration_costs

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
            save_logs=save_logs,
        )
        terminated_vms_in_step = []
        completed_migrations_in_step = []

        # Execute time step
        completed_migrations_in_step = execute_time_step(
            active_vms,
            completed_migrations_in_step,
            terminated_vms_in_step,
            terminated_vms,
            scheduled_vms,
            physical_machines,
            pms_to_turn_off_after_migration,
            initial_physical_machines,
            speed_function_database,
            vm_execution_time_file,
            time_step,
            step,
        )

        num_completed_migrations += len(completed_migrations_in_step)

        if len(completed_migrations_in_step) > 0:
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
        total_pm_switch_costs,
        total_pm_load_costs,
        total_migration_costs,
        num_completed_migrations,
        max_percentage_of_pms_on,
        total_cpu_load,
        total_memory_load,
        total_fully_on_pm,
        step - starting_step,
        total_model_runtime,
    )
