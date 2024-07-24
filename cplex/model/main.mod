main {
  // Define folder paths
  var folderPath = "/home/roberto/job/vm_allocator/cplex/model/";
  var inputFolderPath = "/home/roberto/job/vm_allocator/cplex/simulation/model_input/";

  // Define file names
  var modelFile = "vm_allocation.mod";
  var physicalMachinesFile = "physical_machines.dat";
  var virtualMachinesFile = "virtual_machines.dat";
  
  // Create complete paths by concatenating folder paths and file names
  var modelPath = folderPath + modelFile;
  var physicalMachinesPath = inputFolderPath + physicalMachinesFile;
  var virtualMachinesPath = inputFolderPath + virtualMachinesFile;
  
  var source = new IloOplModelSource(modelPath);
  var cplex = new IloCplex();
  var def = new IloOplModelDefinition(source);
  var model = new IloOplModel(def, cplex);
  
  var physical_machines = new IloOplDataSource(physicalMachinesPath);
  var virtual_machines = new IloOplDataSource(virtualMachinesPath);
  
  model.addDataSource(physical_machines);
  model.addDataSource(virtual_machines);
  
  model.generate();
  
  if (cplex.solve()) {
    writeln(model.printSolution());
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
  def.end();
  cplex.end();
  source.end();
}
