import os
import json
from colorama import Fore, Style, init

init(autoreset=True)

def calculate_load(vm_list, pm_list):
    load_info = {pm['id']: {'cpu_used': 0, 'memory_used': 0, 'is_on': pm['state']} for pm in pm_list}
    for vm in vm_list:
        if vm['running_on_pm'] != -1:
            load_info[vm['running_on_pm']]['cpu_used'] += vm['requested_cpu']
            load_info[vm['running_on_pm']]['memory_used'] += vm['requested_memory']
    for pm in pm_list:
        if pm['cpu_capacity'] > 0 and pm['memory_capacity'] > 0:
            load_info[pm['id']]['cpu_load'] = (load_info[pm['id']]['cpu_used'] / pm['cpu_capacity']) * 100
            load_info[pm['id']]['memory_load'] = (load_info[pm['id']]['memory_used'] / pm['memory_capacity']) * 100
        else:
            load_info[pm['id']]['cpu_load'] = 0
            load_info[pm['id']]['memory_load'] = 0
    return load_info

def log_initial_physical_machines(pm_list, base_path):
    log_folder_path = os.path.join(base_path, 'simulation/log')
    os.makedirs(log_folder_path, exist_ok=True)
    log_file_path = os.path.join(log_folder_path, 'initial_physical_machines.log')

    with open(log_file_path, 'w') as log_file:
        log_file.write("Initial Physical Machines:\n")
        for pm in pm_list:
            log_file.write(f"  PM ID: {pm['id']}, CPU Capacity: {pm['cpu_capacity']}, Memory Capacity: {pm['memory_capacity']}, Max Energy Consumption: {pm['max_energy_consumption']}, Time to Turn On: {pm['time_to_turn_on']}, Time to Turn Off: {pm['time_to_turn_off']}, State: {pm['state']}\n")

def log_allocation(step, active_vms, terminated_vms, migrated_vms, killed_vms, turned_on_pms, turned_off_pms, pm_list, base_path):
    log_folder_path = os.path.join(base_path, 'simulation/log')
    os.makedirs(log_folder_path, exist_ok=True)
    log_file_path = os.path.join(log_folder_path, f'allocation_t{step}.log')

    load_info = calculate_load(active_vms, pm_list)

    with open(log_file_path, 'w') as log_file:
        log_file.write(f"Time Step: {step}\n")
        log_file.write("Virtual Machines Allocation:\n")
        for vm in active_vms:
            log_file.write(f"  VM ID: {vm['id']}, Running on PM: {vm['running_on_pm']}, CPU: {vm['requested_cpu']}, Memory: {vm['requested_memory']}, Execution Time: {vm['current_execution_time']}/{vm['total_execution_time']}, Expected Profit: {vm['expected_profit']}\n")
        if terminated_vms:
            log_file.write("Terminated Virtual Machines:\n")
            for vm in terminated_vms:
                log_file.write(f"  VM ID: {vm['id']}, CPU: {vm['requested_cpu']}, Memory: {vm['requested_memory']}, Total Execution Time: {vm['total_execution_time']}, Expected Profit: {vm['expected_profit']}\n")
        if migrated_vms:
            log_file.write("Migrated Virtual Machines:\n")
            for vm in migrated_vms:
                log_file.write(f"  VM ID: {vm['id']}, From PM: {vm['from_pm']} to PM: {vm['to_pm']}\n")
        if killed_vms:
            log_file.write("Killed Virtual Machines:\n")
            for vm in killed_vms:
                log_file.write(f"  VM ID: {vm['id']}, CPU: {vm['requested_cpu']}, Memory: {vm['requested_memory']}, Expected Profit: {vm['expected_profit']}\n")
        if turned_on_pms or turned_off_pms:
            log_file.write("Physical Machines State Change:\n")
            for pm_id in turned_on_pms:
                pm = next(pm for pm in pm_list if pm['id'] == pm_id)
                if pm['time_to_turn_on'] > 0:
                    log_file.write(f"  PM ID: {pm_id} has been turned ON, remaining time to turn on: {pm['time_to_turn_on']}\n")
                else:
                    log_file.write(f"  PM ID: {pm_id} has been turned ON\n")
            for pm_id in turned_off_pms:
                pm = next(pm for pm in pm_list if pm['id'] == pm_id)
                if pm['time_to_turn_off'] > 0:
                    log_file.write(f"  PM ID: {pm_id} has been turned OFF, remaining time to turn off: {pm['time_to_turn_off']}\n")
                else:
                    log_file.write(f"  PM ID: {pm_id} has been turned OFF\n")
        log_file.write("Physical Machines Load:\n")
        for pm_id, load in load_info.items():
            log_file.write(f"  PM ID: {pm_id}, Is On: {load['is_on']}, CPU Load: {load['cpu_load']:.2f}%, Memory Load: {load['memory_load']:.2f}%\n")
    
    # Print log to console
    print(f"\n{Fore.GREEN}{Style.BRIGHT}====== Time Step: {step} ======{Style.RESET_ALL}")
    print(f"{Fore.CYAN}Virtual Machines Allocation:{Style.RESET_ALL}")
    for vm in active_vms:
        print(f"  {Style.BRIGHT}VM ID:{Style.RESET_ALL} {vm['id']}, {Style.BRIGHT}Running on PM:{Style.RESET_ALL} {vm['running_on_pm']}, {Style.BRIGHT}CPU:{Style.RESET_ALL} {vm['requested_cpu']}, {Style.BRIGHT}Memory:{Style.RESET_ALL} {vm['requested_memory']}, {Style.BRIGHT}Execution Time:{Style.RESET_ALL} {vm['current_execution_time']}/{vm['total_execution_time']}, {Style.BRIGHT}Expected Profit:{Style.RESET_ALL} {vm['expected_profit']}")
    if terminated_vms:
        print(f"{Fore.RED}Terminated Virtual Machines:{Style.RESET_ALL}")
        for vm in terminated_vms:
            print(f"  {Style.BRIGHT}VM ID:{Style.RESET_ALL} {vm['id']}, {Style.BRIGHT}CPU:{Style.RESET_ALL} {vm['requested_cpu']}, {Style.BRIGHT}Memory:{Style.RESET_ALL} {vm['requested_memory']}, {Style.BRIGHT}Total Execution Time:{Style.RESET_ALL} {vm['total_execution_time']}, {Style.BRIGHT}Expected Profit:{Style.RESET_ALL} {vm['expected_profit']}")
    if migrated_vms:
        print(f"{Fore.BLUE}Migrated Virtual Machines:{Style.RESET_ALL}")
        for vm in migrated_vms:
            print(f"  {Style.BRIGHT}VM ID:{Style.RESET_ALL} {vm['id']}, {Style.BRIGHT}From PM:{Style.RESET_ALL} {vm['from_pm']} {Style.BRIGHT}to PM:{Style.RESET_ALL} {vm['to_pm']}")
    if killed_vms:
        print(f"{Fore.YELLOW}Killed Virtual Machines:{Style.RESET_ALL}")
        for vm in killed_vms:
            print(f"  {Style.BRIGHT}VM ID:{Style.RESET_ALL} {vm['id']}, {Style.BRIGHT}CPU:{Style.RESET_ALL} {vm['requested_cpu']}, {Style.BRIGHT}Memory:{Style.RESET_ALL} {vm['requested_memory']}, {Style.BRIGHT}Expected Profit:{Style.RESET_ALL} {vm['expected_profit']}")
    if turned_on_pms or turned_off_pms:
        print(f"{Fore.MAGENTA}Physical Machines State Change:{Style.RESET_ALL}")
        for pm_id in turned_on_pms:
            pm = next(pm for pm in pm_list if pm['id'] == pm_id)
            if pm['time_to_turn_on'] > 0:
                print(f"  {Style.BRIGHT}PM ID:{Style.RESET_ALL} {pm_id} {Style.BRIGHT}has been turned ON{Style.RESET_ALL}, remaining time to turn on: {pm['time_to_turn_on']}")
            else:
                print(f"  {Style.BRIGHT}PM ID:{Style.RESET_ALL} {pm_id} {Style.BRIGHT}has been turned ON{Style.RESET_ALL}")
        for pm_id in turned_off_pms:
            pm = next(pm for pm in pm_list if pm['id'] == pm_id)
            if pm['time_to_turn_off'] > 0:
                print(f"  {Style.BRIGHT}PM ID:{Style.RESET_ALL} {pm_id} {Style.BRIGHT}has been turned OFF{Style.RESET_ALL}, remaining time to turn off: {pm['time_to_turn_off']}")
            else:
                print(f"  {Style.BRIGHT}PM ID:{Style.RESET_ALL} {pm_id} {Style.BRIGHT}has been turned OFF{Style.RESET_ALL}")
    print(f"{Fore.MAGENTA}Physical Machines Load:{Style.RESET_ALL}")
    for pm_id, load in load_info.items():
        print(f"  {Style.BRIGHT}PM ID:{Style.RESET_ALL} {pm_id}, {Style.BRIGHT}Is On:{Style.RESET_ALL} {load['is_on']}, {Style.BRIGHT}CPU Load:{Style.RESET_ALL} {load['cpu_load']:.2f}%, {Style.BRIGHT}Memory Load:{Style.RESET_ALL} {load['memory_load']:.2f}%")
    print(f"{Fore.GREEN}{Style.BRIGHT}============================={Style.RESET_ALL}\n")
