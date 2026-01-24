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

TD=../..
include ${TD}/setup.gmk
PLT=platform-${platform}

# protobuf-c runtime files
SRCDIR = ${PLT}/protobuf-c
HFILES = protobuf-c.h
PBCINC = ${TD}/${BD}/include/protobuf-c
ARTEFACTS = ${TD}/${BD}/lib/libprotobuf-c.a \
	${PBCINC} \
	$(patsubst %, ${PBCINC}/%, ${HFILES})

all: $(if $(wildcard ${PLT}),${ARTEFACTS},${PLT})

${PBCINC}:
	@mkdir -p $@

# Build the runtime library from source
${PLT}/protobuf-c.o: ${SRCDIR}/protobuf-c.c ${SRCDIR}/protobuf-c.h
	@echo "  CC    protobuf-c.c"
	@${CC} -c -Wall -std=gnu11 -O2 -I${SRCDIR} -o $@ $<

${PLT}/libprotobuf-c.a: ${PLT}/protobuf-c.o
	@echo "  AR    libprotobuf-c.a"
	@${AR} rcs $@ $<

${TD}/${BD}/lib/libprotobuf-c.a: ${PLT}/libprotobuf-c.a
	@mkdir -p ${@D}
	@echo "  CP    ${<F} -> $@"
	@cp $< $@

${PBCINC}/%.h: ${SRCDIR}/%.h
	@echo "  CP    ${<F} -> $@"
	@cp $< $@

${PLT}: prep.sh
	platform=${platform} variant=${variant} ./prep.sh
	$(MAKE) --no-print-directory all platform=${platform} variant=${variant}

clean:
	rm -rf ${ARTEFACTS}
	rm -f ${PLT}/*.o ${PLT}/*.a

super-clean: clean
	rm -rf git-repo platform-*

.PHONY: all clean super-clean
