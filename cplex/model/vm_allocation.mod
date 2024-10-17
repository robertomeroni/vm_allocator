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

tuple CplexParameters {
  float time_limit;
  float relative_optimality_gap;
  float absolute_optimality_gap;
}

tuple CplexModelParameters {
  CplexParameters main_model;
  CplexParameters mini_model;
}

// Data
{PhysicalMachine} physical_machines = ...;
{VirtualMachine} virtual_machines = ...;
int nb_points = ...;
Point power_function[pm in physical_machines][1..nb_points]= ...;

float main_time_step = ...; // seconds
float time_window = ...;

float remaining_allocation_time[vm in virtual_machines] = vm.allocation.total_time - vm.allocation.current_time;
float remaining_run_time[vm in virtual_machines] = vm.run.total_time - vm.run.current_time;
float remaining_migration_time[vm in virtual_machines] = vm.migration.total_time - vm.migration.current_time;

int is_fully_turned_on[pm in physical_machines] =
  (pm.s.time_to_turn_on <= 0 ? 1 : 0); 
int is_on[pm in physical_machines] = // if is going to be fully turned ON in the next time step (unless it gets turned OFF)
  (pm.s.time_to_turn_on < main_time_step ? 1 : 0); 
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

int M = card(virtual_machines);

// Energy consumption in 1 second time period of each Physical Machine, depending by the load
float slopeBeforePoint[pm in physical_machines][p in 1..nb_points]=
  (p == 1) ? 0 : (power_function[pm][p].y - power_function[pm][p-1].y)/(power_function[pm][p].x-power_function[pm][p-1].x);
float static_power[pm in physical_machines] = power_function[pm][1].y; 
pwlFunction dynamic_power[pm in physical_machines] = 
  piecewise (p in 1..nb_points){slopeBeforePoint[pm][p] -> power_function[pm][p].x; slopeBeforePoint[pm][nb_points]} (0, 0); 

// Weights
ArchitectureFloat price = ...;
Energy energy = ...;
float PUE = ...;
MigrationWeights migration = ...;
float migration_penalty = ...;
float w_concurrent_migrations = ...;
float w_load_cpu = ...;

float profit[vm in virtual_machines] = (vm.requested.cpu * price.cpu + vm.requested.memory * price.memory); // Profit per second from running a Virtual Machine

CplexModelParameters params = ...;

// Set parameters
execute
{
  cplex.tilim= params.main_model.time_limit;
  cplex.epgap= params.main_model.relative_optimality_gap;
  cplex.epagap= params.main_model.absolute_optimality_gap;
} 

// Decision Variables
dvar boolean new_allocation[virtual_machines][physical_machines];
dvar boolean is_allocation[virtual_machines];
dvar boolean is_allocating_on[virtual_machines][physical_machines];
dvar boolean is_run[virtual_machines]; // if it is running in the new allocation (allocated on a fully turned ON machine and not migrating)
dvar boolean is_running_on[virtual_machines][physical_machines];
dvar boolean is_migration[virtual_machines];
dvar boolean is_first_migration[virtual_machines];
dvar boolean is_migrating_on[virtual_machines][physical_machines];
dvar boolean is_migrating_from[virtual_machines][physical_machines];
dvar boolean is_multiple_migrations[physical_machines];
dvar boolean has_to_be_on[physical_machines];
dvar float+ max_migration_source[physical_machines];
dvar float+ max_migration_target[physical_machines];
dvar float+ max_migration_multiple[physical_machines];

// Expressions
dexpr float cpu_load[pm in physical_machines] = (1 / pm.capacity.cpu) * sum(vm in virtual_machines) vm.requested.cpu * new_allocation[vm][pm];
dexpr float memory_load[pm in physical_machines] = (1 / pm.capacity.memory) * sum(vm in virtual_machines) vm.requested.memory * new_allocation[vm][pm]; 
dexpr float cpu_load_total[pm in physical_machines] = (1 / pm.capacity.cpu) * sum(vm in virtual_machines) vm.requested.cpu * (new_allocation[vm][pm] + is_migrating_from[vm][pm] * remaining_migration_time[vm] / remaining_run_time[vm]);
dexpr float memory_load_total[pm in physical_machines] = (1 / pm.capacity.memory) * sum(vm in virtual_machines) vm.requested.memory * (new_allocation[vm][pm] + is_migrating_from[vm][pm] * remaining_migration_time[vm] / remaining_run_time[vm]);
dexpr float cpu_load_migration[pm in physical_machines] = (1 / pm.capacity.cpu) * sum(vm in virtual_machines) vm.requested.cpu * (new_allocation[vm][pm] + is_migrating_from[vm][pm] - is_allocating_on[vm][pm] * (1 - was_allocating[vm])); // When there is a migration, allow pre-allocation of VMs
dexpr float memory_load_migration[pm in physical_machines] = (1 / pm.capacity.memory) * sum(vm in virtual_machines) vm.requested.memory * (new_allocation[vm][pm] + is_migrating_from[vm][pm] - is_allocating_on[vm][pm] * (1 - was_allocating[vm])); 

dexpr int is_added[vm in virtual_machines] = (1 - sum(pm in physical_machines) old_allocation[vm][pm]) * sum(pm in physical_machines) new_allocation[vm][pm];
dexpr int is_removal[vm in virtual_machines] = sum(pm in physical_machines) old_allocation[vm][pm] * (1 - sum(pm in physical_machines) new_allocation[vm][pm]);

// Model
// Objective Function: net profit per 1000 seconds
maximize   (sum(pm in physical_machines) ( 
	         - PUE * energy.cost * (
	         		 static_power[pm] * has_to_be_on[pm]
	               + dynamic_power[pm] (
		                 w_load_cpu * (
		                     cpu_load_total[pm] 
		                   + migration.energy.cpu_overhead.source * max_migration_source[pm] 
		                   + migration.energy.cpu_overhead.target * max_migration_target[pm] 
		                   + migration.energy.concurrent * w_concurrent_migrations * max_migration_multiple[pm]
		                 ) 
		               + (1 - w_load_cpu) * memory_load_total[pm] 
		             ) * is_on[pm] 
               )
		     + sum (vm in virtual_machines) ( 
		   	         // allocation case
        		       is_allocating_on[vm][pm] * profit[vm] * vm.run.total_time                                                 // total profit
        		     / (pm.s.time_to_turn_on + (remaining_allocation_time[vm] + remaining_run_time[vm]) / pm.features.speed)     // effective remaining time
        		     // run case
        		     + is_running_on[vm][pm] * profit[vm] * vm.run.total_time      // total profit
        		     / (remaining_run_time[vm] / pm.features.speed)                // effective remaining time
		             // migration case
		             + is_migrating_on[vm][pm] * profit[vm] * vm.run.total_time	* migration_penalty                     // total profit
		             / (pm.s.time_to_turn_on + remaining_run_time[vm] / pm.features.speed + vm.migration.down_time)     // effective remaining time
		       )
		   )
		   // removal case
	     - sum(vm in virtual_machines) 
		       is_removal[vm] * profit[vm] * vm.run.current_time
		   ) * 1000;
		       
			   
subject to {
  // If Virtual Machine is allocated, the Physical Machine has to be ON (or turning ON)
  forall(pm in physical_machines) {
    forall (vm in virtual_machines) {
      new_allocation[vm][pm] <= is_on[pm]; 
    }
  }        
  // A Virtual Machine is assigned maximum to one Physical Machine
  forall (vm in virtual_machines) {
    sum (pm in physical_machines) new_allocation[vm][pm] <= 1;
  }
  // If Virtual Machines are allocated to a PM, the PM cannot be turned off 
  forall(pm in physical_machines) {
    M * has_to_be_on[pm] >= sum(vm in virtual_machines) new_allocation[vm][pm];
  }
  // Physical Machine CPU and Memory capacity
  forall(pm in physical_machines) {
    cpu_load[pm] <= 1; 
    memory_load[pm] <= 1; 
  }
  // Physical Machine CPU and Memory capacity during migration
  forall(pm in physical_machines) {
    cpu_load_migration[pm] <= 1;
    memory_load_migration[pm] <= 1;
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
  // If a VM is migrating from a PM, the PM has to be fully turned on
  forall (pm in physical_machines) {
    M * is_fully_turned_on[pm] >= sum(vm in virtual_machines) is_migrating_from[vm][pm];
  }
  // If a VM is migrating to a PM, the PM has to be fully on
  forall (pm in physical_machines) {
    M * is_on[pm] >= sum(vm in virtual_machines) is_migrating_on[vm][pm];
  }
  //  Max source migrations time
  forall (pm in physical_machines) {
    forall (vm in virtual_machines) {
    max_migration_source[pm] >= is_migrating_from[vm][pm] * remaining_migration_time[vm] / remaining_run_time[vm]; 
    }    
  }
  //  Max target migrations time
  forall (pm in physical_machines) {
    forall (vm in virtual_machines) {
    max_migration_target[pm] >= is_migrating_on[vm][pm] * remaining_migration_time[vm] / remaining_run_time[vm]; 
    }    
  }
  // Max multiple migrations time
  forall (pm in physical_machines) {
    forall (vm in virtual_machines) {
    max_migration_multiple[pm] + (1 - is_multiple_migrations[pm]) >= is_migrating_from[vm][pm] * remaining_migration_time[vm] / remaining_run_time[vm]; 
    max_migration_multiple[pm] + (1 - is_multiple_migrations[pm]) >= is_migrating_on[vm][pm] * remaining_migration_time[vm] / remaining_run_time[vm]; 
    }    
  }
  // If two or more migrations are happening from or on a PM, multiple migrations are happening at PM
  forall (pm in physical_machines) {
    2 * is_multiple_migrations[pm] <= sum(vm in virtual_machines) is_migrating_on[vm][pm] + sum(vm in virtual_machines) is_migrating_from[vm][pm];
    1 + 2 * M * is_multiple_migrations[pm] >= sum(vm in virtual_machines) is_migrating_on[vm][pm] + sum(vm in virtual_machines) is_migrating_from[vm][pm];
  }
  // Uniqueness of Virtual Machine state
  forall (vm in virtual_machines) {
    is_allocation[vm] + is_run[vm] + is_migration[vm] + is_removal[vm] <= 1; 
    is_allocation[vm] + is_run[vm] + is_migration[vm] + is_removal[vm] >= sum(pm in physical_machines) old_allocation[vm][pm]; 
  }
}