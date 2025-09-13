FROM ubuntu:24.04 AS builder
ENV DEBIAN_FRONTEND=noninteractive

# docker build  --network host -f Dockerfile.base -t ghcr.io/rse-ops/flux-arm:arm64-noble .
# docker push ghcr.io/rse-ops/flux-arm:arm64-noble
# lmp -v x 2 -v y 2 -v z 2 -in in.reaxff.hns -nocite

RUN apt-get update && apt-get install -y build-essential \
    tar \
    autoconf \
    automake \
    make \
    wget \
    git \
    gcc \
    g++ \
    zip \
    libblas-dev \
    liblapack-dev \
    libfftw3-dev libfftw3-bin \
    libxml2 \
    libxml2-dev \
    hdf5-tools \
    libhdf5-dev \
    cmake \
    libboost-all-dev \
    && apt-get clean

# Utilities
RUN apt-get update && \
    apt-get -qq install -y --no-install-recommends \
        apt-utils \
        locales \
        ca-certificates \
        wget \
        man \
        git \
        flex \
        ssh \
        sudo \
        vim \
        luarocks \
        munge \
        lcov \
        ccache \
        lua5.2 \
        python3-dev \
        python3-pip \
        valgrind \
        jq && \
    rm -rf /var/lib/apt/lists/*

# Compilers, autotools
RUN apt-get update && \
    apt-get -qq install -y --no-install-recommends \
        build-essential \
        pkg-config \
        autotools-dev \
        libtool \
	libffi-dev \
        autoconf \
        automake \
        make \
        clang \
        clang-tidy \
        gcc \
        g++ && \
    rm -rf /var/lib/apt/lists/*

# Python - instead of a system python we install anaconda
RUN pip install --upgrade --ignore-installed --break-system-packages \
        "markupsafe==2.0.0" \
        coverage cffi ply six pyyaml "jsonschema>=2.6,<4.0" \
        sphinx sphinx-rtd-theme sphinxcontrib-spelling breathe
        
RUN apt-get update && \
    apt-get -qq install -y --no-install-recommends \
        libsodium-dev \
        libzmq3-dev \
        libczmq-dev \
        libjansson-dev \
        libmunge-dev \
        libncursesw5-dev \
        liblua5.2-dev \
        liblz4-dev \
        libsqlite3-dev \
        uuid-dev \
        libhwloc-dev \
        libs3-dev \
        libevent-dev \
        libarchive-dev \
        libpam-dev && \
    rm -rf /var/lib/apt/lists/*

# Testing utils and libs
RUN apt-get update && \
    apt-get -qq install -y --no-install-recommends \
        faketime \
        libfaketime \
        pylint \
        cppcheck \
        enchant-2 \
        aspell \
        aspell-en && \
    rm -rf /var/lib/apt/lists/*

RUN locale-gen en_US.UTF-8

# NOTE: luaposix installed by rocks due to Ubuntu bug: #1752082 https://bugs.launchpad.net/ubuntu/+source/lua-posix/+bug/1752082
RUN luarocks install luaposix

# Install openpmix, prrte. Openpmix (pmix2) seems to be installed by hwloc, v5.x
RUN git clone --recurse-submodules https://github.com/openpmix/prrte.git && \
    cd prrte && \
    git checkout v3.0.1 && \
    ./autogen.pl && \
    ./configure --prefix=/opt/prrte && \
    # This installs OK but the exit code is off.
    make -j all install || true
 
ENV LANG=C.UTF-8
ARG FLUX_SECURITY_VERSION=0.11.0

WORKDIR /opt
RUN CCACHE_DISABLE=1 && \
    V=$FLUX_SECURITY_VERSION && \
    PKG=flux-security-$V && \
    URL=https://github.com/flux-framework/flux-security/releases/download && \
    wget ${URL}/v${V}/${PKG}.tar.gz && \
    tar xvfz ${PKG}.tar.gz && \
    cd ${PKG} && \
    ./configure --prefix=/usr --sysconfdir=/etc || cat config.log && \
    make -j 4 && \
    make install && \
    cd .. && \
    rm -rf flux-security-*

# Setup MUNGE directories & key
RUN mkdir -p /var/run/munge && \
    dd if=/dev/urandom bs=1 count=1024 > /etc/munge/munge.key && \
    chown -R munge /etc/munge/munge.key /var/run/munge && \
    chmod 600 /etc/munge/munge.key

ENV FLUX_CORE_VERSION=0.76.0
RUN wget https://github.com/flux-framework/flux-core/releases/download/v${FLUX_CORE_VERSION}/flux-core-${FLUX_CORE_VERSION}.tar.gz && \
    tar xzvf flux-core-${FLUX_CORE_VERSION}.tar.gz && \
    cd flux-core-${FLUX_CORE_VERSION} && \
    ./configure --prefix=/usr --sysconfdir=/etc && \
    make clean && \
    make && \
    sudo make install

RUN sudo apt-get update
RUN sudo apt-get -qq install -y --no-install-recommends \
	libboost-graph-dev \
	libboost-system-dev \
	libboost-filesystem-dev \
	libboost-regex-dev \
	libyaml-cpp-dev \
	libedit-dev \
        libboost-dev \
        libyaml-cpp-dev \
	curl

ENV FLUX_SCHED_VERSION=0.45.0
RUN wget https://github.com/flux-framework/flux-sched/releases/download/v${FLUX_SCHED_VERSION}/flux-sched-${FLUX_SCHED_VERSION}.tar.gz && \
    tar -xzvf flux-sched-${FLUX_SCHED_VERSION}.tar.gz && \
    cd flux-sched-${FLUX_SCHED_VERSION} && \
    ./configure --prefix=/usr --sysconfdir=/etc && \
    make && \
    sudo make install && \
    ldconfig

RUN apt-get update && \
    apt-get install -y libfftw3-dev libfftw3-bin pdsh libfabric-dev libfabric1 \
        openssh-client openssh-server \
        dnsutils telnet strace git g++ \
        unzip bzip2

# Additional debugging
RUN apt-get update && \
    apt-get install -y pdsh \
        openssh-client openssh-server \
        dnsutils telnet strace \
        unzip bzip2

WORKDIR /opt
RUN git clone --recurse-submodules https://github.com/LLNL/Adiak /opt/adiak && \
    cd /opt/adiak && mkdir build && cd build && \
    cmake -DCMAKE_INSTALL_PREFIX=/usr ../ && make -j && make install

RUN wget https://github.com/LLNL/Caliper/archive/refs/tags/v2.13.1.tar.gz && \
    tar -xzf v2.13.1.tar.gz && \
    mkdir caliper-build && cd caliper-build && \
    cmake ../Caliper-2.13.1 -DWITH_FORTRAN=on -DCMAKE_INSTALL_PREFIX=/usr -DWITH_ADIAK=ON -DWITH_MPI=ON && \
    make -j install && \
    cd /opt && rm -rf v2.13.1.tar.gz

COPY ./gke.cmake /opt/gke.cmake
COPY ./Kripke /opt/Kripke
COPY ./SweepSubdomain.cpp /opt/Kripke/src/Kripke/Kernel/SweepSubdomain.cpp
COPY ./kripke.cpp /opt/Kripke/src/kripke.cpp
COPY ./CMakeLists.txt /opt/Kripke/CMakeLists.txt
RUN cd /opt/Kripke && \
    git submodule update --init --recursive && \
    mkdir build && \
    mv /opt/gke.cmake /opt/Kripke/host-configs/gke.cmake && \
    cd /opt/Kripke/build && \
    cmake -C ../host-configs/gke.cmake -DENABLE_CALIPER=ON \
      -DCMAKE_PREFIX_PATH=/usr \
      -DENABLE_MPI=ON \
      -DCMAKE_CXX_FLAGS="-I/opt/Caliper-2.13.1/src/interface/c_fortran -I/opt/Caliper-2.13.1/src/include" \
      -DCALIPER_DIR=/usr/ \
      -DADIAK_DIR=/usr/ \
      -DCMAKE_CXX_COMPILER=mpicxx ../ && make -j 8 && \
    mv /opt/Kripke/build/kripke.exe /usr/local/bin/kripke && \
    rm -rf /opt/Kripke

EXPOSE 22

# Finally, install oras for saving artifacts
RUN export VERSION="1.1.0" && \
    curl -LO "https://github.com/oras-project/oras/releases/download/v${VERSION}/oras_${VERSION}_linux_amd64.tar.gz" && \
    mkdir -p oras-install/ && \
    tar -zxf oras_${VERSION}_*.tar.gz -C oras-install/ && \
    mv oras-install/oras /usr/local/bin/ && \
    rm -rf oras_${VERSION}_*.tar.gz oras-install/

COPY ./caliper.conf /caliper.conf
