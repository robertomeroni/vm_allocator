// Tuple definitions
tuple Execution {
  float current_time;
  float total_time;
  float pm;
}

tuple Migration {
  float current_time;
  float total_time;
  float down_time;
  float from_pm;
  float to_pm;
}

tuple ArchitectureInt {
  int cpu;
  int memory;
}

tuple ArchitectureFloat {
  float cpu;
  float memory;
}

tuple Features {
  float speed;
}

tuple State {
  float time_to_turn_on;
  float time_to_turn_off;
  ArchitectureFloat load;
  int state; // 0 for OFF, 1 for ON
}

tuple PhysicalMachine {
  key int id;
  ArchitectureInt capacity;
  Features features;
  State s;
};

tuple VirtualMachine {
  key int id;
  ArchitectureInt requested;
  Execution allocation;
  Execution run;
  Migration migration;
};

tuple TimeAndPower {
  float time;
  float power;
}

tuple PMWeights {
  TimeAndPower turn_on;
  TimeAndPower turn_off;
}

tuple SourceTarget {
  float source;
  float target;
}

tuple MigrationEnergy {
  SourceTarget cpu_overhead;
  float concurrent;
}

tuple MigrationTime {
  float memory_dirty_rate;
  float network_bandwidth;
  float resume_vm_on_target;
}

tuple MigrationWeights {
  MigrationTime time;
  MigrationEnergy energy;
}

tuple Energy {
  float cost;
  float limit;
}

tuple Point {
  key float x;
  float y;
}

// Data
{PhysicalMachine} physical_machines = ...;
{VirtualMachine} virtual_machines= ...;
float latency[pm in physical_machines][pm in physical_machines] = ...;
int nb_points = ...;
Point power_function[pm in physical_machines][1..nb_points]= ...;

float main_time_step = ...; // seconds
float time_window = ...; // seconds

float remaining_allocation_time[vm in virtual_machines] = vm.allocation.total_time - vm.allocation.current_time;
float remaining_run_time[vm in virtual_machines] = vm.run.total_time - vm.run.current_time;
float remaining_migration_time[vm in virtual_machines] = vm.migration.total_time - vm.migration.current_time;

int is_fully_turned_on[pm in physical_machines] = // if is going to be fully turned ON in the next time step (unless it gets turned OFF)
  (pm.s.time_to_turn_on <= main_time_step ? 1 : 0); 
int old_allocation[vm in virtual_machines][pm in physical_machines] = 
  (vm.allocation.pm == pm.id || vm.run.pm == pm.id || vm.migration.to_pm == pm.id ? 1 : 0);
int was_allocating[vm in virtual_machines] = 
  (vm.allocation.pm > -1 ? 1 : 0); 
int was_running[vm in virtual_machines] = 
  (vm.run.pm > -1 ? 1 : 0); 
int was_migrating[vm in virtual_machines] = // (does not consider a new migration decided in this time step)
  (vm.migration.to_pm > -1 || vm.migration.from_pm > -1 ? 1 : 0); 
int was_migrating_from[vm in virtual_machines][pm in physical_machines] =
  (vm.migration.from_pm == pm.id ? 1 : 0);
//int is_same_group[v1 in virtual_machines][v2 in virtual_machines] = 
//  (v1.group == v2.group ? 1 : 0); 

int M = card(virtual_machines);

// Energy consumption in 1 second time period of each Physical Machine, depending by the load
float slopeBeforePoint[pm in physical_machines][p in 1..nb_points]=
  (p == 1) ? 0 : (power_function[pm][p].y - power_function[pm][p-1].y)/(power_function[pm][p].x-power_function[pm][p-1].x);
float static_power[pm in physical_machines] = power_function[pm][1].y; 
pwlFunction dynamic_power[pm in physical_machines] = 
  piecewise (p in 1..nb_points){slopeBeforePoint[pm][p] -> power_function[pm][p].x; 0} (0, 0); 
 
// Weights
ArchitectureFloat price = ...;
Energy energy = ...;
float PUE = ...;
MigrationWeights migration = ...;
float w_load_cpu = ...;

PMWeights w_pm[pm in physical_machines] = 
  <<pm.s.time_to_turn_on, 0>,                        // turn_on: <time (s), power (W)>
   <pm.s.time_to_turn_off, static_power[pm]>         // turn_off: <time (s), power (W)>
  >;

float profit[vm in virtual_machines] = (vm.requested.cpu * price.cpu + vm.requested.memory * price.memory); // Profit per second from running a Virtual Machine
 
// Decision Variables
dvar boolean is_on[physical_machines]; // if it is on in the new allocation (already on or will be turned on)
dvar boolean new_allocation[virtual_machines][physical_machines];
dvar boolean is_allocation[virtual_machines];
dvar boolean is_allocating_on[virtual_machines][physical_machines];
dvar boolean is_run[virtual_machines]; // if it is running in the new allocation (allocated on a fully turned ON machine and not migrating)
dvar boolean is_running_on[virtual_machines][physical_machines];
dvar boolean is_migration[virtual_machines];
dvar boolean is_first_migration[virtual_machines];
dvar boolean is_migrating_on[virtual_machines][physical_machines];
dvar boolean is_migrating_from[virtual_machines][physical_machines];
dvar float+ extra_cpu_load;   // total future effective cpu load on the physical machines (excluding already allocated vms)
dvar float+ extra_memory_load;   // total future effective memory load on the physical machines (excluding already allocated vms)

// Expressions
dexpr float cpu_load[pm in physical_machines] = (1 / pm.capacity.cpu) * sum(vm in virtual_machines) vm.requested.cpu * new_allocation[vm][pm];
dexpr float memory_load[pm in physical_machines] = (1 / pm.capacity.memory) * sum(vm in virtual_machines) vm.requested.memory * new_allocation[vm][pm]; 
dexpr float cpu_load_extra[pm in physical_machines] = (1 / pm.capacity.cpu) * sum(vm in virtual_machines) vm.requested.cpu * (new_allocation[vm][pm] + is_migrating_from[vm][pm] - is_allocating_on[vm][pm] * (1 - was_allocating[vm])); // When there is a migration, allow pre-allocation of VMs
dexpr float memory_load_extra[pm in physical_machines] = (1 / pm.capacity.memory) * sum(vm in virtual_machines) vm.requested.memory * (new_allocation[vm][pm] + is_migrating_from[vm][pm] - is_allocating_on[vm][pm] * (1 - was_allocating[vm])); 
dexpr float cpu_load_overhead[pm in physical_machines] = (1 / pm.capacity.cpu) * sum(vm in virtual_machines) vm.requested.cpu * (new_allocation[vm][pm] + migration.energy.cpu_overhead.source * is_migrating_from[vm][pm] + migration.energy.cpu_overhead.target * is_migrating_on[vm][pm]);
dexpr int turn_on[pm in physical_machines] = (1 - pm.s.state) * is_on[pm];  
dexpr int turn_off[pm in physical_machines] = pm.s.state * (1 - is_on[pm]); 
dexpr int is_added[vm in virtual_machines] = (1 - sum(pm in physical_machines) old_allocation[vm][pm]) * sum(pm in physical_machines) new_allocation[vm][pm];
dexpr int is_removal[vm in virtual_machines] = sum(pm in physical_machines) old_allocation[vm][pm] * (1 - sum(pm in physical_machines) new_allocation[vm][pm]);
//dexpr float latency_penalty[v1 in virtual_machines][p1 in physical_machines] = sum(v2 in virtual_machines, p2 in physical_machines) latency[p1][p2] * is_same_group[v1][v2] * (is_allocating_on[v2][p2] + is_running_on[v2][p2]);   // sum of the additional latencies when VM runs on PM

dexpr float future_cpu_load[pm in physical_machines] = 
    sum(vm in virtual_machines) (
    	is_allocating_on[vm][pm] * minl(pm.s.time_to_turn_on + remaining_allocation_time[vm] + remaining_run_time[vm], time_window)
	  + is_running_on[vm][pm] * minl(remaining_run_time[vm], time_window)
	  + is_migrating_on[vm][pm] * minl(pm.s.time_to_turn_on + remaining_migration_time[vm] + remaining_run_time[vm], time_window)
	  + is_migrating_from[vm][pm] * minl(remaining_migration_time[vm] + remaining_run_time[vm], time_window)
	) * vm.requested.cpu;
	
dexpr float future_memory_load[pm in physical_machines] = 
    sum(vm in virtual_machines) (
    	is_allocating_on[vm][pm] * minl(pm.s.time_to_turn_on + remaining_allocation_time[vm] + remaining_run_time[vm], time_window)
	  + is_running_on[vm][pm] * minl(remaining_run_time[vm], time_window)
	  + is_migrating_on[vm][pm] * minl(pm.s.time_to_turn_on + remaining_migration_time[vm] + remaining_run_time[vm], time_window)
	  + is_migrating_from[vm][pm] * minl(remaining_migration_time[vm] + remaining_run_time[vm], time_window)
	) * vm.requested.memory;

float cpu_fragmentation_factor[pm in physical_machines] = 0.9;
float memory_fragmentation_factor[pm in physical_machines] = 0.9;
float expected_runtime_factor = 0.9;   //  run time / real completion time (allocation time + run time + eventual migration time)
float expected_cpu_workload = time_window * 1*4;
float expected_memory_workload = time_window * 1*30; 

// Model
// Objective Function Latency 
//maximize   sum (vm in virtual_machines) ( 
//		 	 - PUE * energy.cost * migration_energy[vm] * is_migration[vm] / remaining_migration_time[vm]
//		   ) 
//		 + sum(pm in physical_machines) ( 
//	         - PUE * energy.cost * (
//		             w_pm[pm].turn_on.power * turn_on[pm] * minl(time_window, pm.s.time_to_turn_on)
//		           + w_pm[pm].turn_off.power * turn_off[pm] * minl(time_window, pm.s.time_to_turn_off)
//		           + static_power[pm] * is_on[pm] * time_window
//		           + dynamic_power[pm](w_load_cpu * (cpu_load[pm] + cpu_load_extra[pm]) + (1 - w_load_cpu) * (memory_load[pm] + memory_load_extra[pm])) * is_fully_turned_on[pm]
//               )
//		     + sum (vm in virtual_machines) ( 
//		     	 // allocation case
//		     	 sum (vm2 in virtual_machines, pm2 in physical_machines) 
//        		   is_allocating_on[vm][pm] * is_allocating_on[vm2][pm2] * time_window * profit[vm] * vm.run.total_time                                                                // total profit
//        		 / (pm.s.time_to_turn_on + (0*is_same_group[vm][vm2] * latency[pm][pm2] + remaining_allocation_time[vm] + remaining_run_time[vm]) / pm.features.speed)                    // effective remaining time
//        		 // run case
//        		 + is_running_on[vm][pm] * time_window * profit[vm] * vm.run.total_time          // total profit
//        		 / (remaining_run_time[vm] / pm.features.speed)                    // effective remaining time
//		         // migration case
//		         + is_migrating_on[vm][pm] * time_window * profit[vm] * vm.run.total_time   															// total profit
//		         / ((remaining_run_time[vm] + remaining_migration_time[vm] * migration_penalty) / pm.features.speed)                    // effective remaining time
//		       )		   
//		   );

// Objective Function: time window
maximize   sum(pm in physical_machines) ( 
	         - PUE * energy.cost * (
		             w_pm[pm].turn_off.power * turn_off[pm] * minl(time_window, pm.s.time_to_turn_off)
		           + static_power[pm] * is_on[pm] * time_window
		           + dynamic_power[pm](w_load_cpu * cpu_load_overhead[pm] + (1 - w_load_cpu) * memory_load[pm]) * is_fully_turned_on[pm] 
		           + dynamic_power[pm](w_load_cpu * cpu_fragmentation_factor[pm] + (1 - w_load_cpu) * memory_fragmentation_factor[pm]) * (time_window - pm.s.time_to_turn_on) * is_on[pm]
               )
		     + sum (vm in virtual_machines) ( 
        		   is_allocating_on[vm][pm] * profit[vm] * minl(vm.run.total_time - pm.s.time_to_turn_on - remaining_allocation_time[vm], time_window) * pm.features.speed    // allocation case 
        		 + is_running_on[vm][pm] * profit[vm] * minl(remaining_run_time[vm], time_window) * pm.features.speed   // run case
		         + is_migrating_on[vm][pm] * profit[vm] * minl(remaining_run_time[vm] - remaining_migration_time[vm], time_window) * pm.features.speed    // migration case
			   )
		   )
		   // removal case
		 - sum(vm in virtual_machines) 
		       is_removal[vm] * profit[vm] * vm.run.total_time * (vm.allocation.current_time + vm.run.current_time) / (vm.allocation.total_time + vm.run.total_time)
		   // future profits
		 + extra_cpu_load * expected_runtime_factor * price.cpu + extra_memory_load * expected_runtime_factor * price.memory
		   ;

			   
subject to {
  // If Virtual Machine is allocated, the Physical Machine has to be ON (or turning ON)
  forall(pm in physical_machines) {
    forall (vm in virtual_machines) {
      new_allocation[vm][pm] <= is_fully_turned_on[pm]; 
    }
  }        
  // A Virtual Machine is assigned maximum to one Physical Machine
  forall (vm in virtual_machines) {
    sum (pm in physical_machines) new_allocation[vm][pm] <= 1;
  } 
  // Physical Machine CPU and Memory capacity
  forall(pm in physical_machines) {
    cpu_load[pm] <= 1; 
    memory_load[pm] <= 1; 
  }
  // Physical Machine CPU and Memory capacity during migration
  forall(pm in physical_machines) {
    cpu_load_extra[pm] <= 1;
    memory_load_extra[pm] <= 1;
  } 
  // To enter in a state, Virtual Machine has to be allocated
  forall (vm in virtual_machines) {
    is_added[vm] <= sum(pm in physical_machines) new_allocation[vm][pm];
    is_allocation[vm] <= sum(pm in physical_machines) new_allocation[vm][pm];
    is_run[vm] <= sum(pm in physical_machines) is_fully_turned_on[pm] * new_allocation[vm][pm];
    is_first_migration[vm] <= sum(pm in physical_machines) new_allocation[vm][pm];
    is_migration[vm] <= sum(pm in physical_machines) new_allocation[vm][pm];
    is_allocation[vm] + is_run[vm] + is_migration[vm] <= sum(pm in physical_machines) new_allocation[vm][pm];
  } 
  // If a Virtual Machine is added or if it was allocating and is not removal, VM state is an allocation
  forall (vm in virtual_machines) {
	is_allocation[vm] >= is_added[vm];
	is_removal[vm] + is_allocation[vm] >= was_allocating[vm];
  }
  // A Virtual Machine cannot go from running or migrating state to allocation state 
  forall (vm in virtual_machines) {
    is_allocation[vm] <= 1 - was_running[vm]; 
    is_allocation[vm] <= 1 - was_migrating[vm]; 
  }
  // A Virtual Machine can run only if allocation or migration are completed
  forall (vm in virtual_machines) {
    is_run[vm] <= was_running[vm]; 
  } 
  // Virtual Machine is at first step of migration
  forall (vm in virtual_machines) {
    is_first_migration[vm] <= is_migration[vm];
    is_first_migration[vm] <= was_running[vm];
    is_first_migration[vm] + 1 - is_migration[vm] >= was_running[vm];
  }
  // A Virtual Machine can migrate only if it was running or it was already migrating
  forall (vm in virtual_machines) {
   is_migration[vm] <= is_first_migration[vm] + was_migrating[vm];
  }
  // Migration (if the allocation is different but the VM is not being added or removed it is a migration)
  forall (vm in virtual_machines) {
    forall (pm in physical_machines) {
      is_added[vm] + is_removal[vm] + old_allocation[vm][pm] + (1 - new_allocation[vm][pm]) + is_migration[vm] >= 1;
      is_added[vm] + is_removal[vm] + (1 - old_allocation[vm][pm]) + new_allocation[vm][pm] + is_migration[vm] >= 1;
    }  
  }
  // If a Virtual Machine is migrating, the new allocation should be different from where it is migrating
  forall (vm in virtual_machines) {
    forall (pm in physical_machines) {
       (1 - is_first_migration[vm]) + (1 - new_allocation[vm][pm]) >= old_allocation[vm][pm]; 
    }
  }    
  // If a Virtual Machine was migrating, it cannot be considered for reallocation
  forall (vm in virtual_machines) {
    forall (pm in physical_machines) {
       was_migrating[vm] * old_allocation[vm][pm] <= new_allocation[vm][pm] + is_removal[vm]; 
    }
  }    
  // Iff VM is assigned to PM in new_allocation and if it is already allocating or is an allocation, VM is allocating on PM
  forall (vm in virtual_machines) {
    forall (pm in physical_machines) {
  	   is_allocation[vm] + new_allocation[vm][pm] <= 1 + is_allocating_on[vm][pm];
  	   is_allocating_on[vm][pm] <= is_allocation[vm];
  	   is_allocating_on[vm][pm] <= new_allocation[vm][pm];
    }
  }      	   
  // Iff VM is assigned to PM in new_allocation and is a run, VM is running on PM
  forall (vm in virtual_machines) {
    forall (pm in physical_machines) {
  	   is_run[vm] + new_allocation[vm][pm] <= 1 + is_running_on[vm][pm];
  	   is_running_on[vm][pm] <= is_run[vm];
  	   is_running_on[vm][pm] <= new_allocation[vm][pm];
    }
  }      	   
  // Iff VM is assigned to PM in new_allocation and is a migration, VM is migrating on PM
  forall (vm in virtual_machines) {
    forall (pm in physical_machines) {
  	   is_migration[vm] + new_allocation[vm][pm] <= 1 + is_migrating_on[vm][pm];
  	   is_migrating_on[vm][pm] <= is_migration[vm];
  	   is_migrating_on[vm][pm] <= new_allocation[vm][pm];
    }
  }  
  // Iff a VM was migrating (and still), or if a VM is at first migration and was allocated on PM, VM is migrating from PM
  forall (vm in virtual_machines) {
    forall (pm in physical_machines) {
      was_migrating_from[vm][pm] * is_migration[vm] + is_first_migration[vm] * old_allocation[vm][pm] >= is_migrating_from[vm][pm];
      was_migrating_from[vm][pm] * is_migration[vm] <= is_migrating_from[vm][pm];
      is_first_migration[vm] * old_allocation[vm][pm] <= is_migrating_from[vm][pm];
    }
  }  
  // If a VM is migrating from a PM, the PM has to be on
  forall (pm in physical_machines) {
    M * is_on[pm] >= sum(vm in virtual_machines) is_migrating_from[vm][pm];
  }
  // If a VM is migrating to a PM, the PM has to be fully on
  forall (pm in physical_machines) {
    M * is_fully_turned_on[pm] >= sum(vm in virtual_machines) is_migrating_on[vm][pm];
  }
  // Extra CPU load: Total CPU slots (non allocated) multiplied by time that can be computed in the time window
  extra_cpu_load <= (expected_memory_workload + sum(vm in virtual_machines, pm in physical_machines) (1 - new_allocation[vm][pm]) * vm.requested.cpu * minl(time_window, vm.allocation.total_time + vm.run.total_time)) - sum(pm in physical_machines) future_cpu_load[pm] / expected_runtime_factor ;
  extra_cpu_load <= sum(pm in physical_machines) (is_on[pm] * pm.capacity.cpu * time_window - future_cpu_load[pm]) * cpu_fragmentation_factor[pm] * pm.features.speed;
  // Extra memory load: Total memory slots (non allocated) multiplied by time that can be computed in the time window
  extra_memory_load <= (expected_memory_workload + sum(vm in virtual_machines, pm in physical_machines) (1 - new_allocation[vm][pm]) * vm.requested.memory * minl(time_window, vm.allocation.total_time + vm.run.total_time)) - sum(pm in physical_machines) future_memory_load[pm] / expected_runtime_factor ;
  extra_memory_load <= sum(pm in physical_machines) (is_on[pm] * pm.capacity.memory * time_window - future_memory_load[pm]) * memory_fragmentation_factor[pm] * pm.features.speed;
  // Uniqueness of Virtual Machine state
  forall (vm in virtual_machines) {
    is_allocation[vm] + is_run[vm] + is_migration[vm] + is_removal[vm] <= 1; 
    is_allocation[vm] + is_run[vm] + is_migration[vm] + is_removal[vm] >= sum(pm in physical_machines) old_allocation[vm][pm]; 
  }
}