import os
import csv
import json
import datetime
from colorama import Fore, Style, init
from config import SAVE_LOGS, LOGS_FOLDER_PATH

try:
    profile # type: ignore
except NameError:
    def profile(func):
        return func

init(autoreset=True, strip=False)

def create_log_folder():
    current_datetime = datetime.datetime.now()
    date_time_string = current_datetime.strftime("%Y-%m-%d_%H:%M:%S")
    log_folder_name = f"log_{date_time_string}"
    log_folder_path = os.path.join(LOGS_FOLDER_PATH, log_folder_name)
    os.makedirs(log_folder_path, exist_ok=True)
    return log_folder_path

def log_initial_physical_machines(pms, log_folder_path):
    log_file_path = os.path.join(log_folder_path, 'initial_physical_machines.log')
    with open(log_file_path, 'w') as log_file:
        log_file.write("Initial Physical Machines:\n")
        for pm_id, pm in pms.items():
            log_file.write(f"  PM ID: {pm_id}, CPU Capacity: {pm['capacity']['cpu']}, Memory Capacity: {pm['capacity']['memory']}, Speed: {pm['features']['speed']}, Time to Turn On: {pm['s']['time_to_turn_on']}, Time to Turn Off: {pm['s']['time_to_turn_off']}, State: {pm['s']['state']}\n")
    return log_folder_path

def log_performance(step, model, time_taken, valid, num_vms, num_pms, performance_log_file):
    if valid:
        valid = ''
    else:
        valid = 'not valid'

    with open(performance_log_file, "a", newline='') as f:
        writer = csv.writer(f)
        writer.writerow([step, model, time_taken, valid, num_vms, num_pms])

def log_migrations(active_vms, count_migrations, terminated_vms_in_step, log_folder_path, step, final_step):
    file_path = os.path.join(log_folder_path, 'count_migrations.json')
    
    for vm in active_vms.values():
        if vm['migration']['from_pm'] != -1 and vm['migration']['to_pm'] != -1 and vm['migration']['current_time'] == 0:
            if vm['id'] not in count_migrations:
                count_migrations[vm['id']] = {}
                count_migrations[vm['id']]['count'] = 0
                count_migrations[vm['id']]['steps'] = []
            count_migrations[vm['id']]['count'] += 1
            count_migrations[vm['id']]['steps'].append(step)
    
       
    if step >= final_step:
        for vm_id in active_vms:
            if vm_id not in count_migrations:
                continue
            if os.path.exists(file_path):
                with open(file_path, 'r') as file:
                    try:
                        data = json.load(file)
                    except json.JSONDecodeError:
                        data = {}
            else:
                data = {}
            
            # Update the data with the new migration count
            data[vm_id] = count_migrations[vm_id]

            # Save the updated data back to the JSON file
            with open(file_path, 'w') as file:
                json.dump(data, file, indent=4)
    else:
        for vm in terminated_vms_in_step:
            if vm['id'] in count_migrations:
                if os.path.exists(file_path):
                    with open(file_path, 'r') as file:
                        try:
                            data = json.load(file)
                        except json.JSONDecodeError:
                            data = {}
                else:
                    data = {}

                # Update the data with the new migration count
                data[vm['id']] = count_migrations[vm['id']]

                # Save the updated data back to the JSON file
                with open(file_path, 'w') as file:
                    json.dump(data, file, indent=4)

@profile
def log_allocation(step, active_vms, old_active_vms, terminated_vms_in_step, turned_on_pms, turned_off_pms, pms, cpu_load, memory_load, total_revenue, total_costs, print_to_console=True, log_folder_path=None):
    log_lines = []
    console_lines = []

    def log_line(parts):
        file_line = ""
        console_line = ""
        
        for text, color, bold in parts:
            file_line += text
            
            # Add color and bold formatting for the console
            if bold:
                text = f"{Style.BRIGHT}{text}{Style.RESET_ALL}"
            if color:
                text = f"{color}{text}{Style.RESET_ALL}"
            
            console_line += text
        
        log_lines.append(file_line)
        console_lines.append(console_line)

    previous_state = {}
    for vm_id, vm in old_active_vms.items():
        if vm['allocation']['pm'] != -1:
            previous_state[vm_id] = 'allocating'
        elif vm['run']['pm'] != -1:
            previous_state[vm_id] = 'running'
        elif vm['migration']['from_pm'] != -1 and vm['migration']['to_pm'] != -1:
            previous_state[vm_id] = 'migrating'
        else:
            previous_state[vm_id] = 'non-assigned'

    current_state = {}
    for vm_id, vm in active_vms.items():
        if vm['allocation']['pm'] != -1:
            current_state[vm_id] = 'allocating'
        elif vm['run']['pm'] != -1:
            current_state[vm_id] = 'running'
        elif vm['migration']['from_pm'] != -1 and vm['migration']['to_pm'] != -1:
            current_state[vm_id] = 'migrating'
        else:
            current_state[vm_id] = 'non-assigned'

    allocating_vms = [vm for vm in active_vms.values() if vm['allocation']['pm'] != -1]
    running_vms = [vm for vm in active_vms.values() if vm['run']['pm'] != -1]
    migrating_vms = [vm for vm in active_vms.values() if vm['migration']['from_pm'] != -1 and vm['migration']['to_pm'] != -1]
    non_assigned_vms = [vm for vm in active_vms.values() if vm['allocation']['pm'] == -1 and vm['run']['pm'] == -1 and (vm['migration']['from_pm'] == -1 or vm['migration']['to_pm'] == -1)]

    # Log header
    log_line([(f"====== Time Step: {step} ======", Fore.LIGHTRED_EX, True)])

    # Non-Assigned VMs
    if non_assigned_vms:
        log_line([("Non-Assigned Virtual Machines:", Fore.LIGHTBLACK_EX, True)])
        for vm in non_assigned_vms:
            state_change = " (State Changed)" if vm['id'] not in previous_state else ''
            log_line([
                ("  VM ID: ", Fore.YELLOW if state_change else None, True), (f"{vm['id']}", Fore.YELLOW if state_change else None, False),
                (", CPU: ", Fore.YELLOW if state_change else None, True), (f"{vm['requested']['cpu']}", Fore.YELLOW if state_change else None, False),
                (", Memory: ", Fore.YELLOW if state_change else None, True), (f"{vm['requested']['memory']}", Fore.YELLOW if state_change else None, False),
                (", revenue: $", Fore.YELLOW if state_change else None, True), (f"{vm['revenue']:.6f}", Fore.YELLOW if state_change else None, False),
                (state_change, Fore.YELLOW if state_change else None, False)
            ])

    # Allocating VMs
    if allocating_vms:
        log_line([("Allocating Virtual Machines:", Fore.LIGHTCYAN_EX, True)])
        for vm in allocating_vms:
            vm_id = vm['id']
            state_change = ""
            if (vm['id'] not in previous_state or 
                previous_state[vm['id']] != 'allocating' or 
                vm['id'] not in old_active_vms or 
                old_active_vms[vm['id']]['allocation']['pm'] != vm['allocation']['pm']):
                state_change = " (State Changed)"

            log_line([
                ("  VM ID: ", Fore.YELLOW if state_change else None, True), (f"{vm['id']}", Fore.YELLOW if state_change else None, False),
                (", Allocating on PM: ", Fore.YELLOW if state_change else None, True), (f"{vm['allocation']['pm']}", Fore.YELLOW if state_change else None, False),
                (", Allocation Time: ", Fore.YELLOW if state_change else None, True), (f"{vm['allocation']['current_time']}/{vm['allocation']['total_time']}", Fore.YELLOW if state_change else None, False),
                (", CPU: ", Fore.YELLOW if state_change else None, True), (f"{vm['requested']['cpu']}", Fore.YELLOW if state_change else None, False),
                (", Memory: ", Fore.YELLOW if state_change else None, True), (f"{vm['requested']['memory']}", Fore.YELLOW if state_change else None, False),
                (", revenue: $", Fore.YELLOW if state_change else None, True), (f"{vm['revenue']:.6f}", Fore.YELLOW if state_change else None, False),
                (state_change, Fore.YELLOW if state_change else None, False)
            ])

    # Running VMs
    if running_vms:
        log_line([("Running Virtual Machines:", Fore.GREEN, True)])
        for vm in running_vms:
            state_change = " (State Changed)" if vm['id'] in previous_state and previous_state[vm['id']] != 'running' else ''
            log_line([
                ("  VM ID: ", Fore.YELLOW if state_change else None, True), (f"{vm['id']}", Fore.YELLOW if state_change else None, False),
                (", Running on PM: ", Fore.YELLOW if state_change else None, True), (f"{vm['run']['pm']}", Fore.YELLOW if state_change else None, False),
                (", Execution Time: ", Fore.YELLOW if state_change else None, True), (f"{round(vm['run']['current_time'], 1)}/{vm['run']['total_time']}", Fore.YELLOW if state_change else None, False),
                (", CPU: ", Fore.YELLOW if state_change else None, True), (f"{vm['requested']['cpu']}", Fore.YELLOW if state_change else None, False),
                (", Memory: ", Fore.YELLOW if state_change else None, True), (f"{vm['requested']['memory']}", Fore.YELLOW if state_change else None, False),
                (", revenue: $", Fore.YELLOW if state_change else None, True), (f"{vm['revenue']:.6f}", Fore.YELLOW if state_change else None, False),
                (state_change, Fore.YELLOW if state_change else None, False)
            ])

    # Migrating VMs
    if migrating_vms:
        log_line([("Migrating Virtual Machines:", Fore.LIGHTMAGENTA_EX, True)])
        for vm in migrating_vms:
            state_change = " (State Changed)" if vm['id'] in previous_state and previous_state[vm['id']] != 'migrating' else ''
            log_line([
                ("  VM ID: ", Fore.YELLOW if state_change else None, True), (f"{vm['id']}", Fore.YELLOW if state_change else None, False),
                (", Migrating from PM: ", Fore.YELLOW if state_change else None, True), (f"{vm['migration']['from_pm']}", Fore.YELLOW if state_change else None, False),
                (" to PM: ", Fore.YELLOW if state_change else None, True), (f"{vm['migration']['to_pm']}", Fore.YELLOW if state_change else None, False),
                (", Migration Time: ", Fore.YELLOW if state_change else None, True), (f"{vm['migration']['current_time']}/{vm['migration']['total_time']}", Fore.YELLOW if state_change else None, False),
                (", CPU: ", Fore.YELLOW if state_change else None, True), (f"{vm['requested']['cpu']}", Fore.YELLOW if state_change else None, False),
                (", Memory: ", Fore.YELLOW if state_change else None, True), (f"{vm['requested']['memory']}", Fore.YELLOW if state_change else None, False),
                (", revenue: $", Fore.YELLOW if state_change else None, True), (f"{vm['revenue']:.6f}", Fore.YELLOW if state_change else None, False),
                (state_change, Fore.YELLOW if state_change else None, False)
            ])

    # Completed VMs
    if terminated_vms_in_step:
        log_line([("Completed Virtual Machines:", Fore.BLUE, True)])
        for vm in terminated_vms_in_step:
            state_change = " (State Changed)" if vm['id'] in previous_state else ''
            log_line([
                ("  VM ID: ", Fore.YELLOW if state_change else None, True), (f"{vm['id']}", Fore.YELLOW if state_change else None, False),
                (", CPU: ", Fore.YELLOW if state_change else None, True), (f"{vm['requested']['cpu']}", Fore.YELLOW if state_change else None, False),
                (", Memory: ", Fore.YELLOW if state_change else None, True), (f"{vm['requested']['memory']}", Fore.YELLOW if state_change else None, False),
                (", Total Execution Time: ", Fore.YELLOW if state_change else None, True), (f"{vm['run']['total_time']}", Fore.YELLOW if state_change else None, False),
                (", revenue: $", Fore.YELLOW if state_change else None, True), (f"{vm['revenue']:.6f}", Fore.YELLOW if state_change else None, False),
                (state_change, Fore.YELLOW if state_change else None, False)
            ])

    # Physical Machines header
    log_line([(f"\n------------------------------------------", Fore.LIGHTRED_EX, True)])

    # Physical Machines
    log_line([("\nPhysical Machines:", Fore.MAGENTA, True)])
    
    for pm_id, pm in pms.items():
        state_change = ''
        if pm_id in turned_on_pms:
            if pm['s']['time_to_turn_on'] > 0:
                state_change = " has been turned ON, remaining time to turn on: " + f"{pm['s']['time_to_turn_on']}"
            else:
                state_change = " has been turned ON"
        if pm_id in turned_off_pms:
            if pm['s']['time_to_turn_off'] > 0:
                state_change = " turned OFF, remaining time to turn off: " + f"{pm['s']['time_to_turn_off']}"
            else:
                state_change = " has been turned OFF"
        log_line([
            ("  PM ID: ", Fore.YELLOW if state_change else None, True), (f"{pm_id}", Fore.YELLOW if state_change else None, False),
            (", Is On: ", Fore.YELLOW if state_change else None, True), (f"{pm['s']['state']}", Fore.YELLOW if state_change else None, False),
            (", CPU Load: ", Fore.YELLOW if state_change else None, True), (f"{cpu_load[pm_id] * pm['capacity']['cpu']:.0f}/{pm['capacity']['cpu']} cores ({cpu_load[pm_id] * 100:.2f}%)", Fore.YELLOW if state_change else None, False),
            (", Memory Load: ", Fore.YELLOW if state_change else None, True), (f"{memory_load[pm_id] * pm['capacity']['memory']:.0f}/{pm['capacity']['memory']} GB ({memory_load[pm_id] * 100:.2f}%)", Fore.YELLOW if state_change else None, False),
            (state_change, Fore.YELLOW if state_change else None, False)
        ])

    # Total Revenue and Costs
    log_line([
        ("\nTotal Revenue Gained from Completed VMs: ", Fore.GREEN, True), (f"{total_revenue:.6f}", Fore.GREEN, True), ("$", Fore.GREEN, True)
    ])
    log_line([
        ("Total Costs Incurred: ", Fore.RED, True), (f"{total_costs:.6f}", Fore.RED, True), ("$", Fore.RED, True)
    ])
    log_line([("=============================", Fore.LIGHTRED_EX, True)])

    # Save log to file (without colors and bold formatting)
    if SAVE_LOGS:
        log_file_path = os.path.join(log_folder_path, f'step_{step}.log')
        with open(log_file_path, 'w') as log_file:
            log_file.write('\n'.join(log_lines))

    # Print to console (with colors and bold formatting)
    if print_to_console:
        print('\n'.join(console_lines))

def log_final_net_profit(total_revenue, total_costs, total_pm_energy_cost, total_migration_energy_cost, num_completed_migrations, max_percentage_of_pms_on, total_cpu_load, total_memory_load, total_fully_on_pm, num_pms, non_valid_entries, total_entries, log_folder_path, MASTER_MODEL, USE_RANDOM_SEED, SEED_NUMBER, TIME_STEP, num_steps, REAL_DATA, WORKLOAD_NAME):
    net_profit = total_revenue - total_costs

    # Determine the color based on whether the net profit is positive or negative
    if net_profit >= 0:
        color = Fore.GREEN
    else:
        color = Fore.RED

    avg_pms_on = total_fully_on_pm / num_steps if num_steps != 0 else 0
    avg_cpu_load = total_cpu_load / total_fully_on_pm * 100 if total_fully_on_pm != 0 else 0
    avg_memory_load = total_memory_load / total_fully_on_pm * 100 if total_fully_on_pm != 0 else 0

    final_net_profit_message = f"Final Net Profit: ${net_profit:.6f}"

    total_pm_energy_cost_message = f"Total PM Energy Cost: ${total_pm_energy_cost:.6f}"
    total_migration_energy_cost_message = f"Total Migration Energy Cost: ${total_migration_energy_cost:.6f}"
    completed_migrations_message = f"Completed migrations: {num_completed_migrations}"
    avg_pms_on_message = f"Average number of PMs on: {avg_pms_on}/{num_pms}"
    max_percentage_of_pms_on_message = f"Max percentage of PMs on: {max_percentage_of_pms_on}%"
    avg_pm_loads_message = f"Average PM loads: CPU {avg_cpu_load:.2f}%, Memory {avg_memory_load:.2f}%"
    non_valid_entries_message = f"Non-valid entries: {non_valid_entries}/{total_entries} ({(non_valid_entries / total_entries * 100):.2f}%)"
    time_step_message = f"Time Step: {TIME_STEP}"
    num_steps_message = f"Number of Time Steps: {num_steps}"
    total_revenue_message = f"Total Revenue Gained from Completed VMs: ${total_revenue:.6f}"
    total_costs_message = f"Total Costs Incurred: ${total_costs:.6f}"
    
    print(f"\n{color}{Style.BRIGHT}\033[4m{final_net_profit_message}{Style.RESET_ALL}\n")
    print(total_revenue_message)
    print(total_costs_message)
    print(total_pm_energy_cost_message)
    print(total_migration_energy_cost_message)
    print(completed_migrations_message)
    print(avg_pms_on_message)
    print(max_percentage_of_pms_on_message)
    print(avg_pm_loads_message)
    print(non_valid_entries_message)

    # Save to log file (without colors)
    if SAVE_LOGS:
        log_file_path = os.path.join(log_folder_path, 'final_net_profit.log')
        with open(log_file_path, 'a') as log_file:
            
            if MASTER_MODEL:
                model_message = f"Master Model: {MASTER_MODEL}"
                log_file.write(model_message + '\n')

            if REAL_DATA:
                trace_message = f"Trace: {WORKLOAD_NAME}"
                log_file.write(trace_message + '\n')
            elif USE_RANDOM_SEED:
                seed_message = f"Random Seed Number: {SEED_NUMBER}"
                log_file.write(seed_message + '\n')
            
            

            log_file.write(time_step_message + '\n')
            log_file.write(num_steps_message + '\n')
            log_file.write(non_valid_entries_message + '\n')
            log_file.write('=============================\n')
            log_file.write(total_revenue_message + '\n')
            log_file.write(total_costs_message + '\n')
            log_file.write(total_pm_energy_cost_message + '\n')
            log_file.write(total_migration_energy_cost_message + '\n')
            log_file.write('------------------------------------------\n')
            log_file.write(completed_migrations_message + '\n')
            log_file.write(avg_pms_on_message + '\n')
            log_file.write(max_percentage_of_pms_on_message + '\n')
            log_file.write(avg_pm_loads_message + '\n')
            log_file.write('------------------------------------------\n')
            log_file.write(final_net_profit_message + '\n')
            

    