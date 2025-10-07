terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 4.50.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
  zone    = var.zone
}

// 1. Networking (Correct and Unchanged)
resource "google_compute_network" "vpc" {
  name                    = "compute-cluster-vpc"
  auto_create_subnetworks = false
  mtu                     = 8896
}

resource "google_compute_subnetwork" "subnet" {
  name          = "compute-cluster-subnet"
  ip_cidr_range = "10.10.10.0/24"
  network       = google_compute_network.vpc.self_link
  region        = var.region
}

// 2. Firewall Rules (Correct and Unchanged)
resource "google_compute_firewall" "allow_ssh" {
  name    = "compute-cluster-allow-ssh"
  network = google_compute_network.vpc.name
  allow {
    protocol = "tcp"
    ports    = ["22"]
  }
  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["compute-cluster-node"]
}

resource "google_compute_firewall" "allow_internal" {
  name    = "compute-cluster-allow-internal"
  network = google_compute_network.vpc.name
  allow {
    protocol = "icmp"
  }
  allow {
    protocol = "tcp"
    ports    = ["0-65535"]
  }
  allow {
    protocol = "udp"
    ports    = ["0-65535"]
  }
  source_ranges = [google_compute_subnetwork.subnet.ip_cidr_range]
  target_tags   = ["compute-cluster-node"]
}

// 3. Look up the latest image from your custom family
data "google_compute_image" "compute_image" {
  family  = var.os_image_family
  project = var.project_id
}


// 4. Compute Node Resources
resource "google_compute_instance" "compute_nodes" {
  for_each = toset([for i in range(var.instance_count) : tostring(i)])

  name         = "flux-${each.key}"
  machine_type = var.compute_node_machine_type
  tags         = ["compute-cluster-node"]
  zone         = var.zone

  boot_disk {
    initialize_params {
      image = data.google_compute_image.compute_image.self_link
      size  = var.boot_disk_size_gb
    }
  }

  network_interface {
    subnetwork = google_compute_subnetwork.subnet.self_link
    access_config {} // Assigns an ephemeral public IP for SSH
  }

  metadata_startup_script = <<-BOOT_SCRIPT
    #!/bin/bash
    echo "Compute node ${each.key} is up and running." > /tmp/startup.log
    set -eEu -o pipefail

    export fluxroot=/usr
    export fluxuid=0
    ip_addr=$(hostname -I)
    export STATE_DIR=/var/lib/flux
    mkdir -p /var/lib/flux
    mkdir -p /usr/etc/flux/system/conf.d

    # --cores=IDS Assign cores with IDS to each rank in R, so we  assign 0-(N-1) to each host
    echo "flux R encode --hosts=flux-[0-7]"
    flux R encode --hosts=flux-[0-7] --local > /usr/etc/flux/system/R
    printf "\n📦 Resources\n"
    cat /usr/etc/flux/system/R

    mkdir -p /etc/flux/imp/conf.d/
    echo "[exec]" >> imp.toml
    echo "allowed-users = [ \"flux\", \"root\", \"sochat1_llnl_gov\" ]"  >> imp.toml
    echo "allowed-shells = [ \"/usr/libexec/flux/flux-shell\" ]" >> imp.toml
    mv imp.toml /etc/flux/imp/conf.d/imp.toml

    printf "\n🦊 Independent Minister of Privilege\n"
    cat /etc/flux/imp/conf.d/imp.toml
    cat <<EOT >> /tmp/system.toml
[exec]
imp = "/usr/libexec/flux/flux-imp"

[access]
allow-guest-user = true
allow-root-owner = true

[bootstrap]
curve_cert = "/usr/etc/flux/system/curve.cert"

default_port = 8050
default_bind = "tcp://ens3:%p"
default_connect = "tcp://%h:%p"

hosts = [{host="flux-[0-7]"}]

[tbon]
tcp_user_timeout = "2m"

[resource]
path = "/usr/etc/flux/system/R"

# Remove inactive jobs from the KVS after one week.
[job-manager]
inactive-age-limit = "7d"
EOT

    mv /tmp/system.toml /usr/etc/flux/system/conf.d/system.toml
    echo "🐸 Broker Configuration"
    cat /usr/etc/flux/system/conf.d/system.toml

    chmod u+s /usr/libexec/flux/flux-imp
    chmod 4755 /usr/libexec/flux/flux-imp
    chmod 0644 /etc/flux/imp/conf.d/imp.toml

    cat << "PYTHON_DECODING_SCRIPT" > /tmp/convert_curve_cert.py
#!/usr/bin/env python3
import sys
import base64

string = sys.argv[1]
dest = sys.argv[2]
with open(dest, 'w') as fd:
    fd.write(base64.b64decode(string).decode('utf-8'))
PYTHON_DECODING_SCRIPT

    python3 /tmp/convert_curve_cert.py "IyAgICoqKiogIEdlbmVyYXRlZCBvbiAyMDIzLTA3LTE2IDIwOjM5OjIxIGJ5IENaTVEgICoqKioK
IyAgIFplcm9NUSBDVVJWRSAqKlNlY3JldCoqIENlcnRpZmljYXRlCiMgICBETyBOT1QgUFJPVklE
RSBUSElTIEZJTEUgVE8gT1RIRVIgVVNFUlMgbm9yIGNoYW5nZSBpdHMgcGVybWlzc2lvbnMuCgpt
ZXRhZGF0YQogICAgbmFtZSA9ICJlODZhMTM1MWZiY2YiCiAgICBrZXlnZW4uY3ptcS12ZXJzaW9u
ID0gIjQuMi4wIgogICAga2V5Z2VuLnNvZGl1bS12ZXJzaW9uID0gIjEuMC4xOCIKICAgIGtleWdl
bi5mbHV4LWNvcmUtdmVyc2lvbiA9ICIwLjUxLjAtMTM1LWdiMjA0NjBhNmUiCiAgICBrZXlnZW4u
aG9zdG5hbWUgPSAiZTg2YTEzNTFmYmNmIgogICAga2V5Z2VuLnRpbWUgPSAiMjAyMy0wNy0xNlQy
MDozOToyMSIKICAgIGtleWdlbi51c2VyaWQgPSAiMTAwMiIKICAgIGtleWdlbi56bXEtdmVyc2lv
biA9ICI0LjMuMiIKY3VydmUKICAgIHB1YmxpYy1rZXkgPSAidVEmXnkrcDo3XndPUUQ8OkldLShL
RDkjbVo2I0wmeSlZTGUzTXBOMSIKICAgIHNlY3JldC1rZXkgPSAiVkUjQHBKKXgtRUE/WntrS1cx
ZWY9dTw+WCpOR2hKJjUqallNRSUjQCIKCg==" /tmp/curve.cert

    mv /tmp/curve.cert /usr/etc/flux/system/curve.cert
    chmod u=r,g=,o= /usr/etc/flux/system/curve.cert
    # chown flux:flux /usr/etc/flux/system/curve.cert
    # /usr/sbin/create-munge-key
    service munge start
    mkdir -p /run/flux

    # Remove group and other read
    chmod o-r /usr/etc/flux/system/curve.cert
    chmod g-r /usr/etc/flux/system/curve.cert
    chown -R $fluxuid /run/flux /var/lib/flux /usr/etc/flux/system/curve.cert

    printf "\n✨ Curve certificate generated by helper pod\n"
    cat /usr/etc/flux/system/curve.cert

    mkdir -p /etc/flux/manager
    cat << "FIRST_BOOT_UNIT" > /etc/systemd/system/flux-start.service
[Unit]
Description=Flux message broker
Wants=munge.service

[Service]
Type=simple
NotifyAccess=main
TimeoutStopSec=90
KillMode=mixed
ExecStart=/usr/bin/flux start --broker-opts --config /usr/etc/flux/system/conf.d -Stbon.fanout=256  -Srundir=/run/flux -Sbroker.rc2_none -Sstatedir=/var/lib/flux -Slocal-uri=local:///run/flux/local -Stbon.connect_timeout=5s -Stbon.zmqdebug=1  -Slog-stderr-level=7 -Slog-stderr-mode=local
SyslogIdentifier=flux
DefaultLimitMEMLOCK=infinity
LimitMEMLOCK=infinity
TasksMax=infinity
LimitNPROC=infinity
Restart=always
RestartSec=5s
RestartPreventExitStatus=42
SuccessExitStatus=42
User=root
PermissionsStartOnly=true
Delegate=yes

[Install]
WantedBy=multi-user.target
FIRST_BOOT_UNIT

    systemctl enable flux-start.service
    systemctl start flux-start.service
  BOOT_SCRIPT

  lifecycle {
    create_before_destroy = true
  }
}
