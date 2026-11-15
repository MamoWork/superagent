create schema if not exists auth;
create or replace function auth.jwt() returns jsonb
language sql stable as $$
  select coalesce(nullif(current_setting('request.jwt.claims', true), ''), '{}')::jsonb
$$;

do $$
declare
  t text;
begin
  foreach t in array array[
    'workspaces','memberships','provider_configs','tenant_quotas','tenant_features',
    'config_versions','prompt_templates','scoring_rubrics','pipeline_runs','outbox_messages',
    'audit_log','provider_health','growth_sources','social_leads','outreach_messages',
    'outreach_versions','approval_requests','rate_limit_rules','rate_limit_counters',
    'suppression_list','delivery_log'
  ] loop
    execute format('alter table %I enable row level security', t);
    execute format('drop policy if exists tenant_isolation on %I', t);
    execute format(
      'create policy tenant_isolation on %I using '
      '(tenant_id = (auth.jwt() ->> ''tenant_id'')::uuid) with check '
      '(tenant_id = (auth.jwt() ->> ''tenant_id'')::uuid)',
      t
    );
  end loop;
end $$;
