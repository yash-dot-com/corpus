variable "aws_region" {
  description = "AWS region for all Corpora resources."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Prefix used for resource names."
  type        = string
  default     = "corpora"
}

variable "environment" {
  description = "Deployment environment name."
  type        = string
  default     = "dev"
}

variable "worker_package" {
  description = "Path to the crawl-worker Lambda zip artifact."
  type        = string
}

variable "storage_worker_package" {
  description = "Path to the storage-worker Lambda zip artifact."
  type        = string
}

variable "worker_handler" {
  description = "Crawl worker Lambda handler."
  type        = string
  default     = "lambda_worker.handler"
}

variable "storage_worker_handler" {
  description = "Storage worker Lambda handler."
  type        = string
  default     = "lambda_storage.handler"
}

variable "db_username" {
  description = "RDS master username. Prefer a secret manager in production."
  type        = string
  default     = "corpora"
}

variable "db_password" {
  description = "RDS master password. Pass via TF_VAR_db_password or a secret manager."
  type        = string
  sensitive   = true
}

variable "coordinator_instance_type" {
  description = "EC2 instance type for the single V1 coordinator."
  type        = string
  default     = "t3.micro"
}
