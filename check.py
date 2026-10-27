with open(r'C:\Project\StockerPro\StockerPro\backend\infrastructure\repositories\financial_repository.py') as f:
    s=f.read()
i=s.find('get_financial_candidates')
if i>=0:
    j=s.rfind('async def',0,i)
    print(s[j:j+280])
else:
    print('no')
