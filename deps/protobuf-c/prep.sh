#!/bin/bash

# --- Revised 3-Clause BSD License ---
# Copyright MULTI-TECH SYSTEMS, INC. 2025. All rights reserved.
#
# Redistribution and use in source and binary forms, with or without modification,
# are permitted provided that the following conditions are met:
#
#     * Redistributions of source code must retain the above copyright notice,
#       this list of conditions and the following disclaimer.
#     * Redistributions in binary form must reproduce the above copyright notice,
#       this list of conditions and the following disclaimer in the documentation
#       and/or other materials provided with the distribution.
#     * Neither the name of MULTI-TECH SYSTEMS, INC. nor the names of its
#       contributors may be used to endorse or promote products derived from this
#       software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL MULTI-TECH SYSTEMS, INC. BE LIABLE FOR ANY DIRECT,
# INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
# LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE
# OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF
# ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

set -e
cd $(dirname $0)

# protobuf-c version - using 1.5.0 (latest stable with good embedded support)
PROTOBUFC_VERSION=${PROTOBUFC_VERSION:-1.5.0}
PROTOBUFC_TAG="v${PROTOBUFC_VERSION}"

if [[ ! -d git-repo ]] || [[ "$(cd git-repo && git describe --tags 2>/dev/null || echo '')" != *"${PROTOBUFC_VERSION}"* ]]; then
    rm -rf git-repo platform-*
    echo "Cloning protobuf-c ${PROTOBUFC_VERSION}..."
    git clone -b "${PROTOBUFC_TAG}" --single-branch --depth 1 https://github.com/protobuf-c/protobuf-c.git git-repo
fi

if [[ -z "$platform" ]] || [[ -z "$variant" ]]; then
    echo "Expecting env vars platform/variant to be set - comes naturally if called from a makefile"
    echo "If calling manually try: variant=tests platform=linux $0"
    exit 1
fi

if [[ ! -d platform-$platform ]]; then
    cp -a git-repo platform-$platform
fi

cd platform-$platform
git reset --hard

# We only need the runtime library (protobuf-c.c and protobuf-c.h)
# The protoc-c compiler is used separately on the host
echo "protobuf-c prepared for platform-$platform"
