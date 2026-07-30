# AWS integration implementation plan

This plan is the deployment sequence for the already-approved Corpora V1
contracts. It keeps the coordinator stateful on EC2 and keeps workers
stateless.

## 1. Freeze deployment contracts

1. Keep `config.yaml` for crawl policy and seed URLs.
2. Keep infrastructure values in `.env` for local execution and Terraform
   variables/outputs for AWS.
3. Version the Crawl Job, Worker Result, Storage Queue, and Discovery Queue
   schemas together with the application.
4. Add Lambda adapter entry points that deserialize queue messages and call the
   existing `Worker` and `StorageWorker` classes; adapters must not duplicate
   domain logic.

## 2. Provision shared AWS resources with Terraform

1. Select a region and the account's default VPC/subnets for the V1 learning
   deployment.
2. Create encrypted S3 storage for JSONL documents.
3. Create Crawl, Storage, and Discovery SQS queues with dead-letter queues.
4. Create a small PostgreSQL RDS instance, subnet group, and a security group
   allowing PostgreSQL only from the storage worker security group.
5. Create Lambda execution roles with least-privilege SQS, S3, CloudWatch Logs,
   and VPC networking permissions.
6. Create a coordinator EC2 role, security group, and instance profile. The
   coordinator needs SQS access and Systems Manager access; SSH is not required.
7. Create Lambda event-source mappings for Crawl Queue → Crawl Worker and
   Storage Queue → Storage Worker. Discovery messages are consumed by the
   coordinator process on EC2.

## 3. Build and publish application artifacts

1. Build a worker Lambda zip containing `src/`, dependencies, and the worker
   adapter handler.
2. Build a storage Lambda zip containing `src/`, dependencies, and the storage
   adapter handler.
3. Copy both artifacts to the deployment bucket and pass their paths to
   Terraform.
4. Build the coordinator artifact/container, install it on EC2, and configure a
   systemd service that runs the Discovery Queue consumer and seed scheduler.

## 4. Configure runtime values

Terraform outputs the queue URLs, bucket name, RDS endpoint, and coordinator
instance ID. Use those outputs to create the coordinator `.env` and Lambda
environment variables. Never commit database passwords or AWS credentials.

## 5. Apply and verify in order

1. `terraform fmt -check` and `terraform validate`.
2. `terraform plan` and review cost/security-sensitive changes.
3. `terraform apply`.
4. Run database migrations from a controlled environment.
5. Start the coordinator and submit one seed URL.
6. Verify Crawl Queue delivery, worker logs, Storage Queue delivery, S3 JSONL,
   RDS metadata, and Discovery Queue scheduling.
7. Test a denied robots URL, a redirect to an allowed domain, a redirect to an
   external domain, a retry, and a dead-letter path.

## 6. Operate safely

1. Set Lambda reserved/max concurrency to 10 initially; raise to 20 only after
   measuring downstream load.
2. Keep Lambda timeout at 60 seconds and memory at 512 MB initially.
3. Alarm on queue age, DLQ depth, Lambda errors/throttles, EC2 health, and RDS
   storage/CPU.
4. Destroy only through Terraform after exporting required S3/RDS data.
