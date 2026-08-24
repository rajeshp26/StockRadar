import psycopg2

conn = psycopg2.connect('postgresql://postgres:postgres@127.0.0.1:54322/postgres')
cur = conn.cursor()
cur.execute('ALTER TABLE public.scheduler_state ALTER COLUMN interval_hours TYPE numeric USING interval_hours::numeric')
conn.commit()
print('Fixed scheduler_state.interval_hours -> numeric')
conn.close()
