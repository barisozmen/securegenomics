#!/bin/bash

# SecureGenomics CLI Setup Script
# ================================
# This script installs SecureGenomics CLI and makes the 'securegenomics' command available.
#
# Usage:
#   git clone https://github.com/securegenomics/securegenomics.git
#   cd securegenomics
#   bash setup.sh
#
# Requirements: Python 3.9+, pip

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
}

log_step() {
    echo -e "\n${BLUE}🔧 $1${NC}"
}

# Check if we're in the right directory
check_directory() {
    if [[ ! -f "pyproject.toml" ]] || [[ ! -d "src/securegenomics" ]]; then
        log_error "This script must be run from the SecureGenomics repository root directory."
        log_info "Please run: cd securegenomics && bash setup.sh"
        exit 1
    fi
}

# Check Python version
check_python() {
    log_step "Checking Python installation..."
    
    if ! command -v python3 &> /dev/null; then
        log_error "Python 3 is not installed. Please install Python 3.9 or higher."
        exit 1
    fi
    
    python_version=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    log_info "Found Python $python_version"
    
    # Check if Python version is 3.9+
    if python3 -c "import sys; exit(0 if sys.version_info >= (3, 9) else 1)"; then
        log_success "Python version is compatible"
    else
        log_error "Python 3.9 or higher is required. Found: $python_version"
        exit 1
    fi
}

# Check pip
check_pip() {
    log_step "Checking pip installation..."
    
    if ! command -v pip3 &> /dev/null; then
        log_error "pip3 is not installed. Please install pip3. \n$ sudo apt install python3-pip (ubuntu)\n$ brew install python (mac)
()"
        exit 1
    fi
    
    pip_version=$(pip3 --version | cut -d' ' -f2)
    log_info "Found pip $pip_version"
    log_success "pip is available"
}

# Install dependencies and package
install_package() {
    log_step "Installing SecureGenomics CLI..."
    
    # Upgrade pip to latest version
    log_info "Upgrading pip..."
    pip3 install --upgrade pip
    
    # Install requirements
    log_info "Installing project dependencies..."
    if [[ -f "requirements.txt" ]]; then
        pip3 install -r requirements.txt
        log_success "Dependencies installed successfully"
    else
        log_warning "requirements.txt not found, skipping dependency installation"
    fi
    
    # Install the package in development mode
    log_info "Installing package in development mode..."
    pip3 install -e .
    
    log_success "Package installed successfully"
}

# Test the installation
test_installation() {
    log_step "Testing installation..."
    
    # Test Python import
    if python3 -c "import securegenomics; print(f'Package version: {securegenomics.__version__}')" &> /dev/null; then
        version=$(python3 -c "import securegenomics; print(securegenomics.__version__)")
        log_success "Package import successful (version $version)"
    else
        log_error "Package import failed"
        return 1
    fi
    
    # Test CLI command
    if command -v securegenomics &> /dev/null; then
        cli_version=$(securegenomics --version 2>/dev/null | head -n1 || echo "unknown")
        log_success "CLI command is available: $cli_version"
    else
        log_warning "CLI command 'securegenomics' not found in PATH"
        log_info "You can use 'python3 -m securegenomics' instead"
        
        # Test python -m execution
        if python3 -m securegenomics --version &> /dev/null; then
            log_success "Python module execution works: python3 -m securegenomics"
        else
            log_error "Neither 'securegenomics' command nor 'python3 -m securegenomics' work"
            return 1
        fi
    fi
    
    # Test basic CLI functionality
    log_info "Testing basic CLI functionality..."
    if python3 -m securegenomics system status &> /dev/null; then
        log_success "CLI system status check passed"
    else
        log_warning "CLI system status check failed (this might be normal without server access)"
    fi
}

# Add to PATH if needed
setup_path() {
    log_step "Setting up PATH..."
    
    # Get user's local bin directory
    user_bin=$(python3 -c "import site; import os; print(os.path.join(site.USER_BASE, 'bin'))")
    
    # Check if securegenomics is in PATH
    if command -v securegenomics &> /dev/null; then
        log_success "securegenomics command is already in PATH"
        return 0
    fi
    
    # Check if user bin directory exists and contains securegenomics
    if [[ -f "$user_bin/securegenomics" ]]; then
        log_info "Found securegenomics in $user_bin"
        
        # Check if user bin is in PATH
        if [[ ":$PATH:" != *":$user_bin:"* ]]; then
            log_warning "User bin directory is not in PATH: $user_bin"
            log_info "Adding to PATH for this session..."
            export PATH="$PATH:$user_bin"
            
            # Suggest adding to shell profile
            shell_profile=""
            if [[ -n "$BASH_VERSION" ]]; then
                shell_profile="~/.bashrc"
            elif [[ -n "$ZSH_VERSION" ]]; then
                shell_profile="~/.zshrc"
            else
                shell_profile="~/.profile"
            fi
            
            log_info "To make this permanent, add this line to $shell_profile:"
            echo "export PATH=\"\$PATH:$user_bin\""
        fi
    fi
}

# Create convenience aliases
create_aliases() {
    log_step "Creating convenience commands..."
    
    # Create a wrapper script in a common location
    if [[ -w "/usr/local/bin" ]]; then
        log_info "Creating system-wide command in /usr/local/bin..."
        cat > /usr/local/bin/securegenomics << 'EOF'
#!/bin/bash
# SecureGenomics CLI wrapper script
python3 -m securegenomics "$@"
EOF
        chmod +x /usr/local/bin/securegenomics
        log_success "Created /usr/local/bin/securegenomics"
    else
        log_info "Cannot write to /usr/local/bin (permission denied)"
        log_info "You can use 'python3 -m securegenomics' instead of 'securegenomics'"
    fi
}

# Print usage instructions
print_usage() {
    log_step "Installation Complete! 🎉"
    echo
    log_success "SecureGenomics CLI is now installed and ready to use."
    echo
    log_info "Quick Start Commands:"
    echo "  securegenomics --version          # Check version"
    echo "  securegenomics login              # Login to your account"
    echo "  securegenomics create             # Create a new project"
    echo "  securegenomics keygen <project>   # Generate crypto keys"
    echo "  securegenomics upload <project> <file.vcf>  # Upload data"
    echo "  securegenomics run <project>      # Run analysis"
    echo "  securegenomics result <project>   # Get results"
    echo
    log_info "Alternative execution method:"
    echo "  python3 -m securegenomics --help"
    echo
    log_info "Documentation:"
    echo "  docs/guide.md       - User guide"
    echo "  docs/design.md      - Technical details"
    echo "  docs/CONTRIBUTING.md - Contributing guide"
    echo
    log_info "Need help? Check: https://github.com/securegenomics/securegenomics"
}

# Main installation process
main() {
    echo "🧬 SecureGenomics CLI Setup"
    echo "============================="
    echo
    
    check_directory
    check_python
    check_pip
    install_package
    test_installation
    setup_path
    
    # Try to create system-wide command if possible
    if [[ $EUID -eq 0 ]] || [[ -w "/usr/local/bin" ]]; then
        create_aliases
    fi
    
    print_usage
}

# Handle command line arguments
case "${1:-}" in
    --help|-h)
        echo "SecureGenomics CLI Setup Script"
        echo
        echo "Usage: bash setup.sh [options]"
        echo
        echo "Options:"
        echo "  --help, -h     Show this help message"
        echo "  --test         Test current installation"
        echo "  --clean        Clean installation and reinstall"
        echo
        echo "This script will:"
        echo "  1. Check Python 3.9+ and pip installation"
        echo "  2. Install SecureGenomics CLI in development mode"
        echo "  3. Test the installation"
        echo "  4. Set up the 'securegenomics' command"
        exit 0
        ;;
    --test)
        log_step "Testing current installation..."
        check_directory
        test_installation
        exit 0
        ;;
    --clean)
        log_step "Cleaning previous installation..."
        pip3 uninstall securegenomics -y 2>/dev/null || true
        rm -f /usr/local/bin/securegenomics 2>/dev/null || true
        log_success "Cleaned previous installation"
        ;;
esac

# Run main installation
main

exit 0 