import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import websockets

sys.stdout.reconfigure(encoding='utf-8')

async def run_browser_modal_tests():
    ud = tempfile.mkdtemp()
    chrome_proc = subprocess.Popen([
        r'C:\Program Files\Google\Chrome\Application\chrome.exe',
        '--headless=new',
        '--remote-debugging-port=9333',
        f'--user-data-dir={ud}',
        '--disable-gpu',
        'about:blank'
    ])
    
    try:
        # Wait for Chrome to initialize
        for _ in range(15):
            try:
                urllib.request.urlopen('http://127.0.0.1:9333/json/version')
                break
            except Exception:
                time.sleep(0.5)

        # Create a new tab
        req = urllib.request.Request('http://127.0.0.1:9333/json/new', method='PUT')
        page_info = json.loads(urllib.request.urlopen(req).read())
        ws_url = page_info['webSocketDebuggerUrl']

        async with websockets.connect(ws_url, max_size=10_000_000) as ws:
            msg_id = 0

            async def send_cmd(method, params=None):
                nonlocal msg_id
                msg_id += 1
                payload = {'id': msg_id, 'method': method}
                if params:
                    payload['params'] = params
                await ws.send(json.dumps(payload))
                while True:
                    resp = json.loads(await ws.recv())
                    if resp.get('id') == msg_id:
                        return resp.get('result')

            async def eval_js(expr):
                res = await send_cmd('Runtime.evaluate', {
                    'expression': expr,
                    'awaitPromise': True,
                    'returnByValue': True
                })
                return res.get('result', {}).get('value')

            await send_cmd('Page.enable')
            await send_cmd('Runtime.enable')

            print('=== Navigating to http://localhost:3000/ ===')
            await send_cmd('Page.navigate', {'url': 'http://localhost:3000/'})
            await asyncio.sleep(2.5)

            initial_url = await eval_js('window.location.href')
            print(f'Initial URL: {initial_url}')

            async def search_for(query_text):
                await eval_js(f'''(() => {{
                    const textarea = document.querySelector('textarea');
                    if (textarea) {{
                        const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value").set;
                        setter.call(textarea, {json.dumps(query_text)});
                        textarea.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        textarea.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    }}
                    const btns = Array.from(document.querySelectorAll('button'));
                    const searchBtn = btns.find(b => b.textContent.includes('Find Standards') || b.textContent.includes('Search Standards'));
                    if (searchBtn) searchBtn.click();
                }})()''')

            # ---------------------------------------------------------
            # TEST 1: Tier 1 (IS 694)
            # ---------------------------------------------------------
            print('\n--- TEST 1: Tier 1 Enriched Standard (IS 694) ---')
            await search_for('internal wiring of buildings flexible cords rigid copper conductors IS 694')

            # Wait for search results with IS 694
            for _ in range(25):
                has_is694 = await eval_js('document.body.innerText.includes("IS 694")')
                if has_is694:
                    break
                await asyncio.sleep(0.5)

            url_before = await eval_js('window.location.href')
            print(f'URL before button click: {url_before}')

            click_t1 = await eval_js('''(() => {
                const cards = Array.from(document.querySelectorAll('div')).filter(d => d.innerText && d.innerText.includes('IS 694'));
                for (const c of cards) {
                    const btn = Array.from(c.querySelectorAll('button')).find(b => b.textContent.includes('View Enriched Dossier'));
                    if (btn) {
                        btn.click();
                        return 'Clicked View Enriched Dossier on IS 694';
                    }
                }
                const fallbackBtn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('View Enriched Dossier'));
                if (fallbackBtn) {
                    fallbackBtn.click();
                    return 'Clicked fallback View Enriched Dossier';
                }
                return 'Button not found';
            })()''')
            print(f'Action: {click_t1}')
            await asyncio.sleep(2.0)

            url_after_t1 = await eval_js('window.location.href')
            print(f'URL after button click:  {url_after_t1}')
            assert url_after_t1 == url_before, f'FAIL: URL changed from {url_before} to {url_after_t1}!'

            # Wait up to 3 seconds for detail to load if needed
            for _ in range(10):
                scope_loaded = await eval_js('document.querySelector("[role=\\"dialog\\"]") && document.querySelector("[role=\\"dialog\\"]").innerText.includes("Technical Scope")')
                if scope_loaded:
                    break
                await asyncio.sleep(0.3)

            modal_t1 = await eval_js('''(() => {
                const dialog = document.querySelector('[role="dialog"]');
                if (!dialog) return { found: false };
                const text = dialog.innerText || dialog.textContent;
                return {
                    found: true,
                    has_is_694: text.includes('IS 694'),
                    has_badge: text.includes('Seed Enriched Dossier'),
                    has_scope: text.includes('Technical Scope') || text.includes('Specifies requirements') || text.includes('internal wiring of buildings'),
                    has_certification: text.includes('Certification') || text.includes('ISI'),
                    has_tender: text.includes('Tender Clause') || text.includes('Standard Conformity')
                };
            })()''')
            print(f'Modal Verification: {modal_t1}')
            assert modal_t1.get('found'), 'Modal did not open!'
            assert modal_t1.get('has_is_694'), 'IS 694 not found in modal!'
            assert modal_t1.get('has_badge'), 'Seed Enriched Dossier badge not found!'
            assert modal_t1.get('has_scope'), 'Technical Scope not found in modal!'
            assert modal_t1.get('has_tender'), 'Tender clause not found in modal!'

            # Close modal via Close button
            await eval_js('''(() => {
                const dialog = document.querySelector('[role="dialog"]');
                const closeBtn = dialog.querySelector('button[aria-label="Close dialog"]') || Array.from(dialog.querySelectorAll('button')).find(b => b.textContent.trim() === 'Close');
                if (closeBtn) closeBtn.click();
            })()''')
            await asyncio.sleep(0.5)
            closed_1 = await eval_js('document.querySelector("[role=\\"dialog\\"]") === null')
            print(f'Modal Closed successfully: {closed_1}')
            assert closed_1, 'Modal failed to close!'

            # ---------------------------------------------------------
            # TEST 2: Tier 2 (IS/ISO 21927 (Part 1):2008)
            # ---------------------------------------------------------
            print('\n--- TEST 2: Tier 2 Catalogue Standard (IS/ISO 21927 (Part 1):2008) ---')
            await search_for('smoke barriers IS/ISO 21927')

            for _ in range(25):
                text_found = await eval_js('document.body.innerText.includes("21927")')
                if text_found:
                    break
                await asyncio.sleep(0.5)

            url_before_t2 = await eval_js('window.location.href')
            print(f'URL before button click: {url_before_t2}')

            click_t2 = await eval_js('''(() => {
                const btns = Array.from(document.querySelectorAll('button'));
                const catBtn = btns.find(b => b.textContent.includes('View Catalogue Metadata'));
                if (!catBtn) return 'Button not found';
                catBtn.click();
                return 'Clicked View Catalogue Metadata';
            })()''')
            print(f'Action: {click_t2}')
            await asyncio.sleep(1.0)

            url_after_t2 = await eval_js('window.location.href')
            print(f'URL after button click:  {url_after_t2}')
            assert url_after_t2 == url_before_t2, f'FAIL: URL changed from {url_before_t2} to {url_after_t2}!'

            modal_t2 = await eval_js('''(() => {
                const dialog = document.querySelector('[role="dialog"]');
                if (!dialog) return { found: false };
                const text = dialog.innerText || dialog.textContent;
                return {
                    found: true,
                    has_standard: text.includes('IS/ISO 21927 (Part 1):2008'),
                    has_badge: text.includes('Official BIS Catalogue'),
                    has_dept: text.includes('CIVIL ENGINEERING DEPARTMENT') || text.includes('CED'),
                    has_disclaimer: text.includes('Catalogue metadata available'),
                    has_tender: text.includes('Standard Conformity')
                };
            })()''')
            print(f'Modal Verification: {modal_t2}')
            assert modal_t2.get('found'), 'Modal did not open!'
            assert modal_t2.get('has_standard'), 'IS/ISO 21927 (Part 1):2008 not found in modal!'
            assert modal_t2.get('has_badge'), 'Official BIS Catalogue badge not found!'
            assert modal_t2.get('has_dept'), 'Department not found in modal!'
            assert modal_t2.get('has_disclaimer'), 'Catalogue metadata disclaimer not found!'

            # Close modal via Escape key
            await eval_js('''(() => {
                window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
            })()''')
            await asyncio.sleep(0.5)
            closed_2 = await eval_js('document.querySelector("[role=\\"dialog\\"]") === null')
            print(f'Modal Closed via Escape key: {closed_2}')
            assert closed_2, 'Modal failed to close on Escape!'

            # ---------------------------------------------------------
            # TEST 3: Withdrawn Tier 2 Standard (IS 8042:1989)
            # ---------------------------------------------------------
            print('\n--- TEST 3: Withdrawn Tier 2 Standard (IS 8042:1989) ---')
            await search_for('IS 8042 white portland cement')

            for _ in range(25):
                text_found = await eval_js('document.body.innerText.includes("8042")')
                if text_found:
                    break
                await asyncio.sleep(0.5)

            url_before_t3 = await eval_js('window.location.href')
            print(f'URL before button click: {url_before_t3}')

            click_t3 = await eval_js('''(() => {
                const btns = Array.from(document.querySelectorAll('button'));
                const catBtn = btns.find(b => b.textContent.includes('View Catalogue Metadata'));
                if (!catBtn) return 'Button not found';
                catBtn.click();
                return 'Clicked View Catalogue Metadata';
            })()''')
            print(f'Action: {click_t3}')
            await asyncio.sleep(1.0)

            url_after_t3 = await eval_js('window.location.href')
            print(f'URL after button click:  {url_after_t3}')
            assert url_after_t3 == url_before_t3, f'FAIL: URL changed from {url_before_t3} to {url_after_t3}!'

            modal_t3 = await eval_js('''(() => {
                const dialog = document.querySelector('[role="dialog"]');
                if (!dialog) return { found: false };
                const text = dialog.innerText || dialog.textContent;
                return {
                    found: true,
                    has_standard: text.includes('IS 8042:1989') || text.includes('IS 8042'),
                    has_withdrawn_status: text.includes('Withdrawn Standard') || text.includes('WITHDRAWN'),
                    has_regulatory_notice: text.includes('CRITICAL REGULATORY NOTICE') || text.includes('Outdated / Withdrawn Citation')
                };
            })()''')
            print(f'Modal Verification: {modal_t3}')
            assert modal_t3.get('found'), 'Modal did not open!'
            assert modal_t3.get('has_standard'), 'IS 8042 not found in modal!'
            assert modal_t3.get('has_withdrawn_status'), 'Withdrawn status badge not found!'
            assert modal_t3.get('has_regulatory_notice'), 'Critical regulatory warning notice not found!'

            # Close modal via Backdrop click
            await eval_js('''(() => {
                const dialogBackdrop = document.querySelector('[role="dialog"]');
                if (dialogBackdrop) dialogBackdrop.click();
            })()''')
            await asyncio.sleep(0.5)
            closed_3 = await eval_js('document.querySelector("[role=\\"dialog\\"]") === null')
            print(f'Modal Closed via Backdrop click: {closed_3}')
            assert closed_3, 'Modal failed to close on Backdrop click!'

            # ---------------------------------------------------------
            # TEST 4: Special Characters Standard (IS 16107 (Part 2/Sec 2):2017)
            # ---------------------------------------------------------
            print('\n--- TEST 4: Special Character Standard (IS 16107 (Part 2/Sec 2):2017) ---')
            await search_for('IS 16107 (Part 2/Sec 2)')

            for _ in range(25):
                text_found = await eval_js('document.body.innerText.includes("16107")')
                if text_found:
                    break
                await asyncio.sleep(0.5)

            url_before_t4 = await eval_js('window.location.href')
            print(f'URL before button click: {url_before_t4}')

            click_t4 = await eval_js('''(() => {
                // Find card with Part 2/Sec 2
                const cards = Array.from(document.querySelectorAll('div')).filter(d => d.innerText && d.innerText.includes('Part 2/Sec 2'));
                for (const c of cards) {
                    const btn = Array.from(c.querySelectorAll('button')).find(b => b.textContent.includes('View Catalogue Metadata'));
                    if (btn) {
                        btn.click();
                        return 'Clicked View Catalogue Metadata on IS 16107 (Part 2/Sec 2)';
                    }
                }
                const catBtn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('View Catalogue Metadata'));
                if (!catBtn) return 'Button not found';
                catBtn.click();
                return 'Clicked View Catalogue Metadata';
            })()''')
            print(f'Action: {click_t4}')
            await asyncio.sleep(1.0)

            url_after_t4 = await eval_js('window.location.href')
            print(f'URL after button click:  {url_after_t4}')
            assert url_after_t4 == url_before_t4, f'FAIL: URL changed from {url_before_t4} to {url_after_t4}!'

            modal_t4 = await eval_js('''(() => {
                const dialog = document.querySelector('[role="dialog"]');
                if (!dialog) return { found: false };
                const text = dialog.innerText || dialog.textContent;
                return {
                    found: true,
                    has_standard: text.includes('IS 16107'),
                    has_badge: text.includes('Official BIS Catalogue'),
                    no_404: !text.includes('404') && !text.includes('Not Found')
                };
            })()''')
            print(f'Modal Verification: {modal_t4}')
            assert modal_t4.get('found'), 'Modal did not open!'
            assert modal_t4.get('has_standard'), 'IS 16107 not found in modal!'
            assert modal_t4.get('has_badge'), 'Official BIS Catalogue badge not found!'
            assert modal_t4.get('no_404'), '404 error was displayed in modal!'

            # Close modal via Close button
            await eval_js('''(() => {
                const dialog = document.querySelector('[role="dialog"]');
                const closeBtn = Array.from(dialog.querySelectorAll('button')).find(b => b.textContent.trim() === 'Close');
                if (closeBtn) closeBtn.click();
            })()''')
            await asyncio.sleep(0.5)
            closed_4 = await eval_js('document.querySelector("[role=\\"dialog\\"]") === null')
            print(f'Modal Closed via Close button: {closed_4}')
            assert closed_4, 'Modal failed to close!'

            print('\n======================================================')
            print('🎉 ALL 4 USER JOURNEYS PASSED WITH 100% SUCCESS!')
            print('======================================================')
    finally:
        chrome_proc.terminate()
        try:
            shutil.rmtree(ud, ignore_errors=True)
        except Exception:
            pass

if __name__ == '__main__':
    asyncio.run(run_browser_modal_tests())
