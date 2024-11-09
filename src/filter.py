import random
import heapq

EPSILON = 0.00001


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


def filter_full_and_migrating_pms(active_vms, physical_machines):
    # Collect PM IDs with ongoing migrations
    pms_with_ongoing_migrations = {
        vm["migration"]["to_pm"]
        for vm in active_vms.values()
        if vm["migration"]["to_pm"] != -1
    }.union(
        {
            vm["migration"]["from_pm"]
            for vm in active_vms.values()
            if vm["migration"]["from_pm"] != -1
        }
    )

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
        keep_ids = {pm["id"] for pm in highest_fragmentation_pms}

        for pm_id in list(physical_machines.keys()):
            if pm_id not in keep_ids:
                del physical_machines[pm_id]


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


def filter_vms_on_pms_and_non_allocated(vms, physical_machines):
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

    return filtered_vms


def get_fragmented_pms_list(physical_machines, limit=100):
    if len(physical_machines) > limit:
        return heapq.nlargest(limit, physical_machines.values(), key=sort_key_load)
    else:
        return list(physical_machines.values())


def sort_key_capacity(pm):
    return (
        -pm["features"]["speed"],
        -pm["capacity"]["cpu"],
        -pm["capacity"]["memory"],
        pm["s"]["time_to_turn_on"],
    )


def sort_key_load(pm):
    return (
        -max(pm["s"]["load"]["cpu"], pm["s"]["load"]["memory"]),
        -min(pm["s"]["load"]["cpu"], pm["s"]["load"]["memory"]),
    )


def split_dict_sorted(d, max_elements_per_subset, sort_key):
    n = len(d)
    num_subsets = max(1, (n + max_elements_per_subset - 1) // max_elements_per_subset)
    subsets = []

    # Create a list of tuples with sort_key for min-heap
    items_with_keys = [(sort_key(value), key, value) for key, value in d.items()]
    heapq.heapify(items_with_keys)  # Transform the list into a heap in O(n) time

    for _ in range(num_subsets):
        subset = {}
        for _ in range(max_elements_per_subset):
            if items_with_keys:
                _, key, value = heapq.heappop(items_with_keys)
                subset[key] = value
            else:
                break  # No more items to pop
        subsets.append(subset)

    return subsets


def split_dict_randomly(d, max_elements_per_subset):
    keys = list(d.keys())
    random.shuffle(keys)  # Shuffle the keys to ensure randomness
    n = len(keys)
    # Calculate the number of subsets needed
    num_subsets = max(1, (n + max_elements_per_subset - 1) // max_elements_per_subset)
    # Calculate the approximate size per subset
    size_per_subset = (n + num_subsets - 1) // num_subsets  # Ceiling division
    subsets = []
    for i in range(0, n, size_per_subset):
        subset_keys = keys[i : i + size_per_subset]
        subset_dict = {k: d[k] for k in subset_keys}
        subsets.append(subset_dict)
    return subsets
