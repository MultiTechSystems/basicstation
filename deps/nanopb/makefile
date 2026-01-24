# --- Revised 3-Clause BSD License ---
# Copyright (C) 2025, MULTI-TECH SYSTEMS, INC.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#     * Redistributions of source code must retain the above copyright notice,
#       this list of conditions and the following disclaimer.
#     * Redistributions in binary form must reproduce the above copyright notice,
#       this list of conditions and the following disclaimer in the documentation
#       and/or other materials provided with the distribution.
#     * Neither the name of the copyright holder nor the names of its contributors
#       may be used to endorse or promote products derived from this software
#       without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL SEMTECH BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
# PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
# LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE
# OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF
# ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

TD=../..
include ${TD}/setup.gmk
PLT=platform-${platform}
SD=git-repo

HFILES = pb.h pb_encode.h pb_decode.h pb_common.h
NANOPBINC = ${TD}/${BD}/include
ARTEFACTS = ${TD}/${BD}/lib/libnanopb.a \
	$(patsubst %, ${NANOPBINC}/%, ${HFILES})

all: $(if $(wildcard ${SD}/pb.h),${ARTEFACTS},${PLT})

${PLT}: prep.sh
	platform=${platform} variant=${variant} ./prep.sh
	mkdir -p ${PLT}
	${MAKE} -C . build-nanopb platform=${platform} variant=${variant}
	${MAKE} -C . install-headers platform=${platform} variant=${variant}

build-nanopb: ${PLT}/libnanopb.a

install-headers: ${TD}/${BD}/lib/libnanopb.a $(patsubst %, ${NANOPBINC}/%, ${HFILES})

${PLT}/pb_encode.o: ${SD}/pb_encode.c
	@mkdir -p ${@D}
	${CC} -Wall -O2 -fPIC -I${SD} -c $< -o $@

${PLT}/pb_decode.o: ${SD}/pb_decode.c
	@mkdir -p ${@D}
	${CC} -Wall -O2 -fPIC -I${SD} -c $< -o $@

${PLT}/pb_common.o: ${SD}/pb_common.c
	@mkdir -p ${@D}
	${CC} -Wall -O2 -fPIC -I${SD} -c $< -o $@

${PLT}/libnanopb.a: ${PLT}/pb_encode.o ${PLT}/pb_decode.o ${PLT}/pb_common.o
	${AR} rcs $@ $^

${TD}/${BD}/lib/libnanopb.a: ${PLT}/libnanopb.a
	@mkdir -p ${@D}
	@echo "  CP    ${<F} -> $@"
	@cp $< $@

${NANOPBINC}/%.h: ${SD}/%.h
	@mkdir -p ${@D}
	@echo "  CP    ${<F} -> $@"
	@cp $< $@

clean:
	rm -rf ${ARTEFACTS}
	rm -rf ${PLT}/*.o ${PLT}/*.a

super-clean: clean
	rm -rf git-repo platform-*

.PHONY: all build-nanopb install-headers clean super-clean
