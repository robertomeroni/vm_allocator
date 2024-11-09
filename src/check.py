from calculate import calculate_load


def check_unique_state(vms):
    for vm in vms.values():
        state_count = 0
        if vm["allocation"]["pm"] != -1:
            state_count += 1
        if vm["run"]["pm"] != -1:
            state_count += 1
        if vm["migration"]["from_pm"] != -1 or vm["migration"]["to_pm"] != -1:
            state_count += 1
            if vm["migration"]["from_pm"] == -1 or vm["migration"]["to_pm"] == -1:
                raise ValueError(
                    f"VM {vm['id']} has an incorrect migration state: {vm['migration']}."
                )
        if state_count > 1:
            raise ValueError(
                f"VM {vm['id']} has multiple states: {vm['allocation']}, {vm['run']}, and {vm['migration']}."
            )


def check_overload(vms, pms, time_step):
    # update the load of the PMs
    cpu_load, memory_load = calculate_load(pms, vms, time_step)

    for pm_id, pm in pms.items():
        if cpu_load[pm_id] > 1 or memory_load[pm_id] > 1:
            effective_cpu_load = 0
            effective_memory_load = 0
            for vm in vms.values():
                if (
                    vm["allocation"]["pm"] == pm_id
                    or vm["run"]["pm"] == pm_id
                    or vm["migration"]["from_pm"] == pm_id
                    or vm["migration"]["to_pm"] == pm_id
                ):
                    effective_cpu_load += vm["requested"]["cpu"]
                    effective_memory_load += vm["requested"]["memory"]
            if (
                effective_cpu_load > pm["capacity"]["cpu"]
                or effective_memory_load > pm["capacity"]["memory"]
            ):
                raise ValueError(
                    f"PM {pm_id} is overloaded: cpu_load {cpu_load[pm_id]}, memory_load {memory_load[pm_id]}, effective_cpu_load {effective_cpu_load}, effective_memory_load {effective_memory_load}."
                )


def check_migration_correctness(active_vms):
    for vm in active_vms.values():
        if (
            vm["migration"]["from_pm"] != -1
            and vm["migration"]["to_pm"] == -1
            or vm["migration"]["from_pm"] == -1
            and vm["migration"]["to_pm"] != -1
        ):
            raise ValueError(
                f"VM {vm['id']} has an incorrect migration state: {vm['migration']}."
            )
        elif (
            vm["migration"]["from_pm"] == vm["migration"]["to_pm"]
            and vm["migration"]["from_pm"] != -1
        ):
            raise ValueError(
                f"VM {vm['id']} is migrating to the same PM {vm['migration']['to_pm']}."
            )


def check_zero_load(vms, pms):
    for pm_id, pm in pms.items():
        if pm["s"]["load"]["cpu"] == 0 and pm["s"]["load"]["memory"] == 0:
            if pm["s"]["state"] == 1 and pm["s"]["time_to_turn_on"] == 0:
                for vm in vms.values():
                    if (
                        vm["allocation"]["pm"] == pm_id
                        or vm["run"]["pm"] == pm_id
                        or vm["migration"]["from_pm"] == pm_id
                        or vm["migration"]["to_pm"] == pm_id
                    ):
                        raise ValueError(
                            f"VM {vm['id']} is allocated to PM {pm_id} with zero load: {pm['s']['load']}."
                        )


def check_status_changes(previous_state, current_state):
    for vm_id, current_status in current_state.items():
        if current_status != previous_state.get(vm_id):
            if current_status == "allocating":
                if previous_state.get(vm_id) == "running":
                    raise ValueError(
                        f"VM {vm_id} is allocating but was running in the previous state."
                    )
                elif previous_state.get(vm_id) == "migrating":
                    raise ValueError(
                        f"VM {vm_id} is allocating but was migrating in the previous state."
                    )
            elif current_status == "running":
                if previous_state.get(vm_id) == "non-assigned":
                    raise ValueError(
                        f"VM {vm_id} is running but was non-assigned in the previous state."
                    )
            elif current_status == "migrating":
                if previous_state.get(vm_id) == "non-assigned":
                    raise ValueError(
                        f"VM {vm_id} is migrating but was non-assigned in the previous state."
                    )
            elif current_status == "non-assigned":
                if previous_state.get(vm_id) == "allocating":
                    raise ValueError(
                        f"VM {vm_id} is non-assigned but was allocating in the previous state."
                    )
                elif previous_state.get(vm_id) == "running":
                    raise ValueError(
                        f"VM {vm_id} is non-assigned but was running in the previous state."
                    )
                elif previous_state.get(vm_id) == "migrating":
                    raise ValueError(
                        f"VM {vm_id} is non-assigned but was migrating in the previous state."
                    )
