{
  description = "Python dev-shell for canvas bulk downloads";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = {
    self,
    nixpkgs,
    flake-utils,
    ...
  }:
    flake-utils.lib.eachDefaultSystem (
      system: let
        pkgs = nixpkgs.legacyPackages.${system};
        pythonPackages = pkgs.python3.pkgs;

        canvasApiPy = pythonPackages.buildPythonPackage rec {
          pname = "canvasapi";
          version = "3.3.0";
          pyproject = true;
          build-system = [pythonPackages.setuptools];

          src = pythonPackages.fetchPypi {
            inherit pname version;
            sha256 = "sha256-hvLpMKzIfJo2BXW5aWh/EHq04fPA7kVW3zDRdX6vXvA=";
          };

          propagatedBuildInputs = [
            pythonPackages.requests
            pythonPackages.pytz
            pythonPackages.arrow
          ];

          doCheck = false;
        };

        projectPython = pkgs.python3.withPackages (ps: [
          canvasApiPy
          ps.colorama
          ps.inquirerpy
        ]);

        canvasRun = pkgs.writeShellScriptBin "canvas-bulk-download" ''
          #!${pkgs.stdenv.shell}
          export PATH=${projectPython}/bin:$PATH

          ${projectPython}/bin/python ${./canvas_bulk_download.py} "$@"
        '';
      in {
        devShells.default = pkgs.mkShell {
          packages = [
            projectPython
            pkgs.git
          ];

          shellHook = ''
            echo "Done!"
          '';
        };

        apps.default = flake-utils.lib.mkApp {
          drv = canvasRun;
        };
      }
    );
}
