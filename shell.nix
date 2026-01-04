{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  name = "stockerpro-backend";
  
  buildInputs = with pkgs; [
    # ============================================
    # Python Runtime & Package Management
    # ============================================
    python311
    python311Packages.pip
    python311Packages.virtualenv
    python311Packages.setuptools
    python311Packages.wheel
    
    # ============================================
    # System Libraries (Safe Subset)
    # ============================================
    # Standard C++ library (for NumPy, Pandas, etc.)
    # This is needed for C-extensions to work
    stdenv.cc.cc.lib
    
    # Compression library (for many Python packages)
    # This is needed for packages that use zlib
    zlib
    
    # ============================================
    # Build Tools (For compiling from source)
    # ============================================
    gcc
    gnumake
    pkg-config
  ];

  # ============================================
  # Environment Setup
  # ============================================
  shellHook = ''
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "✅ StockerPro Safe Nix Shell Activated"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    
    # ============================================
    # CRITICAL: Safe LD_LIBRARY_PATH Configuration
    # ============================================
    # We ONLY export:
    #   1. libstdc++ (C++ standard library) - needed for NumPy, Pandas
    #   2. zlib (compression) - needed for various packages
    #
    # We DO NOT export glibc because:
    #   - System binaries (bash, ps, ls, etc.) are linked to Nix's glibc
    #   - Exporting a different glibc forces them to use an incompatible version
    #   - This causes SIGSEGV (Segmentation Fault) in all system commands
    #   - Python's own libc is already correctly configured by Nix
    # ============================================
    
    export LD_LIBRARY_PATH="${pkgs.stdenv.cc.cc.lib}/lib:${pkgs.zlib}/lib:$LD_LIBRARY_PATH"
    
    echo "🔧 Libraries Provided:"
    echo "   • Python 3.11"
    echo "   • libstdc++ (C++ std lib for NumPy/Pandas)"
    echo "   • zlib (compression)"
    echo "   • Build tools (gcc, make, pkg-config)"
    echo ""
    echo "📂 Working in: $(pwd)"
    echo ""
    echo "🚀 To start the backend:"
    echo "   cd backend && ./start.sh"
    echo ""
    echo "📦 To install dependencies:"
    echo "   pip install -r backend/requirements.txt"
    echo ""
    echo "❌ To exit this shell:"
    echo "   exit"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
  '';
}
