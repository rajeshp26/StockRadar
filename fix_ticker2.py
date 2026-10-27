import sys
path = r'C:/Project/StockerPro/StockerPro/backend/infrastructure/repositories/financial_repository.py'
with open(path) as f:
    s = f.read()

old = '"company_id, first_financial_data_loaded_at, status, security_type, loaded"'
if old not in s:
    print('bad')
    sys.exit(1)
s2 = s.replace(old, '"company_id, ticker_symbol, first_financial_data_loaded_at, status, security_type, loaded"')
with open(path, 'w') as f:
    f.write(s2)
print('ok')
sys.exit(0)
