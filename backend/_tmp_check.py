from application.services.portfolio_service import PortfolioService
import asyncio
async def t():
    svc=PortfolioService()
    r=await svc.get_performance_compare(1,'1Y',['SPY'],[9,8,7])
    b=[x for x in r['benchmarks'] if x['symbol']=='SPY'][0]
    print(len(b['data']), b['data'][0]['date'], b['data'][-1]['date'])
asyncio.run(t())
