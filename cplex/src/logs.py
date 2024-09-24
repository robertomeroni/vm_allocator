import os
import datetime
from colorama import Fore, Style, init
from config import SAVE_LOGS, LOGS_FOLDER_PATH, PRINT_TO_CONSOLE

init(autoreset=True, strip=False)

def create_log_folder():
    current_datetime = datetime.datetime.now()
    date_time_string = current_datetime.strftime("%Y-%m-%d_%H:%M:%S")
    log_folder_name = f"log_{date_time_string}"
    log_folder_path = os.path.join(LOGS_FOLDER_PATH, log_folder_name)
    os.makedirs(log_folder_path, exist_ok=True)
    return log_folder_path

def log_initial_physical_machines(pm_list):
    log_folder_path = create_log_folder()
    log_file_path = os.path.join(log_folder_path, 'initial_physical_machines.log')
    with open(log_file_path, 'w') as log_file:
        log_file.write("Initial Physical Machines:\n")
        for pm in pm_list:
            log_file.write(f"  PM ID: {pm['id']}, CPU Capacity: {pm['capacity']['cpu']}, Memory Capacity: {pm['capacity']['memory']}, Speed: {pm['features']['speed']}, Time to Turn On: {pm['s']['time_to_turn_on']}, Time to Turn Off: {pm['s']['time_to_turn_off']}, State: {pm['s']['state']}\n")
    return log_folder_path

def log_allocation(step, active_vms, old_active_vms, terminated_vms, removed_vms, turned_on_pms, turned_off_pms, pm_list, cpu_load, memory_load, total_revenue, total_costs, log_folder_path = None):
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

    allocating_vms = [vm for vm in active_vms if vm['allocation']['pm'] != -1]
    running_vms = [vm for vm in active_vms if vm['run']['pm'] != -1]
    migrating_vms = [vm for vm in active_vms if vm['migration']['from_pm'] != -1 and vm['migration']['to_pm'] != -1]
    non_assigned_vms = [vm for vm in active_vms if vm['allocation']['pm'] == -1 and vm['run']['pm'] == -1 and (vm['migration']['from_pm'] == -1 or vm['migration']['to_pm'] == -1)]

    previous_state = {}
    for vm in old_active_vms:
        if vm['allocation']['pm'] != -1:
            previous_state[vm['id']] = 'allocating'
        elif vm['run']['pm'] != -1:
            previous_state[vm['id']] = 'running'
        elif vm['migration']['from_pm'] != -1 and vm['migration']['to_pm'] != -1:
            previous_state[vm['id']] = 'migrating'
        else:
            previous_state[vm['id']] = 'non-assigned'

    current_state = {}
    for vm in active_vms:
        if vm['allocation']['pm'] != -1:
            current_state[vm['id']] = 'allocating'
        elif vm['run']['pm'] != -1:
            current_state[vm['id']] = 'running'
        elif vm['migration']['from_pm'] != -1 and vm['migration']['to_pm'] != -1:
            current_state[vm['id']] = 'migrating'
        else:
            current_state[vm['id']] = 'non-assigned'

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

    # Terminated VMs
    if terminated_vms:
        log_line([("Terminated Virtual Machines:", Fore.BLUE, True)])
        for vm in terminated_vms:
            state_change = " (State Changed)" if vm['id'] in previous_state and previous_state[vm['id']] == 'running' else ''
            log_line([
                ("  VM ID: ", Fore.YELLOW if state_change else None, True), (f"{vm['id']}", Fore.YELLOW if state_change else None, False),
                (", CPU: ", Fore.YELLOW if state_change else None, True), (f"{vm['requested']['cpu']}", Fore.YELLOW if state_change else None, False),
                (", Memory: ", Fore.YELLOW if state_change else None, True), (f"{vm['requested']['memory']}", Fore.YELLOW if state_change else None, False),
                (", Total Execution Time: ", Fore.YELLOW if state_change else None, True), (f"{vm['run']['total_time']}", Fore.YELLOW if state_change else None, False),
                (", revenue: $", Fore.YELLOW if state_change else None, True), (f"{vm['revenue']:.6f}", Fore.YELLOW if state_change else None, False),
                (state_change, Fore.YELLOW if state_change else None, False)
            ])

    # Removed VMs
    if removed_vms:
        log_line([("Removed Virtual Machines:", Fore.RED, True)])
        for vm in removed_vms:
            log_line([
                ("  VM ID: ", Fore.YELLOW if state_change else None, True), (f"{vm['id']}", Fore.YELLOW if state_change else None, False),
                (", CPU: ", Fore.YELLOW if state_change else None, True), (f"{vm['requested']['cpu']}", Fore.YELLOW if state_change else None, False),
                (", Memory: ", Fore.YELLOW if state_change else None, True), (f"{vm['requested']['memory']}", Fore.YELLOW if state_change else None, False),
                (", revenue: $", Fore.YELLOW if state_change else None, True), (f"{vm['revenue']:.6f}", Fore.YELLOW if state_change else None, False)
            ])

    # Physical Machines header
    log_line([(f"\n------------------------------------------", Fore.LIGHTRED_EX, True)])

    # Physical Machines
    log_line([("\nPhysical Machines:", Fore.MAGENTA, True)])
    for i, pm in enumerate(pm_list):
        state_change = ''
        if pm['id'] in turned_on_pms:
            if pm['s']['time_to_turn_on'] > 0:
                    state_change = " has been turned ON, remaining time to turn on: " + f"{pm['s']['time_to_turn_on']}"
            else:
                    state_change = " has been turned ON"
        if pm['id'] in turned_off_pms:
            if pm['s']['time_to_turn_off'] > 0:
                    state_change = " turned OFF, remaining time to turn off: " + f"{pm['s']['time_to_turn_off']}"
            else:
                    state_change = " has been turned OFF"
        log_line([
            ("  PM ID: ", Fore.YELLOW if state_change else None, True), (f"{pm['id']}", Fore.YELLOW if state_change else None, False),
            (", Is On: ", Fore.YELLOW if state_change else None, True), (f"{pm['s']['state']}", Fore.YELLOW if state_change else None, False),
            (", CPU Load: ", Fore.YELLOW if state_change else None, True), (f"{cpu_load[i] * 100:.2f}%", Fore.YELLOW if state_change else None, False),
            (", Memory Load: ", Fore.YELLOW if state_change else None, True), (f"{memory_load[i] * 100:.2f}%", Fore.YELLOW if state_change else None, False),
            (state_change, Fore.YELLOW if state_change else None, False)
        ])

    # Total Revenue and Costs
    print()
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
    if PRINT_TO_CONSOLE:
        print('\n'.join(console_lines))

def log_final_net_profit(total_revenue, total_costs, num_completed_migrations, num_removed_vms, max_percentage_of_pms_on, log_folder_path, MASTER_MODEL, USE_RANDOM_SEED, SEED_NUMBER, TIME_STEP, final_step, REAL_DATA, WORKLOAD_NAME):
    net_profit = total_revenue - total_costs

    # Determine the color based on whether the net profit is positive or negative
    if net_profit >= 0:
        color = Fore.GREEN
        profit_status = "Profit"
    else:
        color = Fore.RED
        profit_status = "Loss"

    final_net_profit_message = f"Final Net {profit_status}: ${net_profit:.6f}"
    print(f"\n{color}{Style.BRIGHT}\033[4m{final_net_profit_message}{Style.RESET_ALL}\n")

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
            
            time_step_message = f"Time Step: {TIME_STEP}"
            log_file.write(time_step_message + '\n')

            final_step_message = f"Final Step: {final_step}"
            log_file.write(final_step_message + '\n')

            log_file.write('=============================\n')

            total_revenue_message = f"Total Revenue Gained from Completed VMs: ${total_revenue:.6f}"
            log_file.write(total_revenue_message + '\n')
            total_costs_message = f"Total Costs Incurred: ${total_costs:.6f}"
            log_file.write(total_costs_message + '\n')
            log_file.write('------------------------------------------\n')
            log_file.write(f"Completed migrations: {num_completed_migrations}\n")
            log_file.write(f"Removed VMs: {num_removed_vms}\n")
            log_file.write(f"Max percentage of PMs on: {max_percentage_of_pms_on}\n")
            log_file.write('------------------------------------------\n')
            log_file.write(final_net_profit_message + '\n')
            

    