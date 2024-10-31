main {
  // Define folder paths
  var folderPath = "model/";
  var inputFolderPath = "model/data/scalability_test/";

  // Define file names
  var modelFile = "vm_allocation.mod";
  var physicalMachinesFile = "physical_machines.dat";
  var virtualMachinesFile = "virtual_machines.dat";
  var weightsFile = "weights.dat";
  var settingsFile= "settings.ops";
  
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
  model.applyOpsSettings(folderPath, settingsFile);
  
  model.generate();
 
  if (cplex.solve()) {
    writeln("Solution found");
    writeln(model.printSolution());
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
