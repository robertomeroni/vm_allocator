string model_name = ...;

main {
  var model_name = thisOplModel.dataElements.model_name;
  if (model_name == "main") {
  	writeln("\nMAIN MODEL\n")
    var inputFolderPath = "simulation/model_input_main/";
    var modelFile = "vm_allocation.mod";
  }    
  else if (model_name == "mini") {
  	writeln("\nMINI MODEL\n")
    var inputFolderPath = "simulation/model_input_mini/";
    var modelFile = "vm_allocation_mini.mod";
  }    
  else if (model_name == "migration") {
  	writeln("\nMIGRATION MODEL\n")
    var inputFolderPath = "simulation/model_input_migration/";
    var modelFile = "vm_allocation_mini.mod";
  }    
  else if (model_name == "pm_manager") {
  	writeln("\nPM MANAGER\n")
    var inputFolderPath = "simulation/pm_manager/input/";
    var modelFile = "vm_allocation_mini.mod";
  }    

  // Define file names
  var folderPath = "model/";
  var physicalMachinesFile = "physical_machines.dat";
  var virtualMachinesFile = "virtual_machines.dat";
  var weightsFile = "weights.dat";
  
  // Create complete paths by concatenating folder paths and file names
  var modelPath = folderPath + modelFile;
  var physicalMachinesPath = inputFolderPath + physicalMachinesFile;
  var virtualMachinesPath = inputFolderPath + virtualMachinesFile;
  var weightsPath = inputFolderPath + weightsFile;
  
  var source = new IloOplModelSource(modelPath);
  var cplex = new IloCplex();
  var def = new IloOplModelDefinition(source);
  var model = new IloOplModel(def, cplex);
  
  var physical_machines = new IloOplDataSource(physicalMachinesPath);
  var virtual_machines = new IloOplDataSource(virtualMachinesPath);
  var weights = new IloOplDataSource(weightsPath);
  
  model.addDataSource(physical_machines);
  model.addDataSource(virtual_machines);
  model.addDataSource(weights);
  
  model.generate();
  
    // Set initial solution
  if (model_name == "main") {
  	writeln("\nSetting initial solution...\n")
  	
  	var is_allocation_vec = new IloOplCplexVectors();
  	var is_first_migration_vec = new IloOplCplexVectors();
  	var is_run_vec = new IloOplCplexVectors();
  	
    is_allocation_vec.attach(model.is_allocation,model.is_allocation_init);
    is_first_migration_vec.attach(model.is_first_migration,model.is_first_migration_init);
    is_run_vec.attach(model.is_run,model.was_running);
    
    is_allocation_vec.setStart(cplex);   
    is_first_migration_vec.setStart(cplex);   
    is_run_vec.setStart(cplex);   
  }    
  
  if (cplex.solve()) {
    
    writeln(model.printSolution());
    
    write("cpu_load = [");
    for (var pm in model.physical_machines) {
        write(" " + model.cpu_load[pm]);
    }
	write(" ]\n");
	
    write("memory_load = [");
    for (var pm in model.physical_machines) {
        write(" " + model.memory_load[pm]);
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
	
	write("")
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
