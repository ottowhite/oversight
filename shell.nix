{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  packages = [
    pkgs.uv
    pkgs.nodejs
    pkgs.postgresql
  ];

  shellHook = ''
    git config core.hooksPath .githooks
    uv sync --quiet
    source .venv/bin/activate
  '';
}
