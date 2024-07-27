// Tuple definitions
tuple Execution {
  float current_time;
  float total_time;
  float pm;
}

tuple Migration {
  float current_time;
  float total_time;
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
  float max_energy_consumption;
}

tuple State {
  float time_to_turn_on;
  float time_to_turn_off;
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
  int group; // co-allocation of tasks belonging to the same group is preferred
  float expected_profit; // probability to be completed * total_profit
};

tuple TimeAndEnergy {
  float time;
  float energy;
}

tuple PMWeights {
  float is_on;
  TimeAndEnergy turn_on;
  TimeAndEnergy turn_off;
}

tuple Load {
  ArchitectureFloat origin;
  ArchitectureFloat destination;
}

tuple AllocationWeights {
  float time;
  float energy;
  ArchitectureFloat load;
}

tuple MigrationWeights {
  float time;
  float energy;
  Load load;
}

tuple VMWeights {
 AllocationWeights allocation; 
 MigrationWeights migration; 
 float is_removal;
 float colocation;
}

tuple Energy {
  float cost;
  float limit;
}

// Data
{PhysicalMachine} physical_machines = ...;
{VirtualMachine} virtual_machines=...;

float main_time_step = 1.0; // seconds
float remaining_allocation_time[vm in virtual_machines] = vm.allocation.total_time - vm.allocation.current_time;
float remaining_run_time[vm in virtual_machines] = vm.run.total_time - vm.run.current_time;
float remaining_allocation_time_steps[vm in virtual_machines] = ceil(remaining_allocation_time[vm] / main_time_step);
float remaining_run_time_steps[vm in virtual_machines] = ceil(remaining_run_time[vm] / main_time_step);

pwlFunction load_power_consumption[pm in physical_machines] = 
  piecewise {0->0; pm.features.max_energy_consumption->1; 0} (0, 0);
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
int is_same_group[v1 in virtual_machines][v2 in virtual_machines] = 
  (v1.group == v2.group ? 1 : 0); 

// Decision Variables
dvar boolean is_on[physical_machines]; // if it is on in the new allocation (already on or will be turned on)
dvar boolean new_allocation[virtual_machines][physical_machines];
dvar boolean is_allocating_on[virtual_machines][physical_machines];
dvar boolean is_running_on[virtual_machines][physical_machines];
dvar boolean is_migrating_on[virtual_machines][physical_machines];
dvar boolean is_migration[virtual_machines];
dvar boolean is_colocated[virtual_machines][virtual_machines];
dvar int performance_boost[virtual_machines]; // number of colocated Virtual Machines (also counting the colocation with itself)
dvar float vm_time_step[virtual_machines];

// Optional variables to improve readability 
dvar boolean is_run[virtual_machines]; // if it is running in the new allocation (allocated on a fully turned ON machine and not migrating)
dvar boolean is_first_allocation[virtual_machines];
dvar boolean is_first_migration[virtual_machines];
dvar boolean is_allocation[virtual_machines];
dvar boolean is_removal[virtual_machines];
dvar boolean turn_on[physical_machines];
dvar boolean turn_off[physical_machines];
dvar float memory_load[physical_machines];
dvar float cpu_load[physical_machines];

// Weights
Energy energy = 
  <0.1,             // cost, $/kWh         
   1000000.0		// limit
  >; 

PMWeights w_pm[pm in physical_machines] = 
  <1.0,                            // is_on
   <0.1,0.1 * energy.cost>,        // turn_on: <time, energy>
   <0.1,0.1 * energy.cost>         // turn_off: <time, energy>
  >;

VMWeights w_vm[vm in virtual_machines] = 
  <
   <0.1,																					 							 // allocation.time
    0.1,																					 							 // allocation.energy
    <maxl((vm.allocation.current_time + main_time_step) / vm.allocation.total_time, 1),		                             // allocation.load.cpu
     maxl((vm.allocation.current_time + main_time_step) / vm.allocation.total_time, 1)>>, 	 						     // allocation.load.memory
   <0.3,																					                             // migration.time
    0.2,																					                             // migration.energy
     <<minl((vm.migration.total_time - (vm.migration.current_time + main_time_step)) / vm.migration.total_time, 0),      // migration.load.origin.cpu
       minl((vm.migration.total_time - (vm.migration.current_time + main_time_step)) / vm.migration.total_time, 0)>,     // migration.load.origin.memory
      <maxl((vm.migration.current_time + main_time_step) / vm.migration.total_time, 1),		                             // migration.load.destination.cpu
       maxl((vm.migration.current_time + main_time_step) / vm.migration.total_time, 1)>>>, 	 						     // migration.load.destination.memory
   10,																						 							 // is_removal
   0.1																						 							 // colocation		
  >;

// Load weights
float w_load_cpu = 0.8;

// Model
minimize   sum(pm in physical_machines)
			 (w_pm[pm].is_on * is_on[pm] 
		   + (w_pm[pm].turn_on.time + w_pm[pm].turn_on.energy) * turn_on[pm]		    
		   + (w_pm[pm].turn_off.time + w_pm[pm].turn_off.energy) * turn_off[pm]		    
		   + energy.cost * main_time_step * load_power_consumption[pm]((1 - w_load_cpu) * memory_load[pm] + w_load_cpu * cpu_load[pm]))
		    
		   + sum(vm in virtual_machines)
		     ((w_vm[vm].allocation.time + w_vm[vm].allocation.energy) * is_allocation[vm] 
		   + (w_vm[vm].migration.time + w_vm[vm].migration.energy) * is_migration[vm]
		   + w_vm[vm].is_removal * is_removal[vm]
		 
	       - is_allocation[vm] * vm.expected_profit / (remaining_allocation_time_steps[vm] + remaining_run_time_steps[vm])
	       - is_run[vm] * vm.expected_profit / remaining_run_time_steps[vm]);
			
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
  // Physical Machine CPU capacity
  forall(pm in physical_machines) {
    cpu_load[pm] <= 1; 
  }
  // Physical Machine Memory capacity
  forall(pm in physical_machines) {
    memory_load[pm] <= 1; 
  }
  // CPU load percentage of Physical Machine 
  forall (pm in physical_machines) {
    cpu_load[pm] == (1 / pm.capacity.cpu) * sum(vm in virtual_machines) (vm.requested.cpu 
      * (new_allocation[vm][pm] 
      + (w_vm[vm].allocation.load.cpu - 1) * is_allocating_on[vm][pm]
      + w_vm[vm].migration.load.origin.cpu * was_migrating_from[vm][pm] 
      + (w_vm[vm].migration.load.destination.cpu - 1) * is_migrating_on[vm][pm])); // if a VM that has been allocated to this PM is migrating, account only for partial load 
   }  
  // Memory load percentage of Physical Machine
  forall (pm in physical_machines) {
    memory_load[pm] == (1 / pm.capacity.memory) * sum(vm in virtual_machines) vm.requested.memory
      * (new_allocation[vm][pm] 
      + (w_vm[vm].allocation.load.memory - 1) * is_allocating_on[vm][pm]
      + w_vm[vm].migration.load.origin.memory * was_migrating_from[vm][pm] 
      + (w_vm[vm].migration.load.destination.memory - 1) * is_migrating_on[vm][pm]); // if a VM that has been allocated to this PM is migrating, account only for partial load 
   }     
  // Physical Machine gets turned on
  forall (pm in physical_machines) {
    (1 - pm.s.state) * is_on[pm] == turn_on[pm];  
  }    
  // Physical Machine gets turned off
  forall (pm in physical_machines) {
    (pm.s.state) * (1 - is_on[pm]) == turn_off[pm];  
  }
  // Virtual Machine is running (is allocated on a fully turned ON Physical Machine and it is not allocating or migrating)
  forall (vm in virtual_machines) {
    is_first_allocation[vm] <= sum(pm in physical_machines) new_allocation[vm][pm];
    is_allocation[vm] <= sum(pm in physical_machines) new_allocation[vm][pm];
    is_run[vm] <= sum(pm in physical_machines) is_fully_turned_on[pm] * new_allocation[vm][pm];
    is_first_migration[vm] <= sum(pm in physical_machines) new_allocation[vm][pm];
    is_migration[vm] <= sum(pm in physical_machines) new_allocation[vm][pm];
  }
  // Virtual Machine is added to allocation
  forall (vm in virtual_machines) {
    (1 - sum(pm in physical_machines) old_allocation[vm][pm]) * (sum(pm in physical_machines) new_allocation[vm][pm]) == is_first_allocation[vm]; 
  }
  // Virtual Machine is removed from allocation
  forall (vm in virtual_machines) {
    (sum(pm in physical_machines) old_allocation[vm][pm]) * (1 - sum(pm in physical_machines) new_allocation[vm][pm]) == is_removal[vm]; 
  }    
  // If a Virtual Machine is at first allocation or it is still allocating, VM state should be an allocation
  forall (vm in virtual_machines) {
	is_allocation[vm] >= is_first_allocation[vm];
  }
  // A Virtual Machine can allocate only if was not allocated or it was already allocating
  forall (vm in virtual_machines) {
    is_allocation[vm] <= is_first_allocation[vm] + was_allocating[vm]; 
  } 
  // A Virtual Machine can run only if allocation or migration are completed
  forall (vm in virtual_machines) {
    is_run[vm] <= was_running[vm]; 
  } 
  // Migration (if the allocation is different but the VM is not being added or removed it is a migration)
  forall (vm in virtual_machines) {
    forall (pm in physical_machines) {
      is_first_allocation[vm] + is_removal[vm] + old_allocation[vm][pm] + (1 - new_allocation[vm][pm]) + is_migration[vm] >= 1;
      is_first_allocation[vm] + is_removal[vm] + (1 - old_allocation[vm][pm]) + new_allocation[vm][pm] + is_migration[vm] >= 1;
    }  
  }
  // If a Virtual Machine is migrating, the new allocation should be different from where it is migrating
  forall (vm in virtual_machines) {
    forall (pm in physical_machines) {
       was_migrating_from[vm][pm] <= (1 - new_allocation[vm][pm]); 
    }
  }    
  // If a Virtual Machine was migrating, it cannot be considered for reallocation
  forall (vm in virtual_machines) {
    forall (pm in physical_machines) {
       was_migrating[vm] * old_allocation[vm][pm] <= new_allocation[vm][pm] + is_removal[vm]; 
    }
  }    
  // Iff VM is assigned to PM in new_allocation and if it is already allocating or is an allocation, VM is being allocated on PM
  forall (vm in virtual_machines) {
    forall (pm in physical_machines) {
  	   is_allocation[vm] + new_allocation[vm][pm] <= 1 + is_allocating_on[vm][pm];
  	   is_allocating_on[vm][pm] <= is_allocation[vm];
  	   is_allocating_on[vm][pm] <= new_allocation[vm][pm];
    }
  }      	   
  // Iff VM is assigned to PM in new_allocation and is a migration, VM is being migrated on PM
  forall (vm in virtual_machines) {
    forall (pm in physical_machines) {
  	   is_migration[vm] + new_allocation[vm][pm] <= 1 + is_migrating_on[vm][pm];
  	   is_migrating_on[vm][pm] <= is_migration[vm];
  	   is_migrating_on[vm][pm] <= new_allocation[vm][pm];
    }
  }    
  // Uniqueness of Virtual Machine state
  forall (vm in virtual_machines) {
    is_allocation[vm] + is_run[vm] + is_migration[vm] + is_removal[vm] <= 1; 
    is_allocation[vm] + is_run[vm] + is_migration[vm] + is_removal[vm] >= sum(pm in physical_machines) old_allocation[vm][pm]; 
  }
//  // Two Virtual Machines are co-located
//  forall (v1 in virtual_machines) {
//    forall (pm in physical_machines) {
//	    new_allocation[v1][pm] + sum(v2 in virtual_machines) new_allocation[v2][pm] == is_colocated[v1]; 
//	    is_colocated[v1][v2] <= new_allocation[v1][pm];
//	    is_colocated[v1][v2] <= new_allocation[v2][pm];
//		new_allocation[v1][pm] - new_allocation[v2][pm] == 0;
//    }	    
//  }
//  // Co-located Virtual Machines belonging to the same group gain a performance boost
//  forall (v1 in virtual_machines) { 
//   	performance_boost[v1] <= sum(v2 in virtual_machines) (is_same_group[v1][v2] * sum(pm in physical_machines) is_colocated[v1][v2]); 
//  }
//  // Execution time of a Virtual Machine depends on where it runs on
//  forall (vm in virtual_machines) {
//    vm_time_step[vm] == is_run[vm] * main_time_step / sum(pm in physical_machines) new_allocation[vm][pm] * pm.features.speed;
//  }
}