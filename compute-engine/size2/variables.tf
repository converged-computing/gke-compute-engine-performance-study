variable "project_id" {
  description = "The Google Cloud project ID to deploy resources into."
  type        = string
}

variable "region" {
  description = "The GCP region to deploy resources into."
  type        = string
  default     = "us-central1"
}

variable "zone" {
  description = "The GCP zone to deploy resources into."
  type        = string
  default     = "us-central1-a"
}

variable "compute_node_machine_type" {
  description = "The machine type for the compute node instances."
  type        = string
  default     = "c4-standard-16"
}

variable "instance_count" {
  description = "The number of compute nodes to create."
  type        = number
  default     = 2
}

variable "os_image_family" {
  description = "The OS image family to use for the compute instances."
  type        = string
  default     = "flux-compute-engine-caliper"
}

variable "boot_disk_size_gb" {
  description = "Size of the boot disk in GB for compute nodes."
  type        = number
  default     = 256
}
