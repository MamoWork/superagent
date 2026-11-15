create table if not exists growth_sources (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  workspace_id uuid not null references workspaces(id) on delete cascade,
  source_type text not null,
  platform text not null,
  dedupe_key text not null,
  config jsonb not null default '{}'::jsonb,
  cadence_minutes int not null default 30,
  enabled boolean not null default true,
  last_run_at timestamptz,
  last_error text,
  version int not null default 1,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, dedupe_key)
);
create index if not exists growth_sources_enabled_idx
  on growth_sources(tenant_id, enabled, source_type);

create table if not exists social_leads (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  workspace_id uuid not null references workspaces(id) on delete cascade,
  source_id uuid references growth_sources(id) on delete set null,
  platform text not null,
  platform_post_id text not null,
  title text not null default '',
  body text not null default '',
  author_public text,
  source_url text not null,
  published_at timestamptz,
  metrics jsonb not null default '{}'::jsonb,
  raw jsonb,
  subreddit text,
  subreddit_rules jsonb not null default '{}'::jsonb,
  score int check (score between 0 and 100),
  score_reasons jsonb,
  model text,
  prompt_version text,
  status text not null check (status in (
    'discovered','scored','qualified','draft_ready','approved','sent',
    'replied','converted','dropped','watch','suppressed','rejected'
  )),
  dedupe_key text not null,
  version int not null default 1,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, dedupe_key)
);
create index if not exists social_leads_list_idx
  on social_leads(tenant_id, platform, status, created_at desc);

create table if not exists outreach_messages (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  workspace_id uuid not null references workspaces(id) on delete cascade,
  channel text not null,
  provider text,
  lead_id uuid references social_leads(id) on delete cascade,
  user_id uuid,
  rule_key text,
  status text not null check (status in (
    'draft_ready','approved','sent','replied','converted',
    'rejected','suppressed','failed','expired'
  )),
  scheduled_at timestamptz,
  sent_at timestamptz,
  provider_message_id text,
  dedupe_key text not null,
  metadata jsonb not null default '{}'::jsonb,
  version int not null default 1,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, dedupe_key)
);
create index if not exists outreach_messages_list_idx
  on outreach_messages(tenant_id, channel, status, scheduled_at);

create table if not exists outreach_versions (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  workspace_id uuid references workspaces(id) on delete cascade,
  message_id uuid not null references outreach_messages(id) on delete cascade,
  version int not null,
  subject text,
  body_text text not null,
  cta_url text,
  model text,
  prompt_version text,
  risk_flags jsonb not null default '[]'::jsonb,
  approved_by text,
  approved_at timestamptz,
  created_at timestamptz not null default now(),
  unique (tenant_id, message_id, version)
);

create table if not exists approval_requests (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  workspace_id uuid not null references workspaces(id) on delete cascade,
  message_id uuid not null references outreach_messages(id) on delete cascade,
  approval_id text not null,
  provider text not null default 'feishu',
  external_id text,
  status text not null check (status in ('pending','approved','rejected','expired')),
  decided_by text,
  decided_at timestamptz,
  reason text,
  payload jsonb not null default '{}'::jsonb,
  version int not null default 1,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, approval_id)
);
create index if not exists approval_requests_pending_idx
  on approval_requests(tenant_id, status, created_at);

create table if not exists rate_limit_rules (
  tenant_id uuid not null references tenants(id) on delete cascade,
  workspace_id uuid references workspaces(id) on delete cascade,
  channel text not null,
  scope text not null check (scope in ('global','platform','subreddit','user')),
  scope_key text not null default '*',
  window_seconds int not null,
  max_count int not null,
  enabled boolean not null default true,
  version int not null default 1,
  updated_by text,
  updated_at timestamptz not null default now(),
  primary key (tenant_id, channel, scope, scope_key)
);

create table if not exists rate_limit_counters (
  tenant_id uuid not null references tenants(id) on delete cascade,
  workspace_id uuid references workspaces(id) on delete cascade,
  channel text not null,
  scope text not null,
  scope_key text not null,
  window_start timestamptz not null,
  count int not null default 0,
  primary key (tenant_id, channel, scope, scope_key, window_start)
);

create table if not exists suppression_list (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  workspace_id uuid references workspaces(id) on delete cascade,
  kind text not null check (kind in ('email','platform_user','domain')),
  value text not null,
  reason text not null check (reason in (
    'unsubscribe','hard_bounce','complaint','manual',
    'negative_reply','moderator_warning'
  )),
  source text,
  created_at timestamptz not null default now(),
  unique (tenant_id, kind, value)
);

create table if not exists delivery_log (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references tenants(id) on delete cascade,
  workspace_id uuid not null references workspaces(id) on delete cascade,
  message_id uuid references outreach_messages(id) on delete set null,
  lead_id uuid references social_leads(id) on delete set null,
  provider text not null,
  event_type text not null,
  payload jsonb not null default '{}'::jsonb,
  received_at timestamptz not null default now()
);
create index if not exists delivery_log_message_idx
  on delivery_log(tenant_id, message_id, received_at desc);
