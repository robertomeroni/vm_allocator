from math import sqrt, ceil
from weights import safety_margin, price, energy, pue
from utils import calculate_future_load
from workload_predictor import predict_workload

try:
    profile # type: ignore
except NameError:
    def profile(func):
        return func

def pm_sort_key(pm, idle_power):
    return (pm['features']['speed'], sqrt(pm['capacity']['cpu']**2 + pm['capacity']['memory']**2) / idle_power)

def turn_on(pm, total_cpu_capacity, total_memory_capacity, is_on):
    is_on[pm['id']] = 1
    total_cpu_capacity += pm['capacity']['cpu']
    total_memory_capacity += pm['capacity']['memory']
    return total_cpu_capacity, total_memory_capacity

def turn_off(pm, total_cpu_capacity, total_memory_capacity, is_on):
    is_on[pm['id']] = 0
    total_cpu_capacity -= pm['capacity']['cpu']
    total_memory_capacity -= pm['capacity']['memory']
    return total_cpu_capacity, total_memory_capacity

def check_min_profitability(predicted_workload_cpu, predicted_workload_memory, idle_power, non_allocated_workload_cpu, non_allocated_workload_memory):
    total_profit = (non_allocated_workload_cpu + predicted_workload_cpu) * price['cpu'] + (non_allocated_workload_memory + predicted_workload_memory) * price['memory']

    min_idle_power_price = min(idle_power.values()) * energy['cost'] * pue
    if min_idle_power_price > total_profit:
        print(f"Not enough profit to turn on a physical machine. Total profit: {total_profit}, Min idle power price: {min_idle_power_price}")
        return False
    return True

@profile
def scaling_manager(predicted_workload_cpu, predicted_workload_memory, pms, idle_power, non_allocated_workload_cpu, non_allocated_workload_memory, future_load, is_on, max_vm_cpu_requested_cpu, max_vm_cpu_requested_memory, max_vm_memory_requested_cpu, max_vm_memory_requested_memory):
    total_cpu_capacity = 0
    total_memory_capacity = 0
    max_requested_cpu_satisfied = False
    max_requested_memory_satisfied = False

    turned_on_pms = []
    on_and_empty_pms = []
    satisfying_max_cpu_pms = []
    satisfying_max_memory_pms = []

    # Sorted PMs
    sorted_pms = sorted(pms.values(), key=lambda pm: pm_sort_key(pm, idle_power[pm['id']]), reverse=True)
    scale_up_margin_cpu = (predicted_workload_cpu + non_allocated_workload_cpu) * safety_margin
    scale_up_margin_memory = (predicted_workload_memory + non_allocated_workload_memory) * safety_margin
    
    if scale_up_margin_cpu <= 0 and scale_up_margin_memory <= 0:
        for pm_id, pm in pms.items():
            if pm['s']['time_to_turn_on'] == 0 and pm['s']['load']['cpu'] <= 0 and pm['s']['load']['memory'] <= 0:
                is_on[pm_id] = 0
        return
    
    # Calculate the total capacity of the physical machines that are on
    for pm in sorted_pms:
        pm_id = pm['id']
        if pm['s']['state'] == 1:
            if pm['s']['time_to_turn_on'] == 0 and pm['s']['load']['cpu'] <= 0 and pm['s']['load']['memory'] <= 0:
                on_and_empty_pms.append(pm_id)

            pm_free_cpu = pm['capacity']['cpu'] - future_load[0][pm_id] * pm['capacity']['cpu']
            pm_free_memory = pm['capacity']['memory'] - future_load[1][pm_id] * pm['capacity']['memory']
            if pm_free_cpu <= 0 or pm_free_memory <= 0:
                continue
            total_cpu_capacity += pm_free_cpu
            total_memory_capacity += pm_free_memory
            if pm_free_cpu >= max_vm_cpu_requested_cpu and pm_free_memory >= max_vm_cpu_requested_memory:
                max_requested_cpu_satisfied = True
                satisfying_max_cpu_pms.append(pm_id)
            if pm_free_cpu >= max_vm_memory_requested_cpu and pm_free_memory >= max_vm_memory_requested_memory:
                max_requested_memory_satisfied = True
                satisfying_max_memory_pms.append(pm_id)
    
    # Turn on physical machines that are needed
    for pm in sorted_pms:
        pm_id = pm['id']
        if total_cpu_capacity >= scale_up_margin_cpu and total_memory_capacity >= scale_up_margin_memory and max_requested_cpu_satisfied and max_requested_memory_satisfied:
            break
        elif pm['s']['state'] == 0:
            if pm['s']['time_to_turn_off'] > 0:
                continue
            total_cpu_capacity, total_memory_capacity = turn_on(pm, total_cpu_capacity, total_memory_capacity, is_on)
            if pm['capacity']['cpu'] >= max_vm_cpu_requested_cpu and pm['capacity']['memory'] >= max_vm_cpu_requested_memory:
                max_requested_cpu_satisfied = True
                satisfying_max_cpu_pms.append(pm_id)
            if pm['capacity']['cpu'] >= max_vm_memory_requested_cpu and pm['capacity']['memory'] >= max_vm_memory_requested_memory:
                max_requested_memory_satisfied = True
                satisfying_max_memory_pms.append(pm_id)
            turned_on_pms.append(pm_id)

    # If extra physical machines have been turned on during this time step, turn them off
    for pm_id in turned_on_pms:
        if (pm_id not in satisfying_max_cpu_pms or len(satisfying_max_cpu_pms) > 1) and (pm_id not in satisfying_max_memory_pms or len(satisfying_max_memory_pms) > 1):
            if total_cpu_capacity - pm['capacity']['cpu'] >= scale_up_margin_cpu and total_memory_capacity - pm['capacity']['memory'] >= scale_up_margin_memory:
                    total_cpu_capacity, total_memory_capacity = turn_off(pms[pm_id], total_cpu_capacity, total_memory_capacity, is_on)
    
    # If they are not needed, turn off physical machines that are on and empty
    for pm_id in on_and_empty_pms:
        if (pm_id not in satisfying_max_cpu_pms or len(satisfying_max_cpu_pms) > 1) and (pm_id not in satisfying_max_memory_pms or len(satisfying_max_memory_pms) > 1):
            if total_cpu_capacity - pm['capacity']['cpu'] >= scale_up_margin_cpu and total_memory_capacity - pm['capacity']['memory'] >= scale_up_margin_memory:
                total_cpu_capacity, total_memory_capacity = turn_off(pms[pm_id], total_cpu_capacity, total_memory_capacity, is_on)

@profile
def launch_scaling_manager(active_vms, non_allocated_vms, total_non_allocated_cpu, total_non_allocated_memory, physical_machines, is_on, idle_power, actual_time_step, start_time_str, predictions, use_workload_predictor, predictor_model_path, workload_prediction_file, time_step):
    if non_allocated_vms:
        max_vm_cpu = max(non_allocated_vms.values(), key=lambda vm: vm['requested']['cpu'])
        max_vm_memory = max(non_allocated_vms.values(), key=lambda vm: vm['requested']['memory'])
        max_vm_cpu_requested_cpu = max_vm_cpu['requested']['cpu']
        max_vm_cpu_requested_memory = max_vm_cpu['requested']['memory']
        max_vm_memory_requested_cpu = max_vm_memory['requested']['cpu']
        max_vm_memory_requested_memory = max_vm_memory['requested']['memory']
    else:
        max_vm_cpu_requested_cpu = 0
        max_vm_cpu_requested_memory = 0
        max_vm_memory_requested_cpu = 0
        max_vm_memory_requested_memory = 0
    
    if use_workload_predictor:
        max_time_to_turn_on = max(pm['s']['time_to_turn_on'] for pm in physical_machines.values())
        max_step = max(ceil(max_time_to_turn_on / time_step), 1)
        time_window = max_step * time_step 
    else:
        time_window = 1

    future_loads = calculate_future_load(physical_machines, active_vms, time_window, time_step)
    
    if use_workload_predictor:
        for step in range(1, max_step + 1):
            predicted_workload_cpu, predicted_workload_memory = predict_workload(actual_time_step, actual_time_step + step, start_time_str, predictions, predictor_model_path, workload_prediction_file, time_step)
            future_load = future_loads[step - 1]

            scaling_manager(predicted_workload_cpu, predicted_workload_memory, physical_machines, idle_power, total_non_allocated_cpu, total_non_allocated_memory, future_load, is_on, max_vm_cpu_requested_cpu, max_vm_cpu_requested_memory, max_vm_memory_requested_cpu, max_vm_memory_requested_memory)

            if step == 1:
                total_non_allocated_cpu = 0
                total_non_allocated_memory = 0
    else:
        scaling_manager(0, 0, physical_machines, idle_power, total_non_allocated_cpu, total_non_allocated_memory, future_loads[0], is_on, max_vm_cpu_requested_cpu, max_vm_cpu_requested_memory, max_vm_memory_requested_cpu, max_vm_memory_requested_memory)
    