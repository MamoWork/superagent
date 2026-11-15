create extension if not exists pgcrypto;

create table if not exists schema_migrations (
  version text primary key,
  applied_at timestamptz not null default now()
);

create table if not exists tenants (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  created_at timestamptz not null default now()
);

create table if not exists workspaces (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  name text not null,
  created_at timestamptz not null default now()
);
create index if not exists workspaces_tenant_idx on workspaces(tenant_id);

create table if not exists memberships (
  tenant_id uuid not null references tenants(id) on delete cascade,
  user_id uuid not null,
  role text not null check (role in ('owner','admin','member','viewer')),
  created_at timestamptz not null default now(),
  primary key (tenant_id, user_id)
);

create table if not exists platform_registry (
  platform text primary key,
  display_name text not null,
  enabled boolean not null default true
);

create table if not exists channel_registry (
  channel text primary key,
  display_name text not null,
  enabled boolean not null default true
);

create table if not exists content_type_registry (
  content_type text primary key,
  display_name text not null,
  enabled boolean not null default true
);

create table if not exists provider_configs (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  capability text not null,
  provider text not null,
  priority int not null default 100,
  enabled boolean not null default true,
  config jsonb not null default '{}'::jsonb,
  secret_ref text,
  config_schema_version int not null default 1,
  version int not null default 1,
  updated_by text,
  updated_at timestamptz not null default now(),
  unique (tenant_id, capability, provider)
);
create index if not exists provider_configs_lookup_idx
  on provider_configs(tenant_id, capability, enabled, priority);

create table if not exists tenant_quotas (
  tenant_id uuid not null references tenants(id) on delete cascade,
  metric text not null,
  period text not null check (period in ('day','month')),
  limit_value int not null,
  used_value int not null default 0,
  reset_at timestamptz not null,
  version int not null default 1,
  updated_at timestamptz not null default now(),
  primary key (tenant_id, metric, period)
);

create table if not exists tenant_features (
  tenant_id uuid not null references tenants(id) on delete cascade,
  feature_key text not null,
  enabled boolean not null default false,
  config jsonb not null default '{}'::jsonb,
  version int not null default 1,
  updated_at timestamptz not null default now(),
  primary key (tenant_id, feature_key)
);

create table if not exists config_versions (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  table_name text not null,
  record_id uuid not null,
  version int not null,
  diff jsonb not null,
  snapshot jsonb not null default '{}'::jsonb,
  changed_by text,
  created_at timestamptz not null default now()
);
create index if not exists config_versions_record_idx
  on config_versions(tenant_id, table_name, record_id, version desc);

create table if not exists prompt_templates (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  key text not null,
  module text not null,
  version int not null,
  template text not null,
  output_schema jsonb not null,
  model_hint text,
  enabled boolean not null default true,
  created_at timestamptz not null default now(),
  unique (tenant_id, key, version)
);

create table if not exists scoring_rubrics (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  key text not null,
  version int not null,
  dimensions jsonb not null,
  penalties jsonb not null,
  thresholds jsonb not null,
  enabled boolean not null default true,
  created_at timestamptz not null default now(),
  unique (tenant_id, key, version)
);

create table if not exists pipeline_runs (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  workspace_id uuid not null references workspaces(id) on delete cascade,
  pipeline text not null,
  task_type text not null,
  payload jsonb not null default '{}'::jsonb,
  status text not null check (status in ('queued','running','succeeded','failed','dead')),
  priority int not null default 100,
  idempotency_key text not null,
  run_after timestamptz not null default now(),
  locked_at timestamptz,
  locked_by text,
  attempts int not null default 0,
  max_attempts int not null default 5,
  last_error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, idempotency_key)
);
create index if not exists pipeline_runs_claim_idx
  on pipeline_runs(status, priority, run_after);
create index if not exists pipeline_runs_tenant_idx
  on pipeline_runs(tenant_id, status);

create table if not exists outbox_messages (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  workspace_id uuid not null references workspaces(id) on delete cascade,
  topic text not null,
  payload jsonb not null,
  status text not null check (status in ('pending','sending','sent','failed','dead')),
  idempotency_key text not null,
  attempts int not null default 0,
  next_attempt_at timestamptz not null default now(),
  last_error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, idempotency_key)
);
create index if not exists outbox_claim_idx
  on outbox_messages(status, next_attempt_at);

create table if not exists audit_log (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  workspace_id uuid references workspaces(id) on delete set null,
  actor_type text not null check (actor_type in ('user','service','n8n','system')),
  actor_id text,
  action text not null,
  entity_type text not null,
  entity_id uuid,
  before jsonb,
  after jsonb,
  created_at timestamptz not null default now()
);
create index if not exists audit_log_tenant_time_idx
  on audit_log(tenant_id, created_at desc);

create table if not exists provider_health (
  tenant_id uuid not null references tenants(id) on delete cascade,
  capability text not null,
  provider text not null,
  status text not null check (status in ('closed','open','half_open')),
  failure_count int not null default 0,
  last_error text,
  last_checked_at timestamptz,
  opened_at timestamptz,
  primary key (tenant_id, capability, provider)
);
