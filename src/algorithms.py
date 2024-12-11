from copy import deepcopy
from math import sqrt

from utils import evaluate_piecewise_linear_function
from weights import price, pue, w_load_cpu, EPSILON

try:
    profile  # type: ignore
except NameError:

    def profile(func):
        return func


def vm_fits_on_pm(vm, pm):
    if (
        pm["capacity"]["cpu"]
        - (pm["s"]["load"]["cpu"] * pm["capacity"]["cpu"] + vm["requested"]["cpu"])
        >= 0
        and pm["capacity"]["memory"]
        - (
            pm["s"]["load"]["memory"] * pm["capacity"]["memory"]
            + vm["requested"]["memory"]
        )
        >= 0
        and not (pm["s"]["state"] == 0 and pm["s"]["time_to_turn_off"] > 0)
    ):
        if (
            vm["allocation"]["pm"] == -1
            and vm["migration"]["to_pm"] == -1
            and vm["run"]["pm"] != pm["id"]
        ):
            return True
    return False

def vm_exceeds_pm_load(vm, pm):
    return (
        pm["capacity"]["cpu"]
        - (pm["s"]["load"]["cpu"] * pm["capacity"]["cpu"] + vm["requested"]["cpu"])
        < 0
        or pm["capacity"]["memory"]
        - (pm["s"]["load"]["memory"] * pm["capacity"]["memory"] + vm["requested"]["memory"])
        < 0
    )

def algorithms_reallocate_vms(allocation, active_vms):
    for a in allocation:
        vm_id = a["vm_id"]
        pm_id = a["pm_id"]
        if pm_id is not None:
            vm = active_vms.get(vm_id)
            if vm:
                if vm["run"]["pm"] != -1:
                    vm["migration"]["from_pm"] = vm["run"]["pm"]
                    vm["migration"]["to_pm"] = pm_id
                    vm["run"]["pm"] = -1
                else:
                    vm["allocation"]["pm"] = pm_id


def manage_pms_allocation(pms, allocation):
    is_on = dict.fromkeys(pms.keys(), 0)

    # Preprocess allocation to create a set of pm_ids for O(1) lookups
    allocated_pm_ids = set(a["pm_id"] for a in allocation)

    # Iterate through each PM to determine its status
    for pm_id, pm in pms.items():
        pm_state = pm["s"]["state"]
        pm_time_to_turn_on = pm["s"]["time_to_turn_on"]
        pm_load_cpu = pm["s"]["load"]["cpu"]
        pm_load_memory = pm["s"]["load"]["memory"]

        if pm_state == 1 and pm_time_to_turn_on > 0:
            # PM is in the process of turning on
            is_on[pm_id] = 1
        elif pm_load_cpu > 0 or pm_load_memory > 0:
            # PM has active load
            is_on[pm_id] = 1
        elif pm_id in allocated_pm_ids:
            # PM is found in the allocation list
            is_on[pm_id] = 1

    return is_on


def manage_pms_load(vms, pms, is_on):
    for pm_id, pm in pms.items():
        if pm["s"]["state"] == 1 and pm["s"]["time_to_turn_on"] > 0:
            is_on[pm_id] = 1
        else:
            for vm in vms.values():
                if (
                    vm["allocation"]["pm"] == pm_id
                    or vm["run"]["pm"] == pm_id
                    or vm["migration"]["from_pm"] == pm_id
                    or vm["migration"]["to_pm"] == pm_id
                ):
                    is_on[pm_id] = 1
                    break


def first_fit(vms, pms):
    allocation = {vm_id: {"vm_id": vm_id, "pm_id": None} for vm_id in vms}
    sorted_pms = sorted(pms.values(), key=lambda pm: pm["s"]["state"], reverse=True)

    for vm_id, vm in vms.items():
        if vm["allocation"]["pm"] != -1 or vm["migration"]["to_pm"] != -1:
            continue  # VM is already allocated or migrating
        for pm in sorted_pms:
            if vm["run"]["pm"] == pm["id"]:
                break  # VM is already running on the best PM
            if vm_fits_on_pm(vm, pm):
                pm["s"]["load"]["cpu"] += vm["requested"]["cpu"] / pm["capacity"]["cpu"]
                pm["s"]["load"]["memory"] += (
                    vm["requested"]["memory"] / pm["capacity"]["memory"]
                )
                allocation[vm_id]["pm_id"] = pm["id"]
                break  # Move to next VM

    algorithms_reallocate_vms(allocation.values(), vms)
    is_on = manage_pms_allocation(pms, allocation.values())
    return is_on


def best_fit(vms, pms):
    allocation = {vm_id: {"vm_id": vm_id, "pm_id": None} for vm_id in vms}
    sorted_pms = sorted(
        pms.values(),
        key=lambda pm: (
            pm["s"]["load"]["cpu"],
            pm["s"]["load"]["memory"],
        ),
        reverse=True,
    )

    for vm_id, vm in vms.items():
        if vm["allocation"]["pm"] != -1 or vm["migration"]["to_pm"] != -1:
            continue  # VM is already allocated or migrating
        for pm in sorted_pms:
            if vm["run"]["pm"] == pm["id"]:
                break  # VM is already running on the best PM
            if vm_fits_on_pm(vm, pm):
                pm["s"]["load"]["cpu"] += vm["requested"]["cpu"] / pm["capacity"]["cpu"]
                pm["s"]["load"]["memory"] += (
                    vm["requested"]["memory"] / pm["capacity"]["memory"]
                )
                allocation[vm_id]["pm_id"] = pm["id"]
                break  # Move to next VM

    algorithms_reallocate_vms(allocation.values(), vms)
    is_on = manage_pms_allocation(pms, allocation.values())
    return is_on


def get_sort_key_pm(pm, vms, sort_key):
    if sort_key == "OccupiedMagnitude":
        load_w_load_cpu = 0
        memory_load = 0
        for vm in vms.values():
            if vm["allocation"]["pm"] == pm["id"] or vm["run"]["pm"] == pm["id"]:
                load_w_load_cpu += vm["requested"]["cpu"]
                memory_load += vm["requested"]["memory"]
        return sqrt(load_w_load_cpu**2 + memory_load**2)
    elif sort_key == "AbsoluteCapacity":
        return get_magnitude_pm(pm)
    elif sort_key == "PercentageUtil":
        total_vm_magnitude = 0
        for vm in vms.values():
            if vm["allocation"]["pm"] == pm["id"] or vm["run"]["pm"] == pm["id"]:
                total_vm_magnitude += get_magnitude_vm(vm)
        return total_vm_magnitude / get_magnitude_pm(pm)


def get_magnitude_pm(pm):
    return sqrt(pm["capacity"]["cpu"] ** 2 + pm["capacity"]["memory"] ** 2)


def get_magnitude_vm(vm):
    return sqrt(vm["requested"]["cpu"] ** 2 + vm["requested"]["memory"] ** 2)


def get_vms_on_pm_list(vms, pms, is_on):
    vms_on_pm = {pm_id: [] for pm_id in pms}
    for vm in vms.values():
        if vm["allocation"]["pm"] != -1:
            pm_id = vm["allocation"]["pm"]
            if pm_id in vms_on_pm:
                vms_on_pm[pm_id].append(vm)
            else:
                is_on[pm_id] = 1
        elif vm["run"]["pm"] != -1:
            vms_on_pm[vm["run"]["pm"]].append(vm)
        elif vm["migration"]["to_pm"] != -1:
            vms_on_pm[vm["migration"]["to_pm"]].append(vm)
    return vms_on_pm

@profile
def shi_migration(
    vms, physical_machines, time_step, sort_key, failed_migrations_limit=10
):
    pms = {
        pm_id: pm
        for pm_id, pm in physical_machines.items()
        if pm["s"]["state"] == 1
        and pm["s"]["time_to_turn_on"] < time_step
        or pm["s"]["load"]["cpu"] > 0
        or pm["s"]["load"]["memory"] > 0
    }
    is_on = {pm_id: 0 for pm_id in pms}

    vms_on_pm = get_vms_on_pm_list(vms, pms, is_on)
    magnitude_pm = {}
    magnitude_vm = {vm_id: get_magnitude_vm(vm) for vm_id, vm in vms.items()}
    failed_migrations = 0

    for pm_id, pm in pms.items():
        magnitude_pm[pm_id] = get_sort_key_pm(pm, vms, sort_key)
    sorted_pms = sorted(
        pms.values(), key=lambda pm: magnitude_pm[pm["id"]], reverse=True
    )

    for pm in reversed(sorted_pms):
        # Backup VMs and PMs
        vms_copy = deepcopy(vms)
        pms_copy = deepcopy(pms)
        vms_on_pm[pm["id"]].sort(key=lambda vm: magnitude_vm[vm["id"]], reverse=True)

        for vm in vms_on_pm[pm["id"]]:
            if vm["allocation"]["pm"] != -1 or vm["migration"]["to_pm"] != -1:
                continue
            for pm_candidate in sorted_pms:
                if pm_candidate["id"] == pm["id"]:
                    break
                if (
                    pm_candidate["s"]["state"] == 0
                    or pm_candidate["s"]["time_to_turn_on"] > 0
                ):
                    continue
                if vm_fits_on_pm(vm, pm_candidate):
                    vm["migration"]["from_pm"] = vm["run"]["pm"]
                    vm["migration"]["to_pm"] = pm_candidate["id"]
                    pm_candidate["s"]["load"]["cpu"] += (
                        vm["requested"]["cpu"] / pm_candidate["capacity"]["cpu"]
                    )
                    pm_candidate["s"]["load"]["memory"] += (
                        vm["requested"]["memory"] / pm_candidate["capacity"]["memory"]
                    )
                    vms_on_pm[vm["run"]["pm"]].remove(vm)
                    vm["run"]["pm"] = -1
                    magnitude_pm[pm["id"]] = get_sort_key_pm(pm, vms, sort_key)

                    vms_on_pm[pm_candidate["id"]].append(vm)
                    magnitude_pm[pm_candidate["id"]] = get_sort_key_pm(
                        pm_candidate, vms, sort_key
                    )
                    sorted_pms.sort(key=lambda pm: magnitude_pm[pm["id"]], reverse=True)
                    break

        if vms_on_pm[pm["id"]]:
            vms = deepcopy(vms_copy)
            pms = deepcopy(pms_copy)
            vms_on_pm = get_vms_on_pm_list(vms, pms, is_on)
            magnitude_pm[pm["id"]] = get_sort_key_pm(pm, vms, sort_key)
            sorted_pms = sorted(
                pms.values(), key=lambda pm: magnitude_pm[pm["id"]], reverse=True
            )
            failed_migrations += 1

        if failed_migrations_limit and failed_migrations >= failed_migrations_limit:
            print(f"Failed to migrate {failed_migrations} VMs. Limit reached.")
            break

    manage_pms_load(vms, pms, is_on)
    return is_on

@profile
def shi_allocation(vms, pms, sort_key):
    magnitude_pm = {}
    for pm_id, pm in pms.items():
        magnitude_pm[pm_id] = get_sort_key_pm(pm, vms, sort_key)

    for vm in vms.values():
        sorted_pms = sorted(
            pms.values(), key=lambda pm: magnitude_pm[pm["id"]], reverse=True
        )
        for pm in sorted_pms:
            if vm_fits_on_pm(vm, pm):
                vm["allocation"]["pm"] = pm["id"]
                pm["s"]["load"]["cpu"] += vm["requested"]["cpu"] / pm["capacity"]["cpu"]
                pm["s"]["load"]["memory"] += (
                    vm["requested"]["memory"] / pm["capacity"]["memory"]
                )
                magnitude_pm[pm["id"]] = get_sort_key_pm(pm, vms, sort_key)
                break

    allocation = [
        {"vm_id": vm_id, "pm_id": vm["allocation"]["pm"]} for vm_id, vm in vms.items()
    ]
    is_on = manage_pms_allocation(pms, allocation)
    return is_on

@profile
def guazzone_bfd(vms, pms, idle_power):
    allocation = {vm_id: {"vm_id": vm_id, "pm_id": None} for vm_id in vms}
    sorted_vms = sorted(
        vms.values(),
        key=lambda vm: (vm["requested"]["cpu"], vm["requested"]["memory"]),
        reverse=True,
    )

    sorted_pms = sorted(
        pms.values(),
        key=lambda pm: (
            not pm["s"]["state"] == 1,  # Powered-on PMs precede powered-off ones
            pm["s"]["time_to_turn_on"],
            -(
                pm["capacity"]["cpu"] - pm["s"]["load"]["cpu"] * pm["capacity"]["cpu"]
            ),  # Decreasing free CPU capacity
            idle_power[pm["id"]],  # Increasing idle power consumption
        ),
    )

    for vm in sorted_vms:
        vm_id = vm["id"]
        if vm["allocation"]["pm"] != -1 or vm["migration"]["to_pm"] != -1:
            continue  # VM is already allocated or migrating
        for pm in sorted_pms:
            if vm["run"]["pm"] == pm["id"]:
                break  # VM is already running on the best PM
            if vm["run"]["pm"] != -1 and pm["s"]["load"]["cpu"] == 0 and pm["s"]["load"]["memory"] == 0:
                continue
            if vm_fits_on_pm(vm, pm):
                pm["s"]["load"]["cpu"] += vm["requested"]["cpu"] / pm["capacity"]["cpu"]
                pm["s"]["load"]["memory"] += (
                    vm["requested"]["memory"] / pm["capacity"]["memory"]
                )
                allocation[vm_id]["pm_id"] = pm["id"]
                break

    algorithms_reallocate_vms(allocation.values(), vms)
    is_on = manage_pms_allocation(pms, allocation.values())
    return is_on


def backup_allocation(non_allocated_vms, pms, idle_power):
    sorted_pms = sorted(
        pms.values(),
        key=lambda pm: (
            pm["s"]["load"]["cpu"],
            pm["s"]["load"]["memory"],
            -idle_power[pm["id"]],
        ),
        reverse=True,
    )

    for vm in non_allocated_vms.values():
        for pm in sorted_pms:
            if vm_fits_on_pm(vm, pm):
                pm["s"]["load"]["cpu"] += vm["requested"]["cpu"] / pm["capacity"]["cpu"]
                pm["s"]["load"]["memory"] += (
                    vm["requested"]["memory"] / pm["capacity"]["memory"]
                )
                vm["allocation"]["pm"] = pm["id"]
                break  # Move to next VM

@profile
def load_balancer(vms, pm_max, pm_min, specific_power_function_database):
    vms.sort(key=lambda vm: (w_load_cpu * vm["requested"]["cpu"] + (1 - w_load_cpu) * vm["requested"]["memory"]), reverse=True)

    for vm in vms:
        remaining_run_time = vm["run"]["total_time"] - vm["run"]["current_time"]
        revenue_per_second = vm["revenue"] / vm["run"]["total_time"]
        if vm["run"]["pm"] == -1 or vm["migration"]["total_time"] > remaining_run_time or vm_exceeds_pm_load(vm, pm_min):
            continue
        load_before_max = (
            w_load_cpu * pm_max["s"]["load"]["cpu"]
            + (1 - w_load_cpu) * pm_max["s"]["load"]["memory"]
        )
        load_before_min = (
            w_load_cpu * pm_min["s"]["load"]["cpu"]
            + (1 - w_load_cpu) * pm_min["s"]["load"]["memory"]
        )
        load_after_max = w_load_cpu * (
            pm_max["s"]["load"]["cpu"]
            - vm["requested"]["cpu"] / pm_max["capacity"]["cpu"]
        ) + (1 - w_load_cpu) * (
            pm_max["s"]["load"]["memory"]
            - vm["requested"]["memory"] / pm_max["capacity"]["memory"]
        )
        load_after_min = w_load_cpu * (
            pm_min["s"]["load"]["cpu"]
            + vm["requested"]["cpu"] / pm_min["capacity"]["cpu"]
        ) + (1 - w_load_cpu) * (
            pm_min["s"]["load"]["memory"]
            + vm["requested"]["memory"] / pm_min["capacity"]["memory"]
        )
        migration_energy_cost = pue * price["energy"] * vm["migration"]["energy"]
        load_cost_before_max = (
            pue
            * price["energy"]
            * evaluate_piecewise_linear_function(
                specific_power_function_database[pm_max["type"]], load_before_max
            )
        )
        load_cost_before_min = (
            pue
            * price["energy"]
            * evaluate_piecewise_linear_function(
                specific_power_function_database[pm_min["type"]], load_before_min
            )
        )
        load_cost_after_max = (
            pue
            * price["energy"]
            * evaluate_piecewise_linear_function(
                specific_power_function_database[pm_max["type"]], load_after_max
            )
        )
        load_cost_after_min = (
            pue
            * price["energy"]
            * evaluate_piecewise_linear_function(
                specific_power_function_database[pm_min["type"]], load_after_min
            )
        )
        costs_before = (
            load_cost_before_max + load_cost_before_min
        ) * remaining_run_time
        costs_after = (
            (load_cost_after_max + load_cost_after_min)
            * (remaining_run_time + vm["migration"]["down_time"])
            + migration_energy_cost
        )
        gain_before = revenue_per_second * remaining_run_time - costs_before
        gain_after = revenue_per_second * remaining_run_time - costs_after
        if gain_after > gain_before:
            if vm["run"]["pm"] != -1:
                vm["migration"]["from_pm"] = pm_max["id"]
                vm["migration"]["to_pm"] = pm_min["id"]
                vm["run"]["pm"] = -1
            elif vm["allocation"]["pm"] != -1:
                vm["allocation"]["pm"] = pm_min["id"]

            pm_min["s"]["load"]["cpu"] += (
                vm["requested"]["cpu"] / pm_min["capacity"]["cpu"]
            )
            pm_min["s"]["load"]["memory"] += (
                vm["requested"]["memory"] / pm_min["capacity"]["memory"]
            )
