import random
import heapq

EPSILON = 0.00001

def filter_dict_randomly(dict, n):
    if n >= len(dict):
        return dict.copy()
    else:
        keys = random.sample(list(dict), n)
        return {k: dict[k] for k in keys}

def split_dict_randomly(dict, chunk_size):
    keys = list(dict.keys())
    random.shuffle(keys)
    for i in range(0, len(keys), chunk_size):
        yield {k: dict[k] for k in keys[i:i + chunk_size]}

def filter_full_pms(physical_machines):
    # Create a list of PM IDs to remove
    pm_ids_to_remove = [
        pm_id for pm_id, pm in physical_machines.items()
        if pm['s']['load']['cpu'] >= 1 - EPSILON or pm['s']['load']['memory'] >= 1 - EPSILON
    ]
    
    # Remove the PMs from the dictionary
    for pm_id in pm_ids_to_remove:
        del physical_machines[pm_id]

def filter_full_and_migrating_pms(active_vms, physical_machines):
    # Collect PM IDs with ongoing migrations
    pms_with_ongoing_migrations = {
        vm['migration']['to_pm'] for vm in active_vms.values() if vm['migration']['to_pm'] != -1
    }.union({
        vm['migration']['from_pm'] for vm in active_vms.values() if vm['migration']['from_pm'] != -1
    })
    
    # Create a list of PM IDs to remove
    pm_ids_to_remove = [
        pm_id for pm_id, pm in physical_machines.items()
        if pm_id in pms_with_ongoing_migrations or pm['s']['load']['cpu'] >= 1 - EPSILON or pm['s']['load']['memory'] >= 1 - EPSILON
    ]
    
    # Remove the PMs from the dictionary
    for pm_id in pm_ids_to_remove:
        del physical_machines[pm_id]

def filter_fragmented_pms(physical_machines, limit=100):
    if len(physical_machines) > limit:
        # Define the fragmentation key function
        def fragmentation(pm):
            cpu_load = pm['s']['load']['cpu'] * pm['capacity']['cpu']
            mem_load = pm['s']['load']['memory'] * pm['capacity']['memory']
            return (
                max(cpu_load, mem_load), 
                min(cpu_load, mem_load)
            )
        
        # Find the 'limit' PMs with the lowest fragmentation
        lowest_fragmentation_pms = heapq.nsmallest(limit, physical_machines.values(), key=fragmentation)
        
        # Create a set of IDs to keep
        keep_ids = {pm['id'] for pm in lowest_fragmentation_pms}
        
        # Remove PMs not in keep_ids
        for pm_id in list(physical_machines.keys()):
            if pm_id not in keep_ids:
                del physical_machines[pm_id]

def filter_vms_on_pms(vms, physical_machines):
    pm_ids = set(physical_machines.keys())
    filtered_vms = {}

    for vm_id, vm in vms.items():
        allocation_pm = vm['allocation']['pm']
        run_pm = vm['run']['pm']
        migration_from_pm = vm['migration']['from_pm']
        migration_to_pm = vm['migration']['to_pm']
        
        # Check if VM is unallocated or any of its PMs are in the pm_ids set
        if (
            allocation_pm == -1 and run_pm == -1 and migration_from_pm == -1 and migration_to_pm == -1
        ) or (
            allocation_pm in pm_ids or run_pm in pm_ids or migration_from_pm in pm_ids or migration_to_pm in pm_ids
        ):
            filtered_vms[vm_id] = vm
                
    return filtered_vms
