import random

def generate_new_vms(active_vms, new_vms_per_step, existing_ids):
    for _ in range(new_vms_per_step):
        new_vm_id = generate_unique_id(existing_ids)
        new_vm = {
            'id': new_vm_id,
            'requested': {
                'cpu': random.choice([1, 2, 4, 8, 16]),
                'memory': random.choice([4, 8, 16, 32, 64])
            },
            'allocation': {
                'current_time': 0.0,
                'total_time': round(random.uniform(1.0, 3.0), 1),
                'pm': -1  # New VM is not running on any physical machine initially
            },
            'run': {
                'current_time': 0.0,
                'total_time': round(random.uniform(1.0, 10.0), 1),
                'pm': -1  # New VM is not running on any physical machine initially
            },
            'migration': {
                'current_time': 0.0,
                'total_time': round(random.uniform(1.0, 3.0), 1),
                'from_pm': -1,  # New VM is not migrating from any physical machine initially
                'to_pm': -1  # New VM is not migrating on any physical machine initially
            },
            'group': random.randint(1, 5),  # Random group for co-allocation preference
            'expected_profit': round(random.uniform(100.0, 1000.0), 2)
        }
        active_vms.append(new_vm)
        existing_ids.add(new_vm_id)

def generate_unique_id(existing_ids):
    new_id = max(existing_ids) + 1 if existing_ids else 0
    while new_id in existing_ids:
        new_id += 1
    return new_id
