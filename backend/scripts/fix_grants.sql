DO $$
DECLARE
  r RECORD;
BEGIN
  FOR r IN SELECT tablename FROM pg_tables WHERE schemaname='public' LOOP
    EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON public.' || quote_ident(r.tablename) || ' TO service_role';
    EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON public.' || quote_ident(r.tablename) || ' TO anon';
    EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON public.' || quote_ident(r.tablename) || ' TO authenticated';
  END LOOP;
  FOR r IN SELECT sequence_name FROM information_schema.sequences WHERE sequence_schema='public' LOOP
    EXECUTE 'GRANT USAGE, SELECT ON public.' || quote_ident(r.sequence_name) || ' TO service_role';
    EXECUTE 'GRANT USAGE, SELECT ON public.' || quote_ident(r.sequence_name) || ' TO anon';
    EXECUTE 'GRANT USAGE, SELECT ON public.' || quote_ident(r.sequence_name) || ' TO authenticated';
  END LOOP;
  FOR r IN SELECT viewname FROM pg_views WHERE schemaname='public' LOOP
    EXECUTE 'GRANT SELECT ON public.' || quote_ident(r.viewname) || ' TO service_role';
    EXECUTE 'GRANT SELECT ON public.' || quote_ident(r.viewname) || ' TO anon';
    EXECUTE 'GRANT SELECT ON public.' || quote_ident(r.viewname) || ' TO authenticated';
  END LOOP;
END $$;
