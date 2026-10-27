path = r'C:\Project\StockerPro\StockerPro\backend\infrastructure\repositories\financial_repository.py'
with open(path, encoding='utf-8') as f:
    s = f.read()
old = '"company_id, first_financial_data_loaded_at, status, security_type, loaded"'
new = '"company_id, ticker_symbol, first_financial_data_loaded_at, status, security_type, loaded"'
if old in s:
    with open(path, 'w', encoding='utf-8') as f:
        f.write(s.replace(old, new))
    print('ok')
else:
    print('no')
