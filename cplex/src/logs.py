import os
import json
from colorama import Fore, Style, init

init(autoreset=True)

def log_initial_physical_machines(pm_list, base_path):
    log_folder_path = os.path.join(base_path, 'simulation/log')
    os.makedirs(log_folder_path, exist_ok=True)
    log_file_path = os.path.join(log_folder_path, 'initial_physical_machines.log')

    with open(log_file_path, 'w') as log_file:
        log_file.write("Initial Physical Machines:\n")
        for pm in pm_list:
            log_file.write(f"  PM ID: {pm['id']}, CPU Capacity: {pm['capacity']['cpu']}, Memory Capacity: {pm['capacity']['memory']}, Max Energy Consumption: {pm['features']['max_energy_consumption']}, Time to Turn On: {pm['s']['time_to_turn_on']}, Time to Turn Off: {pm['s']['time_to_turn_off']}, State: {pm['s']['state']}\n")

def log_allocation(step, active_vms, terminated_vms, migrated_vms, removed_vms, turned_on_pms, turned_off_pms, pm_list, base_path, cpu_load, memory_load):
    log_folder_path = os.path.join(base_path, 'simulation/log')
    os.makedirs(log_folder_path, exist_ok=True)
    log_file_path = os.path.join(log_folder_path, f'allocation_t{step}.log')

    allocating_vms = [vm for vm in active_vms if vm['allocation']['pm'] != -1]
    running_vms = [vm for vm in active_vms if vm['run']['pm'] != -1]
    migrating_vms = [vm for vm in active_vms if vm['migration']['from_pm'] != -1 and vm['migration']['to_pm'] != -1]
    non_assigned_vms = [vm for vm in active_vms if vm['allocation']['pm'] == -1 and vm['run']['pm'] == -1 and (vm['migration']['from_pm'] == -1 or vm['migration']['to_pm'] == -1)]

    previous_state = {}
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

    with open(log_file_path, 'w') as log_file:
        log_file.write(f"Time Step: {step}\n")
        if non_assigned_vms:
            log_file.write(f"{Style.BRIGHT}Non-Assigned Virtual Machines:{Style.RESET_ALL}\n")
            for vm in non_assigned_vms:
                log_file.write(f"  VM ID: {vm['id']}, CPU: {vm['requested']['cpu']}, Memory: {vm['requested']['memory']}, Expected Profit: {vm['expected_profit']}\n")
        if allocating_vms:
            log_file.write(f"{Style.BRIGHT}Allocating Virtual Machines:{Style.RESET_ALL}\n")
            for vm in allocating_vms:
                state_change = f" {Fore.YELLOW}(State Changed){Style.RESET_ALL}" if vm['id'] in previous_state and previous_state[vm['id']] != 'allocating' else ''
                log_file.write(f"  VM ID: {vm['id']}, Allocating on PM: {vm['allocation']['pm']}, Allocation Time: {vm['allocation']['current_time']}/{vm['allocation']['total_time']}, CPU: {vm['requested']['cpu']}, Memory: {vm['requested']['memory']}, Expected Profit: {vm['expected_profit']}{state_change}\n")
        if running_vms:
            log_file.write(f"{Style.BRIGHT}Running Virtual Machines:{Style.RESET_ALL}\n")
            for vm in running_vms:
                state_change = f" {Fore.YELLOW}(State Changed){Style.RESET_ALL}" if vm['id'] in previous_state and previous_state[vm['id']] != 'running' else ''
                log_file.write(f"  VM ID: {vm['id']}, Running on PM: {vm['run']['pm']}, Execution Time: {vm['run']['current_time']}/{vm['run']['total_time']}, CPU: {vm['requested']['cpu']}, Memory: {vm['requested']['memory']}, Expected Profit: {vm['expected_profit']}{state_change}\n")
        if migrating_vms:
            log_file.write(f"{Style.BRIGHT}Migrating Virtual Machines:{Style.RESET_ALL}\n")
            for vm in migrating_vms:
                state_change = f" {Fore.YELLOW}(State Changed){Style.RESET_ALL}" if vm['id'] in previous_state and previous_state[vm['id']] != 'migrating' else ''
                log_file.write(f"  VM ID: {vm['id']}, Migrating from PM: {vm['migration']['from_pm']} to PM: {vm['migration']['to_pm']}, Migration Time: {vm['migration']['current_time']}/{vm['migration']['total_time']}, CPU: {vm['requested']['cpu']}, Memory: {vm['requested']['memory']}, Expected Profit: {vm['expected_profit']}{state_change}\n")
        if terminated_vms:
            log_file.write(f"{Style.BRIGHT}Terminated Virtual Machines:{Style.RESET_ALL}\n")
            for vm in terminated_vms:
                log_file.write(f"  VM ID: {vm['id']}, CPU: {vm['requested']['cpu']}, Memory: {vm['requested']['memory']}, Total Execution Time: {vm['run']['total_time']}, Expected Profit: {vm['expected_profit']}\n")
        if removed_vms:
            log_file.write(f"{Style.BRIGHT}Removed Virtual Machines:{Style.RESET_ALL}\n")
            for vm in removed_vms:
                log_file.write(f"  VM ID: {vm['id']}, CPU: {vm['requested']['cpu']}, Memory: {vm['requested']['memory']}, Expected Profit: {vm['expected_profit']}\n")
        if turned_on_pms or turned_off_pms:
            log_file.write("Physical Machines State Change:\n")
            for pm_id in turned_on_pms:
                pm = next(pm for pm in pm_list if pm['id'] == pm_id)
                if pm['s']['time_to_turn_on'] > 0:
                    log_file.write(f"  PM ID: {pm_id} has been turned ON, remaining time to turn on: {pm['s']['time_to_turn_on']}\n")
                else:
                    log_file.write(f"  PM ID: {pm_id} has been turned ON\n")
            for pm_id in turned_off_pms:
                pm = next(pm for pm in pm_list if pm['id'] == pm_id)
                if pm['s']['time_to_turn_off'] > 0:
                    log_file.write(f"  PM ID: {pm_id} has been turned OFF, remaining time to turn off: {pm['s']['time_to_turn_off']}\n")
                else:
                    log_file.write(f"  PM ID: {pm_id} has been turned OFF\n")
        log_file.write("Physical Machines Load:\n")
        for i, pm in enumerate(pm_list):
            log_file.write(f"  PM ID: {pm['id']}, Is On: {pm['s']['state']}, CPU Load: {cpu_load[i] * 100:.2f}%, Memory Load: {memory_load[i] * 100:.2f}%\n")

    # Print log to console
    print(f"\n{Fore.GREEN}{Style.BRIGHT}====== Time Step: {step} ======{Style.RESET_ALL}")
    if non_assigned_vms:
        print(f"{Fore.YELLOW}{Style.BRIGHT}Non-Assigned Virtual Machines:{Style.RESET_ALL}")
        for vm in non_assigned_vms:
            print(f"  {Style.BRIGHT}VM ID:{Style.RESET_ALL} {vm['id']}, {Style.BRIGHT}CPU:{Style.RESET_ALL} {vm['requested']['cpu']}, {Style.BRIGHT}Memory:{Style.RESET_ALL} {vm['requested']['memory']}, {Style.BRIGHT}Expected Profit:{Style.RESET_ALL} {vm['expected_profit']}")
    if allocating_vms:
        print(f"{Fore.YELLOW}{Style.BRIGHT}Allocating Virtual Machines:{Style.RESET_ALL}")
        for vm in allocating_vms:
            state_change = f" {Fore.YELLOW}(State Changed){Style.RESET_ALL}" if vm['id'] in previous_state and previous_state[vm['id']] != 'allocating' else ''
            print(f"  {Style.BRIGHT}VM ID:{Style.RESET_ALL} {vm['id']}, {Style.BRIGHT}Allocating on PM:{Style.RESET_ALL} {vm['allocation']['pm']}, {Style.BRIGHT}Allocation Time:{Style.RESET_ALL} {vm['allocation']['current_time']}/{vm['allocation']['total_time']}, {Style.BRIGHT}CPU:{Style.RESET_ALL} {vm['requested']['cpu']}, {Style.BRIGHT}Memory:{Style.RESET_ALL} {vm['requested']['memory']}, {Style.BRIGHT}Expected Profit:{Style.RESET_ALL} {vm['expected_profit']}{state_change}")
    if running_vms:
        print(f"{Fore.GREEN}{Style.BRIGHT}Running Virtual Machines:{Style.RESET_ALL}")
        for vm in running_vms:
            state_change = f" {Fore.YELLOW}(State Changed){Style.RESET_ALL}" if vm['id'] in previous_state and previous_state[vm['id']] != 'running' else ''
            print(f"  {Style.BRIGHT}VM ID:{Style.RESET_ALL} {vm['id']}, {Style.BRIGHT}Running on PM:{Style.RESET_ALL} {vm['run']['pm']}, {Style.BRIGHT}Execution Time:{Style.RESET_ALL} {vm['run']['current_time']}/{vm['run']['total_time']}, {Style.BRIGHT}CPU:{Style.RESET_ALL} {vm['requested']['cpu']}, {Style.BRIGHT}Memory:{Style.RESET_ALL} {vm['requested']['memory']}, {Style.BRIGHT}Expected Profit:{Style.RESET_ALL} {vm['expected_profit']}{state_change}")
    if migrating_vms:
        print(f"{Fore.BLUE}{Style.BRIGHT}Migrating Virtual Machines:{Style.RESET_ALL}")
        for vm in migrating_vms:
            state_change = f" {Fore.YELLOW}(State Changed){Style.RESET_ALL}" if vm['id'] in previous_state and previous_state[vm['id']] != 'migrating' else ''
            print(f"  {Style.BRIGHT}VM ID:{Style.RESET_ALL} {vm['id']}, {Style.BRIGHT}Migrating from PM:{Style.RESET_ALL} {vm['migration']['from_pm']} {Style.BRIGHT}to PM:{Style.RESET_ALL} {vm['migration']['to_pm']}, {Style.BRIGHT}Migration Time:{Style.RESET_ALL} {vm['migration']['current_time']}/{vm['migration']['total_time']}, {Style.BRIGHT}CPU:{Style.RESET_ALL} {vm['requested']['cpu']}, {Style.BRIGHT}Memory:{Style.RESET_ALL} {vm['requested']['memory']}, {Style.BRIGHT}Expected Profit:{Style.RESET_ALL} {vm['expected_profit']}{state_change}")
    if terminated_vms:
        print(f"{Fore.RED}{Style.BRIGHT}Terminated Virtual Machines:{Style.RESET_ALL}")
        for vm in terminated_vms:
            print(f"  {Style.BRIGHT}VM ID:{Style.RESET_ALL} {vm['id']}, {Style.BRIGHT}CPU:{Style.RESET_ALL} {vm['requested']['cpu']}, {Style.BRIGHT}Memory:{Style.RESET_ALL} {vm['requested']['memory']}, {Style.BRIGHT}Total Execution Time:{Style.RESET_ALL} {vm['run']['total_time']}, {Style.BRIGHT}Expected Profit:{Style.RESET_ALL} {vm['expected_profit']}")
    if removed_vms:
        print(f"{Fore.YELLOW}{Style.BRIGHT}Removed Virtual Machines:{Style.RESET_ALL}")
        for vm in removed_vms:
            print(f"  {Style.BRIGHT}VM ID:{Style.RESET_ALL} {vm['id']}, {Style.BRIGHT}CPU:{Style.RESET_ALL} {vm['requested']['cpu']}, {Style.BRIGHT}Memory:{Style.RESET_ALL} {vm['requested']['memory']}, {Style.BRIGHT}Expected Profit:{Style.RESET_ALL} {vm['expected_profit']}")
    if turned_on_pms or turned_off_pms:
        print(f"{Fore.MAGENTA}{Style.BRIGHT}Physical Machines State Change:{Style.RESET_ALL}")
        for pm_id in turned_on_pms:
            pm = next(pm for pm in pm_list if pm['id'] == pm_id)
            if pm['s']['time_to_turn_on'] > 0:
                print(f"  {Style.BRIGHT}PM ID:{Style.RESET_ALL} {pm_id} {Style.BRIGHT}has been turned ON{Style.RESET_ALL}, remaining time to turn on: {pm['s']['time_to_turn_on']}")
            else:
                print(f"  {Style.BRIGHT}PM ID:{Style.RESET_ALL} {pm_id} {Style.BRIGHT}has been turned ON{Style.RESET_ALL}")
        for pm_id in turned_off_pms:
            pm = next(pm for pm in pm_list if pm['id'] == pm_id)
            if pm['s']['time_to_turn_off'] > 0:
                print(f"  {Style.BRIGHT}PM ID:{Style.RESET_ALL} {pm_id} {Style.BRIGHT}has been turned OFF{Style.RESET_ALL}, remaining time to turn off: {pm['s']['time_to_turn_off']}")
            else:
                print(f"  {Style.BRIGHT}PM ID:{Style.RESET_ALL} {pm_id} {Style.BRIGHT}has been turned OFF{Style.RESET_ALL}")
    print(f"{Fore.MAGENTA}{Style.BRIGHT}Physical Machines Load:{Style.RESET_ALL}")
    for i, pm in enumerate(pm_list):
        print(f"  {Style.BRIGHT}PM ID:{Style.RESET_ALL} {pm['id']}, {Style.BRIGHT}Is On:{Style.RESET_ALL} {pm['s']['state']}, {Style.BRIGHT}CPU Load:{Style.RESET_ALL} {cpu_load[i] * 100:.2f}%, {Style.BRIGHT}Memory Load:{Style.RESET_ALL} {memory_load[i] * 100:.2f}%")
    print(f"{Fore.GREEN}{Style.BRIGHT}============================={Style.RESET_ALL}\n")

