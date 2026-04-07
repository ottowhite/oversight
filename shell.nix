{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  packages = [
    pkgs.uv
  ];

  shellHook = ''
    git config core.hooksPath .githooks
  '';
}
