import heapq
from itertools import islice
from weights import EPSILON, w_load_cpu


try:
    profile  # type: ignore
except NameError:

    def profile(func):
        return func


def filter_full_pms_dict(physical_machines):
    # Create a list of PM IDs to remove
    pm_ids_to_remove = [
        pm_id
        for pm_id, pm in physical_machines.items()
        if pm["s"]["load"]["cpu"] >= 1 - EPSILON
        or pm["s"]["load"]["memory"] >= 1 - EPSILON
    ]

    # Remove the PMs from the dictionary
    for pm_id in pm_ids_to_remove:
        del physical_machines[pm_id]


def is_pm_full(pm):
    return (
        pm["s"]["load"]["cpu"] >= 1 - EPSILON
        or pm["s"]["load"]["memory"] >= 1 - EPSILON
    )


def filter_migrating_pms(active_vms, physical_machines):
    # Collect PM IDs with ongoing migrations
    pms_with_ongoing_migrations = set()
    for vm in active_vms.values():
        if vm["migration"]["to_pm"] != -1:
            pms_with_ongoing_migrations.add(vm["migration"]["to_pm"])
        if vm["migration"]["from_pm"] != -1:
            pms_with_ongoing_migrations.add(vm["migration"]["from_pm"])

    for pm_id in pms_with_ongoing_migrations:
        if pm_id in physical_machines:
            del physical_machines[pm_id]


@profile
def filter_full_and_migrating_pms(active_vms, physical_machines):
    # Collect PM IDs with ongoing migrations
    pms_with_ongoing_migrations = set()
    for vm in active_vms.values():
        if vm["migration"]["to_pm"] != -1:
            pms_with_ongoing_migrations.add(vm["migration"]["to_pm"])
        if vm["migration"]["from_pm"] != -1:
            pms_with_ongoing_migrations.add(vm["migration"]["from_pm"])

    # Create a list of PM IDs to remove
    pm_ids_to_remove = [
        pm_id
        for pm_id, pm in physical_machines.items()
        if pm_id in pms_with_ongoing_migrations
        or pm["s"]["load"]["cpu"] >= 1 - EPSILON
        or pm["s"]["load"]["memory"] >= 1 - EPSILON
    ]

    # Remove the PMs from the dictionary
    for pm_id in pm_ids_to_remove:
        del physical_machines[pm_id]


def filter_fragmented_pms(physical_machines, limit=100):
    if len(physical_machines) > limit:
        highest_fragmentation_pms = heapq.nlargest(
            limit, physical_machines.values(), key=sort_key_load
        )

        return {pm["id"]: pm for pm in highest_fragmentation_pms}
    else:
        return physical_machines


def filter_pms_to_turn_off_after_migration(
    physical_machines, pms_to_turn_off_after_migration
):
    for pm_id in pms_to_turn_off_after_migration.keys():
        if pm_id in physical_machines:
            del physical_machines[pm_id]


def filter_vms_on_pms(vms, physical_machines):
    pm_ids = set(physical_machines.keys())
    filtered_vms = {}

    for vm_id, vm in vms.items():
        allocation_pm = vm["allocation"]["pm"]
        run_pm = vm["run"]["pm"]
        migration_from_pm = vm["migration"]["from_pm"]
        migration_to_pm = vm["migration"]["to_pm"]

        if (
            allocation_pm in pm_ids
            or run_pm in pm_ids
            or migration_from_pm in pm_ids
            or migration_to_pm in pm_ids
        ):
            filtered_vms[vm_id] = vm

    return filtered_vms


def filter_vms_on_pms_and_non_allocated(vms, physical_machines, scheduled_vms):
    pm_ids = set(physical_machines.keys())
    filtered_vms = {}

    for vm_id, vm in vms.items():
        allocation_pm = vm["allocation"]["pm"]
        run_pm = vm["run"]["pm"]
        migration_from_pm = vm["migration"]["from_pm"]
        migration_to_pm = vm["migration"]["to_pm"]

        # Check if VM is unallocated or any of its PMs are in the pm_ids set
        if (
            allocation_pm == -1
            and run_pm == -1
            and migration_from_pm == -1
            and migration_to_pm == -1
        ) or (
            allocation_pm in pm_ids
            or run_pm in pm_ids
            or migration_from_pm in pm_ids
            or migration_to_pm in pm_ids
        ):
            filtered_vms[vm_id] = vm

    for vm_list in scheduled_vms.values():
        for scheduled_vm in vm_list:
            if scheduled_vm["id"] in filtered_vms:
                del filtered_vms[scheduled_vm["id"]]

    return filtered_vms


def get_fragmented_pms_list(physical_machines, limit=100):
    if len(physical_machines) > limit:
        return heapq.nlargest(limit, physical_machines.values(), key=sort_key_load)
    else:
        return list(physical_machines.values())


def sort_key_specific_power_capacity(pm, specific_power_function_database):
    return (
        specific_power_function_database[pm["type"]]["0.0"]
        / (
            w_load_cpu * pm["capacity"]["cpu"]
            + (1 - w_load_cpu) * pm["capacity"]["memory"]
        ),
        pm["s"]["time_to_turn_on"],
    )


def sort_key_load(pm):
    return (
        -max(pm["s"]["load"]["cpu"], pm["s"]["load"]["memory"]),
        -min(pm["s"]["load"]["cpu"], pm["s"]["load"]["memory"]),
    )


def sort_key_specific_power_load(pm, specific_power_function_database):
    return (
        specific_power_function_database[pm["type"]]["0.0"],
        -max(pm["s"]["load"]["cpu"], pm["s"]["load"]["memory"]),
        -min(pm["s"]["load"]["cpu"], pm["s"]["load"]["memory"]),
    )


def split_dict_sorted(
    d, max_elements_per_subset, sort_key, specific_power_function_database
):
    items_with_keys = sorted(
        (
            (sort_key(value, specific_power_function_database), key, value)
            for key, value in d.items()
        )
    )

    # Calculate the number of subsets
    n = len(items_with_keys)
    subsets = []

    # Split the sorted items into subsets
    for i in range(0, n, max_elements_per_subset):
        subset_items = items_with_keys[i : i + max_elements_per_subset]
        subset = {key: value for _, key, value in subset_items}
        subsets.append(subset)

    return subsets


def split_dict_unsorted(d, max_size):
    it = iter(d.items())
    for _ in range(0, len(d), max_size):
        yield dict(islice(it, max_size))
