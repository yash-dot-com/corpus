output "crawl_queue_url" { value = aws_sqs_queue.crawl.url }
output "storage_queue_url" { value = aws_sqs_queue.storage.url }
output "discovery_queue_url" { value = aws_sqs_queue.discovery.url }
output "document_bucket" { value = aws_s3_bucket.documents.bucket }
output "database_endpoint" { value = aws_db_instance.postgres.address }
output "coordinator_instance_id" { value = aws_instance.coordinator.id }
