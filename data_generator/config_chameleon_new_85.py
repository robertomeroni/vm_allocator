import os

# Configuration for Physical Machines
pm_config = {
    'cpu_capacity': [48],      # Available CPU capacities in cores
    'memory_capacity': [128],    # Available memory capacities in GB
    'speed_range': (1, 1),                         # Speed range for the machines 
    'time_to_turn_on_range': (25.0, 25.0),            # Time to turn on range in seconds
    'time_to_turn_off_range': (12.0, 12.0),            # Time to turn off range in seconds
    'state_percentage': 0,                            # Percentage of physical machines that are ON initially
}

# Configuration for Virtual Machines
vm_config = {
    'requested_cpu': [1, 2, 4, 8],          # Requested CPU capacities in cores
    'requested_memory': [2, 4, 8, 16],      # Requested memory capacities in GB
    'allocation_time_range': (1.0, 3.0),    # Range for allocation time in seconds
    'execution_time_range': (2.0, 6.0),     # Range for execution time in seconds
}

migration = {
    'time': {  # in seconds
        'memory_dirty_rate': 0.1,  # GB of memory that gets dirty per second during live migration
        'network_bandwidth': 10.0,  # GB/s
        'resume_vm_on_target': 20.0 / 10**3,  # in seconds
    },
    'energy': {  
        'cpu_overhead': {
            'source': 0.015,
            'target': 0.017,
        },
        'concurrent': 0.016
    }
}

# Default Values for the Number of Machines
default_values = {
    'num_physical_machines': 10,            # Default number of physical machines
    'num_virtual_machines': 20,             # Default number of virtual machines
    'running_percentage': 0                # Percentage of VMs that are running at the beginning
}

# Data Folder Path
base_path = '/home/roberto/job/vm_allocator'
data_folder_path = os.path.join(base_path, 'model/data')


# Convenience Aliases for Easy Access
pm_cpu_capacity = pm_config['cpu_capacity']
pm_memory_capacity = pm_config['memory_capacity']
pm_speed_range = pm_config['speed_range']
pm_time_to_turn_on_range = pm_config['time_to_turn_on_range']
pm_time_to_turn_off_range = pm_config['time_to_turn_off_range']
state_percentage = pm_config['state_percentage']

vm_requested_cpu = vm_config['requested_cpu']
vm_requested_memory = vm_config['requested_memory']
allocation_time_range = vm_config['allocation_time_range']
execution_time_range = vm_config['execution_time_range']

migration_time_memory_dirty_rate = migration['time']['memory_dirty_rate']
migration_time_network_bandwidth = migration['time']['network_bandwidth']
migration_time_resume_vm_on_target = migration['time']['resume_vm_on_target']

default_num_physical_machines = default_values['num_physical_machines']
default_num_virtual_machines = default_values['num_virtual_machines']
running_percentage = default_values['running_percentage']
