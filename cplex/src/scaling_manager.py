from math import sqrt, ceil
from weights import safety_margin
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

def scaling_manager(predicted_workload_cpu, predicted_workload_memory, pms, idle_power, non_allocated_workload_cpu, non_allocated_workload_memory, future_load, is_on):
    total_cpu_capacity = 0
    total_memory_capacity = 0
    turned_on_pms = []

    sorted_pms = sorted(pms, key=lambda pm: pm_sort_key(pm, idle_power), reverse=True)
    scale_up_margin_cpu = predicted_workload_cpu * (1 + safety_margin) + non_allocated_workload_cpu
    scale_up_margin_memory = predicted_workload_memory * (1 + safety_margin) + non_allocated_workload_memory
    
    # Calculate the total capacity of the physical machines that are on
    for pm in sorted_pms:
        if is_on[pm['id']]:
            total_cpu_capacity += pm['capacity']['cpu'] - future_load[0][pm['id']]
            total_memory_capacity += pm['capacity']['memory'] - future_load[1][pm['id']]
    print(f"Total CPU capacity: {total_cpu_capacity}, Total memory capacity: {total_memory_capacity}")
    # Turn on physical machines that are needed
    for pm in sorted_pms:
        if total_cpu_capacity >= scale_up_margin_cpu and total_memory_capacity >= scale_up_margin_memory:
            print(f"Total CPU capacity: {total_cpu_capacity}, Total memory capacity: {total_memory_capacity}")
            print(f"Scale up margin CPU: {scale_up_margin_cpu}, Scale up margin memory: {scale_up_margin_memory}")
            break
        elif not is_on[pm['id']]:
            total_cpu_capacity, total_memory_capacity = turn_on(pm, total_cpu_capacity, total_memory_capacity, is_on)
            turned_on_pms.append(pm['id'])

    # If extra physical machines have been turned on during this time step, turn them off
    for pm in reversed(sorted_pms):
        if pm['id'] in turned_on_pms:
            if pm['s']['load']['cpu'] <= 0 and pm['s']['load']['memory'] <= 0:
                if total_cpu_capacity - pm['capacity']['cpu'] >= scale_up_margin_cpu and total_memory_capacity - pm['capacity']['memory'] >= scale_up_margin_memory:
                    total_cpu_capacity, total_memory_capacity = turn_off(pm, total_cpu_capacity, total_memory_capacity, is_on)
    return is_on

def launch_scaling_manager(active_vms, physical_machines, idle_power, actual_time_step, start_time_str, predictions, use_workload_predictor, predictor_model_path, workload_prediction_file, time_step):
    max_time_to_turn_on = max([pm['s']['time_to_turn_on'] for pm in physical_machines])
    max_step = max(ceil(max_time_to_turn_on / time_step), 1)
    time_window = max_step * time_step 

    non_allocated_workload_cpu = 0
    non_allocated_workload_memory = 0
    
    for vm in active_vms:
        if vm['allocation']['pm'] == -1:
            non_allocated_workload_cpu += vm['requested']['cpu']
            non_allocated_workload_memory += vm['requested']['memory']

    future_loads = calculate_future_load(physical_machines, active_vms, actual_time_step, time_window, time_step)
    
    is_on = [1 if pm['s']['load']['cpu'] > 0 or pm['s']['load']['memory'] > 0 else 0 for pm in physical_machines]

    if use_workload_predictor:
        for step in range(1, max_step + 1):
            predicted_workload_cpu, predicted_workload_memory = predict_workload(actual_time_step, actual_time_step + step, start_time_str, predictions, predictor_model_path, workload_prediction_file, time_step)
            future_load = future_loads[step - 1]

            is_on = scaling_manager(predicted_workload_cpu, predicted_workload_memory, physical_machines, idle_power, non_allocated_workload_cpu, non_allocated_workload_memory, future_load, is_on)

            if step == 1:
                print(f"Non-allocated workload: CPU = {non_allocated_workload_cpu}, Memory = {non_allocated_workload_memory}")
                non_allocated_workload_cpu = 0
                non_allocated_workload_memory = 0
    else:
        is_on = scaling_manager(0, 0, physical_machines, idle_power, non_allocated_workload_cpu, non_allocated_workload_memory, future_loads[0], is_on)
    
    return is_on