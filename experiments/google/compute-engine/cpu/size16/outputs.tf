output "list_instances_command" {
  description = "A gcloud command to list the compute instances created by this configuration."
  # We now filter by the common tag we assigned to all instances.
  value = "gcloud compute instances list --filter='tags:compute-cluster-node'"
}

output "ssh_to_a_node_example" {
  description = "Example command to SSH into one of the compute nodes (e.g., the first one)."
  # We provide a static example because the names are now generated dynamically.
  value = "Use 'gcloud compute ssh flux-0 --zone ${var.zone}' to connect to the first node."
}
