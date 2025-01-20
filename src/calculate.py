import json
import os
import csv

from utils import evaluate_piecewise_linear_function, round_down
from weights import price, pue, w_load_cpu


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


def calculate_load_costs(
    physical_machines, active_vms, speed_function_database, time_step
):
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
            if pm:
                pm_speed = evaluate_piecewise_linear_function(
                    speed_function_database[pm["type"]],
                    w_load_cpu * pm["s"]["load"]["cpu"]
                    + (1 - w_load_cpu) * pm["s"]["load"]["memory"],
                )
                remaining_run_time = (
                    vm["allocation"]["total_time"]
                    - vm["allocation"]["current_time"]
                    + vm["run"]["total_time"]
                    - vm["run"]["current_time"]
                ) / pm_speed

                run_time_weight = (
                    remaining_run_time / time_step
                    if remaining_run_time < time_step
                    else 1
                )

                if pm["s"]["state"] == 1 and pm["s"]["time_to_turn_on"] < time_step:
                    cpu_load[pm_id] += (
                        run_time_weight * vm["requested"]["cpu"] / pm["capacity"]["cpu"]
                    )
                    memory_load[pm_id] += (
                        run_time_weight
                        * vm["requested"]["memory"]
                        / pm["capacity"]["memory"]
                    )

    for pm_id in physical_machines.keys():
        if cpu_load[pm_id] > 1:
            cpu_load[pm_id] = round_down(cpu_load[pm_id])
        elif cpu_load[pm_id] < 0:
            raise ValueError(f"CPU load for PM {pm_id} is negative: {cpu_load[pm_id]}")
        if memory_load[pm_id] > 1:
            memory_load[pm_id] = round_down(memory_load[pm_id])
        elif memory_load[pm_id] < 0:
            raise ValueError(
                f"Memory load for PM {pm_id} is negative: {memory_load[pm_id]}"
            )

    return (
        cpu_load,
        memory_load,
    )


def calculate_total_costs(
    active_vms,
    physical_machines,
    completed_migrations_in_step,
    power_function_database,
    speed_function_database,
    time_step,
):
    cpu_load, memory_load = calculate_load_costs(
        physical_machines, active_vms, speed_function_database, time_step
    )

    # Initialize variables
    pm_switch_energy = 0
    pm_load_energy = 0
    migration_energy = 0

    for pm_id, pm in physical_machines.items():
        state = pm["s"]["state"]
        time_to_turn_on = pm["s"]["time_to_turn_on"]
        time_to_turn_off = pm["s"]["time_to_turn_off"]

        if state == 1 and time_to_turn_on > 0:
            turning_on_power = evaluate_piecewise_linear_function(
                power_function_database[pm["type"]], 0
            )
            turning_on_energy = turning_on_power * min(time_step, time_to_turn_on)
            pm_switch_energy += turning_on_energy

        elif state == 0 and time_to_turn_off > 0:
            turning_off_power = evaluate_piecewise_linear_function(
                power_function_database[pm["type"]], 0
            )
            turning_off_energy = turning_off_power * min(time_step, time_to_turn_off)
            pm_switch_energy += turning_off_energy

        if state == 1:
            pm_load_energy += (
                evaluate_piecewise_linear_function(
                    power_function_database[pm["type"]],
                    w_load_cpu * cpu_load[pm_id]
                    + (1 - w_load_cpu) * memory_load[pm_id],
                )
                * time_step
            )

    for vm in completed_migrations_in_step:
        migration_energy += vm["migration"]["energy"]

    # Calculate total costs
    pm_switch_costs = pm_switch_energy * price["energy"] * pue
    pm_load_costs = pm_load_energy * price["energy"] * pue
    migration_costs = migration_energy * price["energy"] * pue
    total_costs = pm_switch_costs + pm_load_costs + migration_costs

    return total_costs, pm_switch_costs, pm_load_costs, migration_costs


def calculate_total_revenue(terminated_vms):
    total_revenue = sum(vm["revenue"] for vm in terminated_vms)
    return total_revenue


def count_non_valid_entries(performance_log_file):
    non_valid_entries = 0
    total_entries = 0

    with open(performance_log_file, "r") as file:
        for line in file:
            if "macro" in line or "micro" in line:
                total_entries += 1
                if "not valid" in line:
                    non_valid_entries += 1
    return non_valid_entries, total_entries


def calculate_performance_metrics(vm_execution_time_file):
    total_wait_time = 0
    total_expected_runtime = 0
    total_real_runtime = 0
    total_time = 0
    num_vms = 0

    with open(vm_execution_time_file, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            wait_time = float(row["Wait Time"])
            expected_runtime = float(row["Expected Runtime"])
            real_runtime = float(row["Real Runtime"])
            total_time_vm = float(row["Total Time"])

            total_wait_time += wait_time
            total_expected_runtime += expected_runtime
            total_real_runtime += real_runtime
            total_time += total_time_vm
            num_vms += 1

    avg_wait_time = total_wait_time / num_vms if num_vms > 0 else 0
    runtime_efficiency = (
        (total_expected_runtime / total_real_runtime) if total_real_runtime > 0 else 0
    )
    overall_time_efficiency = (
        (total_expected_runtime / total_time) if total_time > 0 else 0
    )

    return avg_wait_time, runtime_efficiency, overall_time_efficiency
