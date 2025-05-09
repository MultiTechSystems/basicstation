# --- Revised 3-Clause BSD License ---
# Copyright Semtech Corporation 2022. All rights reserved.
#
# Redistribution and use in source and binary forms, with or without modification,
# are permitted provided that the following conditions are met:
#
#     * Redistributions of source code must retain the above copyright notice,
#       this list of conditions and the following disclaimer.
#     * Redistributions in binary form must reproduce the above copyright notice,
#       this list of conditions and the following disclaimer in the documentation
#       and/or other materials provided with the distribution.
#     * Neither the name of the Semtech corporation nor the names of its
#       contributors may be used to endorse or promote products derived from this
#       software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL SEMTECH CORPORATION. BE LIABLE FOR ANY DIRECT,
# INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
# LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE
# OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF
# ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

TD=../..
platform?=linux
variant?=testsim

all: station sim

prep prep.done:
	./prep.sh

station:
	platform=${platform} variant=${variant} make -C ${TD}

sim: station prep.done
	PATH=${TD}/build-${platform}-${variant}/bin:${PATH} python sim.py runstation

emulate: prep.done
	./emulate.sh

tmux: station prep.done
	@if [ -z "${TMUX}" ]; then \
		echo "Starting new tmux session" ; \
		tmux new-session -d 'python sim.py'; \
		tmux split-window -v 'sleep 1; until ${TD}/build-${platform}-${variant}/bin/station  -h ./shome -t ./shome -l DEBUG; do echo -e "\e[31m== Station stopped. Restarting in 5 Second. Hit CTRL-C to terminate.\e[0m" ; sleep 5; done'; \
		tmux -2 attach-session -d; \
		tmux select-layout even-vertical; \
	else \
		echo "Creating new window inside tmux session"; \
		tmux new-window 'python sim.py'; \
		tmux split-window -v 'sleep 1; until ${TD}/build-${platform}-${variant}/bin/station  -h ./shome -t ./shome -l DEBUG; do echo -e "\e[31m== Station stopped. Restarting in 5 Second. Hit CTRL-C to terminate.\e[0m" ; sleep 5; done'; \
		tmux select-layout even-vertical; \
	fi

clean:
	cd shome && (rm -rf tc* station.log station-ap2.pid spidev cups* version.txt sig*)
	rm -rf ca cups-* tc* upd-sig prep.done

.PHONY: all clean prep tmux emulate sim station
