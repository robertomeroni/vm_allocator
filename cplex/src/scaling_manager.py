from math import sqrt, ceil
from weights import safety_margin, price, energy, pue
from utils import calculate_future_load
from workload_predictor import predict_workload

def pm_sort_key(pm, idle_power):
    pm['magnitude'] = sqrt(pm['capacity']['cpu']**2 + pm['capacity']['memory']**2)
    return (pm['features']['speed'], pm['magnitude'] / idle_power[pm['id']])

def turn_on(pm, total_cpu_capacity, total_memory_capacity, pms_states):
    pms_states[pm['id']] = 1
    total_cpu_capacity += pm['capacity']['cpu']
    total_memory_capacity += pm['capacity']['memory']
    return total_cpu_capacity, total_memory_capacity

def turn_off(pm, total_cpu_capacity, total_memory_capacity, pms_states):
    pms_states[pm['id']] = 0
    total_cpu_capacity -= pm['capacity']['cpu']
    total_memory_capacity -= pm['capacity']['memory']
    return total_cpu_capacity, total_memory_capacity

def check_min_profitability(predicted_workload_cpu, predicted_workload_memory, idle_power, non_allocated_workload_cpu, non_allocated_workload_memory):
    total_profit = (non_allocated_workload_cpu + predicted_workload_cpu) * price['cpu'] + (non_allocated_workload_memory + predicted_workload_memory) * price['memory']

    if min(idle_power) * energy['cost'] * pue > total_profit:
        print(f"Not enough profit to turn on a physical machine. Total profit: {total_profit}, Min idle power price: {min(idle_power) * energy['cost'] * pue}")
        return False
    print(f"Enough profit to turn on a physical machine. Total profit: {total_profit}, Min idle power price: {min(idle_power) * energy['cost'] * pue}")
    return True

def scaling_manager(predicted_workload_cpu, predicted_workload_memory, pms, idle_power, non_allocated_workload_cpu, non_allocated_workload_memory, future_load, is_on, max_vm_cpu_requested_cpu, max_vm_cpu_requested_memory, max_vm_memory_requested_cpu, max_vm_memory_requested_memory):
    total_cpu_capacity = 0
    total_memory_capacity = 0
    max_requested_cpu_satisfied = False
    max_requested_memory_satisfied = False

    turned_on_pms = []
    satisfying_max_cpu_pms = []
    satisfying_max_memory_pms = []

    sorted_pms = sorted(pms, key=lambda pm: pm_sort_key(pm, idle_power), reverse=True)
    scale_up_margin_cpu = predicted_workload_cpu * (1 + safety_margin) + non_allocated_workload_cpu
    scale_up_margin_memory = predicted_workload_memory * (1 + safety_margin) + non_allocated_workload_memory
    
    # Calculate the total capacity of the physical machines that are on
    for pm in sorted_pms:
        if is_on[pm['id']]:
            pm_free_cpu = pm['capacity']['cpu'] - future_load[0][pm['id']] * pm['capacity']['cpu']
            pm_free_memory = pm['capacity']['memory'] - future_load[1][pm['id']] * pm['capacity']['memory']
            print(f"PM ID: {pm['id']}, is on: {is_on[pm['id']]}")
            print(f"PM free CPU: {pm_free_cpu}, PM free memory: {pm_free_memory}")
            print(f"future_load[0][pm['id']]: {future_load[0][pm['id']]}, future_load[1][pm['id']]: {future_load[1][pm['id']]}")
            total_cpu_capacity += pm_free_cpu
            total_memory_capacity += pm_free_memory
            if pm_free_cpu >= max_vm_cpu_requested_cpu and pm_free_memory >= max_vm_cpu_requested_memory:
                max_requested_cpu_satisfied = True
                satisfying_max_cpu_pms.append(pm['id'])
            if pm_free_cpu >= max_vm_memory_requested_cpu and pm_free_memory >= max_vm_memory_requested_memory:
                max_requested_memory_satisfied = True
                satisfying_max_memory_pms.append(pm['id'])
    print(f"Total CPU capacity of turned on PMs: {total_cpu_capacity}, Total memory capacity of turned on PMs: {total_memory_capacity}")
    
    # Turn on physical machines that are needed
    for pm in sorted_pms:
        if total_cpu_capacity >= scale_up_margin_cpu and total_memory_capacity >= scale_up_margin_memory and max_requested_cpu_satisfied and max_requested_memory_satisfied:
            print(f"Total CPU capacity: {total_cpu_capacity}, Total memory capacity: {total_memory_capacity}")
            print(f"Scale up margin CPU: {scale_up_margin_cpu}, Scale up margin memory: {scale_up_margin_memory}")
            break
        elif not is_on[pm['id']]:
            total_cpu_capacity, total_memory_capacity = turn_on(pm, total_cpu_capacity, total_memory_capacity, is_on)
            if pm['capacity']['cpu'] >= max_vm_cpu_requested_cpu and pm['capacity']['memory'] >= max_vm_cpu_requested_memory:
                max_requested_cpu_satisfied = True
                satisfying_max_cpu_pms.append(pm['id'])
            if pm['capacity']['cpu'] >= max_vm_memory_requested_cpu and pm['capacity']['memory'] >= max_vm_memory_requested_memory:
                max_requested_memory_satisfied = True
                satisfying_max_memory_pms.append(pm['id'])
            turned_on_pms.append(pm['id'])
            print(f"PM ID: {pm['id']} turned on")

    # If extra physical machines have been turned on during this time step, turn them off
    for pm in reversed(sorted_pms):
        if pm['id'] in turned_on_pms and (pm['id'] not in satisfying_max_cpu_pms or len(satisfying_max_cpu_pms) > 1) and (pm['id'] not in satisfying_max_memory_pms or len(satisfying_max_memory_pms) > 1):
            if pm['s']['load']['cpu'] <= 0 and pm['s']['load']['memory'] <= 0:
                if total_cpu_capacity - pm['capacity']['cpu'] >= scale_up_margin_cpu and total_memory_capacity - pm['capacity']['memory'] >= scale_up_margin_memory:
                    total_cpu_capacity, total_memory_capacity = turn_off(pm, total_cpu_capacity, total_memory_capacity, is_on)
    return is_on

def launch_scaling_manager(active_vms, non_allocated_vms, physical_machines, idle_power, actual_time_step, start_time_str, predictions, use_workload_predictor, predictor_model_path, workload_prediction_file, time_step):
    if non_allocated_vms:
        max_vm_cpu = max(non_allocated_vms, key=lambda vm: vm['requested']['cpu'])
        max_vm_memory = max(non_allocated_vms, key=lambda vm: vm['requested']['memory'])
        max_vm_cpu_requested_cpu = max_vm_cpu['requested']['cpu']
        max_vm_cpu_requested_memory = max_vm_cpu['requested']['memory']
        max_vm_memory_requested_cpu = max_vm_memory['requested']['cpu']
        max_vm_memory_requested_memory = max_vm_memory['requested']['memory']
    else:
        max_vm_cpu_requested_cpu = 0
        max_vm_cpu_requested_memory = 0
        max_vm_memory_requested_cpu = 0
        max_vm_memory_requested_memory = 0
    
    max_time_to_turn_on = max([pm['s']['time_to_turn_on'] for pm in physical_machines])
    max_step = max(ceil(max_time_to_turn_on / time_step), 1)
    time_window = max_step * time_step 

    non_allocated_workload_cpu = 0
    non_allocated_workload_memory = 0
    
    for vm in active_vms:
        if vm['allocation']['pm'] == -1 and vm['run']['pm'] == -1 and vm['migration']['from_pm'] == -1 and vm['migration']['to_pm'] == -1:
            non_allocated_workload_cpu += vm['requested']['cpu']
            non_allocated_workload_memory += vm['requested']['memory']

    future_loads = calculate_future_load(physical_machines, active_vms, actual_time_step, time_window, time_step)
    
    is_on = [1 if pm['s']['load']['cpu'] > 0 or pm['s']['load']['memory'] > 0 or (pm['s']['state'] == 1 and pm['s']['time_to_turn_on'] > 0) else 0 for pm in physical_machines]

    if use_workload_predictor:
        for step in range(1, max_step + 1):
            predicted_workload_cpu, predicted_workload_memory = predict_workload(actual_time_step, actual_time_step + step, start_time_str, predictions, predictor_model_path, workload_prediction_file, time_step)
            future_load = future_loads[step - 1]

            if predicted_workload_cpu > 0 or predicted_workload_memory > 0 or non_allocated_workload_cpu > 0 or non_allocated_workload_memory > 0:
                if check_min_profitability(predicted_workload_cpu, predicted_workload_memory, idle_power, non_allocated_workload_cpu, non_allocated_workload_memory):
                    is_on = scaling_manager(predicted_workload_cpu, predicted_workload_memory, physical_machines, idle_power, non_allocated_workload_cpu, non_allocated_workload_memory, future_load, is_on, max_vm_cpu_requested_cpu, max_vm_cpu_requested_memory, max_vm_memory_requested_cpu, max_vm_memory_requested_memory)

            if step == 1:
                print(f"Non-allocated workload: CPU = {non_allocated_workload_cpu}, Memory = {non_allocated_workload_memory}")
                non_allocated_workload_cpu = 0
                non_allocated_workload_memory = 0
    else:
        if non_allocated_workload_cpu > 0 or non_allocated_workload_memory > 0:
            if check_min_profitability(0, 0, idle_power, non_allocated_workload_cpu, non_allocated_workload_memory):
                is_on = scaling_manager(0, 0, physical_machines, idle_power, non_allocated_workload_cpu, non_allocated_workload_memory, future_loads[0], is_on, max_vm_cpu_requested_cpu, max_vm_cpu_requested_memory, max_vm_memory_requested_cpu, max_vm_memory_requested_memory)
    
    return is_on