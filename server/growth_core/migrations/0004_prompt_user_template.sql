alter table prompt_templates
  add column if not exists user_template text not null default '';
