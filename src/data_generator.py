import numpy as np
import os
from config import INITIAL_PMS_FILE
from utils import (
    convert_pms_to_model_input_format,
    convert_specific_power_function_to_model_input_format,
    load_pm_database,
)
from weights import migration, price


def generate_unique_id(existing_ids):
    new_id = max(existing_ids, default=-1) + 1
    while new_id in existing_ids:
        new_id += 1
    return new_id


def generate_new_vms(new_vms_per_step, existing_ids, pattern="constant", step=0):
    """
    Generate new VMs based on the specified pattern.

    Parameters:
    - new_vms_per_step: Base number of new VMs per step (used differently depending on the pattern).
    - existing_ids: Set of existing VM IDs.
    - pattern: The pattern to use for VM generation.
    - step: Current time step (useful for time-varying patterns).

    Returns:
    - List of new VM dictionaries.
    """

    # Determine the number of new VMs based on the specified pattern
    if pattern == "constant":
        num_new_vms = new_vms_per_step
    elif pattern == "poisson":
        num_new_vms = np.random.poisson(lam=new_vms_per_step)
    elif pattern == "burst":
        # Generate a burst of VMs every 10 steps
        if step % 10 == 0:
            num_new_vms = new_vms_per_step * 5  # Burst of 5 times the base rate
        else:
            num_new_vms = new_vms_per_step
    elif pattern == "heavy_tail":
        # Number of VMs follows a heavy-tailed Pareto distribution
        num_new_vms = int(np.random.pareto(a=2.0) * new_vms_per_step)
    elif pattern == "sinusoidal":
        # Arrival rate varies with time, e.g., sinusoidal pattern
        lam = new_vms_per_step * (1 + np.sin(step / 10.0 * 2 * np.pi))
        lam = max(lam, 0)  # Ensure lambda is non-negative
        num_new_vms = int(lam)
    elif pattern == "random_spikes":
        # Randomly introduce spikes in VM arrivals
        num_new_vms = new_vms_per_step
        if np.random.rand() < 0.1:  # 10% chance of a spike
            num_new_vms += new_vms_per_step * np.random.randint(5, 10)
    else:
        # Default to constant if pattern is unrecognized
        num_new_vms = new_vms_per_step

    new_vms = []  # List to store new VMs

    for _ in range(num_new_vms):
        new_vm_id = generate_unique_id(existing_ids)

        # Determine resource requests
        if pattern == "heavy_tail":
            # Use Pareto distribution for resource requests
            requested_cpu = int(np.random.pareto(a=2.0) * 1)
            requested_cpu = min(max(requested_cpu, 1), 16)
            requested_memory = int(np.random.pareto(a=2.0) * 4)
            requested_memory = min(max(requested_memory, 4), 32)
        else:
            # Default resource requests
            requested_cpu = np.random.choice(
                [1, 1, 1, 1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 4, 4, 8]
            )
            requested_memory = np.random.choice(
                [1, 1, 1, 1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 4, 4, 8, 8, 16]
            )

        # Random total run time
        run_total_time = np.random.uniform(30.0, 6000.0)

        # Calculate revenue based on requested resources
        revenue = (
            requested_cpu * price["cpu"] + requested_memory * price["memory"]
        ) * run_total_time

        # Migration times calculations
        migration_first_round_time = (
            requested_memory / migration["time"]["network_bandwidth"]
        )
        migration_down_time = (
            migration["time"]["resume_vm_on_target"]
            + migration_first_round_time
            * migration["time"]["memory_dirty_rate"]
            / migration["time"]["network_bandwidth"]
        )
        migration_total_time = migration_first_round_time + migration_down_time
        migration_energy = (
            migration["energy"]["coefficient"] * requested_memory
            + migration["energy"]["constant"]
        )

        new_vm = {
            "id": new_vm_id,
            "requested": {"cpu": requested_cpu, "memory": requested_memory},
            "allocation": {
                "current_time": 0.0,
                "total_time": min(run_total_time * 0.01, 5),
                "pm": -1,
            },
            "run": {"current_time": 0.0, "total_time": run_total_time, "pm": -1},
            "migration": {
                "current_time": 0.0,
                "total_time": migration_total_time,
                "down_time": migration_down_time,
                "from_pm": -1,
                "to_pm": -1,
                "energy": migration_energy,
            },
            "arrival_step": step,
            "revenue": revenue,
        }

        existing_ids.add(new_vm_id)
        new_vms.append(new_vm)  # Add the new VM to the list

    return new_vms  # Return the list of new VMs


def generate_pms(num_pms, composition, composition_shape):
    pm_database, _, _, specific_power_function_database = load_pm_database(
        composition, composition_shape
    )
    pms = {}
    nb_points = 11

    for pm_id in range(num_pms):
        if composition == "homogeneous":
            type = 0
        else:
            type = np.random.randint(0, len(pm_database))
        pms[pm_id] = {"id": pm_id}
        pms[pm_id].update(pm_database[type])

    formatted_pms = convert_pms_to_model_input_format(pms)
    formatted_specific_power_function = (
        convert_specific_power_function_to_model_input_format(
            pms, specific_power_function_database, nb_points
        )
    )

    os.makedirs(os.path.dirname(INITIAL_PMS_FILE), exist_ok=True)
    with open(INITIAL_PMS_FILE, "w") as pm_file:
        pm_file.write(formatted_pms)
        pm_file.write("\n\n")
        pm_file.write(formatted_specific_power_function)

    print(f"Physical machines data saved to {INITIAL_PMS_FILE}")
