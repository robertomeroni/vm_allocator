main {
  // Define folder paths
  var folderPath = "/home/roberto/job/vm_allocator/cplex/model/";
  var inputFolderPath = "/home/roberto/job/vm_allocator/cplex/simulation/model_input/";

  // Define file names
  var modelFile = "vm_allocation_mini.mod";
  var physicalMachinesFile = "physical_machines.dat";
  var virtualMachinesFile = "virtual_machines.dat";
  var weightsFile = "weights.dat";
  var latencyFile = "latency.dat";
  var powerConsumptionFile ="power_consumption.dat"
  
  // Create complete paths by concatenating folder paths and file names
  var modelPath = folderPath + modelFile;
  var physicalMachinesPath = inputFolderPath + physicalMachinesFile;
  var virtualMachinesPath = inputFolderPath + virtualMachinesFile;
  var weightsPath = inputFolderPath + weightsFile;
  var latencyPath = inputFolderPath + latencyFile;
  var powerConsumptionPath = inputFolderPath + powerConsumptionFile;
  
  var source = new IloOplModelSource(modelPath);
  var cplex = new IloCplex();
  var def = new IloOplModelDefinition(source);
  var model = new IloOplModel(def, cplex);
  
  var physical_machines = new IloOplDataSource(physicalMachinesPath);
  var virtual_machines = new IloOplDataSource(virtualMachinesPath);
  var weights = new IloOplDataSource(weightsPath);
  var latency = new IloOplDataSource(latencyPath);
  var power_consumption = new IloOplDataSource(powerConsumptionPath);
  
  model.addDataSource(physical_machines);
  model.addDataSource(virtual_machines);
  model.addDataSource(weights);
  model.addDataSource(latency);
  model.addDataSource(power_consumption);
  
  model.generate();
  
  if (cplex.solve()) {
    writeln("\nMINI MODEL\n")
    writeln(model.printSolution());
    
    write("cpu_load = [");
    for (var pm in model.physical_machines) {
      if (model.is_fully_turned_on[pm])
        write(" " + model.cpu_load[pm]);
      else 
      	write(" " + 0.0);
    }
	write(" ]\n");
	
    write("memory_load = [");
    for (var pm in model.physical_machines) {
      if (model.is_fully_turned_on[pm])
        write(" " + model.memory_load[pm]);
      else 
      	write(" " + 0.0);
    }
	write(" ]\n");
	
    write("Virtual Machines IDs: [");
    for (var vm in model.virtual_machines) {
      write(" " + vm.id);
    }
	write(" ]\n");
	
	write("Physical Machines IDs: [");
    for (var pm in model.physical_machines) {
      write(" " + pm.id);
    }
	write(" ]\n");
	
  } else {
    writeln("No solution");
  }
  
  // End the model and data sources
  model.end();
  physical_machines.end();
  virtual_machines.end();
  latency.end
  def.end();
  cplex.end();
  source.end();
}
