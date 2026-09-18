{ lib
, buildPythonApplication
, setuptools
, httpx
, questionary
, rich
, pytestCheckHook
}:

buildPythonApplication {
  pname = "arga-cli";
  version = "0.1.15";
  pyproject = true;

  src = lib.cleanSource ../.;

  build-system = [ setuptools ];

  dependencies = [
    httpx
    questionary
    rich
  ];

  nativeCheckInputs = [ pytestCheckHook ];

  pythonImportsCheck = [ "arga_cli" "arga_cli.main" ];

  meta = {
    description = "Command-line interface for Arga authentication, MCP installation, and browser validation";
    homepage = "https://github.com/ArgaLabs/arga-cli";
    mainProgram = "arga";
  };
}
