-- Allow inbound integration callbacks (for example social feedback webhooks)
-- to be attributed distinctly from internal services.

alter table audit_log
  drop constraint if exists audit_log_actor_type_check;

alter table audit_log
  add constraint audit_log_actor_type_check
  check (actor_type in ('user', 'service', 'n8n', 'system', 'integration'));
