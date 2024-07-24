// Tuple definitions
tuple Execution {
  float current_time;
  float total_time;
  float pm;
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
  Execution execution;
  Execution migration;
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

tuple MigrationWeights {
  float time;
  float energy;
  Load load;
}

tuple VMWeights {
 float is_added;
 float is_removed;
 MigrationWeights migration; 
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
float remaining_time[vm in virtual_machines] = vm.execution.total_time - vm.execution.current_time;
float remaining_time_steps[vm in virtual_machines] = ceil(remaining_time[vm] / main_time_step);

pwlFunction load_power_consumption[pm in physical_machines] = 
  piecewise {0->0; pm.features.max_energy_consumption->1; 0} (0, 0);
int is_fully_turned_on[pm in physical_machines] = // if is going to be fully turned ON in the next time step (unless it gets turned OFF)
  (pm.s.time_to_turn_on <= main_time_step ? 1 : 0); 

int old_allocation[vm in virtual_machines][pm in physical_machines] = 
  (vm.execution.pm == pm.id ? 1 : 0);
int is_migrating[vm in virtual_machines] = // if it will be migrating in the next time step (does not consider a new migration decided in this time step)
  (vm.migration.total_time - vm.migration.current_time > main_time_step && vm.migration.pm > -1 ? 1 : 0); 
int is_migrating_from[vm in virtual_machines][pm in physical_machines] =
  (vm.migration.pm == pm.id ? 1 : 0);
int is_same_group[v1 in virtual_machines][v2 in virtual_machines] = 
  (v1.group == v2.group ? 1 : 0); 

// Decision Variables
dvar boolean is_on[physical_machines]; // if it is on in the new allocation (already on or will be turned on)
dvar boolean new_allocation[virtual_machines][physical_machines];
dvar boolean is_migration[virtual_machines];
dvar boolean is_colocated[virtual_machines][virtual_machines];
dvar int performance_boost[virtual_machines]; // number of colocated Virtual Machines (also counting the colocation with itself)
dvar float vm_time_step[virtual_machines];

// Optional variables to improve readability 
dvar boolean is_running[virtual_machines]; // if it is running in the new allocation (allocated on a fully turned ON machine and not migrating)
dvar boolean is_added[virtual_machines];
dvar boolean is_removed[virtual_machines];
dvar boolean turn_on[physical_machines];
dvar boolean turn_off[physical_machines];
dvar float+ memory_load[physical_machines];
dvar float+ cpu_load[physical_machines];

// Weights
Energy energy = 
  <0.1,             // cost         
   1000000.0		// limit
  >; 

PMWeights w_pm[pm in physical_machines] = 
  <1.0,               // is_on
   <0.1,0.1 * energy.cost>,        // turn_on: <time, energy>
   <0.1,0.1 * energy.cost>         // turn_off: <time, energy>
  >;

VMWeights w_vm[vm in virtual_machines] = 
  <0.2,																						 // is_added
   0.1,      																				 // is_removed
   <0.3,																					 // migration.time
    0.2,																					 // migration.energy
    <<(vm.migration.total_time - vm.migration.current_time) / vm.migration.total_time,       // migration.load.origin.cpu
      (vm.migration.total_time - vm.migration.current_time) / vm.migration.total_time>,		 // migration.load.origin.memory
    <(vm.migration.total_time - vm.migration.current_time) / vm.migration.total_time,		 // migration.load.destination.cpu
    (vm.migration.total_time - vm.migration.current_time) / vm.migration.total_time>>>, 	 // migration.load.destination.memory
   0.1																						 // colocation		
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
		     (w_vm[vm].is_added * is_added[vm]
		   + (w_vm[vm].migration.time + w_vm[vm].migration.energy) * is_migration[vm]
		   + w_vm[vm].is_removed * is_removed[vm]
		 
	       - (is_running[vm] * vm.expected_profit / remaining_time_steps[vm]));

subject to {
  // Physical Machine CPU capacity
 forall(pm in physical_machines) {
    sum(vm in virtual_machines) 
      (new_allocation[vm][pm] 
     + w_vm[vm].migration.load.origin.cpu * is_migrating_from[vm][pm] * is_migrating[vm]
     + (w_vm[vm].migration.load.destination.cpu - 1) * new_allocation[vm][pm] * (is_migrating[vm] + is_migration[vm])) // if a VM that has been allocated to this PM is migrating, account only for partial load 
     * vm.requested.cpu <= pm.capacity.cpu; 
  }
  // Physical Machine Memory capacity
forall(pm in physical_machines) {
    sum(vm in virtual_machines) 
      (new_allocation[vm][pm] 
     + w_vm[vm].migration.load.origin.memory * is_migrating_from[vm][pm] * is_migrating[vm]
     + (w_vm[vm].migration.load.destination.memory - 1) * new_allocation[vm][pm] * (is_migrating[vm] + is_migration[vm])) // if a VM that has been allocated to this PM is migrating, account only for partial load 
     * vm.requested.memory <= pm.capacity.memory; 
  }
  // If Virtual Machine is allocated, the Physical Machine has to be ON (or about to turn ON)
  forall(pm in physical_machines) {
    forall (vm in virtual_machines) {
     new_allocation[vm][pm] <= is_on[pm]; 
    }
  }        
  // A Virtual Machine is assigned maximum one time
  forall (vm in virtual_machines) {
    sum (pm in physical_machines) new_allocation[vm][pm] <= 1;
  } 
  // Memory load percentage of Physical Machine
  forall (pm in physical_machines) {
    memory_load[pm] == (1 / pm.capacity.memory) * sum(vm in virtual_machines) vm.requested.memory * new_allocation[vm][pm];
  }    
  // CPU load percentage of Physical Machine 
  forall (pm in physical_machines) {
    cpu_load[pm] == (1 / pm.capacity.cpu) * sum(vm in virtual_machines) vm.requested.cpu * new_allocation[vm][pm];
  }    
  // Physical Machine gets turned on
  forall (pm in physical_machines) {
    (1 - pm.s.state) * is_on[pm] == turn_on[pm];  
  }    
  // Physical Machine gets turned off
  forall (pm in physical_machines) {
    (pm.s.state) * (1 - is_on[pm]) == turn_off[pm];  
  }
  // Virtual Machines is running (is allocated on a fully turned ON Physical Machine and it is not migrating)
  forall (vm in virtual_machines) {
    is_running[vm] <= sum(pm in physical_machines) is_fully_turned_on[pm] * new_allocation[vm][pm];
    is_running[vm] <= 1 - is_migrating[vm];
    is_running[vm] <= 1 - is_migration[vm];
  }
  // Virtual Machine is added to allocation
  forall (vm in virtual_machines) {
    (1 - sum(pm in physical_machines) old_allocation[vm][pm]) * (sum(pm in physical_machines) new_allocation[vm][pm]) == is_added[vm]; 
  }
  // Virtual Machine is removed from allocation
  forall (vm in virtual_machines) {
    (sum(pm in physical_machines) old_allocation[vm][pm]) * (1 - sum(pm in physical_machines) new_allocation[vm][pm]) == is_removed[vm]; 
  }    
  // Migration
  forall (vm in virtual_machines) {
    forall (pm in physical_machines) {
      is_added[vm] + is_removed[vm] + old_allocation[vm][pm] + (1 - new_allocation[vm][pm]) + is_migration[vm] >= 1;
      is_added[vm] + is_removed[vm] + (1 - old_allocation[vm][pm]) + new_allocation[vm][pm] + is_migration[vm] >= 1;
    }  
  }
  // If a Virtual Machine is migrating, it cannot be considered for reallocation
  forall (vm in virtual_machines) {
    forall (pm in physical_machines) {
      is_migrating_from[vm][pm] <= 1 + old_allocation[vm][pm] - new_allocation[vm][pm]; 
      is_migrating_from[vm][pm] <= 1 - old_allocation[vm][pm] + new_allocation[vm][pm]; 
    }
  }
  // Two Virtual Machines are co-located
  forall (pm in physical_machines) {
    forall (v1 in virtual_machines) {
      forall (v2 in virtual_machines) {
	    new_allocation[v1][pm] + new_allocation[v2][pm] <= 1 + is_colocated[v1][v2]; 
	    is_colocated[v1][v2] <= new_allocation[v1][pm];
	    is_colocated[v1][v2] <= new_allocation[v2][pm];
      }	    
    }	    
  }
  // Co-located Virtual Machines belonging to the same group gain a performance boost
  forall (v1 in virtual_machines) { 
   	performance_boost[v1] <= sum(v2 in virtual_machines) is_same_group[v1][v2] * is_colocated[v1][v2]; 
  }
  // Execution time of a Virtual Machine depends on where it runs on
  forall (vm in virtual_machines) {
    vm_time_step[vm] == is_running[vm] * main_time_step / sum(pm in physical_machines) new_allocation[vm][pm] * pm.features.speed;
  }
}