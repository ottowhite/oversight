{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  packages = [
    pkgs.uv
    pkgs.nodejs
    pkgs.postgresql
    # Uncomment if you're on NixOS WITHOUT nix-ld — uv otherwise downloads
    # a python-build-standalone interpreter whose hard-coded
    # /lib64/ld-linux-x86-64.so.2 NixOS can't resolve by default. With
    # `programs.nix-ld.enable = true;` in configuration.nix this isn't
    # needed; uv-downloaded Python runs fine via the nix-ld stub.
    # pkgs.python313
  ];

  # See the python313 comment above. Uncomment these two together with
  # pkgs.python313 if you don't have nix-ld available system-wide.
  # UV_PYTHON_DOWNLOADS = "never";
  # UV_PYTHON = "${pkgs.python313}/bin/python3.13";

  # manylinux wheels (numpy, psycopg, ...) call dlopen() on shared libs
  # at *runtime* (e.g. psycopg's pq_ctypes loads libpq.so.5). nix-ld
  # only helps with executable launch, not in-process dlopen, so we still
  # need these on LD_LIBRARY_PATH for the shell session. With nix-ld
  # enabled the C/zlib entries below are arguably redundant, but cheap
  # to keep as belt-and-braces for any wheel that bypasses the
  # nix-ld-managed paths.
  LD_LIBRARY_PATH = pkgs.lib.makeLibraryPath [
    pkgs.stdenv.cc.cc.lib   # libstdc++.so.6, libgcc
    pkgs.zlib               # libz.so.1
    pkgs.postgresql.lib     # libpq.so.5 (psycopg)
  ];

  shellHook = ''
    git config core.hooksPath .githooks
    uv sync --quiet
    source .venv/bin/activate
  '';
}
