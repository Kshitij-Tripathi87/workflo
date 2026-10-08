# Tenant Shield Platform Infrastructure
# Terraform module — provisions the core cloud resources for the SaaS.
# Note: This is a starter template. Adjust provider/region per your cloud.

terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

variable "region" {
  type    = string
  default = "us-east-1"
}

variable "environment" {
  type    = string
  default = "production"
}

provider "aws" {
  region = var.region
}

# --- Storage: S3 Bucket for test artifacts ---
resource "aws_s3_bucket" "artifacts" {
  bucket = "tenant-shield-artifacts-${var.environment}"
}

resource "aws_s3_bucket_lifecycle_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  rule {
    id     = "expire-old-artifacts"
    status = "Enabled"
    expiration {
      days = 90
    }
  }
}

# --- Database: RDS PostgreSQL ---
resource "aws_db_instance" "control_plane_db" {
  identifier          = "tenant-shield-${var.environment}"
  engine              = "postgres"
  engine_version      = "15"
  instance_class      = "db.t3.medium"
  allocated_storage   = 20
  username            = "tenant_shield"
  password            = var.db_password
  skip_final_snapshot = true
}

variable "db_password" {
  type      = string
  sensitive = true
}

# --- Cache + Queue: Redis (ElastiCache) ---
resource "aws_elasticache_cluster" "redis" {
  cluster_id           = "tenant-shield-${var.environment}"
  engine               = "redis"
  node_type            = "cache.t3.micro"
  num_cache_nodes      = 1
  parameter_group_name = "default.redis7"
}

# --- Output the connection strings ---
output "s3_bucket_name" {
  value = aws_s3_bucket.artifacts.bucket
}

output "db_endpoint" {
  value = aws_db_instance.control_plane_db.endpoint
}

output "redis_endpoint" {
  value = aws_elasticache_cluster.redis.cache_nodes[0].address
}
