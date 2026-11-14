"""Public HTTPS report readability and measured-data link, desktop/mobile."""
import asyncio,json
from pathlib import Path
from playwright.async_api import async_playwright
async def main():
 result={'passed':False,'widths':[]};errors=[]
 async with async_playwright() as p:
  b=await p.chromium.launch(executable_path='/usr/bin/google-chrome',headless=True,args=['--no-sandbox','--disable-gpu'])
  page=await b.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
  url='https://diane-asylum-understood-invoice.trycloudflare.com/static/parallel-tts-verification.html'
  try:
   r=await page.goto(url);assert r.status==200
   assert await page.locator('h1').inner_text()=='Faster streaming with parallel word verification'
   assert await page.locator('table').count()==2
   result['table_rows']=await page.locator('tbody tr').count()
   for w in (1280,390):
    await page.set_viewport_size({'width':w,'height':900});width=await page.evaluate('document.documentElement.scrollWidth')
    result['widths'].append({'viewport':w,'document':width});assert width<=w+1
   r=await page.request.get(url.replace('.html','.json'));assert r.status==200
   data=await r.json();assert len(data['optimized'])==18
   result.update(passed=not errors,errors=errors,url=url)
  except Exception as e:result['error']=repr(e)
  finally:await b.close()
 Path('logs/isolation-latency/report-browser.json').write_text(json.dumps(result,indent=2));print(result);assert result['passed']
asyncio.run(main())
