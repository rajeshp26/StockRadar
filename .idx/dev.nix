{ pkgs, ... }: {
  # Which nixpkgs channel to use.
  channel = "stable-24.05"; 

  # Use https://search.nixos.org/packages to find packages
  packages = [
    pkgs.nodejs_20
    pkgs.python313
    pkgs.python313Packages.pip
    pkgs.nodePackages.firebase-tools
    pkgs.jdk17
    pkgs.flutter
  ];

  # Sets environment variables in the workspace
  env = {
    # Set the JDK path for Flutter
    JAVA_HOME = "${pkgs.jdk17.home}";
  };

  idx = {
    # Search for the extensions you want on https://open-vsx.org/ and use "publisher.id"
    extensions = [
      "Dart-Code.flutter"
      "Dart-Code.dart-code"
      "ms-python.python"
    ];

    # Workspace lifecycle hooks
    workspace = {
      # Runs every time the workstation starts
      onStart = {
        # Automatically start the backend in its safe Nix environment
        # This ensures the API is ready as soon as the workstation is opened
        start-backend = "nix-shell shell.nix --run 'cd backend && ./start.sh'";
      };
    };

    # Enable previews
    previews = {
      enable = true;
      previews = {
        web = {
          # Use Next.js (React) for the web preview instead of memory-heavy Flutter Web
          # This resolves the OOM (Out of Memory) issues in the workstation
          command = ["npm" "run" "dev" "--" "-p" "$PORT" "--hostname" "0.0.0.0"];
          manager = "web";
          cwd = "web";
        };
      };
    };
  };
}
