# Configuration for Physical Machines
pm_config = {
    'cpu_capacity': [4, 8, 16, 32],
    'memory_capacity': [16, 32, 64, 128],
    'speed_range': (1.0, 3.0),
    'max_energy_consumption_range': (100.0, 500.0),
    'time_to_turn_on_range': (1.0, 3.0),
    'time_to_turn_off_range': (1.0, 3.0),
    'state_percentage': 0
}

# Configuration for Virtual Machines
vm_config = {
    'requested_cpu': [1, 2, 4, 8],
    'requested_memory': [2, 4, 8, 16],
    'allocation_time_range': (1.0, 3.0),  # Range for allocation time
    'execution_time_range': (2.0, 6.0),
    'expected_profit_range': (10.0, 1000.0),
    'migration_time_range': (1.0, 3.0)
}

# Default Values for the Number of Machines
default_values = {
    'num_physical_machines': 10,
    'num_virtual_machines': 20,
    'running_percentage': 20  # Percentage of VMs that are running at the beginning
}

# Data Folder Path
data_folder_path = '/home/roberto/job/vm_allocator/cplex/model/data'

# Convenience Aliases for Easy Access
pm_cpu_capacity = pm_config['cpu_capacity']
pm_memory_capacity = pm_config['memory_capacity']
pm_speed_range = pm_config['speed_range']
pm_max_energy_consumption_range = pm_config['max_energy_consumption_range']
pm_time_to_turn_on_range = pm_config['time_to_turn_on_range']
pm_time_to_turn_off_range = pm_config['time_to_turn_off_range']
state_percentage = pm_config['state_percentage']

vm_requested_cpu = vm_config['requested_cpu']
vm_requested_memory = vm_config['requested_memory']
allocation_time_range = vm_config['allocation_time_range']
execution_time_range = vm_config['execution_time_range']
vm_expected_profit_range = vm_config['expected_profit_range']
migration_time_range = vm_config['migration_time_range']

default_num_physical_machines = default_values['num_physical_machines']
default_num_virtual_machines = default_values['num_virtual_machines']
running_percentage = default_values['running_percentage']
