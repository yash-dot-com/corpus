# Manual AWS deployment runbook

This runbook mirrors `infra/` and is intended for learning or recovery when
Terraform is unavailable. Use one AWS region consistently.

## 1. Create storage and queues

1. Create a private S3 bucket for JSONL documents with block-public-access,
   server-side encryption, and versioning enabled.
2. Create `corpora-crawl`, `corpora-storage`, and `corpora-discovery` SQS
   standard queues.
3. Create one DLQ per queue and configure a redrive policy with a maximum receive
   count of 5.
4. Record the three queue URLs and bucket name.

## 2. Create PostgreSQL RDS

1. Create a PostgreSQL `db.t3.micro` instance for development.
2. Put it in a DB subnet group spanning at least two subnets.
3. Disable public access.
4. Create a security group that allows TCP 5432 only from the storage worker
   security group.
5. Store the connection string in Secrets Manager. Do not put the password in
   source control or a committed `.env` file.
6. Run Alembic migrations from a controlled host with network access to RDS.

## 3. Create IAM roles

Create separate roles for the coordinator EC2 instance, crawl Lambda, and
storage Lambda. Grant only the actions each component needs:

- Coordinator: `sqs:SendMessage`, `sqs:SendMessageBatch`,
  `sqs:ReceiveMessage`, `sqs:DeleteMessage`, `sqs:GetQueueAttributes`, and
  Systems Manager permissions.
- Crawl Lambda: receive/delete from Crawl Queue, send to Storage and Discovery
  Queues, and write CloudWatch Logs.
- Storage Lambda: receive/delete from Storage Queue, `s3:GetObject` and
  `s3:PutObject` for the document bucket, RDS network access, and Logs.

## 4. Deploy Lambda functions

1. Build the crawl and storage zip artifacts using the project lockfile.
2. Create the crawl Lambda with a 60-second timeout and 512 MB memory.
3. Create the storage Lambda with the same baseline settings and attach it to
   the VPC subnets/security group that can reach RDS. Add an S3 gateway endpoint
   so it does not require a NAT gateway for S3 access.
4. Configure event source mappings with batch size 10.
5. Set maximum/reserved concurrency to 10 initially.
6. Set these environment variables on the functions: queue URLs, document bucket,
   AWS region, and the Secrets Manager name for the database connection.

## 5. Deploy the coordinator EC2 instance

1. Launch a small Amazon Linux instance in the selected VPC/subnet with an
   instance profile and Systems Manager enabled.
2. Install the project from its release artifact, create `/etc/corpora/.env`,
   and set `CORPORA_CRAWL_QUEUE_URL`, `CORPORA_DISCOVERY_QUEUE_URL`,
   `CORPORA_AWS_REGION`, and the database secret name.
3. Copy `config.yaml` to the coordinator host. Keep seed URLs and allowed
   domains in that file.
4. Run the coordinator as a systemd service. It must consume Discovery Queue
   messages continuously and schedule verified jobs in Crawl Queue.
5. Confirm the robots cache and visited set are local to this coordinator; do
   not run a second coordinator until shared state is implemented.

## 6. Smoke test

1. Submit one seed URL and confirm a Crawl Queue message.
2. Confirm the crawl Lambda records fetch/redirect/parse results.
3. Confirm Storage Queue produces an S3 JSONL object and an RDS metadata row.
4. Confirm Discovery Queue messages return to the coordinator and new jobs are
   deduplicated and depth/robots/domain checked.
5. Inspect CloudWatch logs and all DLQs before increasing concurrency.

## Teardown

Drain queues, export required S3/RDS data, disable event-source mappings, then
delete Lambdas, EC2, RDS, queues, and the bucket. S3 versioning means bucket
deletion may require explicitly removing object versions.
