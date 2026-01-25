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
    # Build Tools
    # ============================================
    # GCC compiler with C++ support
    gcc
    gnumake
    pkg-config
    git
    
    # ============================================
    # System Libraries for C Extensions
    # ============================================
    # Use the system's C++ library (not older libstdcxx5)
    # This is critical for Google Cloud Studio IDE compatibility
    stdenv.cc.cc.lib
    zlib
  ];
  
  # ============================================
  # Environment Setup - GOOGLE CLOUD STUDIO COMPATIBLE
  # ============================================
  shellHook = ''
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "✅ StockerPro Nix Shell Activated"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    
    # ============================================
    # CRITICAL: Library Path Configuration
    # ============================================
    # For Google Cloud Studio IDE:
    # - Use stdenv.cc.cc.lib (modern C++ stdlib)
    # - Let the container's glibc handle the rest
    # - Don't try to override system libraries
    # - This prevents GLIBCXX version conflicts
    #
    # Key insight: The venv's numpy was compiled against
    # the container's glibc, so we need to use the container's
    # C++ stdlib, not Nix's libstdcxx5 (which is outdated)
    # ============================================
    
    export LD_LIBRARY_PATH="${pkgs.stdenv.cc.cc.lib}/lib:${pkgs.zlib}/lib:$LD_LIBRARY_PATH"
    
    # Ensure Python can find compiled extensions
    export PYTHONPATH="$PYTHONPATH:."
    
    echo "🔧 Environment Setup:"
    echo "   • Python 3.11 ✅"
    echo "   • C++ stdlib (from container) ✅"
    echo "   • Build tools (gcc, make, pkg-config) ✅"
    echo "   • Google Cloud Studio IDE compatible ✅"
    echo ""
    echo "📂 Working in: $(pwd)"
    echo ""
    echo "🚀 To start the backend:"
    echo "   cd backend && source venv/bin/activate && python -m uvicorn main:app --reload"
    echo ""
    echo "📦 To install dependencies:"
    echo "   pip install -r requirements.txt"
    echo ""
    echo "✨ To test everything works:"
    echo "   python -c 'import numpy; import pandas; import fastapi; print(\"✅ All OK\")'"
    echo ""
    echo "❌ To exit this shell:"
    echo "   exit"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
  '';
}