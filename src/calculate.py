import json
import os
from collections import defaultdict

from utils import round_down, evaluate_piecewise_linear_function
from weights import migration, energy, pue, w_load_cpu


def get_first_vm_arrival_time(vms_trace_file_path):
    if not os.path.exists(vms_trace_file_path):
        raise ValueError(
            f"File {vms_trace_file_path} not found. Please provide a file with real VMs or set REAL_DATA to False."
        )
    with open(vms_trace_file_path, "r") as file:
        real_vms = json.load(file)  # Load VMs from JSON file
    return real_vms[0]["submit_time"]


def get_last_vm_arrival_time(vms_trace_file_path):
    if not os.path.exists(vms_trace_file_path):
        raise ValueError(
            f"File {vms_trace_file_path} not found. Please provide a file with real VMs or set REAL_DATA to False."
        )
    with open(vms_trace_file_path, "r") as file:
        real_vms = json.load(file)  # Load VMs from JSON file
    return real_vms[-1]["submit_time"]


def calculate_load(physical_machines, active_vms, time_step, pm_manager=False):
    cpu_load = {pm_id: 0.0 for pm_id in physical_machines.keys()}
    memory_load = {pm_id: 0.0 for pm_id in physical_machines.keys()}

    for vm in active_vms.values():
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
            if pm and (
                pm["s"]["state"] == 1
                and pm["s"]["time_to_turn_on"] < time_step
                or pm_manager
            ):
                cpu_load[pm_id] += vm["requested"]["cpu"] / pm["capacity"]["cpu"]
                memory_load[pm_id] += (
                    vm["requested"]["memory"] / pm["capacity"]["memory"]
                )

        if vm["migration"]["from_pm"] != -1:
            from_pm_id = vm["migration"]["from_pm"]
            from_pm = physical_machines.get(from_pm_id)
            if from_pm:
                cpu_load[from_pm_id] += (
                    vm["requested"]["cpu"] / from_pm["capacity"]["cpu"]
                )
                memory_load[from_pm_id] += (
                    vm["requested"]["memory"] / from_pm["capacity"]["memory"]
                )

    for pm_id in cpu_load.keys():
        if cpu_load[pm_id] > 1:
            cpu_load[pm_id] = round_down(cpu_load[pm_id])
        if memory_load[pm_id] > 1:
            memory_load[pm_id] = round_down(memory_load[pm_id])

    return cpu_load, memory_load


def calculate_load_costs(physical_machines, active_vms, time_step):
    cpu_load_precise = {pm_id: 0.0 for pm_id in physical_machines.keys()}
    memory_load_precise = {pm_id: 0.0 for pm_id in physical_machines.keys()}

    for vm in active_vms.values():
        pm_id = (
            vm["allocation"]["pm"]
            if vm["allocation"]["pm"] != -1
            else (
                vm["migration"]["to_pm"]
                if vm["migration"]["to_pm"] != -1
                else vm["run"]["pm"]
            )
        )
        remaining_run_time = (
            vm["allocation"]["total_time"]
            - vm["allocation"]["current_time"]
            + vm["run"]["total_time"]
            - vm["run"]["current_time"]
        )
        remaining_migration_time = (
            vm["migration"]["total_time"] - vm["migration"]["current_time"]
        )

        if remaining_run_time < 0 or remaining_migration_time < 0:
            raise ValueError(
                f"Remaining run time or migration time is negative for VM {vm['id']}"
            )

        run_time_weight = (
            remaining_run_time / time_step if remaining_run_time < time_step else 1
        )
        migration_time_weight = (
            remaining_migration_time / time_step
            if remaining_migration_time < time_step
            else 1
        )

        if pm_id != -1:
            pm = physical_machines.get(pm_id)
            if pm and pm["s"]["state"] == 1 and pm["s"]["time_to_turn_on"] < time_step:
                cpu_load_precise[pm_id] += (
                    run_time_weight * vm["requested"]["cpu"] / pm["capacity"]["cpu"]
                )
                memory_load_precise[pm_id] += (
                    run_time_weight
                    * vm["requested"]["memory"]
                    / pm["capacity"]["memory"]
                )

        if vm["migration"]["from_pm"] != -1:
            from_pm_id = vm["migration"]["from_pm"]
            from_pm = physical_machines.get(from_pm_id)
            if from_pm:
                cpu_load_precise[from_pm_id] += (
                    migration_time_weight
                    * vm["requested"]["cpu"]
                    / from_pm["capacity"]["cpu"]
                )
                memory_load_precise[from_pm_id] += (
                    migration_time_weight
                    * vm["requested"]["memory"]
                    / from_pm["capacity"]["memory"]
                )

    for pm_id in physical_machines.keys():
        if cpu_load_precise[pm_id] > 1:
            cpu_load_precise[pm_id] = round_down(cpu_load_precise[pm_id])
        elif cpu_load_precise[pm_id] < 0:
            raise ValueError(
                f"CPU load for PM {pm_id} is negative: {cpu_load_precise[pm_id]}"
            )
        if memory_load_precise[pm_id] > 1:
            memory_load_precise[pm_id] = round_down(memory_load_precise[pm_id])
        elif memory_load_precise[pm_id] < 0:
            raise ValueError(
                f"Memory load for PM {pm_id} is negative: {memory_load_precise[pm_id]}"
            )

    return cpu_load_precise, memory_load_precise


def calculate_total_costs(
    active_vms,
    physical_machines,
    pms_to_turn_off_after_migration,
    power_function_dict,
    time_step,
):
    cpu_load, memory_load = calculate_load_costs(
        physical_machines, active_vms, time_step
    )

    # Initialize variables
    migration_energy_consumption = {pm_id: 0.0 for pm_id in physical_machines}
    pm_energy_consumption = {pm_id: 0.0 for pm_id in physical_machines}

    # Preprocess migration data
    pm_migrations_from = defaultdict(list)
    pm_migrations_to = defaultdict(list)

    for vm in active_vms.values():
        from_pm_id = vm["migration"]["from_pm"]
        to_pm_id = vm["migration"]["to_pm"]
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

        state = pm["s"]["state"]
        time_to_turn_on = pm["s"]["time_to_turn_on"]
        time_to_turn_off = pm["s"]["time_to_turn_off"]

        if state == 1 and time_to_turn_on == 0:
            cpu_migration_overhead = 0.0
            migration_overhead_source = False
            migration_overhead_target = False
            multiple_migrations = False

            # Calculate base load power
            load = w_load_cpu * cpu_load.get(pm_id, 0.0) + (
                1 - w_load_cpu
            ) * memory_load.get(pm_id, 0.0)
            power_base = evaluate_piecewise_linear_function(
                power_function_dict[pm_id], load
            )

            # Get lists of VMs migrating from/to this PM
            vms_from = pm_migrations_from.get(pm_id, [])
            vms_to = pm_migrations_to.get(pm_id, [])

            num_migrations = len(vms_from) + len(vms_to)

            # Determine migration overheads
            if num_migrations > 0:
                if num_migrations > 1:
                    cpu_migration_overhead += migration["energy"]["concurrent"]
                    multiple_migrations = True
                if vms_from:
                    cpu_migration_overhead += migration["energy"]["cpu_overhead"][
                        "source"
                    ]
                    migration_overhead_source = True
                if vms_to:
                    cpu_migration_overhead += migration["energy"]["cpu_overhead"][
                        "target"
                    ]
                    migration_overhead_target = True

                if migration_overhead_source:
                    power_migration_source = evaluate_piecewise_linear_function(
                        power_function_dict[pm_id],
                        load + migration["energy"]["cpu_overhead"]["source"],
                        migration_overhead_source,
                    )
                if migration_overhead_target:
                    power_migration_target = evaluate_piecewise_linear_function(
                        power_function_dict[pm_id],
                        load + migration["energy"]["cpu_overhead"]["target"],
                        migration_overhead_target,
                    )
                if migration_overhead_source and multiple_migrations:
                    power_migration_multiple_source = (
                        evaluate_piecewise_linear_function(
                            power_function_dict[pm_id],
                            load
                            + migration["energy"]["concurrent"]
                            + migration["energy"]["cpu_overhead"]["source"],
                            migration_overhead_source or multiple_migrations,
                        )
                    )
                if migration_overhead_target and multiple_migrations:
                    power_migration_multiple_target = (
                        evaluate_piecewise_linear_function(
                            power_function_dict[pm_id],
                            load
                            + migration["energy"]["concurrent"]
                            + migration["energy"]["cpu_overhead"]["target"],
                            migration_overhead_target or multiple_migrations,
                        )
                    )
                if migration_overhead_source and migration_overhead_target:
                    power_migration_multiple_source_and_target = (
                        evaluate_piecewise_linear_function(
                            power_function_dict[pm_id],
                            load
                            + migration["energy"]["concurrent"]
                            + migration["energy"]["cpu_overhead"]["source"]
                            + migration["energy"]["cpu_overhead"]["target"],
                            migration_overhead_source
                            or migration_overhead_target
                            or multiple_migrations,
                        )
                    )

                (
                    real_time_only_source,
                    real_time_only_target,
                    real_time_multiple_source,
                    real_time_multiple_target,
                    real_time_multiple_source_and_target,
                ) = find_migration_times(vms_from, vms_to)
                real_time_base = max(
                    0,
                    time_step
                    - real_time_only_source
                    - real_time_only_target
                    - real_time_multiple_source
                    - real_time_multiple_target
                    - real_time_multiple_source_and_target,
                )
            else:
                real_time_only_source = 0
                real_time_only_target = 0
                real_time_multiple_source = 0
                real_time_multiple_target = 0
                real_time_multiple_source_and_target = 0
                real_time_base = time_step

        elif state == 1 and time_to_turn_on > 0:
            turning_on_power = evaluate_piecewise_linear_function(
                power_function_dict[pm_id], 0
            )
            turning_on_energy = turning_on_power * min(time_step, time_to_turn_on)

        elif state == 0 and time_to_turn_off > 0:
            turning_off_power = evaluate_piecewise_linear_function(
                power_function_dict[pm_id], 0
            )
            turning_off_energy = turning_off_power * min(time_step, time_to_turn_off)

        if pm_id in pms_to_turn_off_after_migration:
            turning_off_power = evaluate_piecewise_linear_function(
                power_function_dict[pm_id], 0
            )
            turning_off_energy = turning_off_power * min(
                real_time_base, time_to_turn_off
            )
            real_time_base = 0

        base_load_energy = real_time_base * power_base
        pm_energy_consumption[pm_id] = (
            turning_on_energy + turning_off_energy + base_load_energy
        )
        migration_energy_consumption[pm_id] = (
            real_time_only_source * power_migration_source
            + real_time_only_target * power_migration_target
            + real_time_multiple_source * power_migration_multiple_source
            + real_time_multiple_target * power_migration_multiple_target
            + real_time_multiple_source_and_target
            * power_migration_multiple_source_and_target
        )

    # Calculate total costs
    pm_costs = sum(pm_energy_consumption.values()) * energy["cost"] * pue
    migration_costs = sum(migration_energy_consumption.values()) * energy["cost"] * pue
    total_costs = pm_costs + migration_costs

    return total_costs, pm_costs, migration_costs


def calculate_total_revenue(terminated_vms):
    total_revenue = sum(vm["revenue"] for vm in terminated_vms)
    return total_revenue


def find_two_largest(times):
    max_time = second_max_time = 0
    for time in times:
        if time > max_time:
            second_max_time = max_time
            max_time = time
        elif time > second_max_time:
            second_max_time = time
    return max_time, second_max_time


def find_min_extra_time(vms_extra_time, pm_id):
    # Extract extra_time values where from_pm_id matches pm_id
    extra_times = [
        extra_time
        for from_pm_id, extra_time in vms_extra_time.values()
        if from_pm_id == pm_id
    ]

    if not extra_times:
        raise ValueError(
            f"pm id {pm_id} to turn off after migration completed, but no migration completed found"
        )

    # Return the minimum extra_time
    return min(extra_times)


def find_migration_times(vms_from, vms_to):
    # Extract remaining times for source and target migrations
    source_times = [
        vm["migration"]["total_time"] - vm["migration"]["current_time"]
        for vm in vms_from
    ]
    target_times = [
        vm["migration"]["total_time"] - vm["migration"]["current_time"] for vm in vms_to
    ]

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
        real_time_multiple_source_and_target,
    )
