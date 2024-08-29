from utils import round_down
from math import floor

def calculate_future_load(physical_machines, active_vms, actual_time_step, time_window, TIME_STEP):
    # Initialize a list to store the load for each time step
    future_loads = []

    # Iterate through each future time step
    for future_time_step in range(actual_time_step + 1, actual_time_step + floor(time_window / TIME_STEP)):
        actual_time_window = (future_time_step - actual_time_step) * TIME_STEP
        # Initialize load lists for this future time step
        cpu_load = [0.0] * len(physical_machines)
        memory_load = [0.0] * len(physical_machines)

        # Calculate the load for each VM and PM for the current future time step
        for vm in active_vms:
            # Determine the PM for the VM in this time step
            pm_id = vm['allocation']['pm'] if vm['allocation']['pm'] != -1 else (
                vm['migration']['to_pm'] if vm['migration']['to_pm'] != -1 else vm['run']['pm']
            )

            # Check if VM is allocated to a physical machine
            if pm_id != -1:
                # Check if the physical machine is in an active state and will be turned on before this future time step
                if physical_machines[pm_id]['s']['state'] == 1 and physical_machines[pm_id]['s']['time_to_turn_on'] < actual_time_window:
                    remaining_time = physical_machines[pm_id]['s']['time_to_turn_on'] + (vm['allocation']['total_time'] - vm['allocation']['current_time'] + vm['run']['total_time'] - vm['run']['current_time']) / physical_machines[pm_id]['features']['speed']
                    if vm['migration']['to_pm'] != -1:
                        remaining_time += vm['migration']['total_time'] - vm['migration']['current_time'] 
                    if actual_time_window < remaining_time:
                            cpu_load[pm_id] += vm['requested']['cpu'] / physical_machines[pm_id]['capacity']['cpu']
                            memory_load[pm_id] += vm['requested']['memory'] / physical_machines[pm_id]['capacity']['memory']

                # Check if the VM is migrating from a physical machine
                if vm['migration']['from_pm'] != -1:
                    from_pm_id = vm['migration']['from_pm']

                    cpu_load[from_pm_id] += vm['requested']['cpu'] / physical_machines[from_pm_id]['capacity']['cpu']
                    memory_load[from_pm_id] += vm['requested']['memory'] / physical_machines[from_pm_id]['capacity']['memory']

        # Round down the loads for the current future time step
        cpu_load = [round_down(cpu) for cpu in cpu_load]
        memory_load = [round_down(memory) for memory in memory_load]

        # Append the loads for this future time step to the list
        future_loads.append((cpu_load, memory_load))

    return future_loads


