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
float time_window = ...;

ArchitectureFloat price = ...;
Energy energy = ...;
float PUE = ...;
MigrationWeights migration = ...;
float w_load_cpu = ...;

float remaining_allocation_time[vm in virtual_machines] = vm.allocation.total_time - vm.allocation.current_time;
float remaining_run_time[vm in virtual_machines] = vm.run.total_time - vm.run.current_time;
int is_fully_turned_on[pm in physical_machines] = // if is going to be fully turned ON in the next time step (unless it gets turned OFF)
    (pm.s.time_to_turn_on <= main_time_step ? 1 : 0); 
    
// Energy consumption of each Physical Machine, depending by the load
float slopeBeforePoint[pm in physical_machines][p in 1..nb_points]=
  (p == 1) ? 0 : (power_function[pm][p].y - power_function[pm][p-1].y)/(power_function[pm][p].x-power_function[pm][p-1].x);
float static_energy[pm in physical_machines] = power_function[pm][1].y; 
pwlFunction dynamic_energy[pm in physical_machines] = 
  piecewise (p in 1..nb_points){slopeBeforePoint[pm][p] -> power_function[pm][p].x; 0} (0, 0);

dvar boolean allocation[virtual_machines][physical_machines];
dexpr float cpu_load[pm in physical_machines] = pm.s.load.cpu + (1 / pm.capacity.cpu) * sum(vm in virtual_machines) vm.requested.cpu * allocation[vm][pm];
dexpr float memory_load[pm in physical_machines] = pm.s.load.memory + (1 / pm.capacity.memory) * sum(vm in virtual_machines) vm.requested.memory * allocation[vm][pm]; 
dexpr float additional_energy[pm in physical_machines] = 
    dynamic_energy[pm](w_load_cpu * cpu_load[pm] + (1 - w_load_cpu) * memory_load[pm]) * is_fully_turned_on[pm]
  - dynamic_energy[pm](w_load_cpu * pm.s.load.cpu + (1 - w_load_cpu) * pm.s.load.memory);
  
float profit[vm in virtual_machines] = (vm.requested.cpu * price.cpu + vm.requested.memory * price.memory);                   

maximize   sum(pm in physical_machines) ( 
	         - PUE * energy.cost * additional_energy[pm]
		     + sum (vm in virtual_machines) ( 
        		   allocation[vm][pm] * profit[vm] * vm.run.total_time / ((remaining_allocation_time[vm] + remaining_run_time[vm]) / pm.features.speed) // allocation case
		  	   )
		   );
	   
subject to {
  // If Virtual Machine is allocated, the Physical Machine has to be fully ON
  forall(pm in physical_machines) {
    forall (vm in virtual_machines) {
      allocation[vm][pm] <= is_fully_turned_on[pm]; 
    }
  }        
  // A Virtual Machine is assigned maximum to one Physical Machine
  forall (vm in virtual_machines) {
    sum (pm in physical_machines) allocation[vm][pm] <= 1;
  } 
  // Physical Machine CPU capacity
  forall(pm in physical_machines) {
    cpu_load[pm] <= 1; 
  }
  // Physical Machine Memory capacity
  forall(pm in physical_machines) {
    memory_load[pm] <= 1; 
  }
}    