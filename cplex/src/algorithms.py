from math import sqrt
from copy import deepcopy
from config import PRINT_TO_CONSOLE

def algorithms_reallocate_vms(allocation, active_vms):
    for a in allocation:
        for vm in active_vms:
            if a['pm_id'] is not None:
                if a['vm_id'] == vm['id']:
                    if vm['run']['pm'] != -1:
                        vm['migration']['from_pm'] = vm['run']['pm']
                        vm['migration']['to_pm'] = a['pm_id']
                        vm['run']['pm'] = -1
                    else:
                        vm['allocation']['pm'] = a['pm_id']

def vm_fits_on_pm(vm, pm):
    if pm['capacity']['cpu'] - (pm['s']['load']['cpu'] * pm['capacity']['cpu'] + vm['requested']['cpu']) >= 0 and \
       pm['capacity']['memory'] - (pm['s']['load']['memory'] * pm['capacity']['memory'] + vm['requested']['memory']) >= 0 and \
       not (pm['s']['state'] == 0 and pm['s']['time_to_turn_off'] > 0):
        if vm['allocation']['pm'] == -1 and vm['migration']['to_pm'] == -1 and vm['run']['pm'] != pm['id']:
            return True 
    return False

def manage_pms_allocation(pms, allocation):
    is_on = [0 for pm in pms]
    for pm in pms:
        # if a PM is turning ON, let it turn ON
        if pm['s']['state'] == 1 and pm['s']['time_to_turn_on'] > 0:
            is_on[pm['id']] = 1
        elif pm['s']['load']['cpu'] > 0 or pm['s']['load']['memory'] > 0:
            is_on[pm['id']] = 1
        else:
            for a in allocation:
                if pm['id'] == a['pm_id']:
                    is_on[pm['id']] = 1

    return is_on

def manage_pms_load(vms, pms):
    is_on = [0 for pm in pms]
    for pm in pms:
        if pm['s']['state'] == 1 and pm['s']['time_to_turn_on'] > 0:
            is_on[pm['id']] = 1
        for vm in vms:
            if vm['allocation']['pm'] == pm['id'] or vm['run']['pm'] == pm['id'] or vm['migration']['from_pm'] == pm['id'] or vm['migration']['to_pm'] == pm['id']:
                is_on[pm['id']] = 1
                break

    return is_on

def best_fit(vms, pms):
    allocation = [{'vm_id': vm['id'], 'pm_id': None} for vm in vms]
    sorted_pms = sorted(pms, key=lambda pm: pm['s']['load']['cpu'], reverse=True)

    for vm in vms:
        for pm in sorted_pms:
            if vm['allocation']['pm'] != -1 or vm['migration']['to_pm'] != -1 or vm['run']['pm'] == pm['id']:
                break
            if vm_fits_on_pm(vm, pm):
                pm['s']['load']['cpu'] += vm['requested']['cpu'] / pm['capacity']['cpu']
                pm['s']['load']['memory'] += vm['requested']['memory'] / pm['capacity']['memory']
                allocation_entry = next((a for a in allocation if a['vm_id'] == vm['id']), None)
                allocation_entry['pm_id'] = pm['id']
                break
    
    algorithms_reallocate_vms(allocation, vms)
    is_on = manage_pms_allocation(pms, allocation)
    
    return is_on

def get_magnitude_pm(pm, vms):
    cpu_load = 0
    memory_load = 0
    for vm in vms:
        if vm['allocation']['pm'] == pm['id'] or vm['run']['pm'] == pm['id']:
            cpu_load += vm['requested']['cpu']
            memory_load += vm['requested']['memory']
    return sqrt(cpu_load**2 + memory_load**2)

def get_magnitude_vm(vm):
    return sqrt(vm['requested']['cpu']**2 + vm['requested']['memory']**2)

def get_vms_on_pm_list(vms, pms):
    vms_on_pm = {}
    for pm in pms:
        vms_on_pm[pm['id']] = []
    for vm in vms:
        if vm['allocation']['pm'] != -1:
            vms_on_pm[vm['allocation']['pm']].append(vm)
        elif vm['run']['pm'] != -1:
            vms_on_pm[vm['run']['pm']].append(vm)
    return vms_on_pm

def shi_migration(vms, pms, failed_migrations_limit=None):
    vms_on_pm = get_vms_on_pm_list(vms, pms)
    magnitude_pm = {}
    magnitude_vm = {vm['id']: get_magnitude_vm(vm) for vm in vms}
    failed_migrations = 0

    for pm in pms:
        magnitude_pm[pm['id']] = get_magnitude_pm(pm, vms)
    sorted_pms = sorted(pms, key=lambda pm: magnitude_pm[pm['id']], reverse=True)

    for pm in reversed(sorted_pms):
        # Backup VMs and PMs
        vms_copy = deepcopy(vms)
        pms_copy = deepcopy(pms)
        vms_on_pm[pm['id']].sort(key=lambda vm: magnitude_vm[vm['id']], reverse=True)

        for vm in vms_on_pm[pm['id']]:
            if vm['allocation']['pm'] != -1 or vm['migration']['to_pm'] != -1:
                continue
            for pm_candidate in sorted_pms:
                if pm_candidate == pm:
                    break
                if pm_candidate['s']['state'] == 0 or pm_candidate['s']['time_to_turn_on'] > 0:
                    continue
                if vm_fits_on_pm(vm, pm_candidate):
                    vm['migration']['from_pm'] = vm['run']['pm']
                    vm['migration']['to_pm'] = pm_candidate['id']
                    pm_candidate['s']['load']['cpu'] += vm['requested']['cpu'] / pm_candidate['capacity']['cpu']
                    pm_candidate['s']['load']['memory'] += vm['requested']['memory'] / pm_candidate['capacity']['memory']
                    vms_on_pm[vm['run']['pm']].remove(vm)
                    vm['run']['pm'] = -1
                    magnitude_pm[pm['id']] = get_magnitude_pm(pm, vms)

                    vms_on_pm[pm_candidate['id']].append(vm)
                    magnitude_pm[pm_candidate['id']] = get_magnitude_pm(pm_candidate, vms)
                    sorted_pms.sort(key=lambda pm: magnitude_pm[pm['id']], reverse=True)
                    break
        
        if magnitude_pm[pm['id']] != 0:
            vms = deepcopy(vms_copy)
            pms = deepcopy(pms_copy)
            vms_on_pm = get_vms_on_pm_list(vms, pms)
            magnitude_pm[pm['id']] = get_magnitude_pm(pm, vms)
            sorted_pms = sorted(pms, key=lambda pm: magnitude_pm[pm['id']], reverse=True)
            failed_migrations += 1
        
        if failed_migrations_limit and failed_migrations >= failed_migrations_limit:
            print(f"Failed to migrate {failed_migrations} VMs. Limit reached.")
            break

    is_on = manage_pms_load(vms, pms)

    return is_on

def shi_online(vms, pms):
    magnitude_pm = {}
    
    for pm in pms:
        magnitude_pm[pm['id']] = get_magnitude_pm(pm, vms)
    sorted_pms = sorted(pms, key=lambda pm: magnitude_pm[pm['id']], reverse=True)

    for pm in sorted_pms:
        for vm in vms:
            if vm_fits_on_pm(vm, pm):
                vm['allocation']['pm'] = pm['id']
                if PRINT_TO_CONSOLE:
                    print(f"VM {vm['id']} allocated to PM {pm['id']}")
                pm['s']['load']['cpu'] += vm['requested']['cpu'] / pm['capacity']['cpu']
                pm['s']['load']['memory'] += vm['requested']['memory'] / pm['capacity']['memory']
                magnitude_pm[pm['id']] = get_magnitude_pm(pm, vms)
                sorted_pms = sorted(pms, key=lambda pm: magnitude_pm[pm['id']], reverse=True)
                vms.remove(vm)
    allocation = [{'vm_id': vm['id'], 'pm_id': vm['allocation']['pm']} for vm in vms]
    is_on = manage_pms_allocation(pms, allocation)
    
    return is_on

            
def guazzone_bfd(active_vms, pms, power_idle):
    allocation = [{'vm_id': vm['id'], 'pm_id': None} for vm in active_vms]
    
    sorted_vms = sorted(active_vms, key=lambda vm: vm['requested']['cpu'], reverse=True)
    
    for vm in sorted_vms:
        vm_allocated = False  # Flag to indicate if the VM has been allocated
        
        sorted_pms = sorted(pms, key=lambda pm: (
            not pm['s']['state'] == 1,  # Powered-on PMs precede powered-off ones (False < True)
            pm['s']['time_to_turn_on'],
            -(pm['capacity']['cpu'] - pm['s']['load']['cpu'] * pm['capacity']['cpu']),  # Decreasing free CPU capacity
            power_idle[pm['id']]  # Increasing idle power consumption
        ))

        for pm in sorted_pms:
            if vm['allocation']['pm'] != -1 or vm['migration']['to_pm'] != -1:
                break
            if vm_fits_on_pm(vm, pm):
                pm['s']['load']['cpu'] += vm['requested']['cpu'] / pm['capacity']['cpu']
                pm['s']['load']['memory'] += vm['requested']['memory'] / pm['capacity']['memory']
                allocation_entry = next((a for a in allocation if a['vm_id'] == vm['id']), None)
                allocation_entry['pm_id'] = pm['id']
                
                vm_allocated = True  # Set the flag to True
                break  # Exit inner loop after successfully allocating VM to PM
        if vm_allocated:
            break  # Exit outer loop if VM has been allocated
    
    algorithms_reallocate_vms(allocation, active_vms)
    is_on = manage_pms_allocation(pms, allocation)
    
    return is_on