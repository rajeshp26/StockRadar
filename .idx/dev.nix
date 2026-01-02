{pkgs, ...}:
let
  # Only include standard Nix-provided Python tools
  python-with-packages = pkgs.python311.withPackages (ps: with ps; [
    pip
    pytest
    httpx
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
