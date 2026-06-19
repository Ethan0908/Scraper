create extension if not exists pgcrypto;

create table if not exists events (
  id uuid primary key default gen_random_uuid(),
  source_site text not null,
  event_url text not null unique,
  title text not null,
  description text,
  start_time timestamptz,
  end_time timestamptz,
  timezone text,
  city text,
  venue_name text,
  address text,
  cover_image_url text,
  categories text[] default '{}',
  status text default 'active',
  content_hash text,
  first_seen_at timestamptz default now(),
  last_seen_at timestamptz default now(),
  scraped_at timestamptz default now()
);

create table if not exists organizers (
  id uuid primary key default gen_random_uuid(),
  organizer_key text not null unique,
  name text not null,
  role text,
  organizer_type text,
  profile_url text,
  avatar_url text,
  bio text,
  external_website_url text,
  linkedin_url text,
  instagram_url text,
  twitter_url text,
  public_email text,
  platform_contact_url text,
  first_seen_at timestamptz default now(),
  last_seen_at timestamptz default now()
);

create table if not exists event_organizers (
  event_id uuid references events(id) on delete cascade,
  organizer_id uuid references organizers(id) on delete cascade,
  role text not null,
  primary key (event_id, organizer_id, role)
);

create table if not exists scrape_runs (
  id uuid primary key default gen_random_uuid(),
  source_site text not null,
  started_at timestamptz default now(),
  finished_at timestamptz,
  status text,
  events_found integer default 0,
  events_inserted integer default 0,
  events_updated integer default 0,
  errors_count integer default 0,
  log text
);

create index if not exists idx_events_start_time on events(start_time);
create index if not exists idx_events_city on events(city);
create index if not exists idx_organizers_name on organizers(name);
create index if not exists idx_event_organizers_role on event_organizers(role);
