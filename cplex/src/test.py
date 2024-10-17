from collections import defaultdict

# Your list of active VMs
active_vms = [
    {
        'id': 'vm1',
        'migration': {
            'total_time': 100,
            'current_time': 20,
            'from_pm': 'pm1',
            'to_pm': 'pm2'
        }
    },
    {
        'id': 'vm2',
        'migration': {
            'total_time': 80,
            'current_time':70,
            'from_pm': 'pm1',
            'to_pm': 'pm3'
        }
    },
    {
        'id': 'vm3',
        'migration': {
            'total_time': 120,
            'current_time': 70,
            'from_pm': 'pm4',
            'to_pm': 'pm1'
        }
    },
    {
        'id': 'vm4',
        'migration': {
            'total_time': 90,
            'current_time': 60,
            'from_pm': 'pm1',
            'to_pm': 'pm5'
        }
    },
    {
        'id': 'vm5',
        'migration': {
            'total_time': 70,
            'current_time': 40,
            'from_pm': 'pm6',
            'to_pm': 'pm1'
        }
    },
    {
        'id': 'vm6',
        'migration': {
            'total_time': 110,
            'current_time': 50,
            'from_pm': 'pm1',
            'to_pm': 'pm7'
        }
    }
]

# Add vm7 to the list
active_vms.append({
    'id': 'vm7',
    'migration': {
        'total_time': 130,
        'current_time': 0,
        'from_pm': 'pm8',
        'to_pm': 'pm1'
    }
})

# The physical machine we're focusing on
pm = {'id': 'pm1'}
pm_id = pm['id']

def find_two_largest(times):
    max_time = second_max_time = 0
    for time in times:
        if time > max_time:
            second_max_time = max_time
            max_time = time
        elif time > second_max_time:
            second_max_time = time
    return max_time, second_max_time

def find_migration_times_3(vms_from, vms_to):
    """
    Calculate migration time durations based on VMs migrating from and to a PM.

    Parameters:
    - vms_from (list): List of VM dictionaries migrating from the PM.
    - vms_to (list): List of VM dictionaries migrating to the PM.

    Returns:
    - tuple: (real_time_only_source, real_time_only_target,
              real_time_multiple_source, real_time_multiple_target,
              real_time_multiple_source_and_target)
    """
    # Extract remaining times for source and target migrations
    source_times = [vm['migration']['total_time'] - vm['migration']['current_time'] for vm in vms_from]
    target_times = [vm['migration']['total_time'] - vm['migration']['current_time'] for vm in vms_to]

    # Create a list of events: (time, type_flag)
    # type_flag: 0 for source, 1 for target
    events = [(t, 0) for t in source_times] + [(t, 1) for t in target_times]

    # Sort events by time
    events.sort()

    # Initialize counts of running migrations
    n_source_running = len(source_times)
    n_target_running = len(target_times)

    # Initialize previous time marker
    prev_time = 0

    # Initialize result variables
    real_time_only_source = 0
    real_time_only_target = 0
    real_time_multiple_source = 0
    real_time_multiple_target = 0
    real_time_multiple_source_and_target = 0

    # Iterate through each event to calculate durations
    for t, event_type in events:
        duration = t - prev_time

        # Categorize the duration based on active migrations
        if n_source_running > 0 and n_target_running == 0:
            if n_source_running == 1:
                real_time_only_source += duration
            else:
                real_time_multiple_source += duration
        elif n_source_running == 0 and n_target_running > 0:
            if n_target_running == 1:
                real_time_only_target += duration
            else:
                real_time_multiple_target += duration
        elif n_source_running > 0 and n_target_running > 0:
            real_time_multiple_source_and_target += duration
        # If both n_source_running and n_target_running are zero, do nothing

        # Update counts based on the event type
        if event_type == 0:
            n_source_running -= 1
        else:
            n_target_running -= 1

        # Update the previous time marker
        prev_time = t

    return (
        real_time_only_source,
        real_time_only_target,
        real_time_multiple_source,
        real_time_multiple_target,
        real_time_multiple_source_and_target
    )

def find_migration_times_2(vms_from, vms_to):
    # Collect remaining migration times for VMs migrating from the PM
    source_vm_times = [
        vm['migration']['total_time'] - vm['migration']['current_time']
        for vm in vms_from
    ]

    # Collect remaining migration times for VMs migrating to the PM
    target_vm_times = [
        vm['migration']['total_time'] - vm['migration']['current_time']
        for vm in vms_to
    ]

    # Find max and second max times for source VMs
    max_time_source, second_max_time_source = find_two_largest(source_vm_times)

    # Find max and second max times for target VMs
    max_time_target, second_max_time_target = find_two_largest(target_vm_times)

    # Compute effective times
    real_time_only_source = max_time_source
    real_time_only_target = max_time_target
    real_time_multiple_source = max_time_source - second_max_time_source
    real_time_multiple_target = max_time_target - second_max_time_target

    # Combined times for both source and target VMs
    combined_times = source_vm_times + target_vm_times
    max_combined_time, second_max_combined_time = find_two_largest(combined_times)
    real_time_multiple_source_and_target = max_combined_time - second_max_combined_time

    return (
        real_time_only_source,
        real_time_only_target,
        real_time_multiple_source,
        real_time_multiple_target,
        real_time_multiple_source_and_target
    )

def find_migration_times(active_vms, pm):
    pm_id = pm['id']
    
    # Get remaining times for migrations from pm (source)
    source_times = [vm['migration']['total_time'] - vm['migration']['current_time'] 
                    for vm in active_vms if vm['migration']['from_pm'] == pm_id]
    
    # Get remaining times for migrations to pm (target)
    target_times = [vm['migration']['total_time'] - vm['migration']['current_time'] 
                    for vm in active_vms if vm['migration']['to_pm'] == pm_id]
    
    # All unique event times when migrations end
    event_times = sorted(set(source_times + target_times))
    
    # Initialize counts
    n_source_running = len(source_times)
    n_target_running = len(target_times)
    
    # Create a dictionary of events to track migrations ending
    events = {}
    for t in source_times:
        events.setdefault(t, {'source': 0, 'target': 0})
        events[t]['source'] += 1
    for t in target_times:
        events.setdefault(t, {'source': 0, 'target': 0})
        events[t]['target'] += 1
    
    # Sort the event times
    sorted_event_times = sorted(events.keys())
    
    # Initialize variables
    intervals = []
    prev_time = 0
    
    # Process each interval between events
    for t in sorted_event_times:
        # Duration of the current interval
        duration = t - prev_time
        
        # Record the interval and counts
        intervals.append((prev_time, t, n_source_running, n_target_running))
        
        # Update counts based on events at time t
        n_source_running -= events[t]['source']
        n_target_running -= events[t]['target']
        
        # Move to the next time
        prev_time = t
    
    # Compute the durations for each condition
    real_time_only_source = 0
    real_time_only_target = 0
    real_time_multiple_source = 0
    real_time_multiple_target = 0
    real_time_multiple_source_and_target = 0
    
    for start, end, n_source, n_target in intervals:
        duration = end - start
        if n_source > 0 and n_target == 0:
            if n_source == 1:
                real_time_only_source += duration
            elif n_source > 1:
                real_time_multiple_source += duration
        elif n_source == 0 and n_target > 0:
            if n_target == 1:
                real_time_only_target += duration
            elif n_target > 1:
                real_time_multiple_target += duration
        elif n_source > 0 and n_target > 0:
            real_time_multiple_source_and_target += duration
        # If both n_source and n_target are zero, do nothing
    
    return (
        real_time_only_source,
        real_time_only_target,
        real_time_multiple_source,
        real_time_multiple_target,
        real_time_multiple_source_and_target
    )

# Create mappings of PMs to VMs migrating from and to them
pm_migrations_from = defaultdict(list)
pm_migrations_to = defaultdict(list)

for vm in active_vms:
    from_pm_id = vm['migration']['from_pm']
    to_pm_id = vm['migration']['to_pm']
    if from_pm_id != -1:
        pm_migrations_from[from_pm_id].append(vm)
    if to_pm_id != -1:
        pm_migrations_to[to_pm_id].append(vm)
                                                  
# Get lists of VMs migrating from/to this PM
vms_from = pm_migrations_from.get(pm_id, [])
vms_to = pm_migrations_to.get(pm_id, [])

# Run both functions with the appropriate arguments
times = find_migration_times(active_vms, pm)
times_2 = find_migration_times_2(vms_from, vms_to)
times_3 = find_migration_times_3(vms_from, vms_to)
# Print the results
print("Results find_migration_times:")
print("Real time only source:", times[0])
print("Real time only target:", times[1])
print("Real time multiple source:", times[2])
print("Real time multiple target:", times[3])
print("Real time multiple source and target:", times[4])
print("----------------------------------------")
print("Results find_migration_times_2:")
print("Real time only source:", times_2[0])
print("Real time only target:", times_2[1])
print("Real time multiple source:", times_2[2])
print("Real time multiple target:", times_2[3])
print("Real time multiple source and target:", times_2[4])
print("----------------------------------------")
print("Results find_migration_times_3:")
print("Real time only source:", times_3[0])
print("Real time only target:", times_3[1])
print("Real time multiple source:", times_3[2])
print("Real time multiple target:", times_3[3])
print("Real time multiple source and target:", times_3[4])