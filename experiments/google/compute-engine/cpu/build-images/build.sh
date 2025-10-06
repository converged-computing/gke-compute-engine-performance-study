# ubuntu:24.04
# c4d-standard-16

export DEBIAN_FRONTEND=noninteractive

sudo apt-get update && sudo apt-get install -y \
    build-essential \
    cmake \
    gfortran \
    git \
    wget \
    openmpi-bin \
    python3-dev \
    libopenmpi-dev 
    
mkdir /build
sudo mkdir /build
sudo chown $USER /build
cd /build/

wget https://github.com/LLNL/Caliper/archive/refs/tags/v2.13.1.tar.gz && \
    tar -xzf v2.13.1.tar.gz && \
    mkdir caliper-build && cd caliper-build && \
    cmake ../Caliper-2.13.1 -DCMAKE_INSTALL_PREFIX=/usr -DWITH_MPI=ON && \
    sudo make -j install && \
    cd /build && rm -rf v2.13.1.tar.gz Caliper-2.13.1 caliper-build

sudo apt-get update && sudo apt-get install -y build-essential \
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
    && sudo apt-get clean

# Utilities
sudo apt-get update && \
    sudo apt-get -qq install -y --no-install-recommends \
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
    sudo rm -rf /var/lib/apt/lists/*

# Compilers, autotools
sudo apt-get update && \
    sudo apt-get -qq install -y --no-install-recommends \
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
    sudo rm -rf /var/lib/apt/lists/*

sudo pip install --upgrade --ignore-installed --break-system-packages \
        "markupsafe==2.0.0" \
        coverage cffi ply six pyyaml "jsonschema>=2.6,<4.0" \
        sphinx sphinx-rtd-theme sphinxcontrib-spelling 
   
sudo apt-get update && \
    sudo apt-get -qq install -y --no-install-recommends \
        libsodium-dev \
        libzmq3-dev \
        certbot \
        nginx \
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
    sudo rm -rf /var/lib/apt/lists/*

# Testing utils and libs
sudo apt-get update && \
    sudo apt-get -qq install -y --no-install-recommends \
        faketime \
        libfaketime \
        pylint \
        cppcheck \
        enchant-2 \
        aspell \
        aspell-en && \
    sudo rm -rf /var/lib/apt/lists/*

sudo locale-gen en_US.UTF-8
sudo luarocks install luaposix
export LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu

# Install openpmix, prrte. Openpmix (pmix2) seems to be installed by hwloc, v5.x
cd /opt
git clone --recurse-submodules https://github.com/openpmix/prrte.git && \
    cd prrte && \
    git checkout v3.0.1 && \
    ./autogen.pl && \
    ./configure --prefix=/usr && \
    make -j && sudo make -j all install
 
cd /opt
export LANG=C.UTF-8
export FLUX_SECURITY_VERSION=0.14.0
export CCACHE_DISABLE=1
V=$FLUX_SECURITY_VERSION && \
    PKG=flux-security-$V && \
    URL=https://github.com/flux-framework/flux-security/releases/download && \
    wget ${URL}/v${V}/${PKG}.tar.gz && \
    tar xvfz ${PKG}.tar.gz && \
    cd ${PKG} && \
    ./configure --prefix=/usr --sysconfdir=/etc || cat config.log && \
    make -j 4 && \
    sudo make install && \
    cd .. && \
    rm -rf flux-security-*

# Setup MUNGE directories & key
sudo mkdir -p /var/run/munge && \
    dd if=/dev/urandom bs=1 count=1024 > munge.key && sudo mv munge.key /etc/munge/munge.key && \
    sudo chown -R munge /etc/munge/munge.key /var/run/munge && \
    sudo chmod 600 /etc/munge/munge.key

export FLUX_CORE_VERSION=0.76.0
wget https://github.com/flux-framework/flux-core/releases/download/v${FLUX_CORE_VERSION}/flux-core-${FLUX_CORE_VERSION}.tar.gz && \
    tar xzvf flux-core-${FLUX_CORE_VERSION}.tar.gz && \
    cd flux-core-${FLUX_CORE_VERSION} && \
    ./configure --prefix=/usr --sysconfdir=/etc && \
    make clean && \
    make -j && \
    sudo make install

sudo apt-get update
sudo apt-get -qq install -y --no-install-recommends \
	libboost-graph-dev \
	libboost-system-dev \
	libboost-filesystem-dev \
	libboost-regex-dev \
	libyaml-cpp-dev \
	libedit-dev \
        libboost-dev \
        libyaml-cpp-dev \
	curl

cd /opt
export FLUX_SCHED_VERSION=0.45.0
wget https://github.com/flux-framework/flux-sched/releases/download/v${FLUX_SCHED_VERSION}/flux-sched-${FLUX_SCHED_VERSION}.tar.gz && \
    tar -xzvf flux-sched-${FLUX_SCHED_VERSION}.tar.gz && \
    cd flux-sched-${FLUX_SCHED_VERSION} && \
    ./configure --prefix=/usr --sysconfdir=/etc && \
    make -j && \
    sudo make install && \
    sudo ldconfig

sudo apt-get update && \
    sudo apt-get install -y libfftw3-dev libfftw3-bin pdsh libfabric-dev libfabric1 \
        openssh-client openssh-server \
        dnsutils telnet strace git g++ \
        unzip bzip2

# Additional debugging
sudo apt-get update && \
    sudo apt-get install -y pdsh \
        openssh-client openssh-server \
        dnsutils telnet strace \
        unzip bzip2

# Questions for Dan:
# with instrumentation, without instrumentation (instrumentation overhead)
# build on ubuntu base
# should we run these actually on bare metal vs. singularity (or both)? If bare metal, likely will need to rebuild.

# Install from source for now - need to still do instrumented versions later
# Install oras for saving artifacts
cd /opt
VERSION="1.2.0" && \
    curl -LO "https://github.com/oras-project/oras/releases/download/v${VERSION}/oras_${VERSION}_linux_amd64.tar.gz" && \
    mkdir -p oras-install/ && \
    tar -zxf oras_${VERSION}_*.tar.gz -C oras-install/ && \
    sudo mv oras-install/oras /usr/local/bin/ && \
    rm -rf oras_${VERSION}_*.tar.gz oras-install/

sudo apt-get install -y python3-breathe
cd /opt
git clone --recurse-submodules https://github.com/LLNL/Adiak /opt/adiak && \
    cd /opt/adiak && mkdir build && cd build && \
    cmake ../ && make -j && sudo make install

# This is OSU on bare metal, no instrumentation
# /opt/osu-benchmark/build.openmpi/mpi/pt2pt/osu_latency
# /usr/libexec/osu-micro-benchmarks/mpi/pt2pt/osu_latency
cd /opt
export CALIPER_PATH=/usr
git clone --depth 1 https://github.com/ULHPC/tutorials /opt/tutorials && \
    mkdir -p /opt/osu-benchmark && \
    cd /opt/osu-benchmark && \
    ln -s /opt/tutorials/parallel/mpi/OSU_MicroBenchmarks ref.d && \
    ln -s ref.d/Makefile . && \
    ln -s ref.d/scripts  . && \
    mkdir src && \
    cd src && \
    export OSU_VERSION=5.8 && \
    wget --no-check-certificate http://mvapich.cse.ohio-state.edu/download/mvapich/osu-micro-benchmarks-${OSU_VERSION}.tgz && \
    tar xf osu-micro-benchmarks-${OSU_VERSION}.tgz && \
    cd /opt/osu-benchmark && \
    # Compile based on openmpi
    mkdir -p build.openmpi && cd build.openmpi && \
    export LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu && \
    export CPPFLAGS="-I$CALIPER_PATH/include" && \
    export LDFLAGS="-L$CALIPER_PATH/lib64" && \
    export LIBS="-lcaliper -ladiak" && \
    ../src/osu-micro-benchmarks-${OSU_VERSION}/configure CC=mpicc CXX=mpicxx CFLAGS=-I$(pwd)/../src/osu-micro-benchmarks-${OSU_VERSION}/util --prefix=/usr && \
    make && sudo make install

wget https://github.com/LLNL/Caliper/archive/refs/tags/v2.13.1.tar.gz && \
    tar -xzf v2.13.1.tar.gz && \
    mkdir caliper-build && cd caliper-build && \
    cmake ../Caliper-2.13.1 -DWITH_FORTRAN=on -DCMAKE_INSTALL_PREFIX=/usr -DWITH_ADIAK=ON -DWITH_MPI=ON && \
    make -j install && \
    cd /opt && rm -rf v2.13.1.tar.gz

# See Dockerfile in docker for what files were copied here

# kripke
cd /opt
git clone https://github.com/llnl/Kripke
cd /opt/Kripke && \
git submodule update --init --recursive && \
mkdir build && \
# note that gke.cmake was manually added during build of vm - from converged-computing/performance-study on GitHub
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
    
# Install Singularity and pull images
wget https://go.dev/dl/go1.25.1.linux-amd64.tar.gz
rm -rf /usr/local/go && sudo tar -C /usr/local -xzf go1.25.1.linux-amd64.tar.gz
cd /tmp
export APPTAINER_VERSION=1.4.3 # Change this to the latest version if needed

# Download the source code
wget https://github.com/apptainer/apptainer/releases/download/v${APPTAINER_VERSION}/apptainer-${APPTAINER_VERSION}.tar.gz
tar -xzf apptainer-${APPTAINER_VERSION}.tar.gz
cd apptainer-${APPTAINER_VERSION}

# Configure, compile, and install
export PATH=/usr/local/go/bin:$PATH
./mconfig
make -C ./builddir -j$(nproc)
sudo make -C ./builddir install

# Install containers (note I don't think we can use these)
mkdir -p /opt/containers
sudo chown $(id -u) /opt/containers
cd /opt/containers
singularity pull docker://ghcr.io/converged-computing/google-performance-study:osu-caliper-test
singularity pull docker://ghcr.io/converged-computing/google-performance-study:osu-test
singularity pull docker://ghcr.io/converged-computing/google-performance-study:kripke-caliper-test
singularity pull docker://ghcr.io/converged-computing/google-performance-study:kripke-test


