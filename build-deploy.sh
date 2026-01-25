#!/bin/bash
#
# Build and deploy Basic Station to MTCDT gateway
#
# Usage:
#   ./build-deploy.sh              # Build and deploy
#   ./build-deploy.sh --build      # Build only
#   ./build-deploy.sh --deploy     # Deploy only (use last build)
#   ./build-deploy.sh --clean      # Clean objects before build
#   ./build-deploy.sh --restart    # Just restart station on gateway
#

set -e

# Configuration
BUILDSERVER="jreiss@buildslavemtcdt3dm2"
GATEWAY_IP="10.10.200.140"
GATEWAY_USER="admin"
GATEWAY_PASS="admin2019!"
MTS_DEVICE="/home/jreiss/mts-device"
VERSION="2.0.6-27-r5"
RECIPE="lora-basic-station-sx1303"
WORKDIR="$MTS_DEVICE/build/tmp/work/mtcdt-mlinux-linux-gnueabi/$RECIPE/$VERSION/git"
BUILD_DIR="build-mlinux-sx1303"
LOCAL_TMP="/tmp/station-test"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Parse arguments
DO_BUILD=true
DO_DEPLOY=true
DO_CLEAN=false
DO_RESTART_ONLY=false

for arg in "$@"; do
    case $arg in
        --build)
            DO_DEPLOY=false
            ;;
        --deploy)
            DO_BUILD=false
            ;;
        --clean)
            DO_CLEAN=true
            ;;
        --restart)
            DO_BUILD=false
            DO_DEPLOY=false
            DO_RESTART_ONLY=true
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --build     Build only, don't deploy"
            echo "  --deploy    Deploy only, use last build"
            echo "  --clean     Clean object files before building"
            echo "  --restart   Just restart station on gateway"
            echo "  --help      Show this help"
            exit 0
            ;;
        *)
            log_error "Unknown option: $arg"
            exit 1
            ;;
    esac
done

# Just restart?
if $DO_RESTART_ONLY; then
    log_info "Restarting station on gateway..."
    sshpass -p "$GATEWAY_PASS" ssh "$GATEWAY_USER@$GATEWAY_IP" \
        "echo '$GATEWAY_PASS' | sudo -S /etc/init.d/lora-network-server restart"
    log_info "Done!"
    exit 0
fi

# Build phase
if $DO_BUILD; then
    log_info "Copying source files to build server..."
    scp src/*.c src/*.h "$BUILDSERVER:$WORKDIR/src/" 2>/dev/null || true
    scp src-linux/*.c src-linux/*.h "$BUILDSERVER:$WORKDIR/src-linux/" 2>/dev/null || true
    
    if $DO_CLEAN; then
        log_info "Cleaning object files..."
        ssh "$BUILDSERVER" "rm -f $WORKDIR/$BUILD_DIR/s2core/*.o"
    fi
    
    # Record timestamp before build
    BUILD_START=$(date +%s)
    
    log_info "Compiling on build server..."
    # Use direct make instead of bitbake for more reliable rebuilds
    # bitbake -c compile -f doesn't always trigger actual recompilation
    # Remove commonly modified object files to force rebuild
    ssh -o ConnectTimeout=10 -o ServerAliveInterval=30 "$BUILDSERVER" "cd $WORKDIR/$BUILD_DIR/s2core && \
        rm -f ral_lgw.o ral_master.o sx130xconf.o tcpb.o tc.pb.o s2e.o selftest_s2e.o ../lib/libs2core.a ../bin/station && \
        source $MTS_DEVICE/build/tmp/work/mtcdt-mlinux-linux-gnueabi/$RECIPE/$VERSION/temp/run.do_compile 2>&1" | \
        grep -E "(ERROR|error:|warning:|EXE built)" || true
    
    # Check if build succeeded
    if ssh "$BUILDSERVER" "test -f $WORKDIR/$BUILD_DIR/bin/station"; then
        log_info "Build succeeded!"
    else
        log_error "Build failed - binary not found"
        exit 1
    fi
    
    # Verify object files were actually rebuilt
    log_info "Verifying object files were updated..."
    OBJ_TIME=$(ssh "$BUILDSERVER" "stat -c %Y $WORKDIR/$BUILD_DIR/s2core/s2e.o 2>/dev/null || echo 0")
    if [ "$OBJ_TIME" -lt "$BUILD_START" ]; then
        log_warn "Some object files may not have been rebuilt"
        log_warn "This is OK if only deploying existing code"
    else
        log_info "Object files verified - timestamps are current"
    fi
fi

# Deploy phase
if $DO_DEPLOY; then
    log_info "Copying binary from build server..."
    scp "$BUILDSERVER:$WORKDIR/$BUILD_DIR/bin/station" "$LOCAL_TMP"
    
    log_info "Deploying to gateway $GATEWAY_IP..."
    sshpass -p "$GATEWAY_PASS" scp "$LOCAL_TMP" "$GATEWAY_USER@$GATEWAY_IP:/tmp/station"
    
    log_info "Installing and restarting station..."
    sshpass -p "$GATEWAY_PASS" ssh "$GATEWAY_USER@$GATEWAY_IP" \
        "echo '$GATEWAY_PASS' | sudo -S cp /tmp/station /opt/lora/station-sx1303 && \
         echo '$GATEWAY_PASS' | sudo -S chmod +x /opt/lora/station-sx1303 && \
         echo '$GATEWAY_PASS' | sudo -S /etc/init.d/lora-network-server restart"
    
    log_info "Deployment complete!"
fi

log_info "Done!"
