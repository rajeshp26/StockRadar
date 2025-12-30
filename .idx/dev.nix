{pkgs, ...}:
let
  # The only thing Nix needs to provide is the base Python interpreter and pip
  python-with-packages = pkgs.python311.withPackages (ps: with ps; [
    pip # Pip is used to manage libraries in the virtual environment
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
      # The onCreate hook is removed as it is no longer needed.
      # Dependencies are now managed in the .venv virtual environment.
      onCreate = {
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
