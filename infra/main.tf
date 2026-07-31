terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

data "aws_subnet" "first" {
  id = data.aws_subnets.default.ids[0]
}

data "aws_route_tables" "default" {
  vpc_id = data.aws_vpc.default.id
}

data "aws_ami" "amazon_linux" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }

  filter {
    name   = "state"
    values = ["available"]
  }
}

locals {
  name = "${var.project_name}-${var.environment}"
}

resource "aws_s3_bucket" "documents" {
  bucket_prefix = "${local.name}-documents-"
}

resource "aws_s3_bucket_public_access_block" "documents" {
  bucket                  = aws_s3_bucket.documents.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "documents" {
  bucket = aws_s3_bucket.documents.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "documents" {
  bucket = aws_s3_bucket.documents.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}

resource "aws_sqs_queue" "crawl_dlq" { name = "${local.name}-crawl-dlq" }
resource "aws_sqs_queue" "storage_dlq" { name = "${local.name}-storage-dlq" }
resource "aws_sqs_queue" "discovery_dlq" { name = "${local.name}-discovery-dlq" }

resource "aws_sqs_queue" "crawl" {
  name = "${local.name}-crawl"
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.crawl_dlq.arn
    maxReceiveCount     = 5
  })
}

resource "aws_sqs_queue" "storage" {
  name = "${local.name}-storage"
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.storage_dlq.arn
    maxReceiveCount     = 5
  })
}

resource "aws_sqs_queue" "discovery" {
  name = "${local.name}-discovery"
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.discovery_dlq.arn
    maxReceiveCount     = 5
  })
}

resource "aws_security_group" "storage_worker" {
  name_prefix = "${local.name}-storage-"
  description = "Storage worker to RDS access"
  vpc_id      = data.aws_vpc.default.id
  egress {
    protocol    = "-1"
    from_port   = 0
    to_port     = 0
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_vpc_endpoint" "s3" {
  vpc_id            = data.aws_vpc.default.id
  service_name      = "com.amazonaws.${var.aws_region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = data.aws_route_tables.default.ids
}

resource "aws_security_group" "rds" {
  name_prefix = "${local.name}-rds-"
  description = "RDS access only from the storage worker"
  vpc_id      = data.aws_vpc.default.id
  ingress {
    protocol        = "tcp"
    from_port       = 5432
    to_port         = 5432
    security_groups = [aws_security_group.storage_worker.id]
  }
}

resource "aws_db_subnet_group" "postgres" {
  name       = "${local.name}-postgres"
  subnet_ids = data.aws_subnets.default.ids
}

resource "aws_db_instance" "postgres" {
  identifier              = "${local.name}-postgres"
  engine                  = "postgres"
  engine_version          = "16"
  instance_class          = "db.t3.micro"
  allocated_storage       = 20
  storage_encrypted       = true
  db_name                 = "corpora"
  username                = var.db_username
  password                = var.db_password
  db_subnet_group_name    = aws_db_subnet_group.postgres.name
  vpc_security_group_ids  = [aws_security_group.rds.id]
  publicly_accessible     = false
  skip_final_snapshot     = true
  deletion_protection     = false
  backup_retention_period = 1
}

resource "aws_iam_role" "lambda" {
  name = "${local.name}-lambda-role"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_logs" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "lambda_vpc" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

resource "aws_iam_role_policy" "lambda_app" {
  role = aws_iam_role.lambda.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes", "sqs:SendMessage", "sqs:SendMessageBatch"], Resource = [aws_sqs_queue.crawl.arn, aws_sqs_queue.storage.arn, aws_sqs_queue.discovery.arn] },
      { Effect = "Allow", Action = ["s3:GetObject", "s3:PutObject"], Resource = "${aws_s3_bucket.documents.arn}/*" }
    ]
  })
}

resource "aws_lambda_function" "crawl_worker" {
  function_name    = "${local.name}-crawl-worker"
  role             = aws_iam_role.lambda.arn
  runtime          = "python3.12"
  handler          = var.worker_handler
  filename         = var.worker_package
  source_code_hash = filebase64sha256(var.worker_package)
  timeout          = 60
  memory_size      = 512
  environment { variables = { CORPORA_STORAGE_QUEUE_URL = aws_sqs_queue.storage.url, CORPORA_DISCOVERY_QUEUE_URL = aws_sqs_queue.discovery.url } }
}

resource "aws_lambda_function" "storage_worker" {
  function_name    = "${local.name}-storage-worker"
  role             = aws_iam_role.lambda.arn
  runtime          = "python3.12"
  handler          = var.storage_worker_handler
  filename         = var.storage_worker_package
  source_code_hash = filebase64sha256(var.storage_worker_package)
  timeout          = 60
  memory_size      = 512
  vpc_config {
    subnet_ids         = data.aws_subnets.default.ids
    security_group_ids = [aws_security_group.storage_worker.id]
  }
  environment { variables = { CORPORA_DOCUMENT_BUCKET = aws_s3_bucket.documents.bucket, CORPORA_DB_HOST = aws_db_instance.postgres.address, CORPORA_DB_NAME = aws_db_instance.postgres.db_name, CORPORA_DB_USER = var.db_username } }
}

resource "aws_lambda_event_source_mapping" "crawl" {
  event_source_arn                   = aws_sqs_queue.crawl.arn
  function_name                      = aws_lambda_function.crawl_worker.arn
  batch_size                         = 10
  maximum_batching_window_in_seconds = 5
  function_response_types            = ["ReportBatchItemFailures"]
}

resource "aws_lambda_event_source_mapping" "storage" {
  event_source_arn                   = aws_sqs_queue.storage.arn
  function_name                      = aws_lambda_function.storage_worker.arn
  batch_size                         = 10
  maximum_batching_window_in_seconds = 5
  function_response_types            = ["ReportBatchItemFailures"]
}

resource "aws_iam_role" "coordinator" {
  name               = "${local.name}-coordinator-role"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "ec2.amazonaws.com" }, Action = "sts:AssumeRole" }] })
}

resource "aws_iam_role_policy_attachment" "coordinator_ssm" {
  role       = aws_iam_role.coordinator.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy" "coordinator_sqs" {
  role   = aws_iam_role.coordinator.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = ["sqs:SendMessage", "sqs:SendMessageBatch", "sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"], Resource = [aws_sqs_queue.crawl.arn, aws_sqs_queue.discovery.arn] }] })
}

resource "aws_iam_instance_profile" "coordinator" {
  name = "${local.name}-coordinator-profile"
  role = aws_iam_role.coordinator.name
}

resource "aws_security_group" "coordinator" {
  name_prefix = "${local.name}-coordinator-"
  vpc_id      = data.aws_vpc.default.id
  egress {
    protocol    = "-1"
    from_port   = 0
    to_port     = 0
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_instance" "coordinator" {
  ami                         = data.aws_ami.amazon_linux.id
  instance_type               = var.coordinator_instance_type
  subnet_id                   = data.aws_subnet.first.id
  iam_instance_profile        = aws_iam_instance_profile.coordinator.name
  vpc_security_group_ids      = [aws_security_group.coordinator.id]
  associate_public_ip_address = true
  user_data                   = <<-USERDATA
    #!/bin/bash
    echo CORPORA_CRAWL_QUEUE_URL=${aws_sqs_queue.crawl.url} > /etc/corpora.env
    echo CORPORA_DISCOVERY_QUEUE_URL=${aws_sqs_queue.discovery.url} >> /etc/corpora.env
    echo CORPORA_AWS_REGION=${var.aws_region} >> /etc/corpora.env
    echo "Install the versioned coordinator artifact and systemd service before starting the crawl."
  USERDATA
  tags                        = { Name = "${local.name}-coordinator" }
}
