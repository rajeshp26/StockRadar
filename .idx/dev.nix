{pkgs, ...}:

let
  # Only include packages that are definitely in Nixpkgs
  # We use Nix for the environment, and Pip for the specific libraries
  python-with-packages = pkgs.python311.withPackages (ps: with ps; [
    pip
    uvicorn
    fastapi
    pydantic
    psycopg2 # Use the standard nix name here
    pytest
  ]);
in
{
  channel = "stable-24.11"; 

  packages = [
    pkgs.nodejs_20
    pkgs.zulu
    pkgs.postgresql
    python-with-packages
  ];

  env = {
    LD_LIBRARY_PATH = "${pkgs.postgresql.lib}/lib";
  };

  services.firebase.emulators = {
    detect = false;
    projectId = "demo-app";
    services = [ "auth" "firestore" ];
  };

  idx = {
    extensions = [];
    workspace = {
      # This runs once when the project is first created
      onCreate = {
        # Install the libraries that Nix couldn't find
        install-python-libs = ''
          pip install supabase yfinance
        '';
        default.openFiles = [ "src/app/page.tsx" ];
      };
    };

    previews = {
      enable = true;
      previews = {
        web = {
          command = ["npm" "run" "dev" "--" "--port" "$PORT" "--hostname" "0.0.0.0"];
          manager = "web";
        };
      };
    };
  };
}
