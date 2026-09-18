{
  description = "arga-cli: command-line interface for Arga authentication, MCP installation, and browser validation";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    let
      overlay = final: prev: {
        arga-cli = final.python3Packages.callPackage ./nix/arga-cli.nix { };
      };
    in
    {
      overlays.default = overlay;
    }
    // flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs {
          inherit system;
          overlays = [ overlay ];
        };
      in
      {
        packages = {
          default = pkgs.arga-cli;
          arga-cli = pkgs.arga-cli;
        };

        apps.default = {
          type = "app";
          program = "${pkgs.arga-cli}/bin/arga";
        };

        devShells.default = pkgs.mkShell {
          packages = [
            pkgs.uv
            pkgs.python3
            pkgs.ruff
          ];
        };

        checks.build = pkgs.arga-cli;
      });
}
