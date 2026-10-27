path = r'C:\Project\StockerPro\StockerPro\backend\infrastructure\repositories\financial_repository.py'
with open(path) as f:
    s = f.read()
o = '"company_id, first_financial_data_loaded_at, status, security_type, loaded"'
if o in s:
    n = '"company_id, ticker_symbol, first_financial_data_loaded_at, status, security_type, loaded"'
    with open(path, 'w') as f2:
        f2.write(s.replace(o, n))
    print('ok')
else:
    print('no')
