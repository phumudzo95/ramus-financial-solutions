# ── Ramus Cash Loans Credit System — AWS Infrastructure (Terraform) ──────────
# Region: af-south-1 (Cape Town) — primary
# All resources are tagged for cost allocation and compliance.

terraform {
  required_version = ">= 1.9.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.65"
    }
  }
  backend "s3" {
    bucket         = "ramus-terraform-state"
    key            = "credit-system/terraform.tfstate"
    region         = "af-south-1"
    encrypt        = true
    dynamodb_table = "ramus-terraform-locks"
  }
}

provider "aws" {
  region = var.aws_region
  default_tags {
    tags = {
      Project     = "RamusCreditSystem"
      Environment = var.environment
      ManagedBy   = "Terraform"
      CostCenter  = "CreditOperations"
      Compliance  = "NCA-NCR"
    }
  }
}

# ── Variables ─────────────────────────────────────────────────────────────────

variable "aws_region"   { default = "af-south-1" }
variable "environment"  { default = "production" }
variable "db_password"  { sensitive = true }
variable "app_domain"   { description = "e.g. credit.ramuscashloans.co.za" }


# ── VPC ───────────────────────────────────────────────────────────────────────

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "5.13.0"

  name = "ramus-vpc-${var.environment}"
  cidr = "10.0.0.0/16"

  azs             = ["af-south-1a", "af-south-1b", "af-south-1c"]
  private_subnets = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
  public_subnets  = ["10.0.101.0/24", "10.0.102.0/24", "10.0.103.0/24"]

  enable_nat_gateway   = true
  single_nat_gateway   = var.environment != "production"
  enable_dns_hostnames = true
  enable_dns_support   = true
}


# ── RDS PostgreSQL 16 ─────────────────────────────────────────────────────────

resource "aws_db_subnet_group" "main" {
  name       = "ramus-db-subnet-${var.environment}"
  subnet_ids = module.vpc.private_subnets
}

resource "aws_security_group" "rds" {
  name   = "ramus-rds-sg"
  vpc_id = module.vpc.vpc_id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs_tasks.id]
  }
}

resource "aws_db_instance" "postgres" {
  identifier             = "ramus-postgres-${var.environment}"
  engine                 = "postgres"
  engine_version         = "16.4"
  instance_class         = var.environment == "production" ? "db.r8g.large" : "db.t4g.medium"
  allocated_storage      = 100
  max_allocated_storage  = 1000
  storage_type           = "gp3"
  storage_encrypted      = true
  kms_key_id             = aws_kms_key.rds.arn

  db_name  = "ramus_credit"
  username = "ramus_admin"
  password = var.db_password

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]

  backup_retention_period = 35
  backup_window           = "03:00-04:00"
  maintenance_window      = "sun:04:00-sun:05:00"
  deletion_protection     = var.environment == "production"
  multi_az                = var.environment == "production"
  skip_final_snapshot     = var.environment != "production"
  final_snapshot_identifier = var.environment == "production" ? "ramus-final-snapshot" : null

  performance_insights_enabled = true
  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]

  parameter_group_name = aws_db_parameter_group.postgres.name
}

resource "aws_db_parameter_group" "postgres" {
  family = "postgres16"
  name   = "ramus-postgres16-params"

  parameter {
    name  = "log_statement"
    value = "ddl"
  }
  parameter {
    name  = "log_min_duration_statement"
    value = "1000"  # Log queries > 1s
  }
  parameter {
    name  = "ssl"
    value = "1"
  }
}


# ── ElastiCache Redis ─────────────────────────────────────────────────────────

resource "aws_elasticache_subnet_group" "main" {
  name       = "ramus-redis-subnet"
  subnet_ids = module.vpc.private_subnets
}

resource "aws_elasticache_cluster" "redis" {
  cluster_id           = "ramus-redis-${var.environment}"
  engine               = "redis"
  node_type            = var.environment == "production" ? "cache.r7g.medium" : "cache.t4g.micro"
  num_cache_nodes      = 1
  parameter_group_name = "default.redis7"
  engine_version       = "7.1"
  port                 = 6379
  subnet_group_name    = aws_elasticache_subnet_group.main.name
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
}


# ── ECS Fargate — API Service ─────────────────────────────────────────────────

resource "aws_ecs_cluster" "main" {
  name = "ramus-cluster-${var.environment}"

  configuration {
    execute_command_configuration {
      logging = "OVERRIDE"
      log_configuration {
        cloud_watch_log_group_name = aws_cloudwatch_log_group.ecs.name
      }
    }
  }
}

resource "aws_security_group" "ecs_tasks" {
  name   = "ramus-ecs-tasks-sg"
  vpc_id = module.vpc.vpc_id

  ingress {
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_ecs_task_definition" "api" {
  family                   = "ramus-api-${var.environment}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "1024"
  memory                   = "2048"
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([
    {
      name  = "ramus-api"
      image = "${aws_ecr_repository.api.repository_url}:latest"
      portMappings = [{ containerPort = 8000 }]
      environment = [
        { name = "ENVIRONMENT", value = var.environment },
        { name = "AWS_REGION",  value = var.aws_region },
      ]
      secrets = [
        { name = "DATABASE_URL",             valueFrom = aws_ssm_parameter.db_url.arn },
        { name = "JWT_PRIVATE_KEY",          valueFrom = aws_ssm_parameter.jwt_private.arn },
        { name = "JWT_PUBLIC_KEY",           valueFrom = aws_ssm_parameter.jwt_public.arn },
        { name = "TRANSUNION_API_KEY",       valueFrom = aws_ssm_parameter.tu_api_key.arn },
        { name = "TRANSUNION_CLIENT_SECRET", valueFrom = aws_ssm_parameter.tu_secret.arn },
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.api.name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "api"
        }
      }
      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 60
      }
    }
  ])
}

resource "aws_ecs_service" "api" {
  name            = "ramus-api-service"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.environment == "production" ? 3 : 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets         = module.vpc.private_subnets
    security_groups = [aws_security_group.ecs_tasks.id]
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "ramus-api"
    container_port   = 8000
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }
}


# ── Application Load Balancer ─────────────────────────────────────────────────

resource "aws_security_group" "alb" {
  name   = "ramus-alb-sg"
  vpc_id = module.vpc.vpc_id

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_lb" "main" {
  name               = "ramus-alb-${var.environment}"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = module.vpc.public_subnets

  enable_deletion_protection = var.environment == "production"

  access_logs {
    bucket  = aws_s3_bucket.alb_logs.bucket
    enabled = true
  }
}

resource "aws_lb_target_group" "api" {
  name        = "ramus-api-tg"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = module.vpc.vpc_id
  target_type = "ip"

  health_check {
    path                = "/health"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    interval            = 30
  }
}


# ── KMS Keys ──────────────────────────────────────────────────────────────────

resource "aws_kms_key" "rds" {
  description             = "Ramus RDS encryption key"
  deletion_window_in_days = 30
  enable_key_rotation     = true
}

resource "aws_kms_key" "app" {
  description             = "Ramus application data encryption (PII fields)"
  deletion_window_in_days = 30
  enable_key_rotation     = true
}

resource "aws_kms_alias" "app" {
  name          = "alias/ramus-app-${var.environment}"
  target_key_id = aws_kms_key.app.key_id
}


# ── S3 Buckets ────────────────────────────────────────────────────────────────

resource "aws_s3_bucket" "documents" {
  bucket = "ramus-documents-${var.environment}-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket_server_side_encryption_configuration" "documents" {
  bucket = aws_s3_bucket.documents.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.app.arn
    }
  }
}

resource "aws_s3_bucket_versioning" "documents" {
  bucket = aws_s3_bucket.documents.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_public_access_block" "documents" {
  bucket                  = aws_s3_bucket.documents.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket" "audit_logs" {
  bucket = "ramus-audit-logs-${var.environment}-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket_lifecycle_configuration" "audit" {
  bucket = aws_s3_bucket.audit_logs.id
  rule {
    id     = "archive-old-logs"
    status = "Enabled"
    transition {
      days          = 90
      storage_class = "GLACIER"
    }
    expiration {
      days = 2555  # 7 years
    }
  }
}


# ── ECR ───────────────────────────────────────────────────────────────────────

resource "aws_ecr_repository" "api" {
  name                 = "ramus/credit-api"
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "KMS"
    kms_key         = aws_kms_key.app.arn
  }
}


# ── CloudWatch Logs ───────────────────────────────────────────────────────────

resource "aws_cloudwatch_log_group" "api" {
  name              = "/ramus/api/${var.environment}"
  retention_in_days = 90
}

resource "aws_cloudwatch_log_group" "ecs" {
  name              = "/ramus/ecs/${var.environment}"
  retention_in_days = 30
}


# ── WAF ───────────────────────────────────────────────────────────────────────

resource "aws_wafv2_web_acl" "main" {
  name  = "ramus-waf-${var.environment}"
  scope = "REGIONAL"

  default_action { allow {} }

  rule {
    name     = "AWSManagedRulesCommonRuleSet"
    priority = 1
    override_action { none {} }
    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesCommonRuleSet"
        vendor_name = "AWS"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "CommonRules"
      sampled_requests_enabled   = true
    }
  }

  rule {
    name     = "RateLimitAuth"
    priority = 2
    action { block {} }
    statement {
      rate_based_statement {
        limit              = 100
        aggregate_key_type = "IP"
        scope_down_statement {
          byte_match_statement {
            search_string         = "/api/v1/auth"
            field_to_match { uri_path {} }
            text_transformation { priority = 0; type = "NONE" }
            positional_constraint = "STARTS_WITH"
          }
        }
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "AuthRateLimit"
      sampled_requests_enabled   = true
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "RamusWAF"
    sampled_requests_enabled   = true
  }
}


# ── SSM Parameters (secrets) ──────────────────────────────────────────────────

resource "aws_ssm_parameter" "db_url" {
  name  = "/ramus/${var.environment}/DATABASE_URL"
  type  = "SecureString"
  value = "postgresql+asyncpg://ramus_admin:${var.db_password}@${aws_db_instance.postgres.endpoint}/ramus_credit"
}

resource "aws_ssm_parameter" "jwt_private" {
  name  = "/ramus/${var.environment}/JWT_PRIVATE_KEY"
  type  = "SecureString"
  value = "REPLACE_WITH_RSA_PRIVATE_KEY"
  lifecycle { ignore_changes = [value] }
}

resource "aws_ssm_parameter" "jwt_public" {
  name  = "/ramus/${var.environment}/JWT_PUBLIC_KEY"
  type  = "SecureString"
  value = "REPLACE_WITH_RSA_PUBLIC_KEY"
  lifecycle { ignore_changes = [value] }
}

resource "aws_ssm_parameter" "tu_api_key" {
  name  = "/ramus/${var.environment}/TRANSUNION_API_KEY"
  type  = "SecureString"
  value = "REPLACE_WITH_TRANSUNION_API_KEY"
  lifecycle { ignore_changes = [value] }
}

resource "aws_ssm_parameter" "tu_secret" {
  name  = "/ramus/${var.environment}/TRANSUNION_CLIENT_SECRET"
  type  = "SecureString"
  value = "REPLACE_WITH_TRANSUNION_CLIENT_SECRET"
  lifecycle { ignore_changes = [value] }
}

data "aws_caller_identity" "current" {}


# ── Outputs ───────────────────────────────────────────────────────────────────

output "api_endpoint"    { value = "https://${var.app_domain}/api/v1" }
output "alb_dns_name"    { value = aws_lb.main.dns_name }
output "rds_endpoint"    { value = aws_db_instance.postgres.endpoint }
output "ecr_repo_url"    { value = aws_ecr_repository.api.repository_url }
output "kms_app_key_arn" { value = aws_kms_key.app.arn }
