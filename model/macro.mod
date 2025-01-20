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
  float energy;
}

tuple ArchitectureInt {
  int cpu;
  int memory;
}

tuple ArchitectureFloat {
  float cpu;
  float memory;
}

tuple Price {
  float cpu;
  float memory;
  float energy;
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
  State s;
  int type;
};

tuple VirtualMachine {
  key int id;
  ArchitectureInt requested;
  Execution allocation;
  Execution run;
  Migration migration;
};

tuple Point {
  key float x;
  float y;
}

// Data
{PhysicalMachine} physical_machines = ...;
{VirtualMachine} virtual_machines = ...;
int nb_points = ...;
Point energy_intensity_function[pm in physical_machines][1..nb_points]= ...;

float remaining_run_time[vm in virtual_machines] = vm.run.total_time - vm.run.current_time;
float remaining_migration_time[vm in virtual_machines] = vm.migration.total_time - vm.migration.current_time;

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
  (p == 1) ? 0 : (energy_intensity_function[pm][p].y - energy_intensity_function[pm][p-1].y)/(energy_intensity_function[pm][p].x-energy_intensity_function[pm][p-1].x);
float static_energy_intensity[pm in physical_machines] = energy_intensity_function[pm][1].y; 
pwlFunction dynamic_energy_intensity[pm in physical_machines] = 
  piecewise (p in 1..nb_points){slopeBeforePoint[pm][p] -> energy_intensity_function[pm][p].x; slopeBeforePoint[pm][nb_points]} (0, 0); 

// Weights
Price price = ...;
float PUE = ...;
float w_load_cpu = ...;

float revenue[vm in virtual_machines] = (vm.requested.cpu * price.cpu + vm.requested.memory * price.memory); // Revenue per second from running a Virtual Machine

float epgap = ...;

// Set parameters
execute
{
  cplex.epgap=epgap;
  cplex.workmem=16384;
} 

// Decision Variables
dvar boolean new_allocation[virtual_machines][physical_machines];
dvar boolean is_allocation[virtual_machines];
dvar boolean is_allocating_on[virtual_machines][physical_machines];
dvar boolean is_run[virtual_machines]; // if it is running in the new allocation (allocated on a fully turned ON machine and not migrating)
dvar boolean is_migration[virtual_machines];
dvar boolean is_first_migration[virtual_machines];
dvar boolean is_migrating_from[virtual_machines][physical_machines];
dvar boolean has_to_be_on[physical_machines];

// Expressions
dexpr float cpu_load[pm in physical_machines] = (1 / pm.capacity.cpu) * sum(vm in virtual_machines) vm.requested.cpu * new_allocation[vm][pm];
dexpr float memory_load[pm in physical_machines] = (1 / pm.capacity.memory) * sum(vm in virtual_machines) vm.requested.memory * new_allocation[vm][pm]; 
dexpr float cpu_load_migration[pm in physical_machines] = (1 / pm.capacity.cpu) * sum(vm in virtual_machines) vm.requested.cpu * (new_allocation[vm][pm] + is_migrating_from[vm][pm] - is_allocating_on[vm][pm] * (1 - was_allocating[vm])); // When there is a migration, allow pre-allocation of VMs
dexpr float memory_load_migration[pm in physical_machines] = (1 / pm.capacity.memory) * sum(vm in virtual_machines) vm.requested.memory * (new_allocation[vm][pm] + is_migrating_from[vm][pm] - is_allocating_on[vm][pm] * (1 - was_allocating[vm])); 

dexpr int is_added[vm in virtual_machines] = (1 - sum(pm in physical_machines) old_allocation[vm][pm]) * sum(pm in physical_machines) new_allocation[vm][pm];

// Initial Solutions
float is_allocation_init[vm in virtual_machines] = (vm.run.pm == -1 && vm.migration.from_pm == -1);
float is_first_migration_init[vm in virtual_machines] = 0;

// Model
// Objective Function: 
maximize    sum(pm in physical_machines) ( 
	          - PUE * price.energy * (
	         	    static_energy_intensity[pm] * has_to_be_on[pm]
	              + dynamic_energy_intensity[pm] (
		                w_load_cpu * cpu_load[pm] 
		             + (1 - w_load_cpu) * memory_load[pm] 
		            ) 
		        )
		      + sum (vm in virtual_machines) new_allocation[vm][pm] * revenue[vm]
		    )
		    // migration penalties
		   - sum (vm in virtual_machines) is_migration[vm] * (
			     vm.migration.energy * PUE * price.energy     // energy costs
			   + revenue[vm] * vm.migration.down_time        // time costs
			 ) / remaining_run_time[vm]
		  ;
		  
subject to {     
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
    is_allocation[vm] + is_run[vm] + is_migration[vm] <= sum(pm in physical_machines) new_allocation[vm][pm];
  } 
  // If a Virtual Machine is added or if it was allocating, VM state is an allocation
  forall (vm in virtual_machines) {
	is_allocation[vm] >= is_added[vm];
	is_allocation[vm] >= was_allocating[vm];
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
  // Migration (if the allocation is different but the VM is not being added it is a migration)
  forall (vm in virtual_machines) {
    forall (pm in physical_machines) {
      is_added[vm] + old_allocation[vm][pm] + (1 - new_allocation[vm][pm]) + is_migration[vm] >= 1;
      is_added[vm] + (1 - old_allocation[vm][pm]) + new_allocation[vm][pm] + is_migration[vm] >= 1;
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
       was_migrating[vm] * old_allocation[vm][pm] <= new_allocation[vm][pm]; 
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
  // Iff a VM was migrating (and still), or if a VM is at first migration and was allocated on PM, VM is migrating from PM
  forall (vm in virtual_machines) {
    forall (pm in physical_machines) {
      was_migrating_from[vm][pm] * is_migration[vm] + is_first_migration[vm] * old_allocation[vm][pm] >= is_migrating_from[vm][pm];
      was_migrating_from[vm][pm] * is_migration[vm] <= is_migrating_from[vm][pm];
      is_first_migration[vm] * old_allocation[vm][pm] <= is_migrating_from[vm][pm];
    }
  }  
  // Uniqueness of Virtual Machine state
  forall (vm in virtual_machines) {
    is_allocation[vm] + is_run[vm] + is_migration[vm] <= 1; 
    is_allocation[vm] + is_run[vm] + is_migration[vm] >= sum(pm in physical_machines) old_allocation[vm][pm]; 
  }
}