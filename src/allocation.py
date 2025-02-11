import os
import shutil
import subprocess
from copy import deepcopy

from calculate import calculate_load
from config import FLOW_CONTROL_PATH

try:
    profile  # type: ignore
except NameError:

    def profile(func):
        return func


def run_opl_model(
    vm_model_input_file_path,
    pm_model_input_file_path,
    model_input_folder_path,
    model_output_folder_path,
    step,
    model_name,
    hard_time_limit=None,
):
    os.makedirs(model_output_folder_path, exist_ok=True)

    # Copy the input files to the required path
    shutil.copy(
        vm_model_input_file_path,
        os.path.join(model_input_folder_path, "virtual_machines.dat"),
    )
    shutil.copy(
        pm_model_input_file_path,
        os.path.join(model_input_folder_path, "physical_machines.dat"),
    )

    cmd = [
        "oplrun",
        f"-Dmodel_name={model_name}",
        os.path.expanduser(FLOW_CONTROL_PATH),
    ]

    try:
        # Run the OPL model with a timeout
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=hard_time_limit
        )

        # Save the OPL model output
        output_file_path = os.path.join(
            model_output_folder_path, f"opl_output_t{step}.txt"
        )
        with open(output_file_path, "w") as file:
            file.write(result.stdout)

        return result.stdout

    except subprocess.TimeoutExpired:
        return None


def reallocate_vms(vms, new_allocation, vm_ids, pm_ids, is_allocation, is_migration):
    migrated_vms = []

    # Create a mapping of VM IDs to their previous PM
    vm_migration_from_pm = {}

    for vm_index, vm_id in enumerate(vm_ids):
        if is_migration[vm_index] == 1:
            vm = vms[vm_id]

            if vm["run"]["pm"] != -1:
                vm_migration_from_pm[vm_id] = vm["run"]["pm"]
                migrated_vms.append(
                    {"id": vm_id, "from_pm": vm_migration_from_pm[vm_id], "to_pm": -1}
                )
            elif vm["migration"]["from_pm"] != -1:
                vm_migration_from_pm[vm_id] = vm["migration"]["from_pm"]

    # Process the new allocations
    for vm_index, vm_id in enumerate(vm_ids):
        vm = vms[vm_id]  # Access the VM directly using its ID

        # Reset VMs' allocation, migration, and run PMs
        vm["allocation"]["pm"] = -1
        vm["migration"]["from_pm"] = -1
        vm["migration"]["to_pm"] = -1
        vm["run"]["pm"] = -1

        for pm_index, pm_id in enumerate(pm_ids):
            if new_allocation[vm_index][pm_index] == 1:
                if is_allocation[vm_index] == 1:
                    vm["allocation"]["pm"] = pm_id
                elif is_migration[vm_index] == 1:
                    vm["migration"]["from_pm"] = vm_migration_from_pm[vm_id]
                    vm["migration"]["to_pm"] = pm_id
                    for migration in migrated_vms:
                        if migration["id"] == vm_id:
                            migration["to_pm"] = pm_id
                else:
                    vm["run"]["pm"] = pm_id
                break  # Allocation found for this VM, move to the next VM

    # Reset current times for VMs not allocated or migrating
    for vm in vms.values():
        if vm["migration"]["from_pm"] == -1 or vm["migration"]["to_pm"] == -1:
            vm["migration"]["current_time"] = 0.0
        if (
            vm["allocation"]["pm"] == -1
            and vm["run"]["pm"] == -1
            and vm["migration"]["from_pm"] == -1
            and vm["migration"]["to_pm"] == -1
        ):
            vm["allocation"]["current_time"] = 0.0
            vm["run"]["current_time"] = 0.0
            vm["migration"]["current_time"] = 0.0


def migration_reallocate_vms(
    vm_ids, pm_ids, allocation, non_allocated_vms, migrating_on_pms
):
    is_migration = False
    for vm_index, vm_id in enumerate(vm_ids):
        vm = non_allocated_vms.get(vm_id)
        for pm_index in range(len(pm_ids)):
            if allocation[vm_index][pm_index] == 1:
                pm_id = pm_ids[pm_index]
                if vm["run"]["pm"] != -1:
                    vm["migration"]["from_pm"] = vm["run"]["pm"]
                    vm["migration"]["to_pm"] = pm_id
                    vm["run"]["pm"] = -1
                    is_migration = True
                    if pm_id not in migrating_on_pms:
                        migrating_on_pms.append(pm_id)
                elif vm["allocation"]["pm"] != -1:
                    vm["allocation"]["pm"] = pm_id
                elif vm["migration"]["from_pm"] != -1:
                    raise ValueError(
                        f"VM {vm_id} is already migrating from PM {vm['migration']['from_pm']} to PM {vm['migration']['to_pm']}."
                    )

    return is_migration, migrating_on_pms


def update_physical_machines_state(physical_machines, initial_physical_machines, is_on):
    turned_on_pms = []
    turned_off_pms = []

    for pm in physical_machines.values():
        state = is_on.get(pm["id"], pm["s"]["state"])
        # Check if the state or the transition times need to be updated
        if pm["s"]["state"] != state:
            initial_pm = initial_physical_machines.get(pm["id"])
            if state == 1:  # Machine is being turned on
                pm["s"]["time_to_turn_off"] = initial_pm["s"]["time_to_turn_off"]
                pm["s"]["state"] = 1
                turned_on_pms.append(pm["id"])
            else:  # Machine is being turned off
                pm["s"]["time_to_turn_on"] = initial_pm["s"]["time_to_turn_on"]
                pm["s"]["state"] = 0
                turned_off_pms.append(pm["id"])
        elif pm["s"]["state"] == 1 and pm["s"]["time_to_turn_on"] > 0:
            turned_on_pms.append(pm["id"])
        elif pm["s"]["state"] == 0 and pm["s"]["time_to_turn_off"] > 0:
            turned_off_pms.append(pm["id"])
    return turned_on_pms, turned_off_pms


def update_physical_machines_load(physical_machines, cpu_load, memory_load):
    for pm in physical_machines.values():
        pm["s"]["load"]["cpu"] = cpu_load[pm["id"]]
        pm["s"]["load"]["memory"] = memory_load[pm["id"]]


def is_fully_on_next_step(pm, time_step):
    return pm["s"]["state"] == 1 and pm["s"]["time_to_turn_on"] < time_step


def is_allocation_for_all_vms(allocation):
    return all(1 in row for row in allocation)


def get_vms_on_pm(active_vms, pm_id):
    return {
        vm["id"]: vm
        for vm in active_vms.values()
        if vm["allocation"]["pm"] == pm_id
        or vm["run"]["pm"] == pm_id
        or vm["migration"]["from_pm"] == pm_id
        or vm["migration"]["to_pm"] == pm_id
    }


def get_vms_on_pms(active_vms, pm_ids):
    vms_on_pms = {pm_id: [] for pm_id in pm_ids}
    for vm in active_vms.values():
        if vm["run"]["pm"] in pm_ids:
            vms_on_pms[vm["run"]["pm"]].append(vm)
        elif vm["allocation"]["pm"] in pm_ids:
            vms_on_pms[vm["allocation"]["pm"]].append(vm)
    return vms_on_pms


def get_non_allocated_vms(active_vms):
    return {
        vm["id"]: vm
        for vm in active_vms.values()
        if vm["allocation"]["pm"] == -1
        and vm["run"]["pm"] == -1
        and vm["migration"]["from_pm"] == -1
        and vm["migration"]["to_pm"] == -1
    }


def get_non_allocated_workload(active_vms, scheduled_vms):
    non_allocated_vms = {}

    for vm in active_vms.values():
        if (
            vm["allocation"]["pm"] == -1
            and vm["run"]["pm"] == -1
            and vm["migration"]["from_pm"] == -1
            and vm["migration"]["to_pm"] == -1
            and not any(
                vm["id"] == scheduled_vm["id"]
                for vm_list in scheduled_vms.values()
                for scheduled_vm in vm_list
            )
        ):
            non_allocated_vms[vm["id"]] = vm

    return non_allocated_vms


def get_pms_on_schedule(active_vms, scheduled_vms):
    pms_on_schedule = []
    for vm_id, scheduled_vm_list in scheduled_vms.items():
        if scheduled_vm_list:
            vm = active_vms[vm_id]
            if vm["migration"]["from_pm"] not in pms_on_schedule:
                pms_on_schedule.append(vm["migration"]["from_pm"])
    return pms_on_schedule


def schedule_migration(
    physical_machines, active_vms, pm, vms_to_allocate, scheduled_vms, time_step
):
    migrating_vms = [
        vm for vm in active_vms.values() if vm["migration"]["from_pm"] == pm["id"]
    ]
    pm_copy = deepcopy(pm)

    for migrating_vm in migrating_vms:
        scheduled_vms[migrating_vm["id"]] = []

        migrating_to_pm = physical_machines[migrating_vm["migration"]["to_pm"]]
        if (
            vms_to_allocate
            and migrating_to_pm["s"]["state"] == 1
            and migrating_to_pm["s"]["time_to_turn_on"]
            + migrating_vm["migration"]["total_time"]
            - migrating_vm["migration"]["current_time"]
            < time_step
        ):

            cpu_overload = migrating_vm["requested"]["cpu"] / pm["capacity"]["cpu"]
            memory_overload = (
                migrating_vm["requested"]["memory"] / pm["capacity"]["memory"]
            )

            pm_copy["s"]["load"]["cpu"] -= cpu_overload
            pm_copy["s"]["load"]["memory"] -= memory_overload

            for vm in vms_to_allocate:
                if (
                    vm["requested"]["cpu"]
                    + pm_copy["s"]["load"]["cpu"] * pm_copy["capacity"]["cpu"]
                    <= pm_copy["capacity"]["cpu"]
                    and vm["requested"]["memory"]
                    + pm_copy["s"]["load"]["memory"] * pm_copy["capacity"]["memory"]
                    <= pm_copy["capacity"]["memory"]
                ):
                    scheduled_vms[migrating_vm["id"]].append(active_vms[vm["id"]])
                    vms_to_allocate.remove(vm)

                    # Update the scheduled load of the physical machine
                    cpu_scheduled_load = (
                        vm["requested"]["cpu"] / pm_copy["capacity"]["cpu"]
                    )
                    memory_scheduled_load = (
                        vm["requested"]["memory"] / pm_copy["capacity"]["memory"]
                    )
                    pm_copy["s"]["load"]["cpu"] += cpu_scheduled_load
                    pm_copy["s"]["load"]["memory"] += memory_scheduled_load

                    print(
                        f"VM {vm['id']} scheduled on PM {pm['id']} after VM {migrating_vm['id']} migration."
                    )


def solve_overload(pm, physical_machines, active_vms, scheduled_vms, time_step):
    vms_to_allocate = []
    pm_dict = {pm["id"]: pm}

    for vm in active_vms.values():
        if vm["allocation"]["pm"] == pm["id"] and vm["allocation"]["current_time"] == 0:
            vm["allocation"]["pm"] = -1
            vms_to_allocate.append(vm)

    cpu_load, memory_load = calculate_load(pm_dict, active_vms, time_step)
    update_physical_machines_load(pm_dict, cpu_load, memory_load)

    sorted_vms_to_allocate = sorted(
        vms_to_allocate, key=lambda vm: vm["run"]["total_time"], reverse=True
    )

    for vm in sorted_vms_to_allocate:
        if (
            vm["requested"]["cpu"] + pm["s"]["load"]["cpu"] * pm["capacity"]["cpu"]
            <= pm["capacity"]["cpu"]
            and vm["requested"]["memory"]
            + pm["s"]["load"]["memory"] * pm["capacity"]["memory"]
            <= pm["capacity"]["memory"]
        ):
            vm["allocation"]["pm"] = pm["id"]
            pm["s"]["load"]["cpu"] += vm["requested"]["cpu"] / pm["capacity"]["cpu"]
            pm["s"]["load"]["memory"] += (
                vm["requested"]["memory"] / pm["capacity"]["memory"]
            )
            sorted_vms_to_allocate.remove(vm)

    if sorted_vms_to_allocate:
        schedule_migration(
            physical_machines,
            active_vms,
            pm,
            sorted_vms_to_allocate,
            scheduled_vms,
            time_step,
        )


def detect_overload(physical_machines, active_vms, scheduled_vms, time_step):
    cpu_load, memory_load = calculate_load(physical_machines, active_vms, time_step)
    for pm in physical_machines.values():
        pm_dict = {pm["id"]: pm}
        if cpu_load[pm["id"]] > 1 or memory_load[pm["id"]] > 1:
            solve_overload(pm, physical_machines, active_vms, scheduled_vms, time_step)
        cpu_load_pm, memory_load_pm = calculate_load(pm_dict, active_vms, time_step)

        if cpu_load_pm[pm["id"]] > 1 or memory_load_pm[pm["id"]] > 1:
            print()
            print(f"Error on PM {pm['id']}:")
            print(f"CPU load: {cpu_load[pm['id']]}")
            print(f"Memory load: {memory_load[pm['id']]}")
            print()
            for vm in active_vms.values():
                if vm["allocation"]["pm"] == pm["id"]:
                    print(f"VM {vm['id']} allocated on PM {pm['id']}.")
            raise ValueError(f"Cannot proceed: Overload detected on PM {pm['id']}.")
